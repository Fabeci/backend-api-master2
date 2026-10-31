# core/recaptcha.py
"""Vérification Google reCAPTCHA v3 (anti-bot / brute force).

Ne remplace pas une protection DDoS réseau : pour un volume important, utiliser
un reverse proxy / WAF (Cloudflare, nginx limit_req, etc.).
"""
import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger("somapro.recaptcha")

VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def verify_recaptcha(token, action=None, remote_ip=None):
    if not getattr(settings, "RECAPTCHA_ENABLED", False):
        return True

    secret = getattr(settings, "RECAPTCHA_SECRET_KEY", "") or ""
    if not secret:
        logger.error("[recaptcha] RECAPTCHA_ENABLED=True mais secret absent")
        return False
    if not token:
        return False

    payload = {"secret": secret, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            VERIFY_URL, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[recaptcha] vérification impossible : %s", exc)
        return bool(getattr(settings, "RECAPTCHA_FAIL_OPEN", False))

    if not result.get("success"):
        logger.info("[recaptcha] échec : %s", result.get("error-codes"))
        return False

    if action and result.get("action") and result.get("action") != action:
        logger.info("[recaptcha] action inattendue : %s (attendu %s)", result.get("action"), action)
        return False

    score = result.get("score")
    if score is not None:
        try:
            if float(score) < float(getattr(settings, "RECAPTCHA_MIN_SCORE", 0.5)):
                return False
        except (TypeError, ValueError):
            pass

    return True
