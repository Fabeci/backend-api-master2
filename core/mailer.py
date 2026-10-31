# core/mailer.py
# ============================================================================
# Envoi d'e-mail « sûr » : un échec SMTP (identifiants absents, réseau…) ne
# doit JAMAIS faire échouer une création de compte ou d'établissement
# (transactions atomiques). L'erreur est journalisée, jamais propagée.
#
# Supporte le HTML + les images inline (logo SOMAPRO via Content-ID).
# ============================================================================
import logging
from email.mime.image import MIMEImage
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail

logger = logging.getLogger("somapro.mail")


def safe_send_mail(subject, message, recipient_list, from_email=None, fail_silently=None,
                   html_message=None, inline_images=None):
    """Wrapper de `send_mail` qui n'explose jamais. Retourne le nombre envoyé (0 si échec).

    - `html_message` : version HTML (EmailMultiAlternatives).
    - `inline_images` : liste de tuples (content_id, chemin) pour les logos.
    """
    if fail_silently is None:
        fail_silently = getattr(settings, "EMAIL_FAIL_SILENTLY", True)

    from_addr = from_email or getattr(settings, "DEFAULT_FROM_EMAIL", None)

    try:
        if html_message:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=from_addr,
                to=recipient_list,
            )
            msg.attach_alternative(html_message, "text/html")
            for cid, path in (inline_images or []):
                try:
                    with open(path, "rb") as fh:
                        image = MIMEImage(fh.read())
                    image.add_header("Content-ID", f"<{cid}>")
                    image.add_header("Content-Disposition", "inline", filename=Path(path).name)
                    msg.attach(image)
                except OSError as exc:
                    logger.warning("[mail] image inline introuvable %s : %s", path, exc)
            return msg.send(fail_silently=fail_silently)

        return send_mail(
            subject=subject,
            message=message,
            from_email=from_addr,
            recipient_list=recipient_list,
            fail_silently=fail_silently,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[mail] Échec d'envoi à %s : %s", recipient_list, exc)
        return 0
