# analytics/services/outcome_engine.py
# ============================================================================
# MESURE D'EFFICACITÉ DES INTERVENTIONS (Phase 12)
#
# Compare AVANT / APRÈS une intervention (performance + maîtrise), calcule la
# complétion, l'amélioration et l'effectivité (efficace / partielle / inefficace).
# ============================================================================
import logging
from statistics import mean

from django.utils import timezone

logger = logging.getLogger(__name__)


def _avg(values):
    return round(mean(values), 1) if values else None


def _perf_split(apprenant, cutoff):
    """Moyennes de performance avant/après `cutoff` (quiz + évaluations)."""
    from evaluations.models import PassageQuiz, PassageEvaluation

    before, after = [], []
    for p in PassageQuiz.objects.filter(apprenant=apprenant, termine=True, score__isnull=False):
        d = p.date_passage
        (after if (d and d >= cutoff) else before).append(float(p.score))
    for p in PassageEvaluation.objects.filter(apprenant=apprenant, note__isnull=False).select_related('evaluation'):
        d = p.date_soumission or p.date_debut
        bareme = float(getattr(p.evaluation, 'bareme', 20) or 20)
        v = round((float(p.note) / bareme) * 100, 1)
        (after if (d and d >= cutoff) else before).append(v)
    return _avg(before), _avg(after)


def _mastery(intervention):
    from analytics.models import SkillMasteryScore, CompetenceMastery, LearnerLearningState

    if intervention.sequence_id:
        m = SkillMasteryScore.objects.filter(
            apprenant=intervention.apprenant, sequence_id=intervention.sequence_id,
        ).first()
        if m:
            return m.score_precedent, m.score
    if intervention.competence_id:
        cm = CompetenceMastery.objects.filter(
            apprenant=intervention.apprenant, competence_id=intervention.competence_id,
        ).first()
        if cm:
            return cm.score_precedent, cm.score
    ls = LearnerLearningState.objects.filter(apprenant=intervention.apprenant).first()
    return None, (ls.avg_mastery if ls else None)


def _completion(intervention) -> float:
    parts = []
    if intervention.contenu_genere_id:
        parts.append(100.0 if intervention.contenu_genere.a_ete_consulte else 30.0)
    if intervention.quiz_genere_id:
        parts.append(100.0 if intervention.quiz_genere.passe_le else 30.0)
    return round(mean(parts), 1) if parts else 0.0


def _effectiveness(score_before, score_after):
    if score_before is not None and score_after is not None:
        imp = score_after - score_before
        if imp >= 10:  return 'efficace'
        if imp <= -5:  return 'inefficace'
        return 'partielle'
    if score_after is not None:
        if score_after >= 60: return 'efficace'
        if score_after < 50:  return 'inefficace'
        return 'partielle'
    return 'non_mesuree'


def measure_intervention(intervention, save: bool = True):
    """Calcule et persiste l'`InterventionOutcome` d'une intervention."""
    from analytics.models import InterventionOutcome

    cutoff = intervention.created_at or timezone.now()
    before, after = _perf_split(intervention.apprenant, cutoff)
    m_before, m_after = _mastery(intervention)
    completion = _completion(intervention)
    improvement = round(after - before, 1) if (before is not None and after is not None) else None
    effectiveness = _effectiveness(before, after)

    obj, _ = InterventionOutcome.objects.get_or_create(
        intervention=intervention, defaults={'apprenant': intervention.apprenant},
    )
    obj.apprenant = intervention.apprenant
    obj.score_before = before
    obj.score_after = after
    obj.mastery_before = m_before
    obj.mastery_after = m_after
    obj.completion = completion
    obj.improvement = improvement
    obj.effectiveness = effectiveness
    obj.details = {'intervention_type': intervention.intervention_type, 'priority': intervention.priority}
    obj.measured_at = timezone.now()
    if save:
        obj.save()
    return obj


def on_intervention_activity(intervention, kind: str):
    """Appelé quand l'apprenant consomme le contenu/quiz d'une intervention."""
    try:
        if kind == 'quiz':
            intervention.status = 'terminee'
            intervention.completed_at = timezone.now()
            intervention.save(update_fields=['status', 'completed_at'])
        elif intervention.status == 'proposee':
            intervention.status = 'en_cours'
            intervention.save(update_fields=['status'])
        measure_intervention(intervention)
    except Exception as e:  # noqa: BLE001
        logger.warning('[outcome] échec mesure intervention %s : %s', getattr(intervention, 'pk', None), e)


def refresh_outcomes(apprenant) -> list:
    """Re-mesure les interventions disposant d'un contenu/quiz."""
    from analytics.models import LearningIntervention

    ivs = LearningIntervention.objects.filter(
        apprenant=apprenant, status__in=['en_cours', 'terminee'],
    ).exclude(contenu_genere__isnull=True, quiz_genere__isnull=True)
    return [measure_intervention(iv) for iv in ivs]
