# courses/invite_views.py
# =============================================================================
# Invités EXTERNES d'une séance (en plus des éligibles automatiques :
# formateur du cours + apprenants inscrits).
#
#   GET    /api/v1/sessions/<pk>/invites/
#   POST   /api/v1/sessions/<pk>/invites/            { email, nom? }
#   DELETE /api/v1/sessions/<pk>/invites/<invite_id>/
# =============================================================================

import logging

from rest_framework import permissions, status
from rest_framework.views import APIView

from core.rbac import RBACPermission

from courses.meet_views import _get_session
from courses.models import SessionInvite
from courses.serializers import SessionInviteSerializer
from courses.views import api_error, api_success

logger = logging.getLogger(__name__)


class SessionInviteListCreateAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def get(self, request, pk):
        session = _get_session(request, pk)
        items = session.invites_externes.all()
        return api_success("Invités externes", SessionInviteSerializer(items, many=True).data, status.HTTP_200_OK)

    def post(self, request, pk):
        session = _get_session(request, pk)
        email = (request.data.get("email") or "").strip().lower()
        nom = (request.data.get("nom") or "").strip()

        if "@" not in email:
            return api_error("Adresse email invalide.", http_status=status.HTTP_400_BAD_REQUEST)

        obj, created = SessionInvite.objects.get_or_create(
            session=session, email=email,
            defaults={"nom": nom, "ajoute_par": request.user if request.user.is_authenticated else None},
        )
        if not created and nom and obj.nom != nom:
            obj.nom = nom
            obj.save(update_fields=["nom"])

        return api_success(
            "Invité ajouté." if created else "Invité déjà présent.",
            SessionInviteSerializer(obj).data,
            status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class SessionInviteDetailAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def delete(self, request, pk, invite_id):
        session = _get_session(request, pk)
        deleted, _ = SessionInvite.objects.filter(session=session, id=invite_id).delete()
        if not deleted:
            return api_error("Invité introuvable.", http_status=status.HTTP_404_NOT_FOUND)
        return api_success("Invité retiré.", data=None, http_status=status.HTTP_200_OK)
