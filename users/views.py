# users/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404

from users.utils import BaseModelViewSet

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
            "Compte créé. Un code d'activation a été envoyé par email.",
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
            "Nouveau code d'activation envoyé par email.",
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
                    "institution_id": user.institution_id if hasattr(user, 'institution_id') else None,
                    "annee_scolaire_active_id": user.annee_scolaire_active_id if hasattr(user, 'annee_scolaire_active_id') else None,
                },
            },
            http_status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    """
    Invalide le token d'authentification courant.
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


class IsAdminOrHigher(permissions.BasePermission):
    """
    Permission : Admin, Responsable ou SuperUser uniquement.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        role_name = request.user.role.name if request.user.role else None
        return role_name in ['Admin', 'Responsable']


# =========================
# CRUD – ViewSets avec filtrage par rôle
# =========================

class AdminViewSet(BaseModelViewSet):
    """
    ViewSet pour les Admins.
    
    Filtrage selon le rôle :
    - SuperUser : voit tous les admins
    - Admin : voit seulement les admins de son institution
    - Autres : accès refusé
    """
    queryset = Admin.objects.all()
    serializer_class = AdminCrudSerializer
    permission_classes = [IsAdminOrHigher]
    
    def get_queryset(self):
        """Filtre les admins selon le rôle de l'utilisateur"""
        user = self.request.user
        
        # SuperUser : tout voir
        if user.is_superuser:
            return Admin.objects.all()
        
        # Admin : voir seulement son institution
        if user.institution:
            return Admin.objects.filter(institution=user.institution)
        
        # Pas d'institution : rien
        return Admin.objects.none()
    
    def perform_create(self, serializer):
        """Assigne automatiquement l'institution du créateur (sauf SuperUser)"""
        user = self.request.user
        
        # Si l'utilisateur n'est pas SuperUser et a une institution
        if not user.is_superuser and user.institution:
            # L'Admin créé hérite de l'institution du créateur
            serializer.save(institution=user.institution)
        else:
            serializer.save()


class ParentViewSet(BaseModelViewSet):
    """
    ViewSet pour les Parents.
    
    Filtrage selon le rôle :
    - SuperUser : voit tous les parents
    - Admin/Responsable : voit les parents de son institution
    - Autres : accès refusé
    """
    queryset = Parent.objects.all()
    serializer_class = ParentCrudSerializer
    permission_classes = [IsAdminOrHigher]
    
    def get_queryset(self):
        """Filtre les parents selon le rôle de l'utilisateur"""
        user = self.request.user
        
        # SuperUser : tout voir
        if user.is_superuser:
            return Parent.objects.all()
        
        # Admin/Responsable : voir son institution
        if user.institution:
            return Parent.objects.filter(institution=user.institution)
        
        return Parent.objects.none()
    
    def perform_create(self, serializer):
        """Assigne automatiquement l'institution"""
        user = self.request.user
        if not user.is_superuser and user.institution:
            serializer.save(institution=user.institution)
        else:
            serializer.save()


class ApprenantViewSet(BaseModelViewSet):
    """
    ViewSet pour les Apprenants.
    
    Filtrage selon le rôle :
    - SuperUser : voit tous les apprenants
    - Admin/Responsable : voit les apprenants de son institution
    - Formateur : voit les apprenants de SES cours
    - Autres : accès refusé
    """
    queryset = Apprenant.objects.all()
    serializer_class = ApprenantCrudSerializer
    permission_classes = [IsStaffOrReadOnly]
    
    def get_queryset(self):
        """Filtre les apprenants selon le rôle de l'utilisateur"""
        user = self.request.user
        
        # SuperUser : tout voir
        if user.is_superuser:
            return Apprenant.objects.all()
        
        role_name = user.role.name if user.role else None
        
        # Admin/Responsable : voir son institution
        if role_name in ['Admin', 'Responsable']:
            if user.institution:
                return Apprenant.objects.filter(institution=user.institution)
        
        # Formateur : voir les apprenants inscrits dans SES cours
        if role_name == 'Formateur':
            from courses.models import InscriptionCours, Cours
            
            # Récupérer les cours du formateur
            mes_cours = Cours.objects.filter(
                enseignant=user,
                institution=user.institution
            ).values_list('id', flat=True)
            
            # Récupérer les apprenants inscrits dans ces cours
            apprenants_ids = InscriptionCours.objects.filter(
                cours_id__in=mes_cours
            ).values_list('apprenant_id', flat=True).distinct()
            
            return Apprenant.objects.filter(id__in=apprenants_ids)
        
        return Apprenant.objects.none()
    
    def perform_create(self, serializer):
        """Assigne automatiquement l'institution"""
        user = self.request.user
        if not user.is_superuser and user.institution:
            serializer.save(institution=user.institution)
        else:
            serializer.save()


class FormateurViewSet(BaseModelViewSet):
    """
    ViewSet pour les Formateurs.
    
    Filtrage selon le rôle :
    - SuperUser : voit tous les formateurs
    - Admin/Responsable : voit les formateurs de son institution
    - Autres : accès refusé
    """
    queryset = Formateur.objects.all()
    serializer_class = FormateurCrudSerializer
    permission_classes = [IsAdminOrHigher]
    
    def get_queryset(self):
        """Filtre les formateurs selon le rôle de l'utilisateur"""
        user = self.request.user
        
        # SuperUser : tout voir
        if user.is_superuser:
            return Formateur.objects.all()
        
        # Admin/Responsable : voir son institution
        if user.institution:
            return Formateur.objects.filter(institution=user.institution)
        
        return Formateur.objects.none()
    
    def perform_create(self, serializer):
        """Assigne automatiquement l'institution et l'année"""
        user = self.request.user
        if not user.is_superuser and user.institution:
            kwargs = {'institution': user.institution}
            if user.annee_scolaire_active:
                kwargs['annee_scolaire_active'] = user.annee_scolaire_active
            serializer.save(**kwargs)
        else:
            serializer.save()


class ResponsableAcademiqueViewSet(BaseModelViewSet):
    """
    ViewSet pour les Responsables Académiques.
    
    Filtrage selon le rôle :
    - SuperUser : voit tous les responsables
    - Admin : voit les responsables de son institution
    - Autres : accès refusé
    """
    queryset = ResponsableAcademique.objects.all()
    serializer_class = ResponsableAcademiqueCrudSerializer
    permission_classes = [IsAdminOrHigher]
    
    def get_queryset(self):
        """Filtre les responsables selon le rôle de l'utilisateur"""
        user = self.request.user
        
        # SuperUser : tout voir
        if user.is_superuser:
            return ResponsableAcademique.objects.all()
        
        # Admin : voir son institution
        if user.institution:
            return ResponsableAcademique.objects.filter(institution=user.institution)
        
        return ResponsableAcademique.objects.none()
    
    def perform_create(self, serializer):
        """Assigne automatiquement l'institution et l'année"""
        user = self.request.user
        if not user.is_superuser and user.institution:
            kwargs = {'institution': user.institution}
            if user.annee_scolaire_active:
                kwargs['annee_scolaire_active'] = user.annee_scolaire_active
            serializer.save(**kwargs)
        else:
            serializer.save()