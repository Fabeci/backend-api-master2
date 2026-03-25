from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.utils.http import urlencode
from rest_framework.views import exception_handler
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.core.exceptions import ValidationError
from academics.views import api_error, api_success


def send_verification_email(user):
    """
    Envoie un e-mail de vérification au nouvel utilisateur.
    """
    token = user.generate_email_verification_token()
    verification_url = f"{settings.FRONTEND_BASE_URL}{reverse('verify-email')}?{urlencode({'token': token})}"

    subject = "Vérification de votre compte"
    message = (
        f"Bonjour {user.nom},\n\n"
        f"Cliquez sur le lien suivant pour vérifier votre e-mail : {verification_url}\n\n"
        f"Merci !"
    )

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
    response = exception_handler(exc, context)

    if isinstance(exc, NotAuthenticated):
        return Response(
            {
                "status": status.HTTP_401_UNAUTHORIZED,
                "message": "Les informations d'authentification n'ont pas été fournies."
            },
            status=status.HTTP_401_UNAUTHORIZED
        )

    if response is not None:
        response.data['status'] = response.status_code
        response.data['message'] = response.data.get('detail', 'Une erreur s’est produite.')
        response.data.pop('detail', None)

    return response


def send_activation_email(user, subject, url):
    """
    Envoie un email d'activation à l'utilisateur.
    """
    send_mail(
        subject,
        f'Cliquez sur ce lien pour activer votre compte : {url}',
        settings.EMAIL_HOST_USER,
        [user.email],
        fail_silently=False,
    )


class BaseModelViewSet(viewsets.ModelViewSet):
    """
    ViewSet de base avec :
    - filtrage automatique par institution
    - filtrage automatique par année scolaire
    - injection automatique des champs institution / année scolaire
    - réponses uniformisées
    """

    def _get_request_annee_scolaire_id(self):
        request = self.request

        annee_obj = getattr(request, "annee_scolaire", None)
        if annee_obj is not None:
            annee_id = getattr(annee_obj, "id", None)
            if annee_id:
                return annee_id

        annee_id = getattr(request, "annee_scolaire_id", None)
        if annee_id:
            return annee_id

        header_val = (
            request.headers.get("x-annee-scolaire-id")
            or request.META.get("HTTP_X_ANNEE_SCOLAIRE_ID")
        )
        if header_val:
            try:
                return int(header_val)
            except (TypeError, ValueError):
                pass

        user_annee_id = getattr(request.user, "annee_scolaire_active_id", None)
        if user_annee_id:
            return user_annee_id

        return None

    def _get_user_institution_id(self):
        return getattr(self.request.user, "institution_id", None)

    def _serializer_model(self, serializer):
        return getattr(getattr(serializer, "Meta", None), "model", None)

    def _queryset_model(self, qs):
        return getattr(qs, "model", None)

    def _apply_scope_filters(self, qs):
        user = self.request.user
        model = self._queryset_model(qs)

        if model is None:
            return qs

        if not getattr(user, "is_superuser", False):
            if hasattr(model, "institution_id"):
                institution_id = getattr(user, "institution_id", None)
                if not institution_id:
                    return qs.none()
                qs = qs.filter(institution_id=institution_id)

        annee_scolaire_id = self._get_request_annee_scolaire_id()
        if annee_scolaire_id:
            if hasattr(model, "annee_scolaire_id"):
                qs = qs.filter(annee_scolaire_id=annee_scolaire_id)
            elif hasattr(model, "annee_scolaire_active_id"):
                qs = qs.filter(annee_scolaire_active_id=annee_scolaire_id)

        return qs

    def _build_save_kwargs(self, serializer):
        user = self.request.user
        model = self._serializer_model(serializer)
        kwargs = {}

        if model is None:
            return kwargs

        if not getattr(user, "is_superuser", False):
            if hasattr(model, "institution_id"):
                institution_id = getattr(user, "institution_id", None)
                if not institution_id:
                    raise ValidationError({"institution": ["Utilisateur sans institution."]})
                kwargs["institution_id"] = institution_id

        annee_scolaire_id = self._get_request_annee_scolaire_id()
        if annee_scolaire_id:
            if hasattr(model, "annee_scolaire_id"):
                kwargs["annee_scolaire_id"] = annee_scolaire_id
            elif hasattr(model, "annee_scolaire_active_id"):
                kwargs["annee_scolaire_active_id"] = annee_scolaire_id

        return kwargs

    def get_queryset(self):
        qs = super().get_queryset()
        return self._apply_scope_filters(qs)

    def perform_create(self, serializer):
        kwargs = self._build_save_kwargs(serializer)
        serializer.save(**kwargs)

    def perform_update(self, serializer):
        kwargs = self._build_save_kwargs(serializer)
        serializer.save(**kwargs)

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

        if not serializer.is_valid():
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self.perform_create(serializer)
        except ValidationError as e:
            return api_error(
                "Erreur de validation",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        obj = serializer.instance
        return api_success(
            "Création effectuée avec succès",
            data=self.get_serializer(obj).data,
            http_status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)

        if not serializer.is_valid():
            return api_error(
                "Erreur de validation",
                errors=serializer.errors,
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self.perform_update(serializer)
        except ValidationError as e:
            return api_error(
                "Erreur de validation",
                errors=e.message_dict if hasattr(e, "message_dict") else str(e),
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        obj = serializer.instance
        return api_success(
            "Mise à jour effectuée avec succès",
            data=self.get_serializer(obj).data,
            http_status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return api_success(
            "Suppression effectuée avec succès",
            data=None,
            http_status=status.HTTP_204_NO_CONTENT,
        )