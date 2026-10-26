# courses/services/difficulte.py
"""Détection prudente des difficultés à partir d'une conversation.

On ne modifie JAMAIS la maîtrise de l'apprenant : on propose seulement des
actions (quiz, révision du bloc, ressources) et on évite les doublons.
"""
from __future__ import annotations

import logging

from . import rag

logger = logging.getLogger(__name__)

MESSAGES_MIN = 3
MESSAGES_ANALYSES = 10
SEUIL_REPETITION = 2

PHRASES_DIFFICULTE = (
    "je ne comprends pas",
    "je comprends pas",
    "je suis perdu",
    "j ai du mal",
    "je n y arrive pas",
    "reexplique",
    "explique encore",
    "plus simple",
    "simplifie",
    "je bloque",
    "pas clair",
    "c est complique",
    "trop complique",
    "je ne vois pas",
)


def _normaliser(texte: str) -> str:
    return rag._sans_accents((texte or "").lower())


def analyser(conversation, messages=None) -> dict:
    """Retourne {niveau, notions, message, actions} pour la conversation."""
    if messages is None:
        messages = list(
            conversation.messages
            .filter(role="user")
            .order_by("-cree_le", "-id")[:MESSAGES_ANALYSES]
        )
        messages.reverse()

    base = {
        "niveau": "ok",
        "notions": [],
        "message": "",
        "actions": [],
    }
    if len(messages) < MESSAGES_MIN:
        return base

    textes = [(m.contenu or "") for m in messages]

    # 1) Difficulté exprimée explicitement
    explicite = any(
        phrase in _normaliser(texte)
        for texte in textes
        for phrase in PHRASES_DIFFICULTE
    )

    # 2) Notions demandées plusieurs fois (une fois par message maximum)
    occurrences: dict[str, int] = {}
    for texte in textes:
        for mot in set(rag.mots_cles(texte)):
            occurrences[mot] = occurrences.get(mot, 0) + 1

    repetes = sorted(
        (mot for mot, nombre in occurrences.items() if nombre >= SEUIL_REPETITION),
        key=lambda mot: -occurrences[mot],
    )

    if not explicite and not repetes:
        return base

    # Difficulté si : exprimée explicitement, notion répétée 3+ fois,
    # ou au moins deux notions revenues plusieurs fois.
    forts = [mot for mot in repetes if occurrences.get(mot, 0) >= 3]
    niveau = "difficulte" if (explicite or forts or len(repetes) >= 2) else "attention"
    notions = (forts + [m for m in repetes if m not in forts])[:3]

    if notions:
        message = "Tu sembles revenir plusieurs fois sur « " + " », « ".join(notions[:2]) + " »."
    else:
        message = "Tu sembles rencontrer une difficulté sur ce contenu."

    actions = [
        {"type": "quiz", "label": "Faire un quiz ciblé"},
        {"type": "revoir_bloc", "label": "Revoir ce bloc", "bloc_id": conversation.bloc_id},
    ]

    # Ressources existantes uniquement (aucune génération, aucun doublon).
    try:
        ressources = conversation.bloc.sequence.ressources_sequences.all()[:2]
        if ressources:
            actions.append({
                "type": "ressources",
                "label": "Voir les ressources",
                "ressources": [
                    {"id": r.id, "titre": r.titre, "type": r.type_ressource}
                    for r in ressources
                ],
            })
    except Exception:  # noqa: BLE001
        logger.debug("[difficulte] ressources indisponibles", exc_info=True)

    return {
        "niveau": niveau,
        "notions": notions,
        "message": message,
        "actions": actions,
    }
