# analytics/services/refresh_guard.py
# ============================================================================
# GARDE DE FRAÎCHEUR (Phase 18)
#
# Évite de recalculer les moteurs à chaque GET (les endpoints recalculent).
# Si un calcul a eu lieu récemment (< TTL), on le saute et on renvoie l'état
# déjà persisté. Utilise le cache Django (Redis) avec repli silencieux.
# ============================================================================
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)


def fresh_or_run(apprenant, key: str, fn, seconds: int = 60) -> bool:
    """
    Exécute `fn()` au plus une fois par `seconds` pour (apprenant, key).
    Retourne True si `fn` a été exécutée, False si sautée (déjà fraîche).
    Ne casse jamais l'appelant si le cache est indisponible.
    """
    cache_key = f'le_refresh:{key}:{getattr(apprenant, "pk", 0)}'
    try:
        if cache.get(cache_key):
            return False
    except Exception:
        pass

    try:
        fn()
    finally:
        try:
            cache.set(cache_key, 1, seconds)
        except Exception:
            pass
    return True
