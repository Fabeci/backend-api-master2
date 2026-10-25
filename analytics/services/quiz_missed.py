# analytics/services/quiz_missed.py
#
# Détermine les questions RATÉES d'un quiz pour un apprenant, afin d'alimenter
# la génération de contenu de remédiation (trigger `quiz_rate`).
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def questions_ratees_depuis_passage(passage, limit: int = 8) -> list:
    """
    Retourne la liste des questions ratées d'un `PassageQuiz` :
    [{'question', 'bonne_reponse', 'reponse_apprenant', 'explication'}].
    """
    if passage is None:
        return []
    try:
        reponses = passage.reponses_quiz.select_related('question').all()
    except Exception as exc:  # noqa: BLE001
        logger.warning('[quiz_missed] réponses illisibles : %s', exc)
        return []

    out = []
    for rep in reponses:
        question = getattr(rep, 'question', None)
        if question is None:
            continue
        total = question.points or 1
        if (rep.points_obtenus or 0) >= total:
            continue  # réponse correcte → pas une lacune

        bonnes = list(
            question.reponses_predefinies.filter(est_correcte=True).values_list('texte', flat=True)
        )
        try:
            choisies = list(rep.choix_selectionnes.values_list('texte', flat=True))
        except Exception:  # noqa: BLE001
            choisies = []

        out.append({
            'question':          question.enonce_texte or '',
            'bonne_reponse':     ' ; '.join(bonnes),
            'reponse_apprenant': ' ; '.join(choisies) or 'non répondu',
            'explication':       getattr(question, 'explication', '') or '',
        })
        if len(out) >= limit:
            break
    return out


def questions_ratees(apprenant, quiz, limit: int = 8) -> list:
    """Questions ratées du dernier passage d'un apprenant **qui en contient**."""
    if apprenant is None or quiz is None:
        return []
    try:
        from evaluations.models import PassageQuiz
        passages = (
            PassageQuiz.objects
            .filter(apprenant=apprenant, quiz=quiz)
            .order_by('-date_passage')[:10]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning('[quiz_missed] passages introuvables : %s', exc)
        return []

    for passage in passages:
        qs = questions_ratees_depuis_passage(passage, limit)
        if qs:
            return qs
    return []
