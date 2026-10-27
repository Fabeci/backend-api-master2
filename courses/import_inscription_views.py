# courses/import_inscription_views.py
# =============================================================================
# Import d'INSCRIPTIONS à un cours depuis un document.
#
#   POST /api/v1/inscriptions/importer/analyser/   (multipart) → aperçu
#   POST /api/v1/inscriptions/importer/            (multipart) → création
# =============================================================================

import json
import logging
from collections import Counter

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission
from core.tenant import default_institution_id

from courses import import_inscriptions
from courses.models import Cours, InscriptionCours
from courses.utils import filter_queryset_by_role, get_user_context, is_supervision_admin
from courses.views import api_error, api_success
from users.models import Apprenant

logger = logging.getLogger(__name__)

MAX_SIZE = 10 * 1024 * 1024  # 10 Mo


def _role_name(request):
    try:
        return (get_user_context(request) or {}).get("role_name")
    except Exception:
        return None


def _check_access(request):
    """Mêmes règles que la gestion des inscriptions (Admin supervision exclu)."""
    if is_supervision_admin(request.user):
        return "Accès non autorisé pour ce profil."
    if request.user.is_superuser:
        return None
    role = _role_name(request)
    if role not in ("Responsable", "ResponsableAcademique"):
        return "Action réservée aux responsables de l'établissement."
    return None


def _check_file(request):
    f = request.FILES.get("file")
    if not f:
        return None, "Aucun fichier fourni."
    if f.size > MAX_SIZE:
        return None, "Fichier trop volumineux (max 10 Mo)."
    name = (f.name or "").lower()
    if not name.endswith(import_inscriptions.SUPPORTED):
        return None, "Format non pris en charge : CSV, Excel, Word, PDF ou TXT."
    return f, None


def _get_cours(request):
    cours_id = request.data.get("cours") or request.data.get("cours_id")
    if not cours_id:
        return None, "Sélectionnez le cours cible."
    try:
        cours = get_object_or_404(
            filter_queryset_by_role(Cours.objects.all(), request, "Cours"),
            pk=cours_id,
        )
    except Http404:
        return None, "Cours introuvable ou hors de votre périmètre."
    return cours, None


def _resolve(rows, cours, institution_id):
    qs = Apprenant.objects.all()
    if institution_id:
        qs = qs.filter(
            Q(institution_id=institution_id)
            | Q(inscription_scolaire__institution_id=institution_id)
            | Q(inscriptions_cours__institution_id=institution_id)
        ).distinct()

    learners = list(qs)
    by_id = {a.pk: a for a in learners}
    by_email = {
        (a.email or "").strip().lower(): a
        for a in learners if (a.email or "").strip()
    }

    by_name = {}
    for a in learners:
        parts = [import_inscriptions._norm(a.prenom or ""), import_inscriptions._norm(a.nom or "")]
        for n in {" ".join(p for p in parts if p), " ".join(p for p in reversed(parts) if p)}:
            if n:
                by_name.setdefault(n, []).append(a)

    deja = set(
        InscriptionCours.objects.filter(cours=cours).values_list("apprenant_id", flat=True)
    )

    out = []
    for i, row in enumerate(rows, start=1):
        matches = []

        aid = str(row.get("apprenant_id") or "").strip()
        if aid.isdigit() and int(aid) in by_id:
            matches = [by_id[int(aid)]]

        if not matches:
            email = (row.get("email") or "").strip().lower()
            if email and email in by_email:
                matches = [by_email[email]]

        if not matches:
            candidates = set()
            for raw in (
                row.get("raw") or "",
                f"{row.get('prenom') or ''} {row.get('nom') or ''}".strip(),
                f"{row.get('nom') or ''} {row.get('prenom') or ''}".strip(),
            ):
                n = import_inscriptions._norm(raw)
                if n and n in by_name:
                    candidates.update(by_name[n])
            matches = list(candidates)

        label = (
            row.get("nom")
            or row.get("raw")
            or row.get("email")
            or f"Ligne {i}"
        )

        if not matches:
            statut = "introuvable"
            message = "Aucun apprenant correspondant dans l'établissement."
            appr = None
        elif len(matches) > 1:
            statut = "ambigu"
            message = "Plusieurs apprenants correspondent : précisez l'email."
            appr = None
        else:
            appr = matches[0]
            if appr.pk in deja:
                statut = "deja_inscrit"
                message = "Déjà inscrit à ce cours."
            else:
                statut = "ok"
                message = "Sera inscrit."

        out.append({
            "ligne": i,
            "nom": label,
            "email": row.get("email") or (getattr(appr, "email", "") if appr else ""),
            "apprenant_id": getattr(appr, "pk", None),
            "apprenant_nom": (
                f"{appr.prenom or ''} {appr.nom or ''}".strip() if appr else ""
            ),
            "statut": statut,
            "message": message,
            "candidats": (
                [
                    {
                        "id": a.pk,
                        "nom": f"{a.prenom or ''} {a.nom or ''}".strip(),
                        "email": a.email or "",
                    }
                    for a in matches
                ]
                if statut == "ambigu" else []
            ),
        })

    return out


def _stats(rows):
    c = Counter(r["statut"] for r in rows)
    return {
        "total": len(rows),
        "ok": c.get("ok", 0),
        "deja_inscrit": c.get("deja_inscrit", 0),
        "introuvable": c.get("introuvable", 0),
        "ambigu": c.get("ambigu", 0),
    }


class InscriptionImportAnalyseAPIView(APIView):
    """Analyse le document et renvoie les correspondances (sans créer)."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        err = _check_access(request)
        if err:
            return api_error(err, http_status=status.HTTP_403_FORBIDDEN)

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        cours, err = _get_cours(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        try:
            res = import_inscriptions.extract_learners(f.name, f.read())
        except Exception as exc:
            logger.exception("Analyse des inscriptions échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        rows = _resolve(
            res.get("rows") or [],
            cours,
            default_institution_id(),
        )
        stats = _stats(rows)

        return api_success(
            f"{stats['ok']} inscription(s) possible(s) sur {stats['total']} ligne(s).",
            {
                "cours": {"id": cours.id, "titre": cours.titre},
                "stats": stats,
                "rows": rows,
                "warnings": res.get("warnings") or [],
            },
            status.HTTP_200_OK,
        )


class InscriptionImportCreateAPIView(APIView):
    """Crée les inscriptions correspondances « ok »."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        err = _check_access(request)
        if err:
            return api_error(err, http_status=status.HTTP_403_FORBIDDEN)

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        cours, err = _get_cours(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        try:
            res = import_inscriptions.extract_learners(f.name, f.read())
        except Exception as exc:
            logger.exception("Analyse des inscriptions échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        rows = _resolve(
            res.get("rows") or [],
            cours,
            default_institution_id(),
        )

        # Résolutions manuelles des lignes ambiguës : {"12": 345, ...}
        resolutions = request.data.get("resolutions") or {}
        if isinstance(resolutions, str):
            try:
                resolutions = json.loads(resolutions)
            except (TypeError, ValueError):
                resolutions = {}
        if isinstance(resolutions, dict) and resolutions:
            resolved_ids = []
            for key, value in resolutions.items():
                try:
                    resolved_ids.append(int(value))
                except (TypeError, ValueError):
                    continue
            apprenants = Apprenant.objects.filter(pk__in=resolved_ids)
            institution_id = default_institution_id()
            if institution_id:
                apprenants = apprenants.filter(institution_id=institution_id)
            by_id = {a.pk: a for a in apprenants}
            deja = set(
                InscriptionCours.objects.filter(cours=cours)
                .values_list("apprenant_id", flat=True)
            )
            for r in rows:
                chosen = resolutions.get(str(r["ligne"]), resolutions.get(r["ligne"]))
                try:
                    chosen_id = int(chosen)
                except (TypeError, ValueError):
                    continue
                appr = by_id.get(chosen_id)
                if not appr:
                    continue
                r["apprenant_id"] = appr.pk
                r["apprenant_nom"] = f"{appr.prenom or ''} {appr.nom or ''}".strip()
                r["email"] = r.get("email") or appr.email or ""
                if appr.pk in deja:
                    r["statut"] = "deja_inscrit"
                    r["message"] = "Déjà inscrit à ce cours (résolution manuelle)."
                else:
                    r["statut"] = "ok"
                    r["message"] = "Sera inscrit (résolution manuelle)."

        created = 0
        skipped = 0
        errors = []
        created_rows = []
        for r in rows:
            if r["statut"] != "ok" or not r["apprenant_id"]:
                if r["statut"] in ("introuvable", "ambigu", "invalide"):
                    errors.append({
                        "ligne": r["ligne"], "nom": r["nom"], "email": r.get("email") or "",
                        "statut": r["statut"], "message": r["message"],
                    })
                continue
            try:
                _, was_created = InscriptionCours.objects.get_or_create(
                    apprenant_id=r["apprenant_id"],
                    cours=cours,
                    defaults={"statut": "inscrit"},
                )
                if was_created:
                    created += 1
                    created_rows.append(r["ligne"])
                else:
                    skipped += 1
            except Exception as exc:
                logger.exception("Création d'inscription échouée (ligne %s)", r["ligne"])
                errors.append({
                    "ligne": r["ligne"], "nom": r["nom"], "email": r.get("email") or "",
                    "statut": "erreur", "message": str(exc),
                })

        stats = _stats(rows)
        return api_success(
            f"{created} inscription(s) créée(s)"
            + (f", {skipped} déjà présente(s)." if skipped else "."),
            {
                "cours_id": cours.id,
                "cours_titre": cours.titre,
                "created": created,
                "skipped": skipped,
                "stats": stats,
                "rows": rows,
                "errors": errors,
                "created_rows": created_rows,
                "warnings": res.get("warnings") or [],
            },
            status.HTTP_201_CREATED,
        )
