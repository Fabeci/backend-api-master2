# gamification/signals.py
import logging
from django.db.models.signals import post_save
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _get_apprenant(user):
    for attr in ('apprenant', 'profil'):
        obj = getattr(user, attr, None)
        if obj is not None:
            return obj
    try:
        from users.models import Apprenant
        return Apprenant.objects.filter(user=user).first()
    except Exception:
        return None


# ── Connexion quotidienne ────────────────────────────────────────────────────

@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    apprenant = _get_apprenant(user)
    if not apprenant:
        return
    try:
        from .xp_engine      import award_xp
        from .streak_engine  import record_activity
        from .mission_engine import generate_daily_missions

        award_xp(apprenant, 'connexion')
        record_activity(apprenant)
        generate_daily_missions(apprenant)
    except Exception as e:
        logger.error('[gamification/login] %s', e)


# ── Bloc complété ────────────────────────────────────────────────────────────

@receiver(post_save, sender='analytics.BlocAnalyticsSummary')
def on_bloc_summary_gamification(sender, instance, **kwargs):
    if not instance.apprenant:
        return
    if instance.nb_completions != 1:  # seulement la 1ère complétion
        return
    try:
        from .xp_engine       import award_xp
        from .streak_engine   import record_activity
        from .mission_engine  import update_mission_progress

        award_xp(instance.apprenant, 'bloc_complete', reference_id=instance.bloc_id)
        record_activity(instance.apprenant)
        update_mission_progress(instance.apprenant, 'bloc_complete')
    except Exception as e:
        logger.error('[gamification/bloc] %s', e)


# ── Séquence complétée ────────────────────────────────────────────────────────

@receiver(post_save, sender='analytics.SequenceAnalyticsSummary')
def on_sequence_done_gamification(sender, instance, **kwargs):
    if not instance.apprenant:
        return
    if not instance.completee_le:
        return
    # Ne récompenser qu'une seule fois (vérifier XPTransaction)
    from .models import XPTransaction
    already = XPTransaction.objects.filter(
        apprenant=instance.apprenant,
        source='sequence_done',
        reference_id=instance.sequence_id,
    ).exists()
    if already:
        return
    try:
        from .xp_engine      import award_xp
        from .mission_engine import update_mission_progress

        award_xp(instance.apprenant, 'sequence_done', reference_id=instance.sequence_id)
        update_mission_progress(instance.apprenant, 'sequence_done')
    except Exception as e:
        logger.error('[gamification/sequence] %s', e)


# ── Quiz ─────────────────────────────────────────────────────────────────────

@receiver(post_save, sender='evaluations.PassageQuiz')
def on_quiz_gamification(sender, instance, **kwargs):
    if not instance.apprenant:
        return
    try:
        from .xp_engine      import award_xp
        from .streak_engine  import record_activity
        from .mission_engine import update_mission_progress

        award_xp(instance.apprenant, 'quiz_participe', reference_id=instance.pk)
        record_activity(instance.apprenant)
        update_mission_progress(instance.apprenant, 'quiz_participe')

        if instance.termine and instance.score is not None:
            score = float(instance.score)
            if score == 100:
                award_xp(instance.apprenant, 'quiz_parfait', reference_id=instance.pk)
                update_mission_progress(instance.apprenant, 'quiz_parfait')
            elif score >= 60:
                award_xp(instance.apprenant, 'quiz_reussi', reference_id=instance.pk)
                update_mission_progress(instance.apprenant, 'quiz_reussi')
    except Exception as e:
        logger.error('[gamification/quiz] %s', e)


# ── Évaluation soumise ───────────────────────────────────────────────────────

@receiver(post_save, sender='evaluations.PassageEvaluation')
def on_eval_gamification(sender, instance, **kwargs):
    apprenant = getattr(instance, 'apprenant', None)
    if not apprenant:
        return
    try:
        from .xp_engine      import award_xp
        from .mission_engine import update_mission_progress

        if instance.statut == 'soumis':
            award_xp(apprenant, 'eval_soumise', reference_id=instance.pk)
            update_mission_progress(apprenant, 'eval_soumise')

        if instance.statut == 'corrige' and instance.note_obtenue is not None:
            bareme = getattr(instance.evaluation, 'bareme', 100) or 100
            pct    = (float(instance.note_obtenue) / float(bareme)) * 100
            if pct >= 90:
                award_xp(apprenant, 'eval_tres_bien', reference_id=instance.pk)
            elif pct >= 80:
                award_xp(apprenant, 'eval_mention', reference_id=instance.pk)
            elif pct >= 60:
                award_xp(apprenant, 'eval_reussie', reference_id=instance.pk)
            update_mission_progress(apprenant, 'eval_reussie')
    except Exception as e:
        logger.error('[gamification/eval] %s', e)
