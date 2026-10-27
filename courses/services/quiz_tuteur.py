# courses/services/quiz_tuteur.py
"""Mini-quiz « Interroge-moi » généré depuis un bloc de cours.

Les bonnes réponses ne quittent jamais le serveur avant la validation :
le client reçoit uniquement l'énoncé et les options.
"""
from __future__ import annotations

import json
import logging
import random
import re
from html import unescape

from analytics.services.llm_provider import _extract_json_block, call_llm

from django.conf import settings

from courses.models import DocumentChunk

from . import chat_tuteur, rag
from .rag import STOPWORDS

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
    """Retourne (questions, erreur, source). source = 'ia' ou 'contenu'."""
    provider = (getattr(settings, "AI_PROVIDER", "") or "").strip().lower()

    def _secours(erreur: str):
        questions = quiz_depuis_contenu(conversation.bloc)
        if questions:
            return questions, None, "contenu"
        return [], _message_sans_contenu(conversation.bloc), "contenu"

    # Bloc sans texte exploitable (vidéo/audio/lien) : on n'invente pas de quiz.
    if len(_texte_pour_quiz(conversation.bloc).strip()) < 60:
        return [], _message_sans_contenu(conversation.bloc), "contenu"

    if provider == "mock":
        return _secours(
            "Aucun contenu textuel exploitable dans ce bloc pour générer un quiz."
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
        return _secours(f"IA indisponible : {resultat['error']}")

    questions = _valider_questions(_parser_json(resultat.get("content") or ""))
    if len(questions) < 2:
        return _secours("Le quiz généré par l'IA est incomplet.")

    return questions, None, "ia"




# ── Quiz de secours (déterministe, sans IA) ─────────────────────────────────

def _phrases(texte: str) -> list[str]:
    texte = re.sub(r"\s+", " ", unescape(texte or "")).strip()
    morceaux = re.split(r"(?<=[.!?])\s+", texte)
    return [
        m.strip() for m in morceaux
        if 40 <= len(m.strip()) <= 260
    ]


def _mots(texte: str) -> list[str]:
    return [
        m for m in re.findall(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ'-]{4,}", texte or "")
        if m.lower() not in STOPWORDS
    ]




def _texte_pour_quiz(bloc) -> str:
    """Texte du bloc, complété par les extraits du document attaché (PDF/DOCX)."""
    texte = chat_tuteur.texte_du_bloc(bloc)
    if len(texte) >= 120:
        return texte

    try:
        rag.assurer_index_bloc(bloc)
        morceaux = list(
            DocumentChunk.objects
            .filter(bloc=bloc)
            .values_list("texte", flat=True)[:6]
        )
        if morceaux:
            return "\n".join(morceaux)
    except Exception:  # noqa: BLE001
        logger.debug("[quiz_tuteur] extraits documentaires indisponibles", exc_info=True)

    return texte


def _message_sans_contenu(bloc) -> str:
    type_bloc = getattr(bloc, "type_bloc", "")
    if type_bloc in ("video", "audio"):
        return ("Ce bloc est une vidéo/audio : aucun texte n'est disponible pour générer un quiz. "
                "Utilisez un bloc texte ou un document.")
    if type_bloc == "lien":
        return ("Ce bloc est un lien externe : ajoutez un contenu texte ou un document PDF "
                "pour générer un quiz.")
    if type_bloc == "fichier":
        return ("Le document de ce bloc n'a pas pu être lu (PDF scanné ou format non pris en charge). "
                "Ajoutez un texte ou un PDF avec couche texte.")
    return ("Ce bloc ne contient pas assez de texte exploitable pour générer un quiz. "
            "Ajoutez un contenu texte ou un document PDF.")


def quiz_depuis_contenu(bloc) -> list[dict]:
    """Construit 2-3 QCM « complétez la phrase » à partir du texte du bloc.

    Utilisé quand le fournisseur IA est absent ou renvoie un JSON inexploitable.
    """
    texte = _texte_pour_quiz(bloc)
    phrases = _phrases(texte)
    if not phrases and len(texte.strip()) >= 40:
        # Code source / texte sans ponctuation : on utilise le texte tel quel.
        phrases = [texte.strip()[:260]]
    if not phrases:
        return []

    tous_mots = list(dict.fromkeys(_mots(texte)))
    questions: list[dict] = []
    # Shuffle déterministe des options (reproductible, sans enjeu de sécurité).
    rng = random.Random(bloc.id or 1)  # NOSONAR

    for phrase in phrases:
        candidats = [m for m in _mots(phrase) if len(m) >= 5]
        if not candidats:
            continue
        correct = max(candidats, key=len)
        distracteurs = [
            m for m in tous_mots
            if m.lower() != correct.lower()
            and abs(len(m) - len(correct)) <= 5
        ][:3]
        if len(distracteurs) < 3:
            distracteurs = [m for m in tous_mots if m.lower() != correct.lower()][:3]
        if len(distracteurs) < 3:
            continue

        options = [correct, *distracteurs]
        rng.shuffle(options)  # NOSONAR — mélange reproductible des options, sans enjeu de sécurité
        enonce = re.sub(re.escape(correct), "______", phrase, count=1, flags=re.IGNORECASE)
        if "______" not in enonce:
            continue

        questions.append({
            "question": f"Complétez : « {enonce} »",
            "options": options,
            "bonne_reponse": options.index(correct),
            "explication": phrase,
        })
        if len(questions) >= NB_QUESTIONS:
            break

    return questions


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
