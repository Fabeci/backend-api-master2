# analytics/services/quiz_summary.py
"""Agrégation des scores de quiz d'une séquence.

Deux sources alimentent le résumé pédagogique :
  - les quiz d'évaluation (`evaluations.PassageQuiz`) ;
  - les quiz du tuteur (`courses.QuizTuteur`, « Interroge-moi »).

Le résumé (`SequenceAnalyticsSummary`) est la porte d'entrée du moteur de
maîtrise : le sauvegarder déclenche `on_sequence_summary_saved_mastery`
(maîtrise → lacunes → recommandations).
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def scores_quiz_sequence(apprenant_id, sequence_id) -> list[float]:
    """Tous les scores de quiz terminés de l'apprenant sur la séquence."""
    from courses.models import QuizTuteur
    from evaluations.models import PassageQuiz

    scores: list[float] = []

    evaluation_scores = (
        PassageQuiz.objects
        .filter(
            apprenant_id=apprenant_id,
            quiz__sequence_id=sequence_id,
            termine=True,
            score__isnull=False,
        )
        .values_list('score', flat=True)
    )
    scores.extend(float(s) for s in evaluation_scores if s is not None)

    tutor_scores = (
        QuizTuteur.objects
        .filter(
            apprenant_id=apprenant_id,
            bloc__sequence_id=sequence_id,
            statut='corrige',
            score__isnull=False,
        )
        .values_list('score', flat=True)
    )
    scores.extend(float(s) for s in tutor_scores if s is not None)

    return scores


def sync_sequence_quiz_summary(apprenant, sequence):
    """Recalcule et enregistre le résumé quiz de la séquence.

    Retourne (summary, nb_passages, score_moyen).
    """
    from analytics.models import SequenceAnalyticsSummary

    scores = scores_quiz_sequence(apprenant.pk, sequence.pk)
    nb = len(scores)
    moyenne = int(max(0, min(100, round(sum(scores) / nb)))) if nb else 0

    module = getattr(sequence, 'module', None)
    cours = getattr(module, 'cours', None) if module else None

    summary, _ = SequenceAnalyticsSummary.objects.get_or_create(
        apprenant=apprenant,
        sequence=sequence,
        defaults={'module': module, 'cours': cours},
    )
    summary.nb_quiz_passes = nb
    summary.score_moyen_quiz = moyenne
    summary.save(update_fields=['nb_quiz_passes', 'score_moyen_quiz'])

    logger.info(
        '[quiz-summary] seq=%s appr=%s : %s passages, moyenne=%s%%',
        sequence.pk, apprenant.pk, nb, moyenne,
    )
    return summary, nb, moyenne
