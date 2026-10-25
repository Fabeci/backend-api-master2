# core/mailer.py
# ============================================================================
# Envoi d'e-mail « sûr » : un échec SMTP (identifiants absents, réseau…) ne
# doit JAMAIS faire échouer une création de compte ou d'établissement
# (transactions atomiques). L'erreur est journalisée, jamais propagée.
# ============================================================================
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger("somapro.mail")


def safe_send_mail(subject, message, recipient_list, from_email=None, fail_silently=None):
    """Wrapper de `send_mail` qui n'explose jamais. Retourne le nombre envoyé (0 si échec)."""
    if fail_silently is None:
        fail_silently = getattr(settings, "EMAIL_FAIL_SILENTLY", True)
    try:
        return send_mail(
            subject=subject,
            message=message,
            from_email=from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=recipient_list,
            fail_silently=fail_silently,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[mail] Échec d'envoi à %s : %s", recipient_list, exc)
        return 0
