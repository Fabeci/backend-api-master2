# gamification/xp_engine.py
import logging
from datetime import date, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_streak_mult(apprenant) -> float:
    from .models import Streak
    streak = Streak.objects.filter(apprenant=apprenant).first()
    return streak.multiplicateur if streak else 1.0


def _category_for(source: str) -> str:
    from .models import SOURCE_CATEGORY
    return SOURCE_CATEGORY.get(source, 'autre')


def _daily_xp_used(apprenant, category: str) -> int:
    from .models import XPTransaction, SOURCE_CATEGORY
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    sources = [s for s, c in SOURCE_CATEGORY.items() if c == category]
    agg = XPTransaction.objects.filter(
        apprenant=apprenant, created_at__gte=today_start, source__in=sources
    ).aggregate(total=__import__('django.db.models', fromlist=['Sum']).Sum('xp'))
    return agg['total'] or 0


def _under_cap(apprenant, source: str, xp: int) -> bool:
    from .models import DAILY_CAPS
    cat = _category_for(source)
    cap = DAILY_CAPS.get(cat)
    if cap is None:
        return True
    used = _daily_xp_used(apprenant, cat)
    return (used + xp) <= cap


def award_xp(apprenant, source: str, reference_id=None, extra_xp: int = 0) -> int:
    """
    Attribue des XP à l'apprenant.
    Retourne les XP effectivement attribués (0 si plafond atteint).
    """
    from .models import XPTransaction, UserLevel, XP_TABLE

    base_xp = XP_TABLE.get(source, 0) + extra_xp
    if base_xp <= 0:
        return 0

    if not _under_cap(apprenant, source, base_xp):
        logger.debug('[xp] Plafond atteint pour %s — source=%s', apprenant.pk, source)
        return 0

    mult     = _get_streak_mult(apprenant)
    xp_final = max(1, round(base_xp * mult))

    XPTransaction.objects.create(
        apprenant=apprenant,
        source=source,
        xp=xp_final,
        multiplicateur=mult,
        reference_id=reference_id,
    )

    lvl, _ = UserLevel.objects.get_or_create(apprenant=apprenant)
    lvl.xp_total   += xp_final
    lvl.xp_semaine += xp_final
    lvl.save(update_fields=['xp_total', 'xp_semaine', 'updated_at'])
    level_up = lvl.recalculate()

    if level_up:
        logger.info('[xp] Level-up! appr=%s → Niveau %s', apprenant.pk, lvl.niveau)

    # Vérifier badges après gain XP
    try:
        from .badge_engine import check_badges_for_source
        check_badges_for_source(apprenant, source)
    except Exception as e:
        logger.error('[xp] badge check error: %s', e)

    logger.debug('[xp] +%s XP (%s ×%.2f) → appr=%s', xp_final, source, mult, apprenant.pk)
    return xp_final
