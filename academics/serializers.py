
import secrets
import string
from rest_framework import serializers
from academics.models import AnneeScolaire, Classe, Departement, DomaineEtude, Filiere, Groupe, Inscription, Institution, Matiere, Specialite
from users.models import Admin, Apprenant, Formateur, Parent, ResponsableAcademique, UserRole, VerificationCode
from django.db import transaction
from rest_framework.exceptions import ValidationError
from django.core.mail import send_mail
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

class InstitutionSerializer(serializers.ModelSerializer):
    # On remplace l'ancien AdminSerializer par un inline minimal
    admin_account = AdminAccountInlineSerializer(write_only=True, required=True)
    # admin_account_data = serializers.SerializerMethodField(read_only=True)
    # ou si ton modèle Institution a un FK/OneToOne "admin" vers Admin :
    admin_account_data = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Institution
        fields = [
            'nom', 'pays', 'adresse', 'telephone_1', 'telephone_2', 'email', 'logo',
            'description', 'statut', 'type_institution', 'nombre_etudiants', 'site_web',
            'accreditations', 'date_creation',
            'admin_account', 'admin_account_data'
        ]

    def get_admin_account_data(self, obj):
        admin = getattr(obj, 'admin', None)
        if not admin:
            return None
        return {
            "id": admin.id,
            "email": admin.email,
            "nom": admin.nom,
            "prenom": admin.prenom,
            "telephone": admin.telephone,
            "role": getattr(admin.role, "name", None),
            "is_active": admin.is_active,
        }

    def create(self, validated_data):
        admin_data = validated_data.pop('admin_account', None)
        if not admin_data:
            raise ValidationError({"admin_account": "Les informations de l’administrateur sont requises."})

        # Vérif email unique sur l’ensemble des Users (Admin hérite de User)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(email=admin_data['email']).exists():
            raise ValidationError({'admin_account': {'email': 'Un utilisateur avec cet email existe déjà.'}})

        # Mot de passe : généré si absent
        password = admin_data.get('password') or generate_random_password()

        # Rôle FK "Admin"
        try:
            role = UserRole.objects.get(name="Admin")
        except UserRole.DoesNotExist:
            role = UserRole.objects.create(name="Admin")

        with transaction.atomic():
            # 1) Créer l’institution
            institution = Institution.objects.create(**validated_data)

            # 2) Créer l’Admin (multi-table inheritance : on instancie directement Admin)
            admin = Admin(
                email=admin_data['email'],
                nom=admin_data['nom'],
                prenom=admin_data['prenom'],
                telephone=admin_data.get('telephone'),
                pays_residence=admin_data.get('pays_residence'),
                is_active=False,          # inactif tant que l’email n’est pas vérifié
                is_staff=True,            # généralement true pour un Admin d’institution
                is_superuser=False,
                role=role,
                institution=institution,  # si ton modèle Admin a bien ce FK
            )
            admin.set_password(password)
            admin.save()

            # 3) Lier l’admin à l’institution (si champ présent côté Institution)
            #   - Si ton modèle Institution a un champ: admin = models.OneToOneField(Admin, ...)
            #   - Ou admin = models.ForeignKey(Admin, ...)
            if hasattr(institution, "admin"):
                institution.admin = admin
                institution.save(update_fields=["admin"])

            # 4) Générer le code 6 chiffres + envoi email
            v = VerificationCode.create_activation_code(admin)  # TTL 15 min par défaut
            send_mail(
                subject="Somapro - Compte administrateur : code d’activation",
                message=(
                    f"Bonjour {admin.prenom},\n\n"
                    f"Votre compte administrateur pour l’institution « {institution.nom} » a été créé.\n"
                    f"Code d’activation : {v.code} (valide 15 minutes).\n\n"
                    f"Identifiant : {admin.email}\n"
                    f"Mot de passe provisoire : {password}\n\n"
                    f"Merci de valider votre compte et de modifier votre mot de passe après connexion."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin.email],
                fail_silently=False,
            )

        return institution
    
    
class DomaineEtudeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DomaineEtude
        fields = '__all__'
        

class MatiereSerializer(serializers.ModelSerializer):
    class Meta:
        model = Matiere
        fields = '__all__'
        
        
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
    institution = serializers.PrimaryKeyRelatedField(
        queryset=Institution.objects.all()
    )
    responsable_academique = serializers.PrimaryKeyRelatedField(
        queryset=ResponsableAcademique.objects.all()
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
        

class FiliereSerializer(serializers.ModelSerializer):
    # Lecture : nom du domaine
    domaine_etude_label = serializers.StringRelatedField(source="domaine_etude", read_only=True)

    # Écriture : ID du domaine
    domaine_etude = serializers.PrimaryKeyRelatedField(queryset=DomaineEtude.objects.all(), write_only=True)

    class Meta:
        model = Filiere
        fields = [
            "id",
            "nom",
            "domaine_etude",        # write-only (ID)
            "domaine_etude_label",  # read-only (nom)
            "description",
            "date_creation",
            "statut",
        ]
        read_only_fields = ["id", "date_creation"]


class GroupeSerializer(serializers.ModelSerializer):
    enseignants = serializers.PrimaryKeyRelatedField(
        queryset=Formateur.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        model = Groupe
        fields = ["id", "nom", "description", "enseignants"]


class ClasseSerializer(serializers.ModelSerializer):
    # ===== WRITE (IDs) =====
    filieres = serializers.PrimaryKeyRelatedField(queryset=Filiere.objects.all(), many=True)
    matieres = serializers.PrimaryKeyRelatedField(queryset=Matiere.objects.all(), many=True)
    groupes = serializers.PrimaryKeyRelatedField(queryset=Groupe.objects.all(), required=False, allow_null=True)
    apprenants = serializers.PrimaryKeyRelatedField(queryset=Apprenant.objects.all(), required=False, allow_null=True)

    # ===== READ (détails) =====
    filieres_data = FiliereSerializer(source="filieres", many=True, read_only=True)
    matieres_data = MatiereSerializer(source="matieres", many=True, read_only=True)
    groupes_data = GroupeSerializer(source="groupes", read_only=True)
    apprenants_data = ApprenantSerializer(source="apprenants", read_only=True)

    class Meta:
        model = Classe
        fields = [
            "id",
            "nom",
            "description",
            "date_creation",

            # write
            "filieres",
            "matieres",
            "groupes",
            "apprenants",

            # read
            "filieres_data",
            "matieres_data",
            "groupes_data",
            "apprenants_data",
        ]
        read_only_fields = ["id", "date_creation"]
        
        
class InscriptionSerializer(serializers.ModelSerializer):
    apprenant = serializers.StringRelatedField()  # Affiche les informations de l'apprenant (par exemple, son nom)
    institution = serializers.StringRelatedField()  # Affiche le nom de l'institution
    annee_scolaire = serializers.StringRelatedField()  # Affiche l'année scolaire associée

    class Meta:
        model = Inscription
        fields = ['id', 'apprenant', 'institution', 'annee_scolaire', 'statut', 'statut_paiement']