# users/serializers.py

import secrets
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authtoken.models import Token

from django.core.mail import send_mail
from core.mailer import safe_send_mail
from django.conf import settings
from academics.models import AnneeScolaire, Groupe, Institution, Specialite, Departement, Classe, Inscription
# ❌ NE PAS importer les serializers d'academics ici (import circulaire)
# Les imports se feront dans les méthodes via _get_academic_serializers()

from locations.models import Pays
from locations.serializers import PaysSerializer

from .models import (
    User,
    UserRole,
    Admin,
    Parent,
    Apprenant,
    Formateur,
    ResponsableAcademique,
    SuperAdmin,
    VerificationCode,
)
from .security import validate_password_strength


# =============================================================================
# Helpers
# =============================================================================



def _envoyer_code_activation(user):
    """Génère un code d'activation et l'envoie par e-mail (best-effort).

    Utilisé par les créations de comptes côté admin : sans code, un compte
    créé inactif n'était activable par AUCUN écran.
    """
    try:
        from users.models import VerificationCode
        from core.mailer import safe_send_mail
        from django.conf import settings
        v = VerificationCode.create_activation_code(user)
        safe_send_mail(
            subject="Somapro - Code d'activation de votre compte",
            message=(
                f"Bonjour,\n\nVotre compte a été créé.\n"
                f"Code d'activation : {v.code} (valide 15 minutes).\n\n"
                f"Utilisez la page « Confirmer mon e-mail » pour activer votre compte."
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[user.email],
        )
    except Exception:
        pass


def _get_or_create_role(role_name: str) -> UserRole:
    """Récupère ou crée un rôle utilisateur"""
    role, _ = UserRole.objects.get_or_create(name=role_name)
    return role


def _normalize_or_generate_matricule(validated):
    """Normalise ou génère un matricule unique pour un apprenant"""
    matricule = validated.pop("matricule", None)
    if matricule is not None:
        matricule = matricule.strip()
        if matricule == "":
            matricule = None

    if matricule is None:
        year = timezone.now().strftime("%y")
        for _ in range(10):
            candidate = f"APP-{year}{1000 + secrets.randbelow(9000)}"
            if not Apprenant.objects.filter(matricule=candidate).exists():
                return candidate
        return f"APP-{year}{10000 + secrets.randbelow(90000)}"

    return matricule


def _get_academic_serializers():
    """
    Import lazy des serializers d'academics pour éviter l'import circulaire.
    """
    from academics.serializers import (
        InstitutionSerializer,
        GroupeSerializer,
        SpecialiteSerializer,
        DepartementSerializer,
        ClasseSerializer,
    )
    return {
        'InstitutionSerializer': InstitutionSerializer,
        'GroupeSerializer': GroupeSerializer,
        'SpecialiteSerializer': SpecialiteSerializer,
        'DepartementSerializer': DepartementSerializer,
        'ClasseSerializer': ClasseSerializer,
    }


# =============================================================================
# AUTH / ONBOARDING
# =============================================================================

class RegisterSerializer(serializers.Serializer):
    # ✅ SÉCURITÉ : l'inscription publique ne doit JAMAIS permettre de choisir un
    # rôle privilégié (Admin, ResponsableAcademique, SuperAdmin) — cela
    # permettait une escalade de privilèges. Les comptes Admin sont créés via
    # l'onboarding institution (InstitutionSerializer) ou par un admin existant.
    role = serializers.ChoiceField(choices=[
        ("Parent", "Parent"),
        ("Apprenant", "Apprenant"),
        ("Formateur", "Formateur"),
    ])
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    nom      = serializers.CharField(max_length=30)
    prenom   = serializers.CharField(max_length=30)
    telephone = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True)

    pays_residence = serializers.PrimaryKeyRelatedField(
        queryset=Pays.objects.all(), required=False, allow_null=True,
    )

    # Admin / Parent / Responsable
    institution = serializers.PrimaryKeyRelatedField(
        queryset=Institution.objects.all(), required=False, allow_null=True,
    )
    date_entree = serializers.DateField(required=False)

    # Apprenant
    matricule      = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    date_naissance = serializers.DateField(required=False, allow_null=True)
    tuteur = serializers.PrimaryKeyRelatedField(queryset=Parent.objects.all(), required=False, allow_null=True)

    # Inscription
    inscription_annee_scolaire = serializers.PrimaryKeyRelatedField(
        queryset=AnneeScolaire.objects.all(), required=False, allow_null=True,
    )
    inscription_classe = serializers.PrimaryKeyRelatedField(
        queryset=Classe.objects.all(), required=False, allow_null=True,
    )

    # Formateur
    institutions = serializers.PrimaryKeyRelatedField(queryset=Institution.objects.all(), many=True, required=False)
    specialites  = serializers.PrimaryKeyRelatedField(queryset=Specialite.objects.all(), many=True, required=False)
    groupes      = serializers.PrimaryKeyRelatedField(queryset=Groupe.objects.all(), many=True, required=False)

    # ResponsableAcademique
    departement = serializers.PrimaryKeyRelatedField(queryset=Departement.objects.all(), required=False, allow_null=True)

    def validate_email(self, value):
        if get_user_model().objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate_password(self, value):
        # ✅ SÉCURITÉ : applique les validateurs Django (longueur, mot de passe
        # commun, entièrement numérique, similarité avec l'utilisateur).
        return validate_password_strength(value)

    def _attach_role_fk(self, user, role_name: str):
        user.role = _get_or_create_role(role_name)
        user.save(update_fields=["role"])

    @transaction.atomic
    def create(self, validated):
        role = validated.pop("role")

        common = {
            "email":          validated.pop("email"),
            "nom":            validated.pop("nom"),
            "prenom":         validated.pop("prenom"),
            "telephone":      validated.pop("telephone", None),
            "pays_residence": validated.pop("pays_residence", None),
        }
        password = validated.pop("password")

        from core.tenant import default_institution, default_annee_scolaire
        inst = default_institution()
        annee = default_annee_scolaire()
        validated.pop("institution", None)

        if role == "Admin":
            user = Admin(**common, institution=inst)
        elif role == "Parent":
            user = Parent(**common, institution=inst)
        elif role == "Apprenant":
            matricule = _normalize_or_generate_matricule(validated)
            user = Apprenant(
                **common,
                matricule=matricule,
                date_naissance=validated.pop("date_naissance", None),
                tuteur=validated.pop("tuteur", None),
            )
        elif role == "Formateur":
            user = Formateur(**common)
        elif role == "ResponsableAcademique":
            user = ResponsableAcademique(
                **common,
                institution=inst,
                departement=validated.pop("departement", None),
            )
        elif role == "SuperAdmin":
            user = SuperAdmin(**common)
        else:
            raise serializers.ValidationError({"role": "Rôle non supporté."})

        # ✅ MONO-ÉTABLISSEMENT : rattachement forcé
        if inst:
            user.institution = inst
        if annee:
            user.annee_scolaire_active = annee

        # ✅ set_password() TOUJOURS appelé ici
        user.set_password(password)
        user.is_active = False
        user.save()

        if isinstance(user, Formateur):
            validated.pop("institutions", None)
            user.institutions.set([inst] if inst else [])
            user.specialites.set(validated.pop("specialites", []))
            user.groupes.set(validated.pop("groupes", []))

        if isinstance(user, Apprenant):
            annee_scolaire = validated.pop("inscription_annee_scolaire", None)
            classe = validated.pop("inscription_classe", None)
            if classe and inst and getattr(classe, "institution_id", None) != inst.id:
                raise serializers.ValidationError(
                    {"inscription_classe": "La classe doit appartenir à l'établissement."}
                )
            if annee_scolaire and inst and getattr(annee_scolaire, "institution_id", None) != inst.id:
                raise serializers.ValidationError(
                    {"inscription_annee_scolaire": "L'année doit appartenir à l'établissement."}
                )
            if annee_scolaire or classe:
                Inscription.objects.create(
                    apprenant=user,
                    institution=inst,
                    annee_scolaire=annee or annee_scolaire,
                    classe=classe,
                    statut="actif",
                    statut_paiement="en_attente",
                )

        self._attach_role_fk(user, role)

        v = VerificationCode.create_activation_code(user)
        safe_send_mail(
            subject="Somapro - Code d'activation",
            message=f"Votre code d'activation est : {v.code} (valide 15 minutes).",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=None,
        )

        return {"message": "Compte créé. Un code d'activation à 6 chiffres a été envoyé par email."}


class UserLoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email    = attrs.get("email")
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()
        if user is None or not user.check_password(password):
            raise AuthenticationFailed("Identifiants invalides.")

        if not user.is_active:
            raise AuthenticationFailed("Votre compte n'est pas actif ou est bloqué.")

        # ✅ SESSION STABLE — on RÉUTILISE le token existant.
        #    DRF n'autorise qu'un seul token par utilisateur (OneToOne) :
        #    le recréer à chaque connexion déconnectait instantanément les
        #    autres onglets / appareils et toute session en cours.
        token, _ = Token.objects.get_or_create(user=user)
        attrs["user"]  = user
        attrs["token"] = token.key
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code  = serializers.CharField(min_length=6, max_length=6)

    def validate(self, data):
        user = get_user_model().objects.filter(email=data["email"]).first()
        if not user:
            raise serializers.ValidationError({"email": "Utilisateur introuvable."})

        vc = (
            user.verification_codes
            .filter(code=data["code"], purpose="activation", is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not vc or not vc.is_valid():
            raise serializers.ValidationError({"code": "Code invalide ou expiré."})

        data["user"] = user
        data["vc"]   = vc
        return data

    def create(self, validated):
        user = validated["user"]
        vc   = validated["vc"]
        vc.is_used = True
        vc.save(update_fields=["is_used"])
        user.is_active = True
        user.save(update_fields=["is_active"])
        return {"message": "Email vérifié. Votre compte est maintenant actif."}


class ResendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def create(self, validated):
        user = get_user_model().objects.filter(email=validated["email"]).first()
        if not user:
            raise serializers.ValidationError({"email": "Utilisateur introuvable."})
        if user.is_active:
            return {"message": "Ce compte est déjà actif."}

        v = VerificationCode.create_activation_code(user)
        safe_send_mail(
            subject="Somapro - Nouveau code d'activation",
            message=f"Votre nouveau code d'activation est : {v.code} (valide 15 minutes).",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=None,
        )
        return {"message": "Nouveau code envoyé par email."}


# =============================================================================
# Mini serializers
# =============================================================================

class ApprenantMiniSerializer(serializers.ModelSerializer):
    pays_residence = PaysSerializer(read_only=True)

    class Meta:
        model  = Apprenant
        fields = ["id", "email", "nom", "prenom", "matricule", "pays_residence"]


class FormateurMiniSerializer(serializers.ModelSerializer):
    pays_residence = PaysSerializer(read_only=True)

    class Meta:
        model  = Formateur
        fields = ["id", "email", "nom", "prenom", "pays_residence"]


# =============================================================================
# Serializers légers (courses / evaluations)
# =============================================================================

class ApprenantSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Apprenant
        fields = ['id', 'email', 'nom', 'prenom', 'matricule']


class FormateurSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Formateur
        fields = ['id', 'email', 'nom', 'prenom']


# =============================================================================
# CRUD Serializers
# =============================================================================

class BaseUserCrudSerializer(serializers.ModelSerializer):
    # ✅ write_only=True : DRF exclut ce champ de la sortie
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=8
    )

    pays_residence = serializers.SerializerMethodField(read_only=True)
    pays_residence_id = serializers.PrimaryKeyRelatedField(
        source="pays_residence",
        queryset=Pays.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    annee_scolaire_active = serializers.SerializerMethodField(read_only=True)
    annee_scolaire_active_id = serializers.PrimaryKeyRelatedField(
        source="annee_scolaire_active",
        queryset=AnneeScolaire.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    role              = serializers.SerializerMethodField(read_only=True)
    date_joined       = serializers.DateTimeField(read_only=True)
    date_modification = serializers.DateTimeField(read_only=True)
    photo             = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = User
        fields = [
            "id",
            "email", "nom", "prenom", "telephone",
            "photo",
            "role",
            "permissions",
            "pays_residence",         "pays_residence_id",
            "annee_scolaire_active",  "annee_scolaire_active_id",
            "is_active", "is_staff", "is_superuser",
            "date_joined", "date_modification",
            "password",
        ]
        read_only_fields = [
            "id", "photo", "role", "permissions",
            "pays_residence", "annee_scolaire_active",
            "date_joined", "date_modification",
            "is_staff", "is_superuser",
        ]

    # ✅ FIX PRINCIPAL : le mot de passe ne peut JAMAIS apparaître dans la réponse JSON
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop('password', None)
        return data

    def get_role(self, obj):
        return getattr(obj.role, 'name', None) if obj.role else None

    def get_pays_residence(self, obj):
        pays = obj.pays_residence
        if not pays:
            return None
        return {"id": pays.id, "nom": pays.nom, "code": getattr(pays, "code", None)}

    def get_annee_scolaire_active(self, obj):
        a = obj.annee_scolaire_active
        if not a:
            return None
        return {"id": a.id, "libelle": getattr(a, 'libelle', str(a))}

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.photo.url)
        return obj.photo.url

    def _apply_password(self, instance, validated_data):
        """Pop et applique le mot de passe s'il est fourni."""
        password = validated_data.pop("password", None)
        if password:
            # ✅ SÉCURITÉ : refuse les mots de passe faibles (validateurs Django).
            validate_password_strength(password)
            instance.set_password(password)
        return instance


# =============================================================================
# Admin
# =============================================================================

class AdminCrudSerializer(BaseUserCrudSerializer):
    institution = serializers.SerializerMethodField(read_only=True)
    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model  = Admin
        fields = BaseUserCrudSerializer.Meta.fields + ["institution", "institution_id", "date_entree"]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["institution"]

    def get_institution(self, obj):
        if not obj.institution:
            return None
        return _get_academic_serializers()['InstitutionSerializer'](obj.institution).data

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        admin    = Admin(**validated_data)
        # ✅ Hachage garanti
        if password:
            validate_password_strength(password)
            admin.set_password(password)
        else:
            admin.set_unusable_password()
        admin.role     = _get_or_create_role("Admin")
        admin.is_staff = True
        admin.save()
        _envoyer_code_activation(admin)
        return admin

    @transaction.atomic
    def update(self, instance, validated_data):
        self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role     = _get_or_create_role("Admin")
        instance.is_staff = True
        instance.save()
        return instance


# =============================================================================
# Parent
# =============================================================================

class ParentCrudSerializer(BaseUserCrudSerializer):
    institution = serializers.SerializerMethodField(read_only=True)
    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    enfants = serializers.SerializerMethodField(read_only=True)

    class Meta(BaseUserCrudSerializer.Meta):
        model  = Parent
        fields = BaseUserCrudSerializer.Meta.fields + ["institution", "institution_id", "enfants"]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["institution", "enfants"]

    def get_institution(self, obj):
        if not obj.institution:
            return None
        return _get_academic_serializers()['InstitutionSerializer'](obj.institution).data

    def get_enfants(self, obj):
        enfants = Apprenant.objects.filter(tuteur=obj).select_related('annee_scolaire_active', 'groupe')
        result  = []
        for a in enfants:
            annee = a.annee_scolaire_active
            result.append({
                "id":        a.id,
                "prenom":    a.prenom,
                "nom":       a.nom,
                "matricule": a.matricule,
                "annee_scolaire_active": {
                    "id":      annee.id,
                    "libelle": getattr(annee, 'libelle', str(annee)),
                } if annee else None,
            })
        return result

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        parent   = Parent(**validated_data)
        if password:
            validate_password_strength(password)
            parent.set_password(password)
        else:
            parent.set_unusable_password()
        parent.role = _get_or_create_role("Parent")
        parent.save()
        _envoyer_code_activation(parent)
        return parent

    @transaction.atomic
    def update(self, instance, validated_data):
        self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role = _get_or_create_role("Parent")
        instance.save()
        return instance


# =============================================================================
# Apprenant  ← ✅ FIX MAJEUR : create() et update() ajoutés
# =============================================================================

class ApprenantCrudSerializer(BaseUserCrudSerializer):
    matricule      = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    date_naissance = serializers.DateField(required=False, allow_null=True)

    groupe    = serializers.SerializerMethodField(read_only=True)
    groupe_id = serializers.PrimaryKeyRelatedField(
        source="groupe", queryset=Groupe.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    tuteur = serializers.SerializerMethodField(read_only=True)
    institution = serializers.SerializerMethodField(read_only=True)

    def get_groupe(self, obj):
        g = getattr(obj, "groupe", None)
        if not g:
            return None
        return {
            "id": g.id, "nom": g.nom,
            "classe_id": g.classe_id,
            "classe_nom": getattr(g.classe, "nom", None),
        }

    inscription_annee_scolaire = serializers.PrimaryKeyRelatedField(
        queryset=AnneeScolaire.objects.all(), required=False, allow_null=True,
    )
    inscription_classe = serializers.PrimaryKeyRelatedField(
        queryset=Classe.objects.all(), required=False, allow_null=True,
    )

    tuteur_id = serializers.PrimaryKeyRelatedField(
        source="tuteur",
        queryset=Parent.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model  = Apprenant
        fields = BaseUserCrudSerializer.Meta.fields + [
            "matricule", "date_naissance",
            "tuteur",    "tuteur_id",
            "institution",
            "groupe",    "groupe_id",
            "inscription_annee_scolaire",
            "inscription_classe",
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + [
            "tuteur", "institution",
        ]

    def get_institution(self, obj):
        inst = getattr(obj, 'institution', None)
        if not inst:
            return None
        return {"id": inst.id, "nom": inst.nom}

    def get_tuteur(self, obj):
        t = getattr(obj, 'tuteur', None)
        if not t:
            return None
        return {
            "id":             t.id,
            "email":          t.email,
            "nom":            t.nom,
            "prenom":         t.prenom,
            "telephone":      t.telephone,
            "pays_residence": PaysSerializer(t.pays_residence).data if t.pays_residence else None,
        }

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)

        matricule = _normalize_or_generate_matricule(validated_data)
        validated_data["matricule"] = matricule

        annee_scolaire = validated_data.pop("inscription_annee_scolaire", None)
        classe = validated_data.pop("inscription_classe", None)

        apprenant = Apprenant(**validated_data)

        if password:
            validate_password_strength(password)
            apprenant.set_password(password)
        else:
            apprenant.set_unusable_password()

        apprenant.role = _get_or_create_role("Apprenant")
        apprenant.save()
        _envoyer_code_activation(apprenant)

        if annee_scolaire or classe:
            institution = getattr(apprenant, "institution", None)
            if not institution and annee_scolaire:
                institution = getattr(annee_scolaire, "institution", None)
            if not institution and classe:
                institution = getattr(classe, "institution", None)
            Inscription.objects.create(
                apprenant=apprenant,
                institution=institution,
                annee_scolaire=annee_scolaire,
                classe=classe,
                statut="actif",
                statut_paiement="en_attente",
            )

        return apprenant

    @transaction.atomic
    def update(self, instance, validated_data):
        self._apply_password(instance, validated_data)

        annee_scolaire = validated_data.pop("inscription_annee_scolaire", None)
        classe = validated_data.pop("inscription_classe", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)

        instance.role = _get_or_create_role("Apprenant")
        instance.save()

        if annee_scolaire or classe:
            institution = getattr(instance, "institution", None)
            if not institution and annee_scolaire:
                institution = getattr(annee_scolaire, "institution", None)
            if not institution and classe:
                institution = getattr(classe, "institution", None)
            Inscription.objects.create(
                apprenant=instance,
                institution=institution,
                annee_scolaire=annee_scolaire,
                classe=classe,
                statut="actif",
                statut_paiement="en_attente",
            )

        return instance


# =============================================================================
# Formateur
# =============================================================================

class FormateurCrudSerializer(BaseUserCrudSerializer):
    institutions = serializers.SerializerMethodField(read_only=True)
    specialites  = serializers.SerializerMethodField(read_only=True)
    groupes      = serializers.SerializerMethodField(read_only=True)

    institution_ids = serializers.PrimaryKeyRelatedField(
        source="institutions",
        queryset=Institution.objects.all(),
        many=True, write_only=True, required=False,
    )
    specialite_ids = serializers.PrimaryKeyRelatedField(
        source="specialites",
        queryset=Specialite.objects.all(),
        many=True, write_only=True, required=False,
    )
    groupe_ids = serializers.PrimaryKeyRelatedField(
        source="groupes",
        queryset=Groupe.objects.all(),
        many=True, write_only=True, required=False,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model  = Formateur
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institutions",  "institution_ids",
            "specialites",   "specialite_ids",
            "groupes",       "groupe_ids",
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + [
            "institutions", "specialites", "groupes",
        ]

    def get_institutions(self, obj):
        return _get_academic_serializers()['InstitutionSerializer'](obj.institutions.all(), many=True).data

    def get_specialites(self, obj):
        return _get_academic_serializers()['SpecialiteSerializer'](obj.specialites.all(), many=True).data

    def get_groupes(self, obj):
        return _get_academic_serializers()['GroupeSerializer'](obj.groupes.all(), many=True).data

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        # ✅ M2M poppés AVANT la construction (ne peuvent pas être passés au constructeur)
        institutions = validated_data.pop("institutions", [])
        specialites  = validated_data.pop("specialites", [])
        groupes      = validated_data.pop("groupes", [])

        formateur = Formateur(**validated_data)
        if password:
            validate_password_strength(password)
            formateur.set_password(password)
        else:
            formateur.set_unusable_password()
        formateur.role = _get_or_create_role("Formateur")
        formateur.save()
        _envoyer_code_activation(formateur)

        # ✅ M2M assignés après le save()
        formateur.institutions.set(institutions)
        formateur.specialites.set(specialites)
        formateur.groupes.set(groupes)
        return formateur

    @transaction.atomic
    def update(self, instance, validated_data):
        self._apply_password(instance, validated_data)

        institutions = validated_data.pop("institutions", None)
        specialites  = validated_data.pop("specialites", None)
        groupes      = validated_data.pop("groupes", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)

        instance.role = _get_or_create_role("Formateur")
        instance.save()

        if institutions is not None:
            instance.institutions.set(institutions)
        if specialites is not None:
            instance.specialites.set(specialites)
        if groupes is not None:
            instance.groupes.set(groupes)

        return instance


# =============================================================================
# ResponsableAcademique  ← ✅ FIX : create() et update() remis ici (étaient
#                          perdus dans le doublon ModifierMotDePasseSerializer)
# =============================================================================

class ResponsableAcademiqueCrudSerializer(BaseUserCrudSerializer):
    institution         = serializers.SerializerMethodField(read_only=True)
    departement         = serializers.SerializerMethodField(read_only=True)
    departement_id_flat = serializers.SerializerMethodField(read_only=True)
    institution_id_flat = serializers.SerializerMethodField(read_only=True)

    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    departement_id = serializers.PrimaryKeyRelatedField(
        source="departement",
        queryset=Departement.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model  = ResponsableAcademique
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institution",        "institution_id",
            "departement",        "departement_id",
            "departement_id_flat",
            "institution_id_flat",
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + [
            "institution", "departement",
            "departement_id_flat", "institution_id_flat",
        ]

    def get_institution(self, obj):
        inst = obj.institution
        if not inst:
            return None
        return {"id": inst.id, "nom": inst.nom}

    def get_departement(self, obj):
        # Requête fraîche — ignore le cache ORM sur obj.departement
        fresh = ResponsableAcademique.objects.filter(pk=obj.pk).values(
            'departement_id', 'departement__nom', 'departement__description'
        ).first()
        if not fresh or not fresh['departement_id']:
            return None
        return {
            'id':          fresh['departement_id'],
            'nom':         fresh['departement__nom'],
            'description': fresh['departement__description'],
        }

    def get_departement_id_flat(self, obj):
        return ResponsableAcademique.objects.filter(
            pk=obj.pk
        ).values_list('departement_id', flat=True).first()

    def get_institution_id_flat(self, obj):
        return getattr(obj, 'institution_id', None)

    @transaction.atomic
    def create(self, validated_data):
        password    = validated_data.pop("password", None)
        responsable = ResponsableAcademique(**validated_data)
        if password:
            validate_password_strength(password)
            responsable.set_password(password)
        else:
            responsable.set_unusable_password()
        responsable.role = _get_or_create_role("ResponsableAcademique")
        responsable.save()
        _envoyer_code_activation(responsable)
        return responsable

    @transaction.atomic
    def update(self, instance, validated_data):
        self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role = _get_or_create_role("ResponsableAcademique")
        instance.save()
        return instance


# =============================================================================
# Modifier mot de passe  ← ✅ FIX : une seule définition, propre
# =============================================================================

class ModifierMotDePasseSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Le mot de passe actuel est incorrect.")
        return value

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                "confirm_password": "Les deux nouveaux mots de passe ne correspondent pas."
            })
        if data['current_password'] == data['new_password']:
            raise serializers.ValidationError({
                "new_password": "Le nouveau mot de passe doit être différent de l'actuel."
            })
        # ✅ SÉCURITÉ : validateurs Django (mot de passe commun, numérique, etc.)
        validate_password_strength(data['new_password'], self.context['request'].user)
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        # Invalider l'ancien token pour forcer une nouvelle connexion
        Token.objects.filter(user=user).delete()
        return user