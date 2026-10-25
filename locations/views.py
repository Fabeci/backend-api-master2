from django.shortcuts import render
from rest_framework import status, viewsets, permissions
from rest_framework.response import Response

from .models import Pays, Ville, Quartier
from .serializers import PaysSerializer, VilleSerializer, QuartierSerializer


class IsAdminRoleOrReadOnly(permissions.BasePermission):
    """Lecture publique (formulaires) ; écriture réservée à l'Admin."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        role = getattr(getattr(request.user, "role", None), "name", None)
        return bool(getattr(request.user, "is_superuser", False) or role == "Admin")


class PaysViewSet(viewsets.ModelViewSet):
    queryset = Pays.objects.all()
    serializer_class = PaysSerializer
    permission_classes = [IsAdminRoleOrReadOnly]

    def destroy(self, request, *args, **kwargs):
        """MONO-ÉTABLISSEMENT : interdire la suppression d'un pays référencé.

        Auparavant, un DELETE entraînait la suppression en cascade des
        établissements et des comptes utilisateurs rattachés.
        """
        obj = self.get_object()
        from academics.models import Institution
        from users.models import User

        if Institution.objects.filter(pays=obj).exists() or User.objects.filter(pays_residence=obj).exists():
            return Response(
                {"detail": "Ce pays est référencé par un établissement ou un utilisateur : suppression interdite."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)


class VilleViewSet(viewsets.ModelViewSet):
    queryset = Ville.objects.all()
    serializer_class = VilleSerializer
    permission_classes = [IsAdminRoleOrReadOnly]


class QuartierViewSet(viewsets.ModelViewSet):
    queryset = Quartier.objects.all()
    serializer_class = QuartierSerializer
    permission_classes = [IsAdminRoleOrReadOnly]
