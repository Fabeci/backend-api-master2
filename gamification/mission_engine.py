# gamification/mission_engine.py
import logging
import random
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


def update_mission_progress(apprenant, action: str, delta: int = 1):
    """
    Incrémente la progression des missions actives qui ciblent 'action'.
    Déclenche la récompense XP si la mission est complétée.
    """
    from .models import UserMission
    from .xp_engine import award_xp

    missions_actives = UserMission.objects.filter(
        apprenant=apprenant,
        statut='active',
        mission__action=action,
        expire_le__gte=timezone.now(),
    ).select_related('mission')

    for um in missions_actives:
        completed = um.avancer(delta)
        if completed:
            award_xp(apprenant, 'mission_done', extra_xp=um.mission.xp_recompense)
            if um.mission.badge_recompense:
                from .models import UserBadge
                UserBadge.objects.get_or_create(
                    apprenant=apprenant, badge=um.mission.badge_recompense
                )
            logger.info('[mission] ✅ %s — appr=%s', um.mission.titre, apprenant.pk)


def generate_daily_missions(apprenant):
    """
    Génère 3 missions quotidiennes si l'apprenant n'en a pas déjà pour aujourd'hui.
    Adapte la difficulté selon le profil.
    """
    from .models import Mission, UserMission

    today       = timezone.now().date()
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow    = today_start + timedelta(days=1)

    # Déjà des missions aujourd'hui ?
    existing = UserMission.objects.filter(
        apprenant=apprenant,
        type_mission_cache='quotidienne',
        assignee_le__gte=today_start,
    ).count() if False else UserMission.objects.filter(
        apprenant=apprenant,
        mission__type_mission='quotidienne',
        assignee_le__gte=today_start,
    ).count()

    if existing >= 3:
        return []

    # Adapter selon profil
    difficulte = _target_difficulte(apprenant)
    pool = list(
        Mission.objects.filter(
            type_mission='quotidienne',
            difficulte__in=_allowed_difficultes(difficulte),
            est_active=True,
        )
    )
    if len(pool) < 3:
        pool = list(Mission.objects.filter(type_mission='quotidienne', est_active=True))

    selected = random.sample(pool, min(3, len(pool)))
    created  = []

    for mission in selected:
        um = UserMission.objects.create(
            apprenant=apprenant,
            mission=mission,
            cible=mission.quantite,
            expire_le=tomorrow,
        )
        created.append(um)

    logger.debug('[mission] %s missions générées pour appr=%s', len(created), apprenant.pk)
    return created


def _target_difficulte(apprenant) -> str:
    try:
        profil = apprenant.profil_adaptatif
        if profil.score_risque_decrochage >= 60:
            return 'facile'
        if profil.score_engagement >= 80:
            return 'difficile'
    except Exception:
        pass
    return 'normale'


def _allowed_difficultes(cible: str) -> list:
    map_ = {
        'facile':    ['facile'],
        'normale':   ['facile', 'normale'],
        'difficile': ['normale', 'difficile', 'defi'],
    }
    return map_.get(cible, ['facile', 'normale'])


def expire_old_missions():
    """Tâche périodique : expire les missions non complétées passées la deadline."""
    from .models import UserMission
    expired = UserMission.objects.filter(
        statut='active', expire_le__lt=timezone.now()
    )
    count = expired.update(statut='expiree')
    logger.info('[mission] %s missions expirées', count)
