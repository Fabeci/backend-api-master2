# users/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth.hashers import check_password

from users.permissions import IsAdminOrHigher
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


# =============================================================================
# Helpers réponse unifiée
# =============================================================================

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


# =============================================================================
# Helpers internes
# =============================================================================

def _user_institution(user):
    return getattr(user, "institution", None)

def _user_annee_active(user):
    return getattr(user, "annee_scolaire_active", None)

def _role_name(user):
    return getattr(getattr(user, "role", None), "name", None)


# =============================================================================
# Auth & Onboarding
# =============================================================================

class RegisterAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return api_success(
            "Compte créé. Un code d'activation a été envoyé par email.",
            data=serializer.save(),
            http_status=status.HTTP_201_CREATED,
        )


class VerifyEmailAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return api_success("Email vérifié. Compte activé avec succès.", data=serializer.save())


class ResendCodeAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return api_success("Nouveau code d'activation envoyé par email.", data=serializer.save())


class UserLoginAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user  = serializer.validated_data["user"]
        token = serializer.validated_data["token"]

        # ✅ Photo retournée dès le login avec URL absolue
        photo_url = None
        if getattr(user, "photo", None):
            try:
                photo_url = request.build_absolute_uri(user.photo.url)
            except Exception:
                photo_url = None

        return api_success(
            "Authentification réussie.",
            data={
                "token": token,
                "user": {
                    "id":                       user.id,
                    "email":                    user.email,
                    "nom":                      user.nom,
                    "prenom":                   user.prenom,
                    "telephone":                user.telephone,
                    "photo":                    photo_url,          # ✅
                    "role":                     getattr(user.role, "name", None),
                    "is_staff":                 user.is_staff,
                    "is_superuser":             user.is_superuser,
                    "institution_id":           getattr(user, "institution_id", None),
                    "annee_scolaire_active_id": getattr(user, "annee_scolaire_active_id", None),
                },
            },
            http_status=status.HTTP_200_OK,
        )


class LogoutAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return api_success("Déconnexion réussie. Le token a été invalidé.")


# =============================================================================
# Permissions personnalisées
# =============================================================================

class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsAdminOrHigherOrSelf(permissions.BasePermission):
    """
    SuperUser / Admin / Responsable : accès total.
    Autres : uniquement leur propre objet (pk == user.pk).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        role = _role_name(request.user)
        if role in ['Admin', 'Responsable']:
            return True
        pk = view.kwargs.get('pk')
        if pk is not None and str(pk) == str(request.user.pk):
            return True
        return False


# =============================================================================
# Mixin partagé : upload_photo + change_password
# =============================================================================

# ─── Mixin partagé : upload_photo + change_password ──────────────────────────

class ProfileActionsMixin:

    def _check_self_or_admin(self, request, pk):
        user = request.user
        if user.is_superuser:
            return
        if _role_name(user) in ['Admin', 'Responsable']:
            return
        if str(pk) != str(user.pk):
            raise PermissionDenied("Vous ne pouvez modifier que votre propre profil.")

    @action(
        detail=True,
        methods=['patch'],
        url_path='upload-photo',
        permission_classes=[permissions.IsAuthenticated],
        # ✅ NE PAS mettre parser_classes=None — ça écrase avec None et casse get_parsers()
        # DRF utilise automatiquement MultiPartParser + JSONParser par défaut
    )
    def upload_photo(self, request, pk=None):
        self._check_self_or_admin(request, pk)

        photo = request.FILES.get('photo')
        if not photo:
            return api_error("Aucun fichier reçu. Utilisez la clé 'photo'.")
        if not photo.content_type.startswith('image/'):
            return api_error("Le fichier doit être une image.")
        if photo.size > 5 * 1024 * 1024:
            return api_error("Taille maximale : 5 Mo.")

        from .models import User as UserModel
        user_row = UserModel.objects.get(pk=pk)
        user_row.photo = photo
        user_row.save(update_fields=['photo'])

        instance = self.get_object()
        instance.refresh_from_db()
        serializer = self.get_serializer(instance, context={'request': request})
        return api_success("Photo de profil mise à jour.", data=serializer.data)

    @action(
        detail=True,
        methods=['post'],
        url_path='change-password',
        permission_classes=[permissions.IsAuthenticated],
    )
    def change_password(self, request, pk=None):
        self._check_self_or_admin(request, pk)

        old_password = request.data.get('old_password', '').strip()
        new_password = request.data.get('new_password', '').strip()

        if not old_password or not new_password:
            return api_error("Les champs 'old_password' et 'new_password' sont requis.")
        if len(new_password) < 8:
            return api_error("Le nouveau mot de passe doit contenir au moins 8 caractères.")

        instance = self.get_object()

        if not check_password(old_password, instance.password):
            return api_error("Le mot de passe actuel est incorrect.")

        instance.set_password(new_password)
        instance.save(update_fields=['password'])

        return api_success("Mot de passe modifié avec succès.")

# =============================================================================
# CRUD ViewSets
# =============================================================================

class AdminViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Admin.objects.all()
    serializer_class   = AdminCrudSerializer
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


class ParentViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Parent.objects.all()
    serializer_class   = ParentCrudSerializer
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


class ApprenantViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Apprenant.objects.all()
    serializer_class   = ApprenantCrudSerializer
    permission_classes = [IsStaffOrReadOnly]

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)

        if user.is_superuser:
            return Apprenant.objects.all()

        if role_name in ["Admin", "Responsable"]:
            return Apprenant.objects.filter(institution=inst) if inst else Apprenant.objects.none()

        if role_name == "Formateur":
            if not inst:
                return Apprenant.objects.none()
            from courses.models import InscriptionCours, Cours
            cours_ids = Cours.objects.filter(
                enseignant=user, institution=inst
            ).values_list("id", flat=True)
            apprenant_ids = InscriptionCours.objects.filter(
                cours_id__in=cours_ids
            ).values_list("apprenant_id", flat=True).distinct()
            return Apprenant.objects.filter(id__in=apprenant_ids)

        # ✅ Un apprenant peut voir et modifier son propre profil
        if role_name == "Apprenant":
            return Apprenant.objects.filter(pk=user.pk)

        return Apprenant.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)
        if not user.is_superuser and inst:
            serializer.save(institution=inst)
        else:
            serializer.save()


class FormateurViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Formateur.objects.all()
    serializer_class   = FormateurCrudSerializer
    permission_classes = [IsAdminOrHigherOrSelf]

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)

        if user.is_superuser:
            return Formateur.objects.all()

        if role_name in ["Admin", "Responsable"]:
            return Formateur.objects.filter(institution=inst) if inst else Formateur.objects.none()

        # ✅ Un formateur peut voir et modifier son propre profil
        if role_name == "Formateur":
            return Formateur.objects.filter(pk=user.pk)

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


class ResponsableAcademiqueViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = ResponsableAcademique.objects.all()
    serializer_class   = ResponsableAcademiqueCrudSerializer
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
            kwargs = {'institution': inst}
            annee = _user_annee_active(user)
            if annee:
                kwargs['annee_scolaire_active'] = annee
            serializer.save(**kwargs)
        else:
            serializer.save()