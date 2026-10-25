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
    
    
_STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "NOT_AUTHENTICATED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "THROTTLED",
}


def _flatten_field_errors(data) -> dict:
    """Normalise les erreurs (serializer.errors / DRF) en {champ: [messages]}."""
    out = {}
    if isinstance(data, dict):
        for key, val in data.items():
            if key in ("detail", "status", "message", "success", "code", "errors"):
                continue
            msgs = []
            if isinstance(val, (list, tuple)):
                for item in val:
                    if isinstance(item, dict):
                        for sub in item.values():
                            msgs.extend(str(v) for v in (sub if isinstance(sub, list) else [sub]))
                    else:
                        msgs.append(str(item))
            elif isinstance(val, dict):
                for sub in val.values():
                    msgs.extend(str(v) for v in (sub if isinstance(sub, list) else [sub]))
            else:
                msgs.append(str(val))
            cleaned = [m for m in msgs if m]
            if cleaned:
                out[str(key)] = cleaned
    return out


def custom_exception_handler(exc, context):
    """
    Gestionnaire d'exceptions normalisé SOMAPRO.

    Réponse uniforme :
        { success:false, status, code, message, errors:{champ:[messages]}, detail? }
    `message` exploite le détail DRF ou la 1re erreur de champ (jamais un texte
    générique quand une information précise est disponible).
    """
    from django.db.utils import IntegrityError as DjangoIntegrityError

    response = exception_handler(exc, context)

    # Intégrité non gérée par DRF (unicité, FK…) → 409 plutôt que 500
    if response is None and isinstance(exc, DjangoIntegrityError):
        return Response(
            {
                "success": False,
                "status": status.HTTP_409_CONFLICT,
                "code": "CONFLICT",
                "message": "Cette opération entre en conflit avec des données existantes.",
                "errors": {},
            },
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, NotAuthenticated):
        return Response(
            {
                "success": False,
                "status": status.HTTP_401_UNAUTHORIZED,
                "code": "NOT_AUTHENTICATED",
                "message": "Vous devez être connecté pour effectuer cette action.",
                "errors": {},
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )

    if response is None:
        # 500 / erreur non gérée : laissée à Django (jamais exposer de détails).
        return None

    data = response.data
    code = _STATUS_CODES.get(response.status_code, "ERROR")
    field_errors = _flatten_field_errors(data)
    detail = data.get("detail") if isinstance(data, dict) else None

    if detail:
        message = str(detail)
    elif field_errors:
        first_field, msgs = next(iter(field_errors.items()))
        label = "Champ" if first_field == "non_field_errors" else first_field
        message = f"{label} : {msgs[0]}" if msgs else "Erreur de validation."
    elif response.status_code >= 500:
        message = "Une erreur interne est survenue. Veuillez réessayer plus tard."
    else:
        message = "La requête a échoué."

    payload = {
        "success": False,
        "status": response.status_code,
        "code": code,
        "message": message,
        "errors": field_errors,
    }
    if detail:
        payload["detail"] = str(detail)

    response.data = payload
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

    # ---------------------------------------------------------------------
    # Filtrage automatique par institution (si le modèle a institution_id)
    # ---------------------------------------------------------------------
    def get_queryset(self):
        qs = super().get_queryset()
        from core.tenant import default_institution_id

        if hasattr(qs.model, "institution_id"):
            iid = default_institution_id()
            if not iid:
                return qs.none()
            return qs.filter(institution_id=iid)

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
        from core.tenant import default_institution_id
        return default_institution_id()

    # ---------------------------------------------------------------------
    # DRF hooks : c'est ici qu'on force institution
    # ---------------------------------------------------------------------
    def perform_create(self, serializer):
        if self._needs_institution(serializer):
            institution_id = self._get_user_institution_id()
            if not institution_id:
                raise ValidationError({"institution": ["Institution par défaut introuvable."]})
            serializer.save(institution_id=institution_id)
            return
        serializer.save()

    def perform_update(self, serializer):
        if self._needs_institution(serializer):
            institution_id = self._get_user_institution_id()
            if not institution_id:
                raise ValidationError({"institution": ["Institution par défaut introuvable."]})
            serializer.save(institution_id=institution_id)
            return
        serializer.save()

    # ---------------------------------------------------------------------
    # Responses custom : on garde ton format api_success/api_error
    # ---------------------------------------------------------------------
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