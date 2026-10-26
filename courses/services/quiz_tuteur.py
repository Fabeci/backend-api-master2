# courses/services/quiz_tuteur.py
"""Mini-quiz « Interroge-moi » généré depuis un bloc de cours.

Les bonnes réponses ne quittent jamais le serveur avant la validation :
le client reçoit uniquement l'énoncé et les options.
"""
from __future__ import annotations

import json
import logging
import re
from html import unescape

from analytics.services.llm_provider import _extract_json_block, call_llm

from django.conf import settings

from . import chat_tuteur, rag

logger = logging.getLogger(__name__)

NB_QUESTIONS = 3
NB_OPTIONS = 4
MAX_TOKENS_QUIZ = 600

SYSTEM_PROMPT = (
    "Tu es un concepteur de quiz pédagogiques pour SOMAPRO. "
    "À partir du bloc de cours fourni, génère exactement "
    f"{NB_QUESTIONS} questions à choix unique, en français, portant UNIQUEMENT "
    "sur le contenu du bloc. Chaque question a exactement "
    f"{NB_OPTIONS} options et une seule bonne réponse. "
    "Les distracteurs doivent être plausibles mais clairement faux. "
    "Ajoute une explication courte (1 à 3 phrases) par question. "
    "Réponds STRICTEMENT en JSON, sans texte autour, au format : "
    '{"questions":[{"question":"...","options":["...","...","...","..."],'
    '"bonne_reponse":0,"explication":"..."}]}'
)


def _parser_json(texte: str) -> dict | None:
    brut = _extract_json_block(texte or "")
    try:
        return json.loads(brut)
    except Exception:  # noqa: BLE001
        pass
    # Tolérance : premier objet JSON trouvé.
    debut = brut.find("{")
    fin = brut.rfind("}")
    if debut != -1 and fin > debut:
        try:
            return json.loads(brut[debut:fin + 1])
        except Exception:  # noqa: BLE001
            return None
    return None


def _prompt(conversation) -> str:
    bloc = conversation.bloc
    ctx = chat_tuteur.contexte_bloc(bloc)

    lignes = [
        f"COURS : {ctx['cours']}",
        f"MODULE : {ctx['module']}",
        f"SÉQUENCE : {ctx['sequence']}",
        f"BLOC : {ctx['bloc']} ({ctx['type_bloc']})",
    ]
    if ctx["objectifs"]:
        lignes.append(f"OBJECTIFS : {ctx['objectifs']}")

    if ctx["contenu_disponible"]:
        lignes.append("CONTENU DU BLOC :\n" + ctx["contenu"][:2000])
    else:
        lignes.append(
            "CONTENU DU BLOC : non disponible (média/fichier). "
            "Appuie-toi sur le titre et les objectifs, sans inventer."
        )

    try:
        extraits = rag.rechercher(bloc.sequence.module.cours, bloc.titre)
    except Exception:  # noqa: BLE001
        extraits = []
    if extraits:
        lignes.append("EXTRAITS DE DOCUMENTS :")
        for index, extrait in enumerate(extraits[:2], start=1):
            page = f", page {extrait.get('page')}" if extrait.get("page") else ""
            lignes.append(
                f"[{index}] ({extrait.get('source_nom')}{page}) : "
                f"{extrait.get('texte', '')[:700]}"
            )

    lignes.append(f"Génère {NB_QUESTIONS} questions maintenant, au format JSON demandé.")
    return "\n\n".join(lignes)


def _valider_questions(data) -> list[dict]:
    # Certains modèles renvoient directement la liste de questions.
    if isinstance(data, list):
        brut = data
    elif isinstance(data, dict):
        brut = data.get("questions")
    else:
        return []
    if not isinstance(brut, list):
        return []

    valides: list[dict] = []
    for item in brut[:NB_QUESTIONS]:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        options = item.get("options")
        bonne = item.get("bonne_reponse")

        if not question or not isinstance(options, list) or len(options) != NB_OPTIONS:
            continue
        options = [
            re.sub(r"\s+", " ", unescape(str(o)).replace("\xa0", " ")).strip()[:300]
            for o in options
        ]
        if any(not o for o in options):
            continue
        # « B » / « b » → 1
        if isinstance(bonne, str) and bonne.strip().upper()[:1] in ("A", "B", "C", "D"):
            bonne = "ABCD".index(bonne.strip().upper()[:1])
        try:
            bonne = int(bonne)
        except Exception:  # noqa: BLE001
            continue
        if not 0 <= bonne < NB_OPTIONS:
            continue

        valides.append({
            "question": re.sub(r"\s+", " ", unescape(question).replace("\xa0", " ")).strip()[:500],
            "options": options,
            "bonne_reponse": bonne,
            "explication": str(item.get("explication") or "").strip()[:600],
        })

    return valides


def generer_quiz(conversation):
    """Retourne (questions, erreur). Les questions contiennent la clé de correction."""
    provider = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()
    if provider == "mock":
        return [], (
            "L'assistant IA n'est pas configuré (mode démonstration). "
            "Renseignez AI_PROVIDER et une clé API pour générer un quiz."
        )

    try:
        rag.assurer_index_bloc(conversation.bloc)
    except Exception:  # noqa: BLE001
        logger.exception("[quiz_tuteur] indexation RAG impossible")

    resultat = call_llm(
        SYSTEM_PROMPT,
        _prompt(conversation),
        json_mode=True,
        max_tokens=MAX_TOKENS_QUIZ,
        timeout=75,
    )
    if resultat.get("error"):
        return [], f"IA indisponible : {resultat['error']}"

    questions = _valider_questions(_parser_json(resultat.get("content") or ""))
    if len(questions) < 2:
        return [], "Le quiz généré est incomplet. Réessayez."

    return questions, None


def questions_publiques(questions: list[dict]) -> list[dict]:
    """Version envoyée au client : sans bonne réponse ni explication."""
    return [
        {"index": index, "question": q["question"], "options": q["options"]}
        for index, q in enumerate(questions)
    ]


def corriger(questions: list[dict], reponses: list) -> tuple[float, list[dict]]:
    """Note les réponses et retourne (score/100, détails avec corrections)."""
    details: list[dict] = []
    bonnes = 0

    for index, question in enumerate(questions):
        choix = reponses[index] if index < len(reponses) else None
        try:
            choix = int(choix) if choix is not None else None
        except Exception:  # noqa: BLE001
            choix = None
        correct = choix == question["bonne_reponse"]
        bonnes += 1 if correct else 0
        details.append({
            "index": index,
            "choix": choix,
            "bonne_reponse": question["bonne_reponse"],
            "correct": correct,
            "explication": question.get("explication", ""),
        })

    score = round(100.0 * bonnes / max(1, len(questions)), 1)
    return score, details
