# users/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404

from .serializers import (
    RegisterSerializer,
    VerifyEmailSerializer,
    ResendCodeSerializer,
    UserLoginSerializer,
    AdminCrudSerializer,
    ParentCrudSerializer,
    ApprenantCrudSerializer,
    FormateurCrudSerializer,
    ResponsableAcademiqueCrudSerializer,
)
from .models import Admin, Parent, Apprenant, Formateur, ResponsableAcademique


# =========================
# Helpers de réponse unifiée
# =========================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    return Response(
        {
            "success": True,
            "status": http_status,
            "message": message,
            "data": data,
        },
        status=http_status,
    )


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST):
    payload = {
        "success": False,
        "status": http_status,
        "message": message,
    }
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# =========================
# Auth & Onboarding
# =========================

class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return api_success(
            "Compte créé. Un code d’activation a été envoyé par email.",
            data=data,
            http_status=status.HTTP_201_CREATED,
        )


class VerifyEmailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return api_success(
            "Email vérifié. Compte activé avec succès.",
            data=data,
            http_status=status.HTTP_200_OK,
        )


class ResendCodeAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        return api_success(
            "Nouveau code d’activation envoyé par email.",
            data=data,
            http_status=status.HTTP_200_OK,
        )


class UserLoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        token = serializer.validated_data["token"]

        return api_success(
            "Authentification réussie.",
            data={
                "token": token,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "nom": user.nom,
                    "prenom": user.prenom,
                    "telephone": user.telephone,
                    "role": getattr(user.role, "name", None),
                    "is_staff": user.is_staff,
                    "is_superuser": user.is_superuser,
                },
            },
            http_status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    """
    Invalide le token d’authentification courant.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return api_success(
            "Déconnexion réussie. Le token a été invalidé.",
            data=None,
            http_status=status.HTTP_200_OK,
        )


# =========================
# Permissions personnalisées
# =========================

class IsStaffOrReadOnly(permissions.BasePermission):
    """
    - Lecture (GET, HEAD, OPTIONS) : utilisateur authentifié
    - Écriture (POST, PUT, PATCH, DELETE) : staff uniquement
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )


# =========================
# CRUD – ViewSets
# =========================

class AdminViewSet(viewsets.ModelViewSet):
    queryset = Admin.objects.all()
    serializer_class = AdminCrudSerializer
    permission_classes = [IsStaffOrReadOnly]


class ParentViewSet(viewsets.ModelViewSet):
    queryset = Parent.objects.all()
    serializer_class = ParentCrudSerializer
    permission_classes = [IsStaffOrReadOnly]


class ApprenantViewSet(viewsets.ModelViewSet):
    queryset = Apprenant.objects.all()
    serializer_class = ApprenantCrudSerializer
    permission_classes = [IsStaffOrReadOnly]


class FormateurViewSet(viewsets.ModelViewSet):
    queryset = Formateur.objects.all()
    serializer_class = FormateurCrudSerializer
    permission_classes = [IsStaffOrReadOnly]


class ResponsableAcademiqueViewSet(viewsets.ModelViewSet):
    queryset = ResponsableAcademique.objects.all()
    serializer_class = ResponsableAcademiqueCrudSerializer
    permission_classes = [IsStaffOrReadOnly]
