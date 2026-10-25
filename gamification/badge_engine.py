# gamification/badge_engine.py
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)

# Conditions fonctionnelles par badge_code
# Chaque entrée : (source_déclencheurs, fn_condition(apprenant) -> bool)
BADGE_CONDITIONS = {}


def _register(code, triggers):
    """Décorateur pour enregistrer une condition de badge."""
    def decorator(fn):
        BADGE_CONDITIONS[code] = (triggers, fn)
        return fn
    return decorator


@_register('premier_pas', ['connexion'])
def _cond_premier_pas(apprenant):
    return True  # première connexion = toujours accordé


@_register('premier_cours', ['cours_done', 'bloc_complete'])
def _cond_premier_cours(apprenant):
    from analytics.models import BlocAnalyticsSummary
    return BlocAnalyticsSummary.objects.filter(apprenant=apprenant).exists()


@_register('premiere_sequence', ['sequence_done'])
def _cond_premiere_sequence(apprenant):
    from analytics.models import SequenceAnalyticsSummary
    return SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, completee_le__isnull=False
    ).exists()


@_register('premier_quiz', ['quiz_participe', 'quiz_reussi'])
def _cond_premier_quiz(apprenant):
    from evaluations.models import PassageQuiz
    return PassageQuiz.objects.filter(apprenant=apprenant).exists()


@_register('quiz_parfait', ['quiz_parfait'])
def _cond_quiz_parfait(apprenant):
    from evaluations.models import PassageQuiz
    return PassageQuiz.objects.filter(apprenant=apprenant, score=100).exists()


@_register('mention_tres_bien', ['eval_tres_bien'])
def _cond_mention_tres_bien(apprenant):
    from .models import XPTransaction
    return XPTransaction.objects.filter(apprenant=apprenant, source='eval_tres_bien').exists()


@_register('lecteur_vorace', ['bloc_complete'])
def _cond_lecteur_vorace(apprenant):
    from analytics.models import BlocAnalyticsSummary
    return BlocAnalyticsSummary.objects.filter(
        apprenant=apprenant, date_completion__isnull=False
    ).count() >= 10


@_register('streak_7j', ['streak_7j'])
def _cond_streak_7j(apprenant):
    from .models import Streak
    s = Streak.objects.filter(apprenant=apprenant).first()
    return s and s.streak_max >= 7


@_register('streak_30j', ['streak_30j'])
def _cond_streak_30j(apprenant):
    from .models import Streak
    s = Streak.objects.filter(apprenant=apprenant).first()
    return s and s.streak_max >= 30


@_register('phoenix', ['connexion', 'bloc_complete'])
def _cond_phoenix(apprenant):
    from .models import XPTransaction
    from analytics.models import BlocAnalytics
    last = BlocAnalytics.objects.filter(apprenant=apprenant).order_by('-ouvert_le').first()
    if not last:
        return False
    gap = (timezone.now() - last.ouvert_le).days
    # Phoenix : reprendre après ≥ 7 jours d'absence (détecté via streak brisé + retour)
    from .models import Streak
    streak = Streak.objects.filter(apprenant=apprenant).first()
    return streak and streak.streak_actuel >= 1 and streak.peut_reparer is False


@_register('niveau_5', ['bloc_complete', 'sequence_done'])
def _cond_niveau_5(apprenant):
    from .models import UserLevel
    lvl = UserLevel.objects.filter(apprenant=apprenant).first()
    return lvl and lvl.niveau >= 5


def check_badges_for_source(apprenant, source: str):
    """Vérifie tous les badges dont l'un des déclencheurs correspond à 'source'."""
    from .models import Badge, UserBadge
    from .xp_engine import award_xp

    badges_a_verifier = [
        code for code, (triggers, _) in BADGE_CONDITIONS.items()
        if source in triggers
    ]

    for code in badges_a_verifier:
        try:
            badge = Badge.objects.filter(code=code, est_actif=True).first()
            if not badge:
                continue
            if UserBadge.objects.filter(apprenant=apprenant, badge=badge).exists():
                continue
            _, cond_fn = BADGE_CONDITIONS[code]
            if cond_fn(apprenant):
                UserBadge.objects.create(apprenant=apprenant, badge=badge)
                logger.info('[badge] 🏅 %s → %s', badge.nom, apprenant.pk)
                if badge.xp_bonus:
                    award_xp(apprenant, 'badge_bonus', extra_xp=badge.xp_bonus)
        except Exception as e:
            logger.error('[badge] Erreur badge %s: %s', code, e)


def check_all_badges(apprenant):
    """Vérifie tous les badges (utile lors de l'initialisation du profil)."""
    from .models import Badge, UserBadge
    from .xp_engine import award_xp

    for code, (_, cond_fn) in BADGE_CONDITIONS.items():
        try:
            badge = Badge.objects.filter(code=code, est_actif=True).first()
            if not badge:
                continue
            if UserBadge.objects.filter(apprenant=apprenant, badge=badge).exists():
                continue
            if cond_fn(apprenant):
                UserBadge.objects.create(apprenant=apprenant, badge=badge)
                if badge.xp_bonus:
                    award_xp(apprenant, 'badge_bonus', extra_xp=badge.xp_bonus)
        except Exception as e:
            logger.error('[badge] Erreur check_all badge %s: %s', code, e)
