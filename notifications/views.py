# notifications/views.py
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, DestroyModelMixin

from .models import Notification
from .serializers import NotificationSerializer


# ── Helpers réponse unifiée (même pattern que users/views.py) ─────────────────

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    return Response(
        {"success": True, "status": http_status, "message": message, "data": data},
        status=http_status,
    )

def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST):
    payload = {"success": False, "status": http_status, "message": message}
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# ── ViewSet ───────────────────────────────────────────────────────────────────

class NotificationViewSet(ListModelMixin, RetrieveModelMixin, DestroyModelMixin, GenericViewSet):
    """
    Endpoints :
      GET    /api/notifications/              → liste des notifications de l'utilisateur connecté
      GET    /api/notifications/{id}/         → détail d'une notification
      DELETE /api/notifications/{id}/         → supprimer une notification
      PATCH  /api/notifications/{id}/read/    → marquer comme lue
      POST   /api/notifications/read-all/     → marquer TOUTES comme lues
      DELETE /api/notifications/delete-all/   → supprimer TOUTES les notifications lues
      GET    /api/notifications/unread-count/ → nombre de non lues
    """
    serializer_class   = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            user=self.request.user
        ).order_by('-created_at')

    # ── list : supporte ?unread=true ─────────────────────────────────────────
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        unread_only = request.query_params.get('unread', '').lower() in ('1', 'true', 'yes')
        if unread_only:
            qs = qs.filter(is_read=False)
        serializer = self.get_serializer(qs, many=True)
        return api_success(
            "Notifications récupérées.",
            data={
                "notifications": serializer.data,
                "total":         qs.count(),
                "unread_count":  self.get_queryset().filter(is_read=False).count(),
            }
        )

    # ── PATCH /notifications/{id}/read/ ──────────────────────────────────────
    @action(detail=True, methods=['patch'], url_path='read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if notification.is_read:
            return api_success("Déjà marquée comme lue.", data=self.get_serializer(notification).data)
        notification.mark_as_read()
        return api_success("Notification marquée comme lue.", data=self.get_serializer(notification).data)

    # ── POST /notifications/read-all/ ─────────────────────────────────────────
    @action(detail=False, methods=['post'], url_path='read-all')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return api_success(f"{updated} notification(s) marquée(s) comme lue(s).", data={"updated": updated})

    # ── DELETE /notifications/delete-all/ ─────────────────────────────────────
    @action(detail=False, methods=['delete'], url_path='delete-all')
    def delete_all_read(self, request):
        deleted_count, _ = self.get_queryset().filter(is_read=True).delete()
        return api_success(f"{deleted_count} notification(s) lue(s) supprimée(s).", data={"deleted": deleted_count})

    # ── GET /notifications/unread-count/ ─────────────────────────────────────
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return api_success("Compteur récupéré.", data={"unread_count": count})

    # ── destroy : override pour réponse unifiée ───────────────────────────────
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_success("Notification supprimée.", http_status=status.HTTP_200_OK)