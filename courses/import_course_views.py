# courses/import_course_views.py
# =============================================================================
# Import d'un cours complet (modules / séquences / blocs / quiz).
#
#   POST /api/v1/cours/importer/analyser/   (multipart) → aperçu (sans création)
#   POST /api/v1/cours/importer/            (multipart) → création du cours
# =============================================================================

import logging
import re

from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission

from courses import async_import, import_course
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
        return None, "Format non pris en charge : utilisez un fichier Word (.docx), PDF ou image."
    return f, None


def _preview(tree: dict, complet: bool = False) -> dict:
    """Arborescence pour l'aperçu. `complet=True` inclut le HTML et les questions,
    afin que l'interface puisse éditer la structure puis créer sans re-parser."""
    modules = []
    for m in tree.get("modules", []):
        sequences = []
        for s in m.get("sequences", []):
            blocs = []
            for b in s.get("blocs", []):
                item = {"titre": b.get("titre"), "type_bloc": b.get("type_bloc")}
                if complet:
                    item["contenu"] = b.get("contenu") or ""
                blocs.append(item)
            quizzes = []
            for q in s.get("quizzes", []):
                item = {"titre": q.get("titre"), "nb_questions": len(q.get("questions") or [])}
                if complet:
                    item["questions"] = q.get("questions") or []
                    item["description"] = q.get("description") or ""
                quizzes.append(item)
            sequences.append({
                "titre": s.get("titre"),
                "blocs": blocs,
                "quizzes": quizzes,
            })
        modules.append({"titre": m.get("titre"), "sequences": sequences})
    return {
        "titre": tree.get("titre"),
        "stats": tree.get("stats") or {},
        "warnings": tree.get("warnings") or [],
        "modules": modules,
    }


def _build_meta(request, tree, user):
    """Construit et valide les métadonnées du cours (commun fichier / JSON)."""
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

    if not user.is_superuser and role_name == "Formateur":
        # Anti-usurpation : le formateur connecté est toujours l'enseignant.
        meta["enseignant"] = user.id

    if not meta.get("enseignant"):
        return None, api_error("Sélectionnez le formateur responsable du cours.",
                               http_status=status.HTTP_400_BAD_REQUEST)
    if not meta.get("groupe"):
        return None, api_error("Sélectionnez un groupe / une classe.",
                               http_status=status.HTTP_400_BAD_REQUEST)
    if not meta.get("matiere"):
        return None, api_error("Sélectionnez une matière.",
                               http_status=status.HTTP_400_BAD_REQUEST)
    return meta, None


def _stats(modules):
    return {
        "modules": len(modules),
        "sequences": sum(len(m.get("sequences") or []) for m in modules),
        "blocs": sum(len(s.get("blocs") or []) for m in modules for s in (m.get("sequences") or [])),
        "quizzes": sum(len(s.get("quizzes") or []) for m in modules for s in (m.get("sequences") or [])),
        "questions": sum(
            len(q.get("questions") or [])
            for m in modules for s in (m.get("sequences") or [])
            for q in (s.get("quizzes") or [])
        ),
    }


_TYPES = {"texte", "html", "markdown", "video", "audio", "image", "fichier", "lien", "code"}


_DANGEROUS_TAGS = ("script", "iframe", "object", "embed", "form", "input", "button", "link", "meta", "base")


def _clean_html(value: str) -> str:
    """Neutralise les vecteurs XSS du HTML fourni par l'interface d'édition."""
    if not isinstance(value, str):
        return ""
    html = value
    for tag in _DANGEROUS_TAGS:
        html = re.sub(
            rf"<\s*{tag}\b[^>]*>.*?<\s*/\s*{tag}\s*>",
            "", html, flags=re.IGNORECASE | re.DOTALL,
        )
        html = re.sub(rf"<\s*/?\s*{tag}\b[^>]*>", "", html, flags=re.IGNORECASE)
    html = re.sub(
        r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)",
        "", html, flags=re.IGNORECASE,
    )
    html = re.sub(
        r"(href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2",
        r'\1="#"', html, flags=re.IGNORECASE,
    )
    return html


def _sanitize_tree(raw_modules):
    """Normalise l'arborescence éditée par l'utilisateur."""
    out = []
    for m in raw_modules or []:
        if not isinstance(m, dict):
            continue
        sequences = []
        for s in m.get("sequences") or []:
            if not isinstance(s, dict):
                continue
            blocs = []
            for b in s.get("blocs") or []:
                if not isinstance(b, dict):
                    continue
                type_bloc = (b.get("type_bloc") or "html").strip().lower()
                if type_bloc not in _TYPES:
                    type_bloc = "html"
                contenu = _clean_html(b.get("contenu") or "")
                blocs.append({
                    "titre": (b.get("titre") or "Contenu")[:255],
                    "type_bloc": type_bloc,
                    "contenu": contenu,
                    "url": b.get("url") or "",
                    "ordre": len(blocs) + 1,
                    "est_obligatoire": bool(b.get("est_obligatoire", True)),
                    "est_visible": bool(b.get("est_visible", True)),
                })
            quizzes = []
            for q in s.get("quizzes") or []:
                if not isinstance(q, dict):
                    continue
                questions = []
                for item in q.get("questions") or []:
                    if not isinstance(item, dict):
                        continue
                    try:
                        points = float(item.get("points") or 1)
                    except (TypeError, ValueError):
                        points = 1.0
                    questions.append({
                        "enonce_texte": (item.get("enonce_texte") or "")[:4000],
                        "type_question": item.get("type_question") or "choix_unique",
                        "points": points,
                        "indication_reponse": item.get("indication_reponse") or "",
                        "reponses": [
                            {
                                "texte": (r.get("texte") or "")[:2000],
                                "est_correcte": bool(r.get("est_correcte")),
                            }
                            for r in (item.get("reponses") or []) if isinstance(r, dict)
                        ],
                    })
                quizzes.append({
                    "titre": (q.get("titre") or "Quiz")[:255],
                    "description": q.get("description") or "",
                    "questions": questions,
                })
            sequences.append({
                "titre": (s.get("titre") or "Séquence")[:255],
                "description": s.get("description") or "",
                "blocs": blocs,
                "quizzes": quizzes,
                "ordre": len(sequences) + 1,
            })
        out.append({
            "titre": (m.get("titre") or "Module")[:255],
            "description": m.get("description") or "",
            "sequences": sequences,
            "ordre": len(out) + 1,
        })
    return out


def _doublon(meta):
    """Cours déjà existant pour le même groupe/matière/formateur/année."""
    from courses.models import Cours
    return Cours.objects.filter(
        groupe_id=meta.get("groupe"),
        matiere_id=meta.get("matiere"),
        enseignant_id=meta.get("enseignant"),
        annee_scolaire_id=meta.get("annee_scolaire"),
    ).first()


def _doublon_error(cours):
    return api_error(
        f"Un cours existe déjà pour ce groupe, cette matière et ce formateur "
        f"cette année : « {cours.titre} ». Choisissez un autre groupe ou "
        f"modifiez le cours existant.",
        errors={"cours_id": cours.id, "titre": cours.titre},
        http_status=status.HTTP_409_CONFLICT,
    )


class CoursImportTreeCreateAPIView(APIView):
    """Crée le cours depuis l'arborescence éditée (JSON), sans re-parser le fichier."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request):
        user = request.user
        if not can_create_in_context(user):
            return api_error("Action réservée aux formateurs et responsables.",
                             http_status=status.HTTP_403_FORBIDDEN)

        modules = _sanitize_tree(request.data.get("modules"))
        if not modules:
            return api_error("La structure à importer est vide.",
                             http_status=status.HTTP_400_BAD_REQUEST)

        tree = {
            "titre": request.data.get("titre") or "Cours importé",
            "modules": modules,
            "warnings": [],
        }
        tree["stats"] = _stats(modules)

        meta, err = _build_meta(request, tree, user)
        if err:
            return err
        existing = _doublon(meta)
        if existing:
            return _doublon_error(existing)

        try:
            cours = import_course.create_course_from_tree(user, meta, tree)
        except ValidationError as exc:
            return api_error("Erreur de validation", errors=exc.detail,
                             http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Création du cours importé (arbre) échouée")
            return api_error("Impossible de créer le cours importé.",
                             errors={"detail": str(exc)},
                             http_status=status.HTTP_400_BAD_REQUEST)

        stats = tree["stats"]
        return api_success(
            f"Cours importé : {stats['modules']} module(s), "
            f"{stats['sequences']} séquence(s), {stats['blocs']} bloc(s), "
            f"{stats['quizzes']} quiz.",
            {"cours_id": cours.id, "titre": cours.titre, "stats": stats,
             "warnings": tree["warnings"]},
            status.HTTP_201_CREATED,
        )




class CoursImportAsyncTreeCreateAPIView(APIView):
    """Démarre la création du cours en arrière-plan et retourne un task_id."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request):
        user = request.user
        if not can_create_in_context(user):
            return api_error("Action réservée aux formateurs et responsables.",
                             http_status=status.HTTP_403_FORBIDDEN)

        modules = _sanitize_tree(request.data.get("modules"))
        if not modules:
            return api_error("La structure à importer est vide.",
                             http_status=status.HTTP_400_BAD_REQUEST)

        tree = {
            "titre": request.data.get("titre") or "Cours importé",
            "modules": modules,
            "warnings": [],
        }
        meta, err = _build_meta(request, tree, user)
        if err:
            return err
        existing = _doublon(meta)
        if existing:
            return _doublon_error(existing)

        task_id = async_import.lancer_creation_cours(meta, modules, user.id)
        return api_success(
            "Import lancé en arrière-plan.",
            {"task_id": task_id, "stats": _stats(modules)},
            status.HTTP_202_ACCEPTED,
        )


class CoursImportAsyncStatusAPIView(APIView):
    """État d'une création de cours asynchrone."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, task_id):
        data = async_import.statut_import(str(task_id))
        if not data or data.get("user_id") != request.user.id:
            return api_error("Tâche d'import introuvable ou expirée.",
                             http_status=status.HTTP_404_NOT_FOUND)
        payload = {k: v for k, v in data.items() if k != "user_id"}
        return api_success(payload.get("message") or "Import en cours…", payload, status.HTTP_200_OK)

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

        complet = str(request.query_params.get("complet", "")).lower() in ("1", "true", "yes")
        preview = _preview(tree, complet=complet)
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

        meta, err = _build_meta(request, tree, user)
        if err:
            return err
        existing = _doublon(meta)
        if existing:
            return _doublon_error(existing)

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
