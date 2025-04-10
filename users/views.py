import uuid
from django.conf import settings
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.urls import reverse
from users.utils import send_activation_email
from .models import (
    Admin, SuperAdmin, Parent, Apprenant, Formateur, ResponsableAcademique, User
)
from .serializers import (
    AdminSerializer, PasswordResetConfirmSerializer, SuperAdminSerializer, ParentSerializer, ApprenantSerializer, FormateurSerializer, ResponsableAcademiqueSerializer, UserLoginSerializer
)
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import login
from django.utils.encoding import force_str
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from users.models import User, UserRole, Admin, Apprenant, Parent, Formateur, ResponsableAcademique
from .models import User, UserRole, Admin, Apprenant, Parent, Formateur, ResponsableAcademique
import uuid


class RegisterAPIView(APIView):
    def post(self, request):
        data = request.data
        email = data.get("email")
        password = data.get("password")
        role_name = data.get("role")

        if not email or not password or not role_name:
            return Response(
                {"status": status.HTTP_400_BAD_REQUEST, "message": "Email, mot de passe et rôle sont requis", "success": False, "data": None},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            role = UserRole.objects.get(name=role_name)
        except UserRole.DoesNotExist:
            return Response(
                {"status": status.HTTP_400_BAD_REQUEST, "message": "Rôle invalide", "success": False, "data": None},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier si l'utilisateur existe déjà
        if User.objects.filter(email=email).exists():
            return Response(
                {"status": status.HTTP_400_BAD_REQUEST, "message": "Cet email est déjà utilisé", "success": False, "data": None},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Création du profil associé en fonction du rôle
        if role.name == "Admin":
            user = Admin.objects.create_user(
                email=email,
                password=password,
                nom=data.get("nom"),
                prenom=data.get("prenom"),
                telephone=data.get("telephone"),
                pays_residence_id=data.get("pays_residence"),
                role=role,
                activation_token=str(uuid.uuid4()),
                date_entree=data.get("date_entree"), 
                institution_id=data.get("institution")
            )
        elif role.name == "Apprenant":
            user = Apprenant.objects.create_user(
                email=email,
                password=password,
                nom=data.get("nom"),
                prenom=data.get("prenom"),
                telephone=data.get("telephone"),
                pays_residence_id=data.get("pays_residence"),
                role=role,
                activation_token=str(uuid.uuid4()),
                matricule=data.get("matricule"),
                date_naissance=data.get("date_naissance"),
                groupe_id=data.get("groupe"),
                tuteur_id=data.get("tuteur"),
                classe_id=data.get("classe"),
            )
        elif role.name == "Parent":
            user = Parent.objects.create_user(
                email=email,
                password=password,
                nom=data.get("nom"),
                prenom=data.get("prenom"),
                telephone=data.get("telephone"),
                pays_residence_id=data.get("pays_residence"),
                role=role,
                activation_token=str(uuid.uuid4()),
                institution_id=data.get("institution")
            )
        elif role.name == "Formateur":
            user = Formateur.objects.create_user(
                email=email,
                password=password,
                nom=data.get("nom"),
                prenom=data.get("prenom"),
                telephone=data.get("telephone"),
                pays_residence_id=data.get("pays_residence"),
                role=role,
                activation_token=str(uuid.uuid4()),
            )
            
            institutions = data.get("institutions", [])
            specialites = data.get("specialites", [])
            groupes = data.get("groupes", [])

            # Si les données sont None, les remplacer par des listes vides
            user.institutions.set(institutions if institutions is not None else [])
            user.specialites.set(specialites if specialites is not None else [])
            user.groupes.set(groupes if groupes is not None else [])
        elif role.name == "Responsable Académique":
            user = ResponsableAcademique.objects.create(
                email=email,
                password=password,
                nom=data.get("nom"),
                prenom=data.get("prenom"),
                telephone=data.get("telephone"),
                pays_residence_id=data.get("pays_residence"),
                role=role,
                activation_token=str(uuid.uuid4()),
                institution_id=data.get("institution"),
                departement_id=data.get("departement"),
            )

        # Envoi de l'email d'activation
        self.send_activation_email(user)

        return Response(
            {
                "status": status.HTTP_201_CREATED,
                "message": "Utilisateur créé avec succès. Vérifiez votre email pour activer votre compte.",
                "success": True,
                "data": {"user_id": user.id, "email": user.email}
            },
            status=status.HTTP_201_CREATED
        )

    def send_activation_email(self, user):
        # Logique pour envoyer un email d'activation
        activation_link = f"{settings.FRONTEND_URL}/activate/{user.activation_token}"
        subject = "Activation de votre compte"
        message = f"Bonjour {user.nom},\n\nVeuillez activer votre compte en cliquant sur le lien suivant : {activation_link}"
        send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])


class ActivateAccountAPIView(APIView):
    def get(self, request, token):
        user = get_object_or_404(User, activation_token=token)

        if user.is_active:
            return Response({"message": "Ce compte est déjà activé", "success": False, "status": status.HTTP_400_BAD_REQUEST}, status=status.HTTP_400_BAD_REQUEST)

        user.is_active = True
        user.activation_token = None  # Supprime le token après activation
        user.save()

        return Response({"message": "Compte activé avec succès"}, status=status.HTTP_200_OK)
    
    
def activate_user_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True  # Activer l'utilisateur
        user.save()
        return HttpResponse("Votre compte a été activé avec succès.")
    else:
        return HttpResponse("Le lien d'activation est invalide ou expiré.")
    
    
# Exemple pour Admin
class UserLoginAPIView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']

            # Vérifiez si l'utilisateur est activé
            if not user.is_active:
                return Response({"message": "Le compte est désactivé."}, status=status.HTTP_400_BAD_REQUEST)

            # Connectez l'utilisateur
            login(request, user)

            # Récupérez ou créez un token pour l'utilisateur
            token, created = Token.objects.get_or_create(user=user)

            return Response({
                "message": "Connexion réussie.",
                "token": token.key  # Retournez le token
            }, status=status.HTTP_200_OK)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
    
class AdminListCreateAPIView(APIView):
    def get(self, request, *args, **kwargs):
        admins = Admin.objects.all()
        serializer = AdminSerializer(admins, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = AdminSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Compte créé avec succès. Vérifiez votre mail pour l'activer."},
                status=status.HTTP_201_CREATED
            )
        # Retourner un seul message d'erreur général
        all_errors = [
            f"{field}: {', '.join(messages)}"
            for field, messages in serializer.errors.items()
        ]
        error_message = " ".join(all_errors)  # Combiner toutes les erreurs en une seule chaîne
        return Response({"message": error_message}, status=status.HTTP_400_BAD_REQUEST)


# Exemple pour Apprenant
class ApprenantListCreateAPIView(APIView):
    def get(self, request, *args, **kwargs):
        apprenants = Apprenant.objects.all()
        serializer = ApprenantSerializer(apprenants, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = ApprenantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {   
                    "message": "Compte créé avec succès. Vérifiez votre mail pour l'activer.",
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED
            )
        # Retourner un seul message d'erreur général
        all_errors = [
            f"{field}: {', '.join(messages)}"
            for field, messages in serializer.errors.items()
        ]
        error_message = " ".join(all_errors)  # Combiner toutes les erreurs en une seule chaîne
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": error_message
            }, status=status.HTTP_400_BAD_REQUEST)
    
 
# SuperAdmin   
class SuperAdminListCreateAPIView(APIView):
    def get(self, request, *args, **kwargs):
        super_admins = SuperAdmin.objects.all()
        serializer = SuperAdminSerializer(super_admins, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = SuperAdminSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Parent
class ParentListCreateAPIView(APIView):
    def get(self, request, *args, **kwargs):
        parents = Parent.objects.all()
        serializer = ParentSerializer(parents, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = ParentSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {   
                    "message": "Compte créé avec succès.",
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED
            )
        # Retourner un seul message d'erreur général
        all_errors = [
            f"{field}: {', '.join(messages)}"
            for field, messages in serializer.errors.items()
        ]
        error_message = " ".join(all_errors)  # Combiner toutes les erreurs en une seule chaîne
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": error_message
            }, status=status.HTTP_400_BAD_REQUEST)


# Formateur
class FormateurListCreateAPIView(APIView):
    def get(self, request, *args, **kwargs):
        formateurs = Formateur.objects.all()
        serializer = FormateurSerializer(formateurs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = FormateurSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {   
                    "message": "Compte créé avec succès. Vérifiez votre mail pour l'activer.",
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED
            )
        # Retourner un seul message d'erreur général
        all_errors = [
            f"{field}: {', '.join(messages)}"
            for field, messages in serializer.errors.items()
        ]
        error_message = " ".join(all_errors)  # Combiner toutes les erreurs en une seule chaîne
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": error_message
            }, status=status.HTTP_400_BAD_REQUEST)


# ResponsableAcademique
class ResponsableAcademiqueListCreateAPIView(APIView):
    def get(self, request, *args, **kwargs):
        responsables = ResponsableAcademique.objects.all()
        serializer = ResponsableAcademiqueSerializer(responsables, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        serializer = ResponsableAcademiqueSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {   
                    "message": "Compte créé avec succès. Vérifiez votre mail pour l'activer.",
                    "status": status.HTTP_201_CREATED
                },
                status=status.HTTP_201_CREATED
            )
        # Retourner un seul message d'erreur général
        all_errors = [
            f"{field}: {', '.join(messages)}"
            for field, messages in serializer.errors.items()
        ]
        error_message = " ".join(all_errors)  # Combiner toutes les erreurs en une seule chaîne
        return Response(
            {
                "status": status.HTTP_400_BAD_REQUEST,
                "message": error_message
            }, status=status.HTTP_400_BAD_REQUEST)
    

class ActivateUserAPIView(APIView):
    """
    APIView pour activer un utilisateur via un lien d'activation.
    """

    def get(self, request, uidb64, token, *args, **kwargs):
        try:
            # Décoder l'UID
            uid = urlsafe_base64_decode(uidb64).decode()
            user = get_object_or_404(User, pk=uid)

            # Vérifier le jeton
            if default_token_generator.check_token(user, token):
                if not user.is_active:
                    user.is_active = True
                    user.save()
                    return Response(
                        {"status": status.HTTP_200_OK, "message": "Compte activé avec succès."},
                        status=status.HTTP_200_OK
                    )
                else:
                    return Response(
                        {"status": status.HTTP_400_BAD_REQUEST, "error": "Le compte est déjà activé."},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response(
                    {"status": status.HTTP_400_BAD_REQUEST, "error": "Lien d'activation invalide ou expiré."},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (ValueError, TypeError, User.DoesNotExist):
            return Response(
                {"status": status.HTTP_400_BAD_REQUEST, "error": "Lien d'activation invalide."},
                status=status.HTTP_400_BAD_REQUEST
            )


class LogoutAPIView(APIView):
    """
    API pour déconnecter l'utilisateur en supprimant son token d'authentification.
    """
    permission_classes = [IsAuthenticated]  # L'utilisateur doit être authentifié

    def post(self, request, *args, **kwargs):
        try:
            # Supprimer le token de l'utilisateur connecté
            token = Token.objects.get(user=request.user)
            token.delete()

            return Response(
                {"status": status.HTTP_200_OK, "message": "Déconnexion réussie."},
                status=status.HTTP_200_OK
            )
        except Token.DoesNotExist:
            return Response(
                {"status": status.HTTP_400_BAD_REQUEST, "message": "Aucun token trouvé pour cet utilisateur."},
                status=status.HTTP_400_BAD_REQUEST
            )
            

class PasswordResetAPIView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        try:
            user = get_user_model().objects.get(email=email)
            uid = urlsafe_base64_encode(str(user.pk).encode())
            token = default_token_generator.make_token(user)

            # Construction du lien de réinitialisation
            reset_link = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
            reset_url = f"{settings.FRONTEND_BASE_URL}{reset_link}"
            # Appel de la fonction pour envoyer l'email de réinitialisation
            send_activation_email(user, subject="Renitialisation du mot de passe", url=reset_link)
            return Response({"message": "Un email de réinitialisation a été envoyé à votre adresse."}, status=status.HTTP_200_OK)
        except get_user_model().DoesNotExist:
            return Response({"error": "Utilisateur non trouvé avec cet email."}, status=status.HTTP_404_NOT_FOUND)
        

class PasswordResetConfirmAPIView(generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request, uidb64, token, *args, **kwargs):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"error": "Lien invalide ou utilisateur non trouvé."}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({"error": "Jeton invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({"message": "Mot de passe réinitialisé avec succès."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)