from rest_framework import serializers
from django.contrib.auth import authenticate
from academics.models import Groupe, Institution, Specialite
from users.utils import send_activation_email, send_verification_email
from django.contrib.auth import get_user_model
from .models import (
    User, Admin, SuperAdmin, Parent, Apprenant, Formateur, ResponsableAcademique
)
from django.db import transaction
from django.urls import reverse
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.mail import send_mail
from rest_framework.exceptions import AuthenticationFailed


def generate_activation_link(user, frontend_url):
    """
    Génère un lien d'activation sécurisé pour un utilisateur.

    Args:
        user (User): Instance de l'utilisateur pour lequel générer le lien d'activation.
        frontend_url (str): URL de base de l'application frontend.

    Returns:
        str: Lien d'activation complet.
    """
    # Génération des identifiants sécurisés
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)

    # Construction du lien d'activation
    activation_link = reverse('activate_user', kwargs={'uidb64': uid, 'token': token})
    activation_url = f"{frontend_url}{activation_link}"

    return activation_url


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'nom', 'prenom', 'telephone', 'pays_residence', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return {
            "message": "Un e-mail de vérification a été envoyé à l'adresse fournie."
        }
        

class UserRegisterSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'nom', 'prenom', 'telephone', 'pays_residence', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            user.is_active = False  # L'utilisateur est inactif jusqu'à la vérification
            user.save()
            
            uid = urlsafe_base64_encode(str(user.pk).encode())
            token = default_token_generator.make_token(user)

            activation_link = reverse('activate_user', kwargs={'uidb64': uid, 'token': token})
            activation_url = f"{settings.FRONTEND_URL}{activation_link}"

            send_mail(
                'Activer votre compte',
                f'Cliquez sur ce lien pour activer votre compte : {activation_url}',
                settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            return {
                "message": "Un e-mail de vérification a été envoyé à l'adresse fournie."
            }
        

class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        # Chercher l'utilisateur dans la base de données
        user = get_user_model().objects.filter(email=email).first()

        if user is None:
            raise AuthenticationFailed("Identifiants invalides.")
        
        # Vérifier le mot de passe
        if not user.check_password(password):
            raise AuthenticationFailed("Identifiants invalides.")
        
        # Vérifier si l'utilisateur est actif
        if not user.is_active:
            raise AuthenticationFailed("Votre compte n'est pas actif ou est bloqué.")
        
        data['user'] = user
        return data
       

class AdminSerializer(UserSerializer):
    password = serializers.CharField(write_only=True, required=False)
    class Meta(UserSerializer.Meta):
        model = Admin
        fields = UserRegisterSerializer.Meta.fields + ['date_entree', 'institution']
    
    def create(self, validated_data):
        password = validated_data.pop('password')
        admin = Admin(**validated_data)
        admin.set_password(password)  # Hachage du mot de passe
        admin.save()
        # Génération des identifiants sécurisés
        activation_url = generate_activation_link(admin, settings.FRONTEND_BASE_URL)
        send_activation_email(admin, subject="Activation du compte", url=activation_url)
        return admin


class SuperAdminSerializer(UserSerializer):
    class Meta(UserSerializer.Meta):
        model = SuperAdmin
        fields = UserSerializer.Meta.fields
        

class ParentSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Parent
        fields = ['email', 'password', 'nom', 'prenom', 'telephone', 'pays_residence', 'institution']

    def create(self, validated_data):
        email = validated_data.get('email')
        password = validated_data.pop('password')

        # Vérifiez si un utilisateur avec cet email existe déjà
        if get_user_model().objects.filter(email=email).exists():
            raise serializers.ValidationError({'email': 'Un utilisateur avec cet email existe déjà.'})

        # Créer l'utilisateur de base
        user = Parent(**validated_data)
        user.set_password(password)
        user.save()
        return user
    

class ApprenantSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Apprenant
        fields = ['email', 'password', 'nom', 'prenom', 'telephone', 'pays_residence', 'matricule', 'date_naissance', 'groupe', 'tuteur', 'classe']

    def create(self, validated_data):
        # Récupérer le mot de passe et le retirer de validated_data
        password = validated_data.pop('password')
        email = validated_data.get('email')
        # Créer l'utilisateur de base sans les champs spécifiques à Apprenant
        user_data = {
            'email': validated_data.pop('email'),
            'nom': validated_data.pop('nom'),
            'prenom': validated_data.pop('prenom'),
            'telephone': validated_data.pop('telephone', None),
            'pays_residence': validated_data.pop('pays_residence', None),
            'password': password
        }
        user, created = get_user_model().objects.get_or_create(email=email, defaults=user_data)
        if not created:
            raise serializers.ValidationError({'email': 'Un utilisateur avec cet email existe déjà.'})
        # user = get_user_model().objects.create_user(**user_data)
        
        # Créer l'instance Apprenant et la lier à l'utilisateur de base
        apprenant = Apprenant.objects.create(
            email=user.email,  # Cela assure que l'email est bien défini
            nom=user.nom,
            prenom=user.prenom,
            telephone=user.telephone,
            pays_residence=user.pays_residence,
            matricule=validated_data.get('matricule'),
            date_naissance=validated_data.get('date_naissance'),
            groupe=validated_data.get('groupe'),
            tuteur=validated_data.get('tuteur'),
            classe=validated_data.get('classe')
        )

        return apprenant
 

class FormateurSerializer(UserSerializer):
    institutions = serializers.PrimaryKeyRelatedField(queryset=Institution.objects.all(), many=True)
    specialites = serializers.PrimaryKeyRelatedField(queryset=Specialite.objects.all(), many=True)
    groupes = serializers.PrimaryKeyRelatedField(queryset=Groupe.objects.all(), many=True)

    class Meta(UserSerializer.Meta):
        model = Formateur
        fields = UserSerializer.Meta.fields + ['institutions', 'specialites', 'groupes']

    def create(self, validated_data):
        institutions = validated_data.pop('institutions')
        specialites = validated_data.pop('specialites')
        groupes = validated_data.pop('groupes')
        formateur = Formateur.objects.create_user(**validated_data)
        formateur.institutions.set(institutions)
        formateur.specialites.set(specialites)
        formateur.groupes.set(groupes)
        activation_url = generate_activation_link(formateur, settings.FRONTEND_BASE_URL)
        send_activation_email(formateur, subject="Activation du compte", url=activation_url)
        return formateur


class ResponsableAcademiqueSerializer(UserSerializer):
    # specialite = serializers.CharField()

    class Meta(UserSerializer.Meta):
        model = ResponsableAcademique
        fields = UserSerializer.Meta.fields + ['institution', 'departement']

    def create(self, validated_data):
        responsable = ResponsableAcademique.objects.create_user(**validated_data)
        
        activation_url = generate_activation_link(responsable, settings.FRONTEND_BASE_URL)
        send_activation_email(responsable, subject="Activation du compte", url=activation_url)
        return responsable
    
    
class PasswordResetConfirmSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    confirm_password = serializers.CharField(write_only=True, min_length=8, max_length=128)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"error": "Les mots de passe ne correspondent pas."})
        return data