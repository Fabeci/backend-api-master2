# courses/import_views.py
# =============================================================================
# Import de BLOCS dans une séquence (extraction puis création en lot).
#
#   POST /api/v1/blocs-contenu/importer/            (multipart)  → brouillon
#   POST /api/v1/sequences/<pk>/blocs/importer/     (JSON)       → création
# =============================================================================

import logging

from django.db.models import Max
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.views import APIView

from core.rbac import RBACPermission

from courses import import_blocs
from courses.models import BlocContenu, Sequence
from courses.utils import can_create_in_context
from courses.views import api_error, api_success

logger = logging.getLogger(__name__)


class BlocsImportExtractAPIView(APIView):
    """Extrait un brouillon de blocs depuis un fichier (sans rien créer)."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        f = request.FILES.get("file")
        if not f:
            return api_error("Aucun fichier fourni.", http_status=status.HTTP_400_BAD_REQUEST)
        if f.size > 10 * 1024 * 1024:
            return api_error("Fichier trop volumineux (max 10 Mo).", http_status=status.HTTP_400_BAD_REQUEST)
        try:
            res = import_blocs.extract_blocs(f.name, f.read())
        except Exception as exc:
            logger.exception("Import blocs échoué (%s)", getattr(f, "name", "?"))
            return api_error("Impossible d'extraire les blocs du fichier.",
                             errors={"detail": str(exc)}, http_status=status.HTTP_400_BAD_REQUEST)
        return api_success(f"{res['nb']} bloc(s) extrait(s).", res, status.HTTP_200_OK)


class SequenceBlocsImportCreateAPIView(APIView):
    """Crée en lot des blocs dans une séquence (après aperçu)."""
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        seq = get_object_or_404(Sequence.objects.select_related("module__cours"), pk=pk)

        user = request.user
        if not (getattr(user, "is_superuser", False) or can_create_in_context(user, seq.module.cours)):
            return api_error("Action réservée au créateur du cours.", http_status=status.HTTP_403_FORBIDDEN)

        items = request.data.get("blocs") or []
        if not isinstance(items, list) or not items:
            return api_error("Aucun bloc à importer.", http_status=status.HTTP_400_BAD_REQUEST)

        max_ordre = BlocContenu.objects.filter(sequence=seq).aggregate(m=Max("ordre"))["m"] or 0
        created, errors = 0, []

        for i, b in enumerate(items, start=1):
            if not isinstance(b, dict):
                continue
            titre = (b.get("titre") or "").strip()
            if not titre:
                errors.append({"ligne": i, "message": "Titre manquant."})
                continue

            type_bloc = (b.get("type_bloc") or "texte").strip().lower()
            if type_bloc not in import_blocs.TYPES:
                type_bloc = "texte"

            try:
                ordre = int(b.get("ordre") or (max_ordre + i))
            except Exception:
                ordre = max_ordre + i

            contenu = b.get("contenu") or ""
            url = b.get("url") or ""
            kwargs = {
                "sequence": seq,
                "titre": titre,
                "type_bloc": type_bloc,
                "ordre": ordre,
                "est_obligatoire": bool(b.get("est_obligatoire", True)),
                "est_visible": bool(b.get("est_visible", True)),
            }
            if type_bloc == "html":
                kwargs["contenu_html"] = contenu
            elif type_bloc == "markdown":
                kwargs["contenu_markdown"] = contenu
            elif type_bloc == "code":
                kwargs["code_source"] = contenu
            elif type_bloc == "video":
                kwargs["video_url"] = url or contenu
            elif type_bloc == "audio":
                kwargs["audio_url"] = url or contenu
            elif type_bloc == "lien":
                kwargs["lien_externe"] = url or contenu
            else:
                kwargs["contenu_texte"] = contenu

            try:
                BlocContenu.objects.create(**kwargs)
                created += 1
            except Exception as exc:
                errors.append({"ligne": i, "message": str(exc)})

        return api_success(
            f"{created} bloc(s) créé(s).",
            {"created": created, "errors": errors},
            status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
        )
