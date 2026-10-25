# users/authentication.py
"""
Authentification DRF par token AVEC expiration.

On conserve le schéma `Authorization: Token <clé>` et la réponse de login
existante (`data.token`) → **compatible** avec le frontend actuel, tout en
ajoutant une durée de vie configurable (`AUTH_TOKEN_TTL`, en secondes).
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """Token DRF à expiration GLISSANTE.

    `AUTH_TOKEN_TTL` est un délai d'INACTIVITÉ (et non une durée de vie fixe) :
    chaque requête authentifiée repousse l'échéance. Un utilisateur actif n'est
    donc jamais déconnecté ; seule une longue inactivité ferme la session.
    """

    keyword = "Token"

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)

        ttl = getattr(settings, "AUTH_TOKEN_TTL", None)
        if not ttl:
            return user, token

        now = timezone.now()
        ttl = int(ttl)

        # 1) Inactivité trop longue -> session expirée
        if token.created < now - timedelta(seconds=ttl):
            token.delete()
            raise AuthenticationFailed(
                "Votre session a expiré. Veuillez vous reconnecter."
            )

        # 2) Activité -> on repousse l'échéance (écriture limitée : au plus
        #    une fois par `AUTH_TOKEN_RENEW_AFTER` secondes).
        renew_after = int(getattr(settings, "AUTH_TOKEN_RENEW_AFTER", 300))
        if token.created < now - timedelta(seconds=renew_after):
            token.created = now
            token.save(update_fields=["created"])

        return user, token
