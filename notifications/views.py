# notifications/views.py

from django.utils import timezone
from django.db.models import Count, Q
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification, PreferenceNotification, DigestNotification, CanalNotification
from .serializers import (
    NotificationSerializer,
    NotificationListSerializer,
    MarquerLueSerializer,
    PreferenceNotificationSerializer,
    DigestNotificationSerializer,
)


# ============================================================================
# NOTIFICATION VIEWSET
# ============================================================================

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Centre de notifications de l'utilisateur connecté.

    GET  /notifications/                  → liste (allégée)
    GET  /notifications/{id}/             → détail complet
    GET  /notifications/non_lues/         → non lues uniquement
    GET  /notifications/compteur/         → { total, non_lues, par_priorite }
    POST /notifications/marquer_lues/     → marquer une liste (ou toutes) comme lues
    POST /notifications/{id}/marquer_lue/ → marquer une seule comme lue
    DELETE /notifications/supprimer_lues/ → supprimer toutes les notifs lues
    """

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs   = (
            Notification.objects
            .filter(recipient=user)
            .select_related("sender", "institution", "annee_scolaire")
            .order_by("-created_at")
        )

        # Filtres query params
        type_     = self.request.query_params.get("type")
        canal     = self.request.query_params.get("canal")
        priorite  = self.request.query_params.get("priorite")
        is_read   = self.request.query_params.get("is_read")
        expirees  = self.request.query_params.get("expirees", "false")

        if type_:
            qs = qs.filter(type=type_)
        if canal:
            qs = qs.filter(canal=canal)
        if priorite:
            qs = qs.filter(priorite=priorite)
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == "true")

        # Par défaut on masque les expirées
        if expirees.lower() == "false":
            qs = qs.filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
            )

        return qs

    def get_serializer_class(self):
        if self.action == "retrieve":
            return NotificationSerializer
        return NotificationListSerializer

    # ── Actions custom ────────────────────────────────────────────────────────

    @action(detail=False, methods=["get"], url_path="non_lues")
    def non_lues(self, request):
        """Retourne uniquement les notifications non lues."""
        qs = self.get_queryset().filter(is_read=False)
        serializer = NotificationListSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="compteur")
    def compteur(self, request):
        """
        Retourne un résumé des compteurs pour le badge du centre de notifications.
        {
            "total":     12,
            "non_lues":   5,
            "par_priorite": { "basse": 1, "moyenne": 2, "haute": 1, "critique": 1 }
            "par_canal":    { "in_app": 10, "email": 2 }
        }
        """
        qs = self.get_queryset()

        total    = qs.count()
        non_lues = qs.filter(is_read=False).count()

        par_priorite = {
            item["priorite"]: item["count"]
            for item in qs.filter(is_read=False)
                          .values("priorite")
                          .annotate(count=Count("id"))
        }
        par_canal = {
            item["canal"]: item["count"]
            for item in qs.values("canal").annotate(count=Count("id"))
        }

        return Response({
            "total":        total,
            "non_lues":     non_lues,
            "par_priorite": par_priorite,
            "par_canal":    par_canal,
        })

    @action(detail=False, methods=["post"], url_path="marquer_lues")
    def marquer_lues(self, request):
        """
        Marque une liste de notifications comme lues.
        Si `ids` est absent → marque TOUTES les non lues.
        Body: { "ids": [1, 2, 3] }  (optionnel)
        """
        serializer = MarquerLueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ids = serializer.validated_data.get("ids")
        qs  = self.get_queryset().filter(is_read=False)

        if ids:
            qs = qs.filter(id__in=ids)

        count = qs.update(is_read=True, read_at=timezone.now())
        return Response({"marquees": count}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="marquer_lue")
    def marquer_lue(self, request, pk=None):
        """Marque une notification unique comme lue."""
        notif = self.get_object()
        notif.marquer_comme_lue()
        return Response({"detail": "Notification marquée comme lue."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["delete"], url_path="supprimer_lues")
    def supprimer_lues(self, request):
        """Supprime toutes les notifications déjà lues de l'utilisateur connecté."""
        count, _ = self.get_queryset().filter(is_read=True).delete()
        return Response({"supprimees": count}, status=status.HTTP_200_OK)


# ============================================================================
# PRÉFÉRENCES VIEWSET
# ============================================================================

class PreferenceNotificationViewSet(viewsets.ModelViewSet):
    """
    Gestion des préférences de notification de l'utilisateur connecté.

    GET    /preferences/          → liste ses préférences
    POST   /preferences/          → créer une préférence
    PATCH  /preferences/{id}/     → modifier est_active
    DELETE /preferences/{id}/     → supprimer
    POST   /preferences/reset/    → remettre les préférences par défaut
    """

    permission_classes   = [permissions.IsAuthenticated]
    serializer_class     = PreferenceNotificationSerializer
    http_method_names    = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return PreferenceNotification.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=["post"], url_path="reset")
    def reset(self, request):
        """
        Remet toutes les préférences de l'utilisateur à leur valeur par défaut
        (supprime les entrées personnalisées → comportement = tout activé).
        """
        count, _ = self.get_queryset().delete()
        return Response(
            {"detail": f"{count} préférence(s) réinitialisée(s)."},
            status=status.HTTP_200_OK
        )


# ============================================================================
# DIGEST VIEWSET
# ============================================================================

class DigestNotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Historique des digests envoyés à l'utilisateur connecté.

    GET /digests/       → liste
    GET /digests/{id}/  → détail avec les notifications groupées
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = DigestNotificationSerializer

    def get_queryset(self):
        return (
            DigestNotification.objects
            .filter(user=self.request.user)
            .prefetch_related("notifications")
            .order_by("-created_at")
        )