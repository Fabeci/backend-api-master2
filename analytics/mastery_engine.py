# analytics/mastery_engine.py
# ============================================================================
# MOTEUR DE MAÎTRISE — BKT simplifié
# Score = 45% quiz + 30% complétion + 25% temps
# ============================================================================
import logging

logger = logging.getLogger(__name__)

WEIGHTS = {'quiz': 0.45, 'completion': 0.30, 'temps': 0.25}


def get_mastery_level(score: float) -> str:
    if score < 40:  return 'non_acquis'
    if score < 70:  return 'fragile'
    if score < 90:  return 'maitrise'
    return 'expert'


def _score_temps(ratio_pct: int) -> float:
    """Transforme le ratio temps passé/estimé en score 0-100."""
    if ratio_pct <= 0:
        return 0.0
    if 50 <= ratio_pct <= 130:
        return 100.0
    if ratio_pct < 50:
        return max(0.0, float(ratio_pct) * 2.0)
    # > 130 : trop long, pénalité douce
    return max(20.0, 100.0 - (ratio_pct - 130) * 0.5)


def compute_sequence_mastery(apprenant, sequence):
    """
    Calcule et persiste le SkillMasteryScore pour (apprenant, sequence).
    Retourne l'objet SkillMasteryScore ou None si aucune donnée.
    """
    from .models import SkillMasteryScore, SequenceAnalyticsSummary

    summary = SequenceAnalyticsSummary.objects.filter(
        apprenant=apprenant, sequence=sequence
    ).first()
    if not summary:
        return None

    score_quiz = float(summary.score_moyen_quiz or 0)

    total = summary.nb_blocs_total or 1
    done  = summary.nb_blocs_completes or 0
    score_completion = min(100.0, (done / total) * 100)

    score_temps = _score_temps(summary.ratio_temps_pct or 0)

    score = (
        score_quiz       * WEIGHTS['quiz'] +
        score_completion * WEIGHTS['completion'] +
        score_temps      * WEIGHTS['temps']
    )

    module = getattr(sequence, 'module', None)
    cours  = getattr(module, 'cours', None) if module else None

    # ✅ Robuste aux doublons éventuels (pas de contrainte unique) :
    #    on prend la première ligne existante, sinon on en crée une.
    obj = SkillMasteryScore.objects.filter(
        apprenant=apprenant, sequence=sequence,
    ).order_by('pk').first()
    if obj is None:
        obj = SkillMasteryScore(apprenant=apprenant, sequence=sequence, module=module, cours=cours)
    score_precedent       = obj.score if obj.pk else None
    obj.score_quiz        = round(score_quiz, 2)
    obj.score_completion  = round(score_completion, 2)
    obj.score_temps       = round(score_temps, 2)
    obj.score_precedent   = score_precedent
    obj.score             = round(score, 2)
    obj.niveau            = get_mastery_level(score)
    obj.tendance          = _compute_tendance(score, score_precedent)
    # ✅ Confiance : quantité de preuves (complétions + quiz) — 5 preuves = 1.0
    evidence = int(summary.nb_blocs_completes or 0) + int(summary.nb_quiz_passes or 0)
    obj.confidence        = round(min(1.0, evidence / 5.0), 2)
    obj.save()

    logger.debug('[mastery] seq=%s appr=%s → %.1f (%s/%s)',
                 sequence.pk, apprenant.pk, score, obj.niveau, obj.tendance)
    return obj


def _compute_tendance(score_actuel: float, score_precedent) -> str:
    if score_precedent is None:
        return 'stable'
    delta = score_actuel - score_precedent
    if delta >= 10:
        return 'hausse'
    if delta <= -10:
        return 'baisse'
    return 'stable'


def compute_module_mastery(apprenant, module):
    """Agrège les scores de séquence pour calculer le mastery du module."""
    from .models import SkillMasteryScore
    from courses.models import Sequence

    seq_ids = list(Sequence.objects.filter(module=module).values_list('pk', flat=True))
    if not seq_ids:
        return None

    scores = list(
        SkillMasteryScore.objects.filter(apprenant=apprenant, sequence_id__in=seq_ids)
        .values_list('score', flat=True)
    )
    if not scores:
        return None

    score  = sum(scores) / len(scores)
    cours  = getattr(module, 'cours', None)

    obj = SkillMasteryScore.objects.filter(
        apprenant=apprenant, module=module,
    ).order_by('pk').first()
    if obj is None:
        obj = SkillMasteryScore(apprenant=apprenant, module=module, cours=cours)
    obj.cours  = obj.cours or cours
    obj.score  = round(score, 2)
    obj.niveau = get_mastery_level(score)
    obj.save()
    return obj


def compute_cours_mastery(apprenant, cours):
    """Agrège les scores de module pour calculer le mastery du cours."""
    from .models import SkillMasteryScore
    from courses.models import Module

    mod_ids = list(Module.objects.filter(cours=cours).values_list('pk', flat=True))
    if not mod_ids:
        return None

    scores = list(
        SkillMasteryScore.objects.filter(apprenant=apprenant, module_id__in=mod_ids)
        .values_list('score', flat=True)
    )
    if not scores:
        return None

    score = sum(scores) / len(scores)
    obj = SkillMasteryScore.objects.filter(
        apprenant=apprenant, cours=cours,
    ).order_by('pk').first()
    if obj is None:
        obj = SkillMasteryScore(apprenant=apprenant, cours=cours)
    obj.score  = round(score, 2)
    obj.niveau = get_mastery_level(score)
    obj.save()
    return obj
