from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils.http import urlencode
from rest_framework.views import exception_handler
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator

from academics.views import api_error, api_success

def send_verification_email(user):
    """
    Envoie un e-mail de vérification au nouvel utilisateur.
    """
    token = user.generate_email_verification_token()  # Implémentez une méthode pour générer un token sécurisé
    verification_url = f"{settings.FRONTEND_BASE_URL}{reverse('verify-email')}?{urlencode({'token': token})}"
    
    subject = "Vérification de votre compte"
    message = f"Bonjour {user.nom},\n\nCliquez sur le lien suivant pour vérifier votre e-mail : {verification_url}\n\nMerci !"
    
    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=False,
    )
    
    
def custom_exception_handler(exc, context):
    """
    Gestionnaire personnalisé pour les exceptions.
    """
    # Appelez le gestionnaire d'exceptions par défaut fourni par DRF
    response = exception_handler(exc, context)

    # Personnalisez le message pour certaines exceptions spécifiques
    if isinstance(exc, NotAuthenticated):
        return Response(
            {
                "status": status.HTTP_401_UNAUTHORIZED,
                "message": "Les informations d'authentification n'ont pas été fournies."
            },
            status=status.HTTP_401_UNAUTHORIZED
        )
    # elif isinstance(exc, AuthenticationFailed):
    #     return Response(
    #         {
    #             "status": status.HTTP_401_UNAUTHORIZED,
    #             "message": "Vos informations d'authentification sont incorrectes."
    #         },
    #         status=status.HTTP_401_UNAUTHORIZED
    #     )

    # Si une réponse existe déjà, laissez-la intacte
    if response is not None:
        response.data['status'] = response.status_code
        response.data['message'] = response.data.get('detail', 'Une erreur s’est produite.')
        response.data.pop('detail', None)

    return response


def send_activation_email(user, subject, url):
    """
    Envoie un email d'activation à l'utilisateur.

    Args:
        user (User): Instance de l'utilisateur pour lequel envoyer l'email.
        frontend_url (str): URL de base de l'application frontend.
        subject (str): Sujet de l'email. Par défaut : "Activer votre compte".
    """

    # Envoi de l'email
    send_mail(
        subject,
        f'Cliquez sur ce lien pour activer votre compte : {url}',
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=False,
    )
    

class BaseModelViewSet(viewsets.ModelViewSet):

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return api_success(
            "Liste récupérée avec succès",
            data=serializer.data,
            http_status=status.HTTP_200_OK,
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return api_success(
            "Élément récupéré avec succès",
            data=serializer.data,
            http_status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Création effectuée avec succès",
                data=self.get_serializer(obj).data,
                http_status=status.HTTP_201_CREATED,
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if serializer.is_valid():
            obj = serializer.save()
            return api_success(
                "Mise à jour effectuée avec succès",
                data=self.get_serializer(obj).data,
                http_status=status.HTTP_200_OK,
            )
        return api_error(
            "Erreur de validation",
            errors=serializer.errors,
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_success(
            "Suppression effectuée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT,
        )
