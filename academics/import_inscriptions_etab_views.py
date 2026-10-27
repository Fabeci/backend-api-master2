# academics/import_inscriptions_etab_views.py
# =============================================================================
#   POST /api/v1/inscriptions-etab/importer/analyser/   (multipart) → aperçu
#   POST /api/v1/inscriptions-etab/importer/            (multipart) → création
# =============================================================================

import json
import logging

from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission

from academics import import_inscriptions_etab
from academics.models import AnneeScolaire, Institution
from courses import import_inscriptions
from courses.views import api_error, api_success

logger = logging.getLogger(__name__)

MAX_SIZE = 10 * 1024 * 1024


def _role_name(request):
    role = getattr(request.user, "role", None)
    raw = getattr(role, "name", None) if role else None
    if not raw:
        return None
    key = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    if key in ("responsable", "responsableacademique", "responsableacad"):
        return "Responsable"
    return raw


def _check_access(request):
    if request.user.is_superuser:
        return None
    if _role_name(request) in ("Admin", "Responsable", "ResponsableAcademique"):
        return None
    return "Action réservée à l'administration de l'établissement."


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


def _context(request):
    """MONO-ÉTABLISSEMENT : institution/année de référence, non négociables."""
    from core.tenant import default_institution, default_annee_scolaire
    institution = default_institution()
    annee = default_annee_scolaire()
    if not institution or not annee:
        return None, None, "Institution ou année scolaire par défaut introuvable."
    return institution, annee, None


class InscriptionEtabImportAnalyseAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        err = _check_access(request)
        if err:
            return api_error(err, http_status=status.HTTP_403_FORBIDDEN)

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        institution, annee, err = _context(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        try:
            res = import_inscriptions.extract_learners(f.name, f.read())
        except Exception as exc:
            logger.exception("Analyse inscriptions établissement échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        rows = import_inscriptions_etab.resolve(
            res.get("rows") or [], institution, annee
        )
        st = import_inscriptions_etab.stats(rows)

        return api_success(
            f"{st['ok'] + st['nouveau']} inscription(s) possible(s) sur {st['total']} ligne(s).",
            {
                "institution": {"id": institution.id, "nom": institution.nom},
                "annee_scolaire": {"id": annee.id, "libelle": getattr(annee, "annee_format_classique", str(annee))},
                "stats": st,
                "rows": rows,
                "warnings": res.get("warnings") or [],
            },
            status.HTTP_200_OK,
        )


class InscriptionEtabImportCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        err = _check_access(request)
        if err:
            return api_error(err, http_status=status.HTTP_403_FORBIDDEN)

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        institution, annee, err = _context(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        try:
            res = import_inscriptions.extract_learners(f.name, f.read())
        except Exception as exc:
            logger.exception("Analyse inscriptions établissement échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        rows = import_inscriptions_etab.resolve(
            res.get("rows") or [], institution, annee
        )

        resolutions = request.data.get("resolutions") or {}
        if isinstance(resolutions, str):
            try:
                resolutions = json.loads(resolutions)
            except (TypeError, ValueError):
                resolutions = {}
        if isinstance(resolutions, dict) and resolutions:
            from users.models import Apprenant
            ids = []
            for v in resolutions.values():
                try:
                    ids.append(int(v))
                except (TypeError, ValueError):
                    continue
            by_id = {a.pk: a for a in Apprenant.objects.filter(pk__in=ids, institution=institution)}
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
                r["statut"] = "ok"
                r["message"] = "Inscription à créer (résolution manuelle)."

        created = import_inscriptions_etab.create(rows, institution, annee)

        return api_success(
            f"{created['created_inscriptions']} inscription(s) créée(s)"
            + (f", {len(created['created_accounts'])} compte(s) apprenant créé(s)."
               if created["created_accounts"] else "."),
            {
                "institution_id": institution.id,
                "annee_scolaire_id": annee.id,
                "created": created["created_inscriptions"],
                "skipped": created["skipped"],
                "accounts": created["created_accounts"],
                "errors": created.get("errors") or [],
                "rows": rows,
                "stats": import_inscriptions_etab.stats(rows),
                "warnings": res.get("warnings") or [],
            },
            status.HTTP_201_CREATED,
        )
