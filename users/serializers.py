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
from academics.models import AnneeScolaire

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
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=8
    )

    pays_residence = serializers.SerializerMethodField(read_only=True)
    pays_residence_id = serializers.PrimaryKeyRelatedField(
        source="pays_residence",
        queryset=Pays.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    def get_pays_residence(self, obj):
        pays = obj.pays_residence
        if not pays:
            return None
        # ✅ Accès direct — correspond exactement à PaysSerializer {id, nom, code}
        return {
            "id":   pays.id,
            "nom":  pays.nom,
            "code": getattr(pays, "code", None),
        }

    annee_scolaire_active    = serializers.SerializerMethodField(read_only=True)
    annee_scolaire_active_id = serializers.PrimaryKeyRelatedField(
        source="annee_scolaire_active",
        queryset=AnneeScolaire.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    # ✅ Déclaré explicitement → évite le KeyError DRF sur la FK
    role = serializers.SerializerMethodField(read_only=True)

    # ✅ Déclaré explicitement → date_modification n'est pas auto-détecté sans ça
    date_joined       = serializers.DateTimeField(read_only=True)
    date_modification = serializers.DateTimeField(read_only=True)

    # ✅ URL absolue photo
    photo = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = User
        fields = [
            "id",
            "email", "nom", "prenom", "telephone",
            "photo",
            "role",
            "pays_residence", "pays_residence_id",
            "annee_scolaire_active", "annee_scolaire_active_id",
            "is_active", "is_staff", "is_superuser",
            "date_joined", "date_modification",
            "password",
        ]
        read_only_fields = [
            "id",
            "photo",
            "role",
            "pays_residence",
            "annee_scolaire_active",
            "date_joined",
            "date_modification",
            "is_staff",
            "is_superuser",
        ]

    def get_role(self, obj):
        """Retourne le nom du rôle en string — jamais l'objet FK brut."""
        return getattr(obj.role, 'name', None) if obj.role else None

    def get_annee_scolaire_active(self, obj):
        if not obj.annee_scolaire_active:
            return None
        a = obj.annee_scolaire_active
        return {
            "id":      a.id,
            "libelle": getattr(a, 'libelle', str(a)),
        }

    def get_photo(self, obj):
        if not obj.photo:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.photo.url)
        return obj.photo.url

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
    institution = serializers.SerializerMethodField(read_only=True)
    institution_id = serializers.PrimaryKeyRelatedField(
        source="institution",
        queryset=Institution.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    # ✅ Liste des enfants (Apprenant.tuteur = FK vers Parent)
    enfants = serializers.SerializerMethodField(read_only=True)

    class Meta(BaseUserCrudSerializer.Meta):
        model = Parent
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institution",
            "institution_id",
            "enfants",   # ✅
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + [
            "institution", "enfants"
        ]

    def get_institution(self, obj):
        if not obj.institution:
            return None
        serializers_dict = _get_academic_serializers()
        InstitutionSerializer = serializers_dict['InstitutionSerializer']
        return InstitutionSerializer(obj.institution).data

    def get_enfants(self, obj):
        # Apprenant.tuteur = ForeignKey(Parent) → related_name par défaut
        enfants = Apprenant.objects.filter(tuteur=obj).select_related(
            'annee_scolaire_active', 'groupe'
        )
        result = []
        for a in enfants:
            annee = a.annee_scolaire_active
            result.append({
                "id":     a.id,
                "prenom": a.prenom,
                "nom":    a.nom,
                "matricule": a.matricule,
                "annee_scolaire_active": {
                    "id":      annee.id,
                    "libelle": getattr(annee, 'libelle', str(annee)),
                } if annee else None,
            })
        return result

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
    matricule      = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    date_naissance = serializers.DateField(required=False, allow_null=True)

    groupe = serializers.SerializerMethodField(read_only=True)
    tuteur = serializers.SerializerMethodField(read_only=True)
    # ✅ AJOUTER institution
    institution = serializers.SerializerMethodField(read_only=True)

    groupe_id = serializers.PrimaryKeyRelatedField(
        source="groupe", queryset=Groupe.objects.all(),
        write_only=True, required=False, allow_null=True,
    )
    tuteur_id = serializers.PrimaryKeyRelatedField(
        source="tuteur", queryset=Parent.objects.all(),
        write_only=True, required=False, allow_null=True,
    )

    class Meta(BaseUserCrudSerializer.Meta):
        model = Apprenant
        fields = BaseUserCrudSerializer.Meta.fields + [
            "matricule", "date_naissance",
            "groupe", "groupe_id",
            "tuteur", "tuteur_id",
            "institution",  # ✅ AJOUTER
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + [
            "groupe", "tuteur", "institution"
        ]

    # ✅ AJOUTER cette méthode
    def get_institution(self, obj):
        # Essaie le champ direct d'abord
        inst = getattr(obj, 'institution', None)
        if not inst:
            # Fallback : via le groupe
            groupe = getattr(obj, 'groupe', None)
            if groupe:
                inst = getattr(groupe, 'institution', None)
        if not inst:
            return None
        return {"id": inst.id, "nom": inst.nom}

    def get_groupe(self, obj):
        if not hasattr(obj, 'groupe') or not obj.groupe:
            return None
        serializers_dict = _get_academic_serializers()
        GroupeSerializer = serializers_dict['GroupeSerializer']
        return GroupeSerializer(obj.groupe).data

    def get_tuteur(self, obj):
        t = getattr(obj, 'tuteur', None)
        if not t:
            return None
        return {
            "id": t.id, "email": t.email,
            "nom": t.nom, "prenom": t.prenom,
            "telephone": t.telephone,
            "pays_residence": PaysSerializer(t.pays_residence).data if t.pays_residence else None,
        }

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
    institution = serializers.SerializerMethodField(read_only=True)
    departement = serializers.SerializerMethodField(read_only=True)

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
        model = ResponsableAcademique
        fields = BaseUserCrudSerializer.Meta.fields + [
            "institution", "institution_id",
            "departement", "departement_id",
        ]
        read_only_fields = BaseUserCrudSerializer.Meta.read_only_fields + [
            "institution", "departement"
        ]

    def get_institution(self, obj):
        # ✅ Accès direct — pas de serializer externe
        inst = obj.institution
        if not inst:
            return None
        return {"id": inst.id, "nom": inst.nom}

    def get_departement(self, obj):
        # ✅ Accès direct via select_related — contourne tout filtrage
        dept = obj.departement
        if not dept:
            return None
        return {
            "id":          dept.id,
            "nom":         dept.nom,
            "description": getattr(dept, "description", None),
        }

class ModifierMotDePasseSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Le mot de passe actuel est incorrect.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = self._apply_password(instance, validated_data)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.role = _get_or_create_role("ResponsableAcademique")
        instance.save()
        return instance


class ModifierMotDePasseSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
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
        return data

    def save(self):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        # Invalider l'ancien token pour forcer une nouvelle connexion
        Token.objects.filter(user=user).delete()
        return user