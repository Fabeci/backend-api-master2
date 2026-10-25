# courses/import_course_views.py
# =============================================================================
# Import d'un cours complet (modules / séquences / blocs / quiz).
#
#   POST /api/v1/cours/importer/analyser/   (multipart) → aperçu (sans création)
#   POST /api/v1/cours/importer/            (multipart) → création du cours
# =============================================================================

import logging

from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission

from courses import import_course
from courses.utils import can_create_in_context
from courses.views import api_error, api_success

logger = logging.getLogger(__name__)

MAX_SIZE = 15 * 1024 * 1024  # 15 Mo
META_FIELDS = (
    "groupe",
    "matiere",
    "enseignant",
    "institution",
    "annee_scolaire",
    "volume_horaire",
    "date_debut",
    "date_fin",
    "statut",
    "image",
)


def _check_file(request):
    f = request.FILES.get("file")
    if not f:
        return None, "Aucun fichier fourni."
    if f.size > MAX_SIZE:
        return None, "Fichier trop volumineux (max 15 Mo)."
    name = (f.name or "").lower()
    if not name.endswith(import_course.SUPPORTED):
        return None, "Format non pris en charge : utilisez un fichier Word (.docx) ou PDF."
    return f, None


def _preview(tree: dict) -> dict:
    """Arborescence allégée (sans le HTML) pour l'aperçu côté interface."""
    modules = []
    for m in tree.get("modules", []):
        sequences = []
        for s in m.get("sequences", []):
            sequences.append({
                "titre": s.get("titre"),
                "blocs": [
                    {"titre": b.get("titre"), "type_bloc": b.get("type_bloc")}
                    for b in s.get("blocs", [])
                ],
                "quizzes": [
                    {"titre": q.get("titre"), "nb_questions": len(q.get("questions") or [])}
                    for q in s.get("quizzes", [])
                ],
            })
        modules.append({"titre": m.get("titre"), "sequences": sequences})
    return {
        "titre": tree.get("titre"),
        "stats": tree.get("stats") or {},
        "warnings": tree.get("warnings") or [],
        "modules": modules,
    }


class CoursImportAnalyseAPIView(APIView):
    """Analyse le document et renvoie la structure détectée (sans rien créer)."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        if not can_create_in_context(request.user):
            return api_error(
                "Action réservée aux formateurs et responsables.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        try:
            tree = import_course.extract_course(f.name, f.read())
        except Exception as exc:
            logger.exception("Analyse du cours importé échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        preview = _preview(tree)
        st = preview["stats"]
        if not st.get("modules"):
            return api_error(
                "Aucun module détecté dans le document. Ajoutez des titres (« Module 1 », "
                "« Séquence 1 », « Quiz »…) puis réessayez.",
                data=preview,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        return api_success(
            f"{st.get('modules', 0)} module(s), {st.get('sequences', 0)} séquence(s), "
            f"{st.get('blocs', 0)} bloc(s), {st.get('quizzes', 0)} quiz détectés.",
            preview,
            status.HTTP_200_OK,
        )


class CoursImportCreateAPIView(APIView):
    """Crée le cours complet à partir du document et des métadonnées fournies."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        user = request.user
        if not can_create_in_context(user):
            return api_error(
                "Action réservée aux formateurs et responsables.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        f, err = _check_file(request)
        if err:
            return api_error(err, http_status=status.HTTP_400_BAD_REQUEST)

        try:
            tree = import_course.extract_course(f.name, f.read())
        except Exception as exc:
            logger.exception("Analyse du cours importé échouée (%s)", getattr(f, "name", "?"))
            return api_error(
                "Impossible d'analyser le document.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        if not tree.get("modules"):
            return api_error(
                "Aucun module détecté dans le document.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Métadonnées du cours ────────────────────────────────────────────
        meta = {}
        for field in META_FIELDS:
            value = request.data.get(field)
            if value not in (None, "", "null", "undefined"):
                meta[field] = value

        meta["titre"] = (
            request.data.get("titre")
            or tree.get("titre")
            or "Cours importé"
        )[:255]

        try:
            meta["volume_horaire"] = int(meta.get("volume_horaire") or 0)
        except (TypeError, ValueError):
            meta["volume_horaire"] = 0

        role_name = user.role.name if getattr(user, "role", None) else None

        from core.tenant import default_institution, default_annee_scolaire
        inst = default_institution()
        annee = default_annee_scolaire()
        if inst:
            meta["institution"] = inst.id
        if annee:
            meta["annee_scolaire"] = annee.id

        if not user.is_superuser:
            if role_name == "Formateur":
                # Anti-usurpation : le formateur connecté est toujours l'enseignant.
                meta["enseignant"] = user.id

        if not meta.get("enseignant"):
            return api_error(
                "Sélectionnez le formateur responsable du cours.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        if not meta.get("groupe"):
            return api_error("Sélectionnez un groupe / une classe.", http_status=status.HTTP_400_BAD_REQUEST)
        if not meta.get("matiere"):
            return api_error("Sélectionnez une matière.", http_status=status.HTTP_400_BAD_REQUEST)

        try:
            cours = import_course.create_course_from_tree(user, meta, tree)
        except ValidationError as exc:
            return api_error(
                "Erreur de validation",
                errors=exc.detail,
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("Création du cours importé échouée")
            return api_error(
                "Impossible de créer le cours importé.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        stats = tree.get("stats") or {}
        return api_success(
            f"Cours importé : {stats.get('modules', 0)} module(s), "
            f"{stats.get('sequences', 0)} séquence(s), {stats.get('blocs', 0)} bloc(s), "
            f"{stats.get('quizzes', 0)} quiz.",
            {
                "cours_id": cours.id,
                "titre": cours.titre,
                "stats": stats,
                "warnings": tree.get("warnings") or [],
            },
            status.HTTP_201_CREATED,
        )
