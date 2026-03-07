# users/views.py
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import send_mail
from django.conf import settings
from .models import User
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
    permission_classes = [IsAdminOrHigherOrSelf]  # ✅ au lieu de IsAdminOrHigher

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)

        if user.is_superuser:
            return Parent.objects.all()

        # ✅ Parent peut voir/modifier son profil
        if role_name == "Parent":
            return Parent.objects.filter(pk=user.pk)

        # ✅ Admin / Responsable : parents de leur institution
        if role_name in ["Admin", "Responsable"]:
            return Parent.objects.filter(institution=inst) if inst else Parent.objects.none()

        return Parent.objects.none()

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


        # ✅ Un formateur peut voir et modifier son propre profil
        if role_name == "Formateur":
            return Formateur.objects.filter(pk=user.pk)
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


class ResponsableAcademiqueViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = ResponsableAcademique.objects.all()
    serializer_class   = ResponsableAcademiqueCrudSerializer

    # ✅ RA peut modifier son profil (self), Admin/SuperUser gardent le contrôle
    permission_classes = [IsAdminOrHigherOrSelf]   # ← au lieu de IsAdminOrHigher

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)

        if user.is_superuser:
            return ResponsableAcademique.objects.all()

        # ✅ Responsable académique : voit/modifie son propre profil
        if role_name in ["Responsable", "ResponsableAcademique", "Responsable Académique"]:
            return ResponsableAcademique.objects.filter(pk=user.pk)

        # ✅ Admin/Responsable (selon ta politique) : RA de leur institution
        # (si tu veux que Responsable puisse aussi voir tous les RA, laisse "Responsable" ici)
        if role_name in ["Admin", "Responsable"]:
            return ResponsableAcademique.objects.filter(institution=inst) if inst else ResponsableAcademique.objects.none()

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
        
class PasswordResetAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        if not email:
            return api_error("L'adresse email est requise.")

        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            # ✅ Ne pas révéler si l'email existe ou non (sécurité)
            return api_success("Si cet email existe, un lien a été envoyé.")

        uid   = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # ✅ URL frontend : adapte selon ton domaine
        reset_url = f"{settings.FRONTEND_URL}/authentication/reset-password?token={token}&uid={uid}"

        send_mail(
            subject="Réinitialisation de votre mot de passe",
            message=(
                f"Bonjour {user.prenom},\n\n"
                f"Cliquez sur le lien ci-dessous pour réinitialiser votre mot de passe :\n\n"
                f"{reset_url}\n\n"
                f"Ce lien est valide 24 heures.\n\n"
                f"Si vous n'avez pas fait cette demande, ignorez cet email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return api_success("Si cet email existe, un lien a été envoyé.")


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, uidb64=None, token=None):
        # Accepte depuis l'URL OU depuis le body (frontend envoie dans le body)
        uid_raw      = uidb64   or request.data.get('uid', '')
        token_raw    = token    or request.data.get('token', '')
        new_password = request.data.get('new_password', '').strip()

        if not uid_raw or not token_raw:
            return api_error("Lien invalide ou expiré.", http_status=status.HTTP_400_BAD_REQUEST)
        if not new_password:
            return api_error("Le nouveau mot de passe est requis.")
        if len(new_password) < 8:
            return api_error("Le mot de passe doit contenir au moins 8 caractères.")

        try:
            uid  = force_str(urlsafe_base64_decode(uid_raw))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return api_error("Lien invalide ou expiré.", http_status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token_raw):
            return api_error("Lien expiré ou déjà utilisé.", http_status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])

        # ✅ Invalider tous les tokens DRF existants
        Token.objects.filter(user=user).delete()

        return api_success("Mot de passe réinitialisé avec succès. Vous pouvez vous connecter.")