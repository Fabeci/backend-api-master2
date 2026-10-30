
import secrets
import string
from rest_framework import serializers
from academics.models import AnneeScolaire, Classe, Departement, DomaineEtude, Filiere, Groupe, Inscription, Institution, Matiere, Specialite
from locations.models import Pays
from locations.serializers import PaysSerializer
from users.models import Admin, Apprenant, Formateur, Parent, ResponsableAcademique, UserRole, VerificationCode
from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.core.mail import send_mail
from core.mailer import safe_send_mail
from django.conf import settings

from users.serializers import ApprenantSerializer



def generate_random_password(length=12):
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class AdminAccountInlineSerializer(serializers.Serializer):
    # champs nécessaires pour créer un Admin
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)
    nom = serializers.CharField(max_length=30)
    prenom = serializers.CharField(max_length=30)
    telephone = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True)
    pays_residence = serializers.PrimaryKeyRelatedField(
        queryset=Parent._meta.get_field('pays_residence').remote_field.model.objects.all(),
        required=False, allow_null=True
    )

# academics/serializers.py
# Section InstitutionSerializer - COPIER-COLLER CETTE PARTIE COMPLÈTE

import secrets
import string
from rest_framework import serializers
from academics.models import Institution
from locations.models import Pays
from locations.serializers import PaysSerializer
from users.models import Admin, UserRole, VerificationCode
from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.core.mail import send_mail
from django.conf import settings


def generate_random_password(length=12):
    """Génère un mot de passe aléatoire sécurisé"""
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))


class AdminAccountInlineSerializer(serializers.Serializer):
    """Serializer pour créer un compte admin inline lors de la création d'une institution"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)
    nom = serializers.CharField(max_length=30)
    prenom = serializers.CharField(max_length=30)
    telephone = serializers.CharField(max_length=15, required=False, allow_blank=True, allow_null=True)
    pays_residence = serializers.PrimaryKeyRelatedField(
        queryset=Pays.objects.all(),
        required=False,
        allow_null=True
    )


class InstitutionSerializer(serializers.ModelSerializer):
    # ===== LECTURE : objets complets =====
    pays = PaysSerializer(read_only=True)
    admin_account_data = serializers.SerializerMethodField(read_only=True)
    logo_url           = serializers.SerializerMethodField(read_only=True)  # ✅ URL absolue

    # ===== ÉCRITURE : IDs =====
    pays_id = serializers.PrimaryKeyRelatedField(
        source="pays",
        queryset=Pays.objects.all(),
        write_only=True,
        required=True,
    )
    logo              = serializers.ImageField(write_only=True, required=False, allow_null=True)

    # Admin: deux modes possibles
    admin_account = AdminAccountInlineSerializer(write_only=True, required=False)
    existing_admin_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Institution
        fields = [
            "id",
            "nom",
            "pays",
            "pays_id",
            "adresse",
            "telephone_1",
            "telephone_2",
            "email",
            "logo",
            "logo_url",
            "description",
            "statut",
            "type_institution",
            "nombre_etudiants",
            "site_web",
            "accreditations",
            "date_creation",
            "admin_account",
            "existing_admin_id",
            "admin_account_data",
        ]
        read_only_fields = ["id", "date_creation"]
        
    def get_logo_url(self, obj):
        """Retourne toujours une URL absolue ou None."""
        if not obj.logo:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.logo.url)
        from django.conf import settings
        base = getattr(settings, "SITE_URL", "http://localhost:8000").rstrip("/")
        return f"{base}{settings.MEDIA_URL}{obj.logo.name}"

    def get_admin_account_data(self, obj):
        # 1) FK directe: institution.admin
        admin = getattr(obj, "admin", None)
        if admin:
            return {
                "id": admin.id,
                "email": admin.email,
                "nom": admin.nom,
                "prenom": admin.prenom,
                "telephone": admin.telephone,
                "role": getattr(admin.role, "name", None),
                "is_active": admin.is_active,
            }

        # 2) Relation inverse via related_name (si défini)
        for rel_name in ("admins", "administrateurs", "admin_set"):
            rel = getattr(obj, rel_name, None)
            if rel is not None:
                admin = rel.order_by("-id").first()
                if admin:
                    return {
                        "id": admin.id,
                        "email": admin.email,
                        "nom": admin.nom,
                        "prenom": admin.prenom,
                        "telephone": admin.telephone,
                        "role": getattr(admin.role, "name", None),
                        "is_active": admin.is_active,
                    }

        # 3) Fallback: essayer plusieurs noms de FK dans Admin
        try:
            admin = (
                Admin.objects.filter(institution=obj).order_by("-id").first()
            )
            if admin:
                return {
                    "id": admin.id,
                    "email": admin.email,
                    "nom": admin.nom,
                    "prenom": admin.prenom,
                    "telephone": admin.telephone,
                    "role": getattr(admin.role, "name", None),
                    "is_active": admin.is_active,
                }
        except Exception:
            pass

        try:
            admin = (
                Admin.objects.filter(etablissement=obj).order_by("-id").first()
            )
            if admin:
                return {
                    "id": admin.id,
                    "email": admin.email,
                    "nom": admin.nom,
                    "prenom": admin.prenom,
                    "telephone": admin.telephone,
                    "role": getattr(admin.role, "name", None),
                    "is_active": admin.is_active,
                }
        except Exception:
            pass

        return None


    def validate(self, attrs):
        """
        Validation:
        - Admin totalement optionnel (CREATE et UPDATE)
        - Si fourni, on interdit de fournir les deux modes en même temps
        """
        admin_data = attrs.get("admin_account", None)
        existing_admin_id = attrs.get("existing_admin_id", None)

        # Si DRF place existing_admin_id dans attrs, il y sera.
        # Si tu constates qu'il n'y est pas (selon ton impl), récupère aussi depuis initial_data.
        if existing_admin_id is None:
            try:
                existing_admin_id = self.initial_data.get("existing_admin_id")
            except Exception:
                pass

        # Interdire les deux en même temps
        if admin_data and existing_admin_id:
            raise ValidationError(
                {
                    "admin": (
                        "Vous ne pouvez pas à la fois créer un admin (admin_account) "
                        "et en sélectionner un existant (existing_admin_id). Choisissez une seule option."
                    )
                }
            )

        # IMPORTANT: on ne force PAS admin (optionnel)
        return attrs

    def create(self, validated_data):
        """
        Création d'une institution avec admin optionnel

        3 modes possibles:
        1. Sans admin (institution créée sans admin)
        2. Avec admin existant (existing_admin_id)
        3. Avec nouvel admin (admin_account)
        """
        admin_data = validated_data.pop("admin_account", None)
        existing_admin_id = validated_data.pop("existing_admin_id", None)

        # En cas où existing_admin_id n'est pas injecté dans validated_data
        if existing_admin_id is None:
            existing_admin_id = self.initial_data.get("existing_admin_id")

        with transaction.atomic():
            institution = Institution.objects.create(**validated_data)

            admin = None

            if existing_admin_id:
                # MODE SÉLECTION : assigne un admin existant
                try:
                    admin = Admin.objects.select_related("institution").get(id=existing_admin_id)

                    # Détacher d'une ancienne institution si nécessaire
                    if admin.institution and admin.institution != institution:
                        old_institution = admin.institution
                        # Si Institution a un champ admin (FK) et qu'il pointe vers cet admin
                        if hasattr(old_institution, "admin") and old_institution.admin_id == admin.id:
                            old_institution.admin = None
                            old_institution.save(update_fields=["admin"])

                    # Assigner à la nouvelle institution
                    admin.institution = institution
                    admin.save(update_fields=["institution"])

                except Admin.DoesNotExist:
                    raise ValidationError({"existing_admin_id": "Administrateur introuvable."})

            elif admin_data:
                # MODE CRÉATION : créer un nouvel admin
                from django.contrib.auth import get_user_model

                User = get_user_model()

                if User.objects.filter(email=admin_data["email"]).exists():
                    raise ValidationError(
                        {"admin_account": {"email": "Un utilisateur avec cet email existe déjà."}}
                    )

                password = admin_data.get("password") or generate_random_password()
                role, _ = UserRole.objects.get_or_create(name="Admin")

                admin = Admin(
                    email=admin_data["email"],
                    nom=admin_data["nom"],
                    prenom=admin_data["prenom"],
                    telephone=admin_data.get("telephone"),
                    pays_residence=admin_data.get("pays_residence"),
                    is_active=False,
                    is_staff=True,
                    is_superuser=False,
                    role=role,
                    institution=institution,
                )
                admin.set_password(password)
                admin.save()

                # Code d'activation + email
                v = VerificationCode.create_activation_code(admin)
                safe_send_mail(
                    subject="Somapro - Compte administrateur : code d'activation",
                    message=(
                        f"Bonjour {admin.prenom},\n\n"
                        f"Votre compte administrateur pour l'institution « {institution.nom} » a été créé.\n"
                        f"Code d'activation : {v.code} (valide 15 minutes).\n\n"
                        f"Identifiant : {admin.email}\n\n"
                        f"Pour définir votre mot de passe, utilisez « Mot de passe oublié » sur la page de connexion.\n"
                        f"Merci de valider votre compte puis de définir votre mot de passe."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[admin.email],
                    fail_silently=None,
                )

            # Lier l'admin à l'institution (si le champ existe)
            if admin and hasattr(institution, "admin"):
                institution.admin = admin
                institution.save(update_fields=["admin"])

        return institution

    def update(self, instance, validated_data):
        """
        Mise à jour d'une institution
        - Si admin_account ou existing_admin_id fourni: change l'admin
        - Sinon: met juste à jour les infos de l'institution
        """
        admin_data = validated_data.pop("admin_account", None)
        existing_admin_id = validated_data.pop("existing_admin_id", None)

        if existing_admin_id is None:
            existing_admin_id = self.initial_data.get("existing_admin_id")

        with transaction.atomic():
            # 1) Update champs Institution
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            # 2) Changement admin (optionnel)
            if existing_admin_id:
                try:
                    new_admin = Admin.objects.get(id=existing_admin_id)

                    # Détacher l'ancien admin si la relation existe
                    if hasattr(instance, "admin") and instance.admin:
                        old_admin = instance.admin
                        old_admin.institution = None
                        old_admin.save(update_fields=["institution"])

                    new_admin.institution = instance
                    new_admin.save(update_fields=["institution"])

                    if hasattr(instance, "admin"):
                        instance.admin = new_admin
                        instance.save(update_fields=["admin"])

                except Admin.DoesNotExist:
                    raise ValidationError({"existing_admin_id": "Administrateur introuvable."})

            elif admin_data:
                from django.contrib.auth import get_user_model

                User = get_user_model()

                if User.objects.filter(email=admin_data["email"]).exists():
                    raise ValidationError(
                        {"admin_account": {"email": "Un utilisateur avec cet email existe déjà."}}
                    )

                password = admin_data.get("password") or generate_random_password()
                role, _ = UserRole.objects.get_or_create(name="Admin")

                admin = Admin(
                    email=admin_data["email"],
                    nom=admin_data["nom"],
                    prenom=admin_data["prenom"],
                    telephone=admin_data.get("telephone"),
                    pays_residence=admin_data.get("pays_residence"),
                    is_active=False,
                    is_staff=True,
                    role=role,
                    institution=instance,
                )
                admin.set_password(password)
                admin.save()

                v = VerificationCode.create_activation_code(admin)
                safe_send_mail(
                    subject="Somapro - Nouveau compte administrateur",
                    message=(
                        f"Bonjour {admin.prenom},\n\n"
                        f"Un nouveau compte administrateur pour l'institution « {instance.nom} » a été créé.\n"
                        f"Code d'activation : {v.code} (valide 15 minutes).\n\n"
                        f"Identifiant : {admin.email}\n"
                        f"Pour définir votre mot de passe, utilisez « Mot de passe oublié » sur la page de connexion.\n"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[admin.email],
                    fail_silently=None,
                )

                if hasattr(instance, "admin"):
                    instance.admin = admin
                    instance.save(update_fields=["admin"])

        return instance
    
    
class DomaineEtudeSerializer(serializers.ModelSerializer):
    departement_label = serializers.StringRelatedField(
        source="departement.nom", read_only=True
    )
    class Meta:
        model = DomaineEtude
        fields = '__all__'
        

class MatiereSerializer(serializers.ModelSerializer):
    institution = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Matiere
        fields = "__all__"

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        if not user.is_superuser:
            validated_data["institution_id"] = user.institution_id
        return super().create(validated_data)
        
        
class SpecialiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialite
        fields = '__all__'
        
        
class AnneeScolaireSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnneeScolaire
        fields = '__all__'


class DepartementSerializer(serializers.ModelSerializer):
    # ===== WRITE (IDs) =====
    # L'établissement est déduit du compte connecté (jamais saisi dans le formulaire).
    institution = serializers.PrimaryKeyRelatedField(read_only=True)
    # Responsable facultatif : un département peut exister sans responsable.
    responsable_academique = serializers.PrimaryKeyRelatedField(
        queryset=ResponsableAcademique.objects.all(),
        required=False,
        allow_null=True,
    )

    # ===== READ (labels) =====
    institution_label = serializers.StringRelatedField(
        source="institution",
        read_only=True
    )
    responsable_academique_label = serializers.StringRelatedField(
        source="responsable_academique",
        read_only=True
    )

    class Meta:
        model = Departement
        fields = [
            "id",
            "nom",
            "description",

            # write
            "institution",
            "responsable_academique",

            # read
            "institution_label",
            "responsable_academique_label",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        from core.tenant import default_institution
        user = self.context.get("request").user if self.context.get("request") else None
        institution = (getattr(user, "institution", None) if user else None) or default_institution()
        responsable = attrs.get(
            "responsable_academique",
            getattr(self.instance, "responsable_academique", None),
        )
        if responsable and institution and responsable.institution_id != institution.id:
            raise serializers.ValidationError({
                "responsable_academique":
                    "Le responsable doit appartenir à votre établissement."
            })
        return attrs
        

class FiliereSerializer(serializers.ModelSerializer):
    departement = serializers.PrimaryKeyRelatedField(
        queryset=Departement.objects.all(), required=False, allow_null=True,
    )
    departement_label = serializers.StringRelatedField(
        source="departement", read_only=True
    )
    domaine_etude_label = serializers.StringRelatedField(
        source="domaine_etude", read_only=True
    )
    domaine_etude = serializers.PrimaryKeyRelatedField(
        queryset=DomaineEtude.objects.all(), required=False, allow_null=True,
    )
    institution = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Filiere
        fields = [
            "id", "nom", "departement", "departement_label",
            "domaine_etude", "domaine_etude_label",
            "institution", "description", "date_creation", "statut",
        ]
        read_only_fields = ["id", "date_creation"]

    def validate(self, attrs):
        from core.tenant import default_institution
        request = self.context.get("request")
        user = getattr(request, "user", None)
        institution = (getattr(user, "institution", None) if user else None) or default_institution()

        departement = attrs.get(
            "departement", getattr(self.instance, "departement", None),
        )
        domaine = attrs.get(
            "domaine_etude", getattr(self.instance, "domaine_etude", None),
        )

        if departement and institution and departement.institution_id != institution.id:
            raise serializers.ValidationError({
                "departement": "Le département doit appartenir à votre établissement."
            })
        if domaine:
            if institution and domaine.institution_id != institution.id:
                raise serializers.ValidationError({
                    "domaine_etude": "Le domaine d'étude doit appartenir à votre établissement."
                })
            if (departement and domaine.departement_id
                    and domaine.departement_id != departement.id):
                raise serializers.ValidationError({
                    "domaine_etude": "Le domaine d'étude doit appartenir au département sélectionné."
                })
        return attrs

    def create(self, validated_data):
        from core.tenant import default_institution
        request = self.context["request"]
        user = request.user
        validated_data["institution"] = (
            getattr(user, "institution", None) or default_institution()
        )
        return super().create(validated_data)
    
class GroupeSerializer(serializers.ModelSerializer):
    enseignants = serializers.PrimaryKeyRelatedField(
        queryset=Formateur.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        model = Groupe
        fields = ["id", "nom", "description", "institution", "classe", "enseignants", "annee_scolaire"]


class ClasseSerializer(serializers.ModelSerializer):
    # ===== WRITE (IDs) =====
    filieres = serializers.PrimaryKeyRelatedField(queryset=Filiere.objects.all(), many=True)
    matieres = serializers.PrimaryKeyRelatedField(queryset=Matiere.objects.all(), many=True)
    groupes  = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    # ===== READ (détails) =====
    filieres_data  = FiliereSerializer(source="filieres", many=True, read_only=True)
    matieres_data  = MatiereSerializer(source="matieres", many=True, read_only=True)
    groupes_data   = GroupeSerializer(source="groupes",   many=True, read_only=True)

    # ✅ Labels lecture seule pour annee_scolaire et institution
    annee_scolaire_display = serializers.StringRelatedField(source="annee_scolaire", read_only=True)
    institution_display    = serializers.StringRelatedField(source="institution",    read_only=True)

    class Meta:
        model = Classe
        fields = [
            "id",
            "nom",
            "description",
            "date_creation",

            # ✅ FK en écriture (acceptent un ID entier)
            "annee_scolaire",
            "institution",

            # ✅ Labels en lecture
            "annee_scolaire_display",
            "institution_display",

            # write
            "filieres",
            "matieres",

            # read
            "groupes",
            "filieres_data",
            "matieres_data",
            "groupes_data",
        ]
        read_only_fields = ["id", "date_creation", "groupes"]
               
class InscriptionSerializer(serializers.ModelSerializer):
    # Champs en lecture seule (affichage)
    apprenant_display      = serializers.StringRelatedField(source='apprenant',      read_only=True)
    institution_display    = serializers.StringRelatedField(source='institution',    read_only=True)
    annee_scolaire_display = serializers.StringRelatedField(source='annee_scolaire', read_only=True)
    classe_display         = serializers.StringRelatedField(source='classe',         read_only=True)

    class Meta:
        model  = Inscription
        fields = [
            'id',
            # IDs en écriture
            'apprenant', 'institution', 'annee_scolaire', 'classe',
            # Labels en lecture
            'apprenant_display', 'institution_display',
            'annee_scolaire_display', 'classe_display',
            'statut', 'statut_paiement',
        ]

class AffectationEnseignementSerializer(serializers.ModelSerializer):
    """Affectation (formateur, groupe, matière, année) — lue par les 3 rôles."""
    formateur_nom = serializers.SerializerMethodField()
    groupe_nom = serializers.CharField(source='groupe.nom', read_only=True)
    matiere_nom = serializers.CharField(source='matiere.nom', read_only=True)
    annee_libelle = serializers.CharField(source='annee_scolaire.annee_format_classique', read_only=True)

    class Meta:
        model = __import__('academics.models', fromlist=['AffectationEnseignement']).AffectationEnseignement
        fields = [
            'id', 'formateur', 'formateur_nom', 'groupe', 'groupe_nom',
            'matiere', 'matiere_nom', 'annee_scolaire', 'annee_libelle',
            'institution', 'est_actif', 'date_creation',
        ]
        read_only_fields = ['institution', 'date_creation']

    def get_formateur_nom(self, obj):
        u = getattr(obj, 'formateur', None)
        if not u:
            return None
        nom = f"{getattr(u, 'prenom', '') or ''} {getattr(u, 'nom', '') or ''}".strip()
        return nom or getattr(u, 'email', None)

    def create(self, validated_data):
        groupe = validated_data.get('groupe')
        if groupe is not None and not validated_data.get('institution_id'):
            validated_data['institution_id'] = getattr(groupe, 'institution_id', None)
        return super().create(validated_data)


class SemestreSerializer(serializers.ModelSerializer):
    classe_nom = serializers.CharField(source='classe.nom', read_only=True)
    annee_libelle = serializers.CharField(source='annee_scolaire.annee_format_classique', read_only=True)

    class Meta:
        model = __import__('academics.models', fromlist=['Semestre']).Semestre
        fields = '__all__'
        read_only_fields = ['institution']


class UESerializer(serializers.ModelSerializer):
    semestre_numero = serializers.IntegerField(source='semestre.numero', read_only=True)
    semestre_libelle = serializers.SerializerMethodField()
    ecs = serializers.SerializerMethodField()

    class Meta:
        model = __import__('academics.models', fromlist=['UE']).UE
        fields = '__all__'
        read_only_fields = ['institution']

    def get_semestre_libelle(self, obj):
        return str(obj.semestre) if obj.semestre else None

    def get_ecs(self, obj):
        return [
            {'id': m.id, 'nom': m.nom, 'credits': m.credits, 'coefficient': m.coefficient}
            for m in obj.matieres.all()
        ]
