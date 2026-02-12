# users/serializers.py

import random
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authtoken.models import Token

from django.core.mail import send_mail
from django.conf import settings

from academics.models import Groupe, Institution, Specialite, Departement, Classe
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


# =============================================================================
# Helpers
# =============================================================================

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
            candidate = f"APP-{year}{random.randint(1000, 9999)}"
            if not Apprenant.objects.filter(matricule=candidate).exists():
                return candidate
        return f"APP-{year}{random.randint(10000, 99999)}"

    return matricule


def _get_academic_serializers():
    """
    Import lazy des serializers d'academics pour éviter l'import circulaire.
    Cette fonction est appelée uniquement quand nécessaire.
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
    role = serializers.ChoiceField(choices=[
        ("Admin", "Admin"),
        ("Parent", "Parent"),
        ("Apprenant", "Apprenant"),
        ("Formateur", "Formateur"),
        ("ResponsableAcademique", "ResponsableAcademique"),
        ("SuperAdmin", "SuperAdmin"),
    ])
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    nom = serializers.CharField(max_length=30)
    prenom = serializers.CharField(max_length=30)
    telephone = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True)

    pays_residence = serializers.PrimaryKeyRelatedField(
        queryset=Pays.objects.all(),
        required=False,
        allow_null=True,
    )

    # Admin / Parent / Responsable
    institution = serializers.PrimaryKeyRelatedField(
        queryset=Institution.objects.all(),
        required=False,
        allow_null=True,
    )
    date_entree = serializers.DateField(required=False)

    # Apprenant
    matricule = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    date_naissance = serializers.DateField(required=False, allow_null=True)
    groupe = serializers.PrimaryKeyRelatedField(queryset=Groupe.objects.all(), required=False, allow_null=True)
    tuteur = serializers.PrimaryKeyRelatedField(queryset=Parent.objects.all(), required=False, allow_null=True)
    classe = serializers.PrimaryKeyRelatedField(queryset=Classe.objects.all(), required=False, allow_null=True)

    # Formateur
    institutions = serializers.PrimaryKeyRelatedField(queryset=Institution.objects.all(), many=True, required=False)
    specialites = serializers.PrimaryKeyRelatedField(queryset=Specialite.objects.all(), many=True, required=False)
    groupes = serializers.PrimaryKeyRelatedField(queryset=Groupe.objects.all(), many=True, required=False)

    # ResponsableAcademique
    departement = serializers.PrimaryKeyRelatedField(queryset=Departement.objects.all(), required=False, allow_null=True)

    def validate_email(self, value):
        if get_user_model().objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def _attach_role_fk(self, user, role_name: str):
        user.role = _get_or_create_role(role_name)
        user.save(update_fields=["role"])

    @transaction.atomic
    def create(self, validated):
        role = validated.pop("role")

        common = {
            "email": validated.pop("email"),
            "nom": validated.pop("nom"),
            "prenom": validated.pop("prenom"),
            "telephone": validated.pop("telephone", None),
            "pays_residence": validated.pop("pays_residence", None),
        }
        password = validated.pop("password")

        if role == "Admin":
            user = Admin(**common, institution=validated.pop("institution", None))
        elif role == "Parent":
            user = Parent(**common, institution=validated.pop("institution", None))
        elif role == "Apprenant":
            matricule = _normalize_or_generate_matricule(validated)
            user = Apprenant(
                **common,
                matricule=matricule,
                date_naissance=validated.pop("date_naissance", None),
                groupe=validated.pop("groupe", None),
                tuteur=validated.pop("tuteur", None),
                classe=validated.pop("classe", None),
            )
        elif role == "Formateur":
            user = Formateur(**common)
        elif role == "ResponsableAcademique":
            user = ResponsableAcademique(
                **common,
                institution=validated.pop("institution", None),
                departement=validated.pop("departement", None),
            )
        elif role == "SuperAdmin":
            user = SuperAdmin(**common)
        else:
            raise serializers.ValidationError({"role": "Rôle non supporté."})

        user.set_password(password)
        user.is_active = False
        user.save()

        if isinstance(user, Formateur):
            user.institutions.set(validated.pop("institutions", []))
            user.specialites.set(validated.pop("specialites", []))
            user.groupes.set(validated.pop("groupes", []))

        self._attach_role_fk(user, role)

        v = VerificationCode.create_activation_code(user)
        send_mail(
            subject="Somapro - Code d'activation",
            message=f"Votre code d'activation est : {v.code} (valide 15 minutes).",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        return {"message": "Compte créé. Un code d'activation à 6 chiffres a été envoyé par email."}


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = User.objects.filter(email=email).first()
        if user is None or not user.check_password(password):
            raise AuthenticationFailed("Identifiants invalides.")

        if not user.is_active:
            raise AuthenticationFailed("Votre compte n'est pas actif ou est bloqué.")

        token, _ = Token.objects.get_or_create(user=user)

        attrs["user"] = user
        attrs["token"] = token.key
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=6)

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
        data["vc"] = vc
        return data

    def create(self, validated):
        user = validated["user"]
        vc = validated["vc"]
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
        send_mail(
            subject="Somapro - Nouveau code d'activation",
            message=f"Votre nouveau code d'activation est : {v.code} (valide 15 minutes).",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        return {"message": "Nouveau code envoyé par email."}


# =============================================================================
# Mini serializers (utilisés pour les références simples)
# =============================================================================

class ApprenantMiniSerializer(serializers.ModelSerializer):
    pays_residence = PaysSerializer(read_only=True)

    class Meta:
        model = Apprenant
        fields = ["id", "email", "nom", "prenom", "matricule", "pays_residence"]


class FormateurMiniSerializer(serializers.ModelSerializer):
    pays_residence = PaysSerializer(read_only=True)

    class Meta:
        model = Formateur
        fields = ["id", "email", "nom", "prenom", "pays_residence"]


# =============================================================================
# Serializers utilisés par courses/evaluations (simples, sans objets imbriqués)
# =============================================================================

class ApprenantSerializer(serializers.ModelSerializer):
    """Serializer simple pour Apprenant (utilisé par courses/evaluations)"""
    class Meta:
        model = Apprenant
        fields = ['id', 'email', 'nom', 'prenom', 'matricule']


class FormateurSerializer(serializers.ModelSerializer):
    """Serializer simple pour Formateur (utilisé par courses/evaluations)"""
    class Meta:
        model = Formateur
        fields = ['id', 'email', 'nom', 'prenom']


# =============================================================================
# CRUD Serializers - Retournent des OBJETS COMPLETS en lecture
# =============================================================================

class BaseUserCrudSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)

    # ✅ LECTURE : Objet complet
    pays_residence = PaysSerializer(read_only=True)

    # ✅ ÉCRITURE : ID uniquement
    pays_residence_id = serializers.PrimaryKeyRelatedField(
        source="pays_residence",
        queryset=Pays.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "nom",
            "prenom",
            "telephone",
            "pays_residence",       # objet complet en lecture
            "pays_residence_id",    # ID en écriture
            "is_active",
            "password",
        ]
        read_only_fields = ["id", "pays_residence"]

    def validate_email(self, value):
        qs = User.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def _apply_password(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return instance


class AdminCrudSerializer(BaseUserCrudSerializer):
    # ✅ LECTURE : Objet institution complet via SerializerMethodField
    institution = serializers.SerializerMethodField(read_only=True)
    
    # ✅ ÉCRITURE : ID uniquement
    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model = Admin
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institution",      # objet complet en lecture
            "institution_id",   # ID en écriture
            "date_entree",
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["institution"]

    def get_institution(self, obj):
        """Retourne l'objet institution complet"""
        if not obj.institution:
            return None
        serializers_dict = _get_academic_serializers()
        InstitutionSerializer = serializers_dict['InstitutionSerializer']
        return InstitutionSerializer(obj.institution).data

    @transaction.atomic
    def create(self, validated_data):
        validated_data["role"] = _get_or_create_role("Admin")
        password = validated_data.pop("password", None)

        admin = Admin(**validated_data)
        if password:
            admin.set_password(password)
        admin.is_staff = True
        admin.save()
        return admin

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role = _get_or_create_role("Admin")
        instance.is_staff = True
        instance.save()
        return instance


class ParentCrudSerializer(BaseUserCrudSerializer):
    # ✅ LECTURE : Objet institution complet
    institution = serializers.SerializerMethodField(read_only=True)
    
    # ✅ ÉCRITURE : ID uniquement
    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model = Parent
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institution",
            "institution_id",
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["institution"]

    def get_institution(self, obj):
        """Retourne l'objet institution complet"""
        if not obj.institution:
            return None
        serializers_dict = _get_academic_serializers()
        InstitutionSerializer = serializers_dict['InstitutionSerializer']
        return InstitutionSerializer(obj.institution).data

    @transaction.atomic
    def create(self, validated_data):
        validated_data["role"] = _get_or_create_role("Parent")
        password = validated_data.pop("password", None)

        parent = Parent(**validated_data)
        if password:
            parent.set_password(password)
        parent.save()
        return parent

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role = _get_or_create_role("Parent")
        instance.save()
        return instance


class ApprenantCrudSerializer(BaseUserCrudSerializer):
    matricule = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    date_naissance = serializers.DateField(required=False, allow_null=True)

    # ✅ LECTURE : Objets complets
    groupe = serializers.SerializerMethodField(read_only=True)
    tuteur = serializers.SerializerMethodField(read_only=True)

    # ✅ ÉCRITURE : IDs uniquement
    groupe_id = serializers.PrimaryKeyRelatedField(
        source="groupe",
        queryset=Groupe.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    tuteur_id = serializers.PrimaryKeyRelatedField(
        source="tuteur",
        queryset=Parent.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model = Apprenant
        fields = BaseUserCrudSerializer.Meta.fields + [
            "matricule",
            "date_naissance",
            "groupe",           # objet complet en lecture
            "groupe_id",        # ID en écriture
            "tuteur",           # objet complet en lecture
            "tuteur_id",        # ID en écriture
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["groupe", "tuteur"]

    def get_groupe(self, obj):
        """Retourne l'objet groupe complet"""
        if not hasattr(obj, 'groupe') or not obj.groupe:
            return None
        serializers_dict = _get_academic_serializers()
        GroupeSerializer = serializers_dict['GroupeSerializer']
        return GroupeSerializer(obj.groupe).data

    def get_tuteur(self, obj):
        """Retourne l'objet tuteur complet (Parent)"""
        if not hasattr(obj, 'tuteur'):
            return None
        t = obj.tuteur
        if not t:
            return None
        return {
            "id": t.id,
            "email": t.email,
            "nom": t.nom,
            "prenom": t.prenom,
            "telephone": t.telephone,
            "pays_residence": PaysSerializer(t.pays_residence).data if t.pays_residence else None,
        }

    def validate_matricule(self, value):
        if value is None:
            return None
        value = value.strip()
        return value or None

    @transaction.atomic
    def create(self, validated_data):
        validated_data["role"] = _get_or_create_role("Apprenant")
        password = validated_data.pop("password", None)

        m = validated_data.get("matricule")
        if isinstance(m, str) and m.strip() == "":
            validated_data["matricule"] = None

        apprenant = Apprenant(**validated_data)
        if password:
            apprenant.set_password(password)
        apprenant.save()
        return apprenant

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = self._apply_password(instance, validated_data)

        if "matricule" in validated_data:
            m = validated_data.get("matricule")
            validated_data["matricule"] = (m.strip() if isinstance(m, str) else m) or None

        for k, v in validated_data.items():
            setattr(instance, k, v)

        instance.role = _get_or_create_role("Apprenant")
        instance.save()
        return instance


class FormateurCrudSerializer(BaseUserCrudSerializer):
    # ✅ LECTURE : Objets complets (listes)
    institutions = serializers.SerializerMethodField(read_only=True)
    specialites = serializers.SerializerMethodField(read_only=True)
    groupes = serializers.SerializerMethodField(read_only=True)

    # ✅ ÉCRITURE : IDs uniquement
    institution_ids = serializers.PrimaryKeyRelatedField(
        source="institutions",
        queryset=Institution.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    specialite_ids = serializers.PrimaryKeyRelatedField(
        source="specialites",
        queryset=Specialite.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )
    groupe_ids = serializers.PrimaryKeyRelatedField(
        source="groupes",
        queryset=Groupe.objects.all(),
        many=True,
        write_only=True,
        required=False,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model = Formateur
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institutions",         # objets complets en lecture
            "institution_ids",      # IDs en écriture
            "specialites",          # objets complets en lecture
            "specialite_ids",       # IDs en écriture
            "groupes",              # objets complets en lecture
            "groupe_ids",           # IDs en écriture
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["institutions", "specialites", "groupes"]

    def get_institutions(self, obj):
        """Retourne les objets institutions complets"""
        serializers_dict = _get_academic_serializers()
        InstitutionSerializer = serializers_dict['InstitutionSerializer']
        return InstitutionSerializer(obj.institutions.all(), many=True).data

    def get_specialites(self, obj):
        """Retourne les objets specialites complets"""
        serializers_dict = _get_academic_serializers()
        SpecialiteSerializer = serializers_dict['SpecialiteSerializer']
        return SpecialiteSerializer(obj.specialites.all(), many=True).data

    def get_groupes(self, obj):
        """Retourne les objets groupes complets"""
        serializers_dict = _get_academic_serializers()
        GroupeSerializer = serializers_dict['GroupeSerializer']
        return GroupeSerializer(obj.groupes.all(), many=True).data

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password", None)

        institutions = validated_data.pop("institutions", [])
        specialites = validated_data.pop("specialites", [])
        groupes = validated_data.pop("groupes", [])

        formateur = Formateur(**validated_data)
        if password:
            formateur.set_password(password)
        formateur.role = _get_or_create_role("Formateur")
        formateur.save()

        formateur.institutions.set(institutions)
        formateur.specialites.set(specialites)
        formateur.groupes.set(groupes)
        return formateur

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = self._apply_password(instance, validated_data)

        institutions = validated_data.pop("institutions", None)
        specialites = validated_data.pop("specialites", None)
        groupes = validated_data.pop("groupes", None)

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


class ResponsableAcademiqueCrudSerializer(BaseUserCrudSerializer):
    # ✅ LECTURE : Objets complets
    institution = serializers.SerializerMethodField(read_only=True)
    departement = serializers.SerializerMethodField(read_only=True)

    # ✅ ÉCRITURE : IDs uniquement
    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )
    departement_id = serializers.PrimaryKeyRelatedField(
        source="departement",
        queryset=Departement.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model = ResponsableAcademique
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institution",      # objet complet en lecture
            "institution_id",   # ID en écriture
            "departement",      # objet complet en lecture
            "departement_id",   # ID en écriture
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + ["institution", "departement"]

    def get_institution(self, obj):
        """Retourne l'objet institution complet"""
        if not obj.institution:
            return None
        serializers_dict = _get_academic_serializers()
        InstitutionSerializer = serializers_dict['InstitutionSerializer']
        return InstitutionSerializer(obj.institution).data

    def get_departement(self, obj):
        """Retourne l'objet departement complet"""
        if not obj.departement:
            return None
        serializers_dict = _get_academic_serializers()
        DepartementSerializer = serializers_dict['DepartementSerializer']
        return DepartementSerializer(obj.departement).data

    @transaction.atomic
    def create(self, validated_data):
        validated_data["role"] = _get_or_create_role("ResponsableAcademique")
        password = validated_data.pop("password", None)

        ra = ResponsableAcademique(**validated_data)
        if password:
            ra.set_password(password)
        ra.save()
        return ra

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role = _get_or_create_role("ResponsableAcademique")
        instance.save()
        return instance