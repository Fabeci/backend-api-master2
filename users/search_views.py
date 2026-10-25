# users/search_views.py
# =============================================================================
# RECHERCHE GLOBALE — endpoint agrégé, filtré par rôle.
#
#   GET /api/v1/search/?q=<terme>&limit=<n>
#
#   → { "query": "...", "results": [ { type, label, id, nom, prenom,
#                                      subtitle, url } ] }
#
# Le filtrage par rôle est obtenu en RÉUTILISANT les `get_queryset()` des
# ViewSets CRUD existants (source unique de vérité) : aucune règle d'accès
# n'est dupliquée ici. Un rôle qui n'a pas le droit de voir une ressource
# obtient simplement un queryset vide pour ce type.
# =============================================================================

from django.db.models import Q
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView


def _scoped_queryset(viewset_cls, request):
    """
    Instancie un ViewSet sans passer par la couche HTTP afin de récupérer
    son queryset filtré par rôle. Retourne None en cas d'échec.
    """
    try:
        vs = viewset_cls()
        vs.request = request
        vs.kwargs = {}
        vs.args = ()
        vs.format_kwarg = None
        qs = vs.get_queryset()
        return qs
    except Exception:
        return None


def _person_result(type_key, label, obj, url_tpl):
    return {
        "type": type_key,
        "label": label,
        "id": obj.pk,
        "nom": getattr(obj, "nom", "") or "",
        "prenom": getattr(obj, "prenom", "") or "",
        "subtitle": getattr(obj, "matricule", None) or getattr(obj, "email", "") or "",
        "url": url_tpl.format(obj.pk),
    }


class GlobalSearchAPIView(APIView):
    """Recherche globale multi-entités, restreinte au périmètre du rôle."""

    permission_classes = [permissions.IsAuthenticated]

    # type_key, libellé, champs texte cherchés, gabarit d'URL front
    PEOPLE = [
        ("apprenant",   "Apprenant",   ("nom", "prenom", "email", "matricule"), "/apprenants/{}"),
        ("formateur",   "Formateur",   ("nom", "prenom", "email"),              "/formateurs/{}"),
        ("parent",      "Parent",      ("nom", "prenom", "email"),              "/parents/{}"),
        ("admin",       "Admin",       ("nom", "prenom", "email"),              "/admins/{}"),
        ("responsable", "Responsable", ("nom", "prenom", "email"),              "/responsables/{}"),
    ]

    def get(self, request):
        q = (request.query_params.get("q") or "").strip()

        try:
            limit = int(request.query_params.get("limit", 6))
        except (TypeError, ValueError):
            limit = 6
        limit = max(1, min(limit, 20))

        if len(q) < 2:
            return Response({"query": q, "results": []})

        results = []

        # ── Personnes (scoping via les ViewSets CRUD) ────────────────────────
        from .views import (
            ApprenantViewSet,
            FormateurViewSet,
            ParentViewSet,
            AdminViewSet,
            ResponsableAcademiqueViewSet,
        )

        vs_map = {
            "apprenant":   ApprenantViewSet,
            "formateur":   FormateurViewSet,
            "parent":      ParentViewSet,
            "admin":       AdminViewSet,
            "responsable": ResponsableAcademiqueViewSet,
        }

        # ✅ Un apprenant / parent n'a pas à parcourir l'annuaire du personnel
        #    (admins, formateurs, responsables, autres parents) : on ne lui
        #    présente que les apprenants — et le ViewSet le limite à lui-même.
        from core.rbac import display_role
        role = display_role(request.user)
        people = self.PEOPLE
        if role in ('Apprenant', 'Parent'):
            people = [p for p in self.PEOPLE if p[0] == 'apprenant']

        for type_key, label, fields, url_tpl in people:
            qs = _scoped_queryset(vs_map[type_key], request)
            if qs is None:
                continue
            cond = Q()
            for field in fields:
                cond |= Q(**{f"{field}__icontains": q})
            try:
                rows = qs.filter(cond).distinct().order_by("nom", "prenom")[:limit]
            except Exception:
                continue
            for obj in rows:
                results.append(_person_result(type_key, label, obj, url_tpl))

        # ── Cours ────────────────────────────────────────────────────────────
        try:
            from courses.models import Cours
            from courses.utils import filter_queryset_by_role

            cours_qs = filter_queryset_by_role(Cours.objects.all(), request, "Cours")
            for c in cours_qs.filter(Q(titre__icontains=q)).distinct()[:limit]:
                enseignant = getattr(c, "enseignant", None)
                ens_nom = ""
                if enseignant is not None:
                    ens_nom = f"{enseignant.prenom or ''} {enseignant.nom or ''}".strip()
                results.append({
                    "type": "cours",
                    "label": "Cours",
                    "id": c.pk,
                    "nom": c.titre or "(sans titre)",
                    "prenom": "",
                    "subtitle": ens_nom,
                    "url": f"/formations/cours/detail/{c.pk}",
                })
        except Exception:
            pass

        # ── Évaluations ──────────────────────────────────────────────────────
        try:
            from evaluations.models import Evaluation
            from courses.utils import filter_queryset_by_role

            eval_qs = filter_queryset_by_role(Evaluation.objects.all(), request, "Evaluation")
            cond = Q(titre__icontains=q) | Q(consigne_texte__icontains=q)
            for e in eval_qs.filter(cond).distinct()[:limit]:
                cours_titre = getattr(getattr(e, "cours", None), "titre", "") or ""
                results.append({
                    "type": "evaluation",
                    "label": "Évaluation",
                    "id": e.pk,
                    "nom": e.titre or "(sans titre)",
                    "prenom": "",
                    "subtitle": cours_titre,
                    "url": f"/formations/cours/detail/{e.cours_id}",
                })
        except Exception:
            pass

        return Response({"query": q, "results": results})
