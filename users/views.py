# users/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions, viewsets
from rest_framework.authtoken.models import Token
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from users.permissions import IsAdminOrHigher
from users.utils import BaseModelViewSet

from .serializers import (
    ModifierMotDePasseSerializer,
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
        {"success": True, "status": http_status, "message": message, "data": data},
        status=http_status,
    )


def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST):
    payload = {"success": False, "status": http_status, "message": message}
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
                    "institution_id": getattr(user, "institution_id", None),
                    "annee_scolaire_active_id": getattr(user, "annee_scolaire_active_id", None),
                },
            },
            http_status=status.HTTP_200_OK,
        )

class LogoutAPIView(APIView):
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
    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsAdminOrHigherOrSelf(permissions.BasePermission):
    """
    Permission :
    - SuperUser             : accès total (lecture + écriture)
    - Admin / Responsable   : accès total (selon queryset)
    - Tout utilisateur auth : lecture seule (GET, HEAD, OPTIONS)
    - Utilisateur lui-même  : peut modifier son propre profil
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        role_name = request.user.role.name if request.user.role else None
        if role_name in ['Admin', 'Responsable']:
            return True

        # ✅ Lecture autorisée pour TOUS les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return True

        # ✅ Écriture autorisée uniquement sur son propre profil
        pk = view.kwargs.get('pk')
        if pk is not None and str(pk) == str(request.user.pk):
            return True

        return False
    
# =========================
# Helpers internes (évite les 500 AttributeError)
# =========================

def _user_institution(user):
    return getattr(user, "institution", None)

def _user_annee_active(user):
    return getattr(user, "annee_scolaire_active", None)

def _role_name(user):
    role = getattr(user, "role", None)
    return getattr(role, "name", None)



# =========================
# CRUD – ViewSets avec filtrage par rôle
# =========================

class AdminViewSet(BaseModelViewSet):
    queryset = Admin.objects.all()
    serializer_class = AdminCrudSerializer
    permission_classes = [IsAdminOrHigher]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return Admin.objects.all()

        inst = _user_institution(user)
        if inst:
            return Admin.objects.filter(institution=inst)

        return Admin.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)

        if not user.is_superuser and inst:
            serializer.save(institution=inst)
        else:
            serializer.save()


class ParentViewSet(BaseModelViewSet):
    queryset = Parent.objects.all()
    serializer_class = ParentCrudSerializer
    permission_classes = [IsAdminOrHigher]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return Parent.objects.all()

        inst = _user_institution(user)
        if inst:
            return Parent.objects.filter(institution=inst)

        return Parent.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)

        if not user.is_superuser and inst:
            serializer.save(institution=inst)
        else:
            serializer.save()


class ApprenantViewSet(BaseModelViewSet):
    queryset = Apprenant.objects.all()
    serializer_class = ApprenantCrudSerializer
    permission_classes = [IsStaffOrReadOnly]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return Apprenant.objects.all()

        role_name = _role_name(user)
        inst = _user_institution(user)

        if role_name in ["Admin", "Responsable"]:
            if inst:
                return Apprenant.objects.filter(institution=inst)
            return Apprenant.objects.none()

        if role_name == "Formateur":
            from courses.models import InscriptionCours, Cours

            # ⚠️ si inst est None, renvoyer none (évite erreurs)
            if not inst:
                return Apprenant.objects.none()

            mes_cours = Cours.objects.filter(
                enseignant=user,
                institution=inst
            ).values_list("id", flat=True)

            apprenants_ids = InscriptionCours.objects.filter(
                cours_id__in=mes_cours
            ).values_list("apprenant_id", flat=True).distinct()

            return Apprenant.objects.filter(id__in=apprenants_ids)

        return Apprenant.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)

        if not user.is_superuser and inst:
            serializer.save(institution=inst)
        else:
            serializer.save()


class FormateurViewSet(BaseModelViewSet):
    queryset = Formateur.objects.all()
    serializer_class = FormateurCrudSerializer
    permission_classes = [IsAdminOrHigherOrSelf]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return Formateur.objects.all()

        inst = _user_institution(user)
        role_name = _role_name(user)

        # ✅ Admin / Responsable / Formateur : limité à leur institution
        if role_name in ['Admin', 'Responsable', 'Formateur']:
            if inst:
                return Formateur.objects.filter(institution=inst)
            return Formateur.objects.none()

        # ✅ Apprenant (et autres rôles authentifiés) :
        # Lecture seule autorisée → on expose les formateurs de leur institution
        # pour permettre l'affichage de la fiche enseignant dans les cours.
        if inst:
            return Formateur.objects.filter(institution=inst)

        # Aucune institution → aucun résultat
        return Formateur.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)

        if not user.is_superuser and inst:
            kwargs = {"institution": inst}
            annee = _user_annee_active(user)
            if annee:
                kwargs["annee_scolaire_active"] = annee
            serializer.save(**kwargs)
        else:
            serializer.save()

class ResponsableAcademiqueViewSet(BaseModelViewSet):
    queryset = ResponsableAcademique.objects.all()
    serializer_class = ResponsableAcademiqueCrudSerializer
    permission_classes = [IsAdminOrHigher]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return ResponsableAcademique.objects.all()

        inst = _user_institution(user)
        if inst:
            return ResponsableAcademique.objects.filter(institution=inst)

        return ResponsableAcademique.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)

        if not user.is_superuser and inst:
            kwargs = {"institution": inst}
            annee = _user_annee_active(user)
            if annee:
                kwargs["annee_scolaire_active"] = annee
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

class ChangePasswordAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = ModifierMotDePasseSerializer(
            data=request.data,
            context={'request': request}
        )
        if not serializer.is_valid():
            return api_error(
                message="Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return api_success(
            "Mot de passe modifié avec succès. Veuillez vous reconnecter.",
            data=None,
            http_status=status.HTTP_200_OK,
        )