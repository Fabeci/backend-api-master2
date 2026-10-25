# users/views.py
import logging
from django.contrib.auth.tokens import default_token_generator
from django.db.models import Q
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
from rest_framework.throttling import AnonRateThrottle
from django.contrib.auth.hashers import check_password

logger = logging.getLogger(__name__)


class LoginRateThrottle(AnonRateThrottle):
    """5 tentatives par minute par IP sur le login."""
    scope = 'login'

from users.permissions import IsAdminOrHigher
from users.utils import BaseModelViewSet
from core.rbac import RBACPermission

from courses.models import InscriptionCours, Cours
from users.models import Formateur as FormateurModel

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
from .security import validate_password_strength


# =============================================================================
# Helpers réponse unifiée
# =============================================================================

def api_success(message: str, data=None, http_status=status.HTTP_200_OK):
    return Response(
        {"success": True, "status": http_status, "message": message, "data": data},
        status=http_status,
    )

def api_error(message: str, errors=None, http_status=status.HTTP_400_BAD_REQUEST):
    # Message plus précis quand des erreurs de champ sont fournies
    if errors and isinstance(errors, dict) and (not message or message == "Erreur de validation"):
        for _field, _val in errors.items():
            _msgs = _val if isinstance(_val, (list, tuple)) else [_val]
            _first = next((str(m) for m in _msgs if m), None)
            if _first:
                message = f"{_field} : {_first}"
                break
    payload = {"success": False, "status": http_status, "message": message}
    _code_map = {
        400: "VALIDATION_ERROR", 401: "NOT_AUTHENTICATED", 403: "PERMISSION_DENIED",
        404: "NOT_FOUND", 409: "CONFLICT", 429: "THROTTLED",
    }
    payload["code"] = _code_map.get(http_status, "SERVER_ERROR" if http_status >= 500 else "ERROR")
    if errors is not None:
        payload["errors"] = errors
    return Response(payload, status=http_status)


# =============================================================================
# Helpers internes
# =============================================================================

def _user_institution(user):
    """MONO-ÉTABLISSEMENT : toujours l'institution de référence."""
    from core.tenant import default_institution
    return default_institution()

def _user_annee_active(user):
    """Année active de l'utilisateur si elle appartient à l'institution de
    référence, sinon l'année courante de cette institution."""
    from core.tenant import default_institution_id, default_annee_scolaire
    annee = getattr(user, "annee_scolaire_active", None)
    if annee and getattr(annee, "institution_id", None) == default_institution_id():
        return annee
    return default_annee_scolaire()

def _role_name(user):
    return getattr(getattr(user, "role", None), "name", None)

def _get_responsable_context(user):
    """Recharge département et institution depuis la BD pour éviter le cache ORM."""
    from users.models import ResponsableAcademique as RA
    fresh = RA.objects.filter(pk=user.pk).values('departement_id', 'institution_id').first()
    if fresh:
        return fresh['departement_id'], fresh['institution_id']
    return getattr(user, 'departement_id', None), getattr(user, 'institution_id', None)

# =============================================================================
# Auth & Onboarding
# =============================================================================

class RegisterAPIView(APIView):
    # ✅ Création PUBLIQUE retirée : réservée aux profils habilités
    #    (SuperAdmin/Admin). L'auto-inscription anonyme n'est plus possible.
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        role = getattr(request.user, "role", None)
        role_name = role.name if role else None
        if not (getattr(request.user, "is_superuser", False) or role_name in ("SuperAdmin", "Admin")):
            return api_error(
                "Création de compte réservée à l'administration.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

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
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        from django.core.cache import cache
        from parametres.services import securite_tentatives_login_max

        # ✅ Verrouillage après N tentatives échouées (Paramètres → Sécurité).
        email = str(request.data.get("email") or "").strip().lower()
        maxi  = securite_tentatives_login_max()
        cle   = f"login_fail:{email}" if email else f"login_fail_ip:{request.META.get('REMOTE_ADDR', '')}"
        if maxi and cache.get(cle, 0) >= maxi:
            return api_error(
                "Trop de tentatives échouées. Réessayez dans quelques minutes.",
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = UserLoginSerializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            cache.set(cle, cache.get(cle, 0) + 1, 900)  # fenêtre de 15 min
            raise
        cache.delete(cle)

        user  = serializer.validated_data["user"]
        token = serializer.validated_data["token"]

        # Déclenche le signal user_logged_in pour la gamification et les analytics
        from django.contrib.auth.signals import user_logged_in
        user_logged_in.send(sender=user.__class__, request=request, user=user)

        # ✅ Photo retournée dès le login avec URL absolue
        photo_url = None
        if getattr(user, "photo", None):
            try:
                photo_url = request.build_absolute_uri(user.photo.url)
            except Exception:
                photo_url = None

        # Récupérer institution complète
        institution = getattr(user, "institution", None)
        departement = getattr(user, "departement", None)
        pays = getattr(user, "pays_residence", None)
        annee = getattr(user, "annee_scolaire_active", None)

        # ✅ Parent : nombre d'enfants (permet au front de masquer cours/évaluations si aucun)
        nombre_enfants = None
        if getattr(getattr(user, "role", None), "name", "") == "Parent":
            from .models import Apprenant
            nombre_enfants = Apprenant.objects.filter(tuteur_id=user.id).count()

        # ✅ Durée de session (inactivité) pilotée par Paramètres → Sécurité
        #    (établissement > global). Le front l'utilise pour son minuteur.
        from parametres.services import securite_session_expiration_h
        session_expiration_minutes = securite_session_expiration_h(institution) * 60

        return api_success(
            "Authentification réussie.",
            data={
                "token": token,
                "session_expiration_minutes": session_expiration_minutes,
                "user": {
                    "id":                       user.id,
                    "email":                    user.email,
                    "nom":                      user.nom,
                    "prenom":                   user.prenom,
                    "telephone":                user.telephone,
                    "photo":                    photo_url,          # ✅
                    "role":                     getattr(user.role, "name", None),
                    "permissions":              list(getattr(user, "permissions", []) or []),
                    "is_staff":                 user.is_staff,
                    "is_superuser":             user.is_superuser,
                    "nombre_enfants":           nombre_enfants,
                    "institution_id":           getattr(user, "institution_id", None),
                    "institution":              {"id": institution.id, "nom": institution.nom} if institution else None,
                    "annee_scolaire_active_id": getattr(user, "annee_scolaire_active_id", None),
                    "annee_scolaire_active":    {"id": annee.id, "libelle": str(annee)} if annee else None,
                    "pays_residence":           {"id": pays.id, "nom": pays.nom, "code": pays.code} if pays else None,
                    "departement_id":           getattr(user, "departement_id", None),
                    "departement":              {"id": departement.id, "nom": departement.nom} if departement else None,
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
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        role_name = request.user.role.name if request.user.role else None
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique', 'Responsable Académique', 'Responsable académique']:
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
        # ✅ SÉCURITÉ : extension contrôlée + vérification du contenu réel.
        allowed_ext = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        if not (photo.name or '').lower().endswith(allowed_ext):
            return api_error("Format d'image non autorisé (jpg, png, gif, webp).")
        if photo.size > 5 * 1024 * 1024:
            return api_error("Taille maximale : 5 Mo.")
        try:
            from PIL import Image
            Image.open(photo).verify()
            photo.seek(0)
        except Exception:
            return api_error("Fichier image invalide ou corrompu.")

        # ✅ SÉCURITÉ : passer par le queryset scopé (institution) au lieu de
        # User.objects.get(pk=pk) qui permettait d'écraser la photo d'un
        # utilisateur d'une autre institution.
        instance = self.get_object()
        instance.photo = photo
        instance.save(update_fields=['photo'])
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

        # ✅ SÉCURITÉ : validateurs Django (mot de passe commun, numérique, etc.)
        try:
            validate_password_strength(new_password, instance)
        except Exception as exc:
            return api_error("Mot de passe trop faible.", errors=getattr(exc, "detail", str(exc)))

        instance.set_password(new_password)
        instance.save(update_fields=['password'])

        return api_success("Mot de passe modifié avec succès.")

# =============================================================================
# CRUD ViewSets
# =============================================================================

class AdminViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Admin.objects.select_related('institution', 'role', 'pays_residence').all()
    serializer_class   = AdminCrudSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHigher, RBACPermission]

    def get_queryset(self):
        user = self.request.user
        qs = Admin.objects.select_related('institution', 'role', 'pays_residence')
        if user.is_superuser:
            return qs.all()
        inst = _user_institution(user)
        if inst:
            return qs.filter(institution=inst)
        return Admin.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)
        if not user.is_superuser and inst:
            serializer.save(institution=inst)
        else:
            serializer.save()


class ParentViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Parent.objects.select_related('institution', 'role', 'pays_residence').all()
    serializer_class   = ParentCrudSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHigherOrSelf, RBACPermission]

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)
        qs_base   = Parent.objects.select_related('institution', 'role', 'pays_residence')

        if user.is_superuser:
            return qs_base.all()

        if role_name == "Parent":
            return Parent.objects.filter(pk=user.pk)

        if role_name == "Admin":
            return qs_base.filter(institution=inst) if inst else Parent.objects.none()

        if role_name in ["ResponsableAcademique", "Responsable", "Responsable Académique"]:
            dept_id, inst_id = _get_responsable_context(user)

            if not inst_id:
                return Parent.objects.none()

            if dept_id:
                from academics.models import Filiere, Groupe
                filiere_ids = Filiere.objects.filter(
                    institution_id=inst_id,
                    domaine_etude__departement_id=dept_id
                ).values_list('id', flat=True)
                groupe_ids = Groupe.objects.filter(
                    institution_id=inst_id,
                    classe__filieres__id__in=filiere_ids
                ).values_list('id', flat=True)
                # Parents dont un enfant est inscrit dans ces groupes
                apprenant_ids = Apprenant.objects.filter(
                    institution_id=inst_id,
                    groupe_id__in=groupe_ids
                ).values_list('id', flat=True)
                return Parent.objects.filter(
                    pk__in=Apprenant.objects.filter(
                        id__in=apprenant_ids
                    ).values_list('tuteur_id', flat=True)
                ).distinct()

            return Parent.objects.filter(institution=inst) if inst else Parent.objects.none()

        if role_name == "Formateur":
            # ✅ Parents des apprenants de SES cours (enseignant direct ou groupe).
            cours_ids = Cours.objects.filter(
                Q(enseignant=user) | Q(groupe__enseignants=user)
            ).values_list('id', flat=True)
            appr_ids = InscriptionCours.objects.filter(
                cours_id__in=cours_ids
            ).values_list('apprenant_id', flat=True).distinct()
            return Parent.objects.filter(children__id__in=appr_ids).distinct()

        return Parent.objects.none()
class ApprenantViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Apprenant.objects.select_related('institution', 'role', 'groupe', 'tuteur', 'pays_residence', 'annee_scolaire_active').all()
    serializer_class   = ApprenantCrudSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHigherOrSelf, RBACPermission]

    _qs_base = staticmethod(lambda: Apprenant.objects.select_related(
        'institution', 'role', 'groupe', 'tuteur', 'pays_residence', 'annee_scolaire_active'
    ))

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)

        if user.is_superuser:
            return self._qs_base().all()

        if role_name == "Admin":
            return self._qs_base().filter(institution=inst) if inst else Apprenant.objects.none()

        # ✅ Responsable : son DÉPARTEMENT (repli établissement si le
        #    département n'a pas encore de structure académique liée).
        if role_name in ["ResponsableAcademique", "Responsable", "Responsable Académique"]:
            if not inst:
                return Apprenant.objects.none()
            dept_id, _ = _get_responsable_context(user)
            if dept_id:
                qs_dept = self._qs_base().filter(
                    institution=inst,
                    groupe__classe__filieres__domaine_etude__departement_id=dept_id,
                ).distinct()
                if qs_dept.exists():
                    return qs_dept
            return self._qs_base().filter(institution=inst)

        if role_name == "Formateur":

            try:
                formateur_obj = FormateurModel.objects.get(pk=user.pk)
            except FormateurModel.DoesNotExist:
                return Apprenant.objects.none()

            formateur_inst_ids = list(formateur_obj.institutions.values_list('id', flat=True))

            if not formateur_inst_ids:
                return Apprenant.objects.none()

            # ✅ Inclut les cours enseignés via un GROUPE (et pas seulement
            #    `enseignant=user`) — cohérent avec `can_manage_cours`.
            cours_ids = list(
                Cours.objects.filter(
                    Q(enseignant=user) | Q(groupe__enseignants=user),
                    institution_id__in=formateur_inst_ids,
                ).distinct().values_list("id", flat=True)
            )

            if not cours_ids:
                return Apprenant.objects.none()

            apprenant_ids = InscriptionCours.objects.filter(
                cours_id__in=cours_ids
            ).values_list("apprenant_id", flat=True).distinct()

            # ✅ Filtre supplémentaire : uniquement les apprenants de ses institutions
            return Apprenant.objects.filter(
                id__in=apprenant_ids,
                institution_id__in=formateur_inst_ids  # ← c'est ça qui manquait
            )
        if role_name == "Parent":
            return Apprenant.objects.filter(tuteur=user)

        if role_name == "Apprenant":
            groupe_id = getattr(user, 'groupe_id', None)
            if groupe_id:
                return Apprenant.objects.filter(groupe_id=groupe_id)
            return Apprenant.objects.filter(pk=user.pk)

        return Apprenant.objects.none()

    @action(detail=False, methods=['post'], url_path='affecter-groupe')
    def affecter_groupe(self, request):
        # ✅ L'affectation des apprenants aux groupes est réservée aux autres
        # profils : on refuse explicitement l'Admin d'établissement.
        role_name = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None
        if role_name == 'Admin':
            return api_error("L'affectation des groupes n'est pas autorisée pour ce profil.",
                             http_status=status.HTTP_403_FORBIDDEN)

        """Affecte un même groupe à plusieurs apprenants (le groupe pilote les cours)."""
        from academics.models import Groupe
        ids = request.data.get('apprenant_ids') or []
        if not isinstance(ids, list) or not ids:
            return api_error("Aucun apprenant sélectionné.")
        groupe = Groupe.objects.filter(pk=request.data.get('groupe_id')).first()
        if not groupe:
            return api_error("Groupe introuvable.")
        qs = self.get_queryset().filter(id__in=ids)          # scoping Admin/Responsable
        items = list(qs)
        total = len(items)
        n = 0
        for a in items:
            if a.groupe_id != groupe.id:
                a.groupe = groupe
                a.save(update_fields=['groupe'])             # déclenche la resynchro des cours
                n += 1
        already = total - n
        if total == 0:
            message = "Aucun apprenant accessible dans votre périmètre pour cette sélection."
        elif n == 0:
            message = f"Aucun changement : {total} apprenant(s) déjà dans « {groupe.nom} »."
        else:
            message = f"{n} apprenant(s) affecté(s) au groupe « {groupe.nom} »."
        return api_success(
            message,
            {'count': n, 'already': already, 'total': total, 'groupe': groupe.id, 'groupe_nom': groupe.nom},
        )

    def perform_create(self, serializer):
        user = self.request.user
        inst = _user_institution(user)
        if not user.is_superuser and inst:
            serializer.save(institution=inst)
        else:
            serializer.save()

class FormateurViewSet(ProfileActionsMixin, BaseModelViewSet):
    queryset           = Formateur.objects.select_related('role', 'pays_residence', 'annee_scolaire_active').prefetch_related('institutions', 'specialites', 'groupes').all()
    serializer_class   = FormateurCrudSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHigherOrSelf, RBACPermission]

    _qs_base = staticmethod(lambda: Formateur.objects.select_related(
        'role', 'pays_residence', 'annee_scolaire_active'
    ).prefetch_related('institutions', 'specialites', 'groupes'))

    def get_queryset(self):
        user      = self.request.user
        role_name = _role_name(user)
        inst      = _user_institution(user)

        if user.is_superuser:
            return self._qs_base().all()

        if role_name == "Formateur":
            return self._qs_base().filter(pk=user.pk)

        if role_name == "Admin":
            return self._qs_base().filter(institutions=inst) if inst else Formateur.objects.none()

        # ✅ Responsable : formateurs assignés aux groupes de son département
        if role_name in ["ResponsableAcademique", "Responsable", "Responsable Académique"]:
            from users.models import ResponsableAcademique as RA
            fresh = RA.objects.filter(pk=user.pk).values('departement_id', 'institution_id').first()
            dept_id = fresh['departement_id'] if fresh else None
            inst_id = fresh['institution_id'] if fresh else getattr(user, 'institution_id', None)

            dept_id, inst_id = _get_responsable_context(user)

            if not inst_id:
                return Formateur.objects.none()

            # ✅ Responsable : formateurs de SON DÉPARTEMENT (via leurs groupes),
            #    avec repli établissement si le département n'a pas de structure.
            if dept_id:
                qs_dept = Formateur.objects.filter(
                    institutions__id=inst_id,
                    academics_groupes__classe__filieres__domaine_etude__departement_id=dept_id,
                ).distinct()
                if qs_dept.exists():
                    return qs_dept
            return Formateur.objects.filter(institutions__id=inst_id).distinct()

        # Autres rôles authentifiés : lecture seule sur l'institution
        if inst:
            return Formateur.objects.filter(institutions=inst)

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
    queryset = ResponsableAcademique.objects.all()
    serializer_class = ResponsableAcademiqueCrudSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminOrHigherOrSelf, RBACPermission]

    def get_queryset(self):
        user = self.request.user
        role_name = _role_name(user)

        if user.is_superuser:
            return ResponsableAcademique.objects.select_related(
                'institution', 'departement', 'pays_residence', 'role'
            ).all()

        if role_name in ["Responsable", "ResponsableAcademique", "Responsable Académique"]:
            # ✅ defer() force Django à ne PAS utiliser le cache — recharge tout depuis la BD
            return ResponsableAcademique.objects.select_related(
                'institution', 'pays_residence', 'role'
            ).filter(pk=user.pk)
            # ⚠️ NE PAS mettre departement dans select_related ici
            # → le serializer fera sa propre requête fraîche

        if role_name in ["Admin", "ResponsableAcademique"]:
            inst = _user_institution(user)
            return ResponsableAcademique.objects.select_related(
                'institution', 'departement', 'pays_residence', 'role'
            ).filter(institution=inst) if inst else ResponsableAcademique.objects.none()

        return ResponsableAcademique.objects.none()
    
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

        # ✅ URL frontend : base + route RÉELLE de l'application.
        base = getattr(settings, "FRONTEND_BASE_URL", None) or settings.FRONTEND_URL
        reset_url = f"{base.rstrip('/')}/connexion/reinitialiser-mot-de-passe?token={token}&uid={uid}"

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

        # ✅ SÉCURITÉ : validateurs Django (mot de passe commun, numérique, etc.)
        try:
            validate_password_strength(new_password, user)
        except Exception as exc:
            return api_error("Mot de passe trop faible.", errors=getattr(exc, "detail", str(exc)))

        user.set_password(new_password)
        user.save(update_fields=['password'])

        # ✅ Invalider tous les tokens DRF existants
        Token.objects.filter(user=user).delete()

        return api_success("Mot de passe réinitialisé avec succès. Vous pouvez vous connecter.")
