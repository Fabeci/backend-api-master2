
import secrets
import string
from rest_framework import serializers
from academics.models import AnneeScolaire, Classe, DomaineEtude, Filiere, Groupe, Inscription, Institution, Matiere, Specialite
from users.models import Admin, UserRole
from users.serializers import AdminSerializer
from django.db import transaction
from django.core.exceptions import ValidationError


def generate_random_password(length=8):
    # Utilisation de secrets pour générer un mot de passe aléatoire
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for i in range(length))

class InstitutionSerializer(serializers.ModelSerializer):
    admin_account = AdminSerializer(write_only=True)  # Champ pour les détails de l'Admin
    admin_account_data = AdminSerializer(read_only=True, source='admin')

    class Meta:
        model = Institution
        fields = ['nom', 'pays', 'adresse', 'telephone_1', 'telephone_2', 'email', 'logo', 
                  'description', 'statut', 'type_institution', 'nombre_etudiants', 'site_web', 
                  'accreditations', 'date_creation', 'admin_account', 'admin_account_data']

    def create(self, validated_data):
        admin_data = validated_data.pop('admin_account')
        # Vérification si l'email de l'administrateur existe déjà
        if Admin.objects.filter(email=admin_data['email']).exists():
            raise ValidationError({'admin_account': {'email': 'Un utilisateur avec cet email existe déjà.'}})
        
        # Génération d'un mot de passe aléatoire si aucun mot de passe n'est fourni
        if 'password' not in admin_data:
            admin_data['password'] = generate_random_password()
        
        try:
            admin_data['role'] = UserRole.objects.get(name="Admin")
        except UserRole.DoesNotExist:
            raise ValidationError({'admin_account': {'role': "Le rôle 'Admin' est introuvable."}})
        
        with transaction.atomic():
            institution = Institution.objects.create(**validated_data)
            # Création de l'Admin associé à cette Institution
            admin_data['institution'] = institution
            admin = Admin.objects.create_user(**admin_data)
            institution.admin = admin
            
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
        

class FiliereSerializer(serializers.ModelSerializer):
    domaine_etude = serializers.StringRelatedField()  # Affiche le nom du domaine d'étude
    class Meta:
        model = Filiere
        fields = ['id', 'nom', 'domaine_etude', 'description', 'date_creation', 'statut']

class GroupeSerializer(serializers.ModelSerializer):
    enseignants = serializers.StringRelatedField(many=True)  # Affiche les formateurs associés
    class Meta:
        model = Groupe
        fields = ['id', 'nom', 'enseignants', 'description']

class ClasseSerializer(serializers.ModelSerializer):
    filieres = FiliereSerializer(many=True)  # Sérialise les filières associées
    matieres = serializers.StringRelatedField(many=True)  # Sérialise les matières
    groupes = GroupeSerializer()  # Sérialise le groupe associé
    apprenants = serializers.StringRelatedField()  # Sérialise l'apprenant associé
    class Meta:
        model = Classe
        fields = ['id', 'nom', 'description', 'date_creation', 'filieres', 'matieres', 'groupes', 'apprenants']
        
        
class InscriptionSerializer(serializers.ModelSerializer):
    apprenant = serializers.StringRelatedField()  # Affiche les informations de l'apprenant (par exemple, son nom)
    institution = serializers.StringRelatedField()  # Affiche le nom de l'institution
    annee_scolaire = serializers.StringRelatedField()  # Affiche l'année scolaire associée

    class Meta:
        model = Inscription
        fields = ['id', 'apprenant', 'institution', 'annee_scolaire', 'statut', 'statut_paiement']