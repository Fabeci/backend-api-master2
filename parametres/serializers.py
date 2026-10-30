# parametres/serializers.py
import zoneinfo

from rest_framework import serializers

from .models import ParametresPlateforme, ParametresInstitution, PreferencesUtilisateur


SESSION_ERROR = (
    "La durée d’expiration de session doit être un nombre entier d’heures "
    "(minimum 1, exemple : 24)."
)


def _session_field_messages(serializer) -> None:
    """Messages français explicites pour le champ d’expiration de session."""
    field = serializer.fields.get('securite_session_expiration_h')
    if field is None:
        return
    field.min_value = 1
    field.max_value = 8760
    field.error_messages.update({
        'invalid': SESSION_ERROR,
        'min_value': SESSION_ERROR,
        'max_value': SESSION_ERROR,
    })


class SessionExpirationValidationMixin:
    def validate_securite_session_expiration_h(self, value):
        if value is not None and not (1 <= value <= 8760):
            raise serializers.ValidationError(SESSION_ERROR)
        return value


class GeneralValidationMixin:
    """Langue FR/EN et fuseau horaire IANA."""

    def validate_langue_defaut(self, value):
        if value and value not in ('fr', 'en'):
            raise serializers.ValidationError("Langue non supportée (fr/en).")
        return value

    def validate_fuseau_horaire(self, value):
        if not value:
            return value
        try:
            zones = zoneinfo.available_timezones()
        except Exception:
            zones = set()
        # Sur un poste sans base tzdata (Windows), on ne bloque pas l'enregistrement.
        if zones and value not in zones:
            raise serializers.ValidationError(
                "Fuseau horaire IANA invalide (ex. Africa/Dakar, Europe/Paris)."
            )
        return value


class ParametresPlateformeSerializer(SessionExpirationValidationMixin, GeneralValidationMixin, serializers.ModelSerializer):
    class Meta:
        model  = ParametresPlateforme
        exclude = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _session_field_messages(self)


class ParametresInstitutionSerializer(SessionExpirationValidationMixin, GeneralValidationMixin, serializers.ModelSerializer):
    class Meta:
        model  = ParametresInstitution
        exclude = ['id', 'institution']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _session_field_messages(self)


class PreferencesUtilisateurSerializer(serializers.ModelSerializer):
    class Meta:
        model  = PreferencesUtilisateur
        exclude = ['id', 'user']
