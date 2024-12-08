from rest_framework import serializers
from academics.models import AnneeScolaire, Classe, DomaineEtude, Filiere, Groupe, Inscription, Institution, Matiere, Specialite
from users.models import Admin
from users.serializers import AdminSerializer


class InstitutionSerializer(serializers.ModelSerializer):
    administrateur = AdminSerializer(write_only=True)  # Champ pour les détails de l'Admin

    class Meta:
        model = Institution
        fields = ['nom', 'pays', 'adresse', 'telephone', 'email', 'logo', 'description', 'statut', 'type_institution', 
                  'nombre_etudiants', 'site_web', 'accreditations', 'administrateur']

    def create(self, validated_data):
        admin_data = validated_data.pop('administrateur')
        
        # Création de l'Institution
        institution = Institution.objects.create(**validated_data)
        
        # Création de l'Admin associé à cette Institution
        admin_data['institution'] = institution
        admin_data['is_admin'] = True  # On marque cet utilisateur comme admin
        admin = Admin.objects.create(**admin_data)

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