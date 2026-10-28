# courses/services/quiz_finalisation.py
"""Effets pédagogiques de la correction d'un quiz « Interroge-moi ».

Appelé UNE SEULE FOIS, après la première correction d'un `QuizTuteur` :
  1. met à jour le résumé de séquence (maîtrise → lacunes → recommandations) ;
  2. journalise l'événement `quiz.completed` ;
  3. attribue XP / streak / missions (première correction du bloc seulement) ;
  4. trace un événement formateur avec le score et la réussite.

Chaque étape est isolée : un échec de la gamification ou de l'analytics ne doit
jamais empêcher l'apprenant de voir sa correction.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def finaliser_quiz_tuteur(quiz) -> None:
    """Applique les conséquences pédagogiques d'un quiz corrigé."""
    if not quiz or quiz.statut != 'corrige' or quiz.score is None:
        return

    from courses.models import EvenementTuteur, QuizTuteur

    apprenant = getattr(quiz, 'apprenant', None)
    bloc = getattr(quiz, 'bloc', None)
    sequence = getattr(bloc, 'sequence', None) if bloc else None
    if apprenant is None or bloc is None or sequence is None:
        return

    cours = quiz.cours or getattr(getattr(sequence, 'module', None), 'cours', None)
    score = float(quiz.score)

    # Idempotence : un seul bilan par quiz (même si l'endpoint est rejoué).
    try:
        if EvenementTuteur.objects.filter(
            type='quiz',
            metadata__evenement='quiz_termine',
            metadata__quiz_id=quiz.pk,
        ).exists():
            return
    except Exception:  # noqa: BLE001
        logger.debug('[quiz-final] vérification idempotence impossible', exc_info=True)

    # 1) Résumé de séquence → maîtrise → lacunes → recommandations.
    try:
        from analytics.services.quiz_summary import sync_sequence_quiz_summary
        sync_sequence_quiz_summary(apprenant, sequence)
    except Exception:  # noqa: BLE001
        logger.exception('[quiz-final] mise à jour du résumé impossible (quiz=%s)', quiz.pk)

    # 2) Événement pédagogique (analytics).
    try:
        from analytics.services.event_service import record_event
        record_event(
            apprenant, 'quiz.completed',
            sequence=sequence, bloc=bloc, source='tuteur',
            metadata={'quiz_id': quiz.pk, 'score': score, 'source': 'tuteur'},
        )
    except Exception:  # noqa: BLE001
        logger.exception('[quiz-final] événement quiz.completed impossible')

    # 3) Gamification : uniquement à la première correction de ce bloc.
    try:
        premiere_fois = not QuizTuteur.objects.filter(
            apprenant=apprenant, bloc=bloc, statut='corrige',
        ).exclude(pk=quiz.pk).exists()

        if premiere_fois:
            from gamification.xp_engine import award_xp
            from gamification.streak_engine import record_activity
            from gamification.mission_engine import update_mission_progress

            award_xp(apprenant, 'quiz_participe', reference_id=quiz.pk)
            record_activity(apprenant)
            update_mission_progress(apprenant, 'quiz_participe')

            if score >= 60:
                award_xp(apprenant, 'quiz_reussi', reference_id=quiz.pk)
                update_mission_progress(apprenant, 'quiz_reussi')

            if score >= 100:
                award_xp(apprenant, 'quiz_parfait', reference_id=quiz.pk)
                update_mission_progress(apprenant, 'quiz_parfait')
    except Exception:  # noqa: BLE001
        logger.exception('[quiz-final] gamification impossible (quiz=%s)', quiz.pk)

    # 4) Traçabilité formateur : score et réussite (dans metadata, sans migration).
    try:
        EvenementTuteur.objects.create(
            type='quiz',
            apprenant=apprenant,
            cours=cours,
            bloc=bloc,
            institution=getattr(cours, 'institution', None) or getattr(apprenant, 'institution', None),
            metadata={
                'evenement': 'quiz_termine',
                'quiz_id': quiz.pk,
                'score': score,
                'reussi': score >= 60,
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception('[quiz-final] événement formateur impossible (quiz=%s)', quiz.pk)
