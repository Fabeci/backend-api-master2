# gamification/streak_engine.py
import logging
from datetime import date, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

STREAK_BONUS = {7: 'streak_7j', 30: 'streak_30j', 90: 'streak_90j'}


def record_activity(apprenant):
    """
    Appeler chaque fois qu'un apprenant réalise une activité pédagogique.
    Met à jour le streak et déclenche les bonus de palier.
    """
    from .models import Streak
    from .xp_engine import award_xp

    today = date.today()
    streak, _ = Streak.objects.get_or_create(apprenant=apprenant)

    if streak.derniere_activite == today:
        return  # déjà enregistré aujourd'hui

    yesterday = today - timedelta(days=1)

    if streak.derniere_activite == yesterday:
        # Continuité — on prolonge le streak
        streak.streak_actuel += 1
    elif streak.derniere_activite == today - timedelta(days=2) and streak.protections_dispo > 0:
        # Protection auto si 1 jour manquant et protection disponible
        streak.streak_actuel += 1
        streak.protections_dispo     -= 1
        streak.protections_utilisees += 1
        logger.info('[streak] Protection utilisée auto — appr=%s', apprenant.pk)
    elif streak.peut_reparer and streak.derniere_activite and (today - streak.derniere_activite).days <= 2:
        # Réparation manuelle déjà demandée
        streak.streak_actuel += 1
        streak.peut_reparer   = False
        streak.reparations_ce_mois += 1
    else:
        # Streak brisé
        if streak.streak_actuel >= 3 and streak.reparations_ce_mois < 1:
            streak.peut_reparer = True
            logger.info('[streak] Streak brisé à %s — réparation possible — appr=%s',
                        streak.streak_actuel, apprenant.pk)
        streak.streak_actuel = 1

    streak.derniere_activite = today
    streak.streak_max = max(streak.streak_max, streak.streak_actuel)

    # Bonus de palier
    for palier, source in STREAK_BONUS.items():
        if streak.streak_actuel == palier:
            award_xp(apprenant, source)
            logger.info('[streak] Palier %sj atteint — appr=%s', palier, apprenant.pk)
            break

    streak.save()


def use_protection(apprenant) -> bool:
    """Utiliser manuellement une protection de streak."""
    from .models import Streak
    streak = Streak.objects.filter(apprenant=apprenant).first()
    if not streak or streak.protections_dispo < 1:
        return False
    streak.protections_dispo     -= 1
    streak.protections_utilisees += 1
    streak.save(update_fields=['protections_dispo', 'protections_utilisees', 'updated_at'])
    return True


def repair_streak(apprenant) -> bool:
    """Demander la réparation d'un streak brisé (max 1/mois)."""
    from .models import Streak
    streak = Streak.objects.filter(apprenant=apprenant).first()
    if not streak or not streak.peut_reparer or streak.reparations_ce_mois >= 1:
        return False
    streak.peut_reparer = True
    streak.save(update_fields=['peut_reparer', 'updated_at'])
    return True
