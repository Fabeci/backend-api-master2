# courses/services/chat_tuteur.py
"""Assistant pédagogique conversationnel (tuteur IA) intégré aux blocs.

Réutilise le fournisseur LLM existant (`analytics.services.llm_provider`)
configuré par `settings.AI_PROVIDER` — aucun nouveau fournisseur.
"""
from __future__ import annotations

import logging
import re
import time

from django.conf import settings
from django.utils.html import strip_tags

from analytics.services.llm_provider import call_llm

logger = logging.getLogger(__name__)

MAX_QUESTION = 2000          # caractères par message apprenant
MAX_CONTEXTE = 7000          # extrait du bloc envoyé au modèle
HISTORIQUE_MAX = 8           # messages précédents réinjectés
MAX_TOKENS = 1100
MAX_HISTORIQUE_MESSAGE = 1200


SYSTEM_PROMPT = (
    "Tu es l'assistant pédagogique de SOMAPRO, un tuteur patient, précis et progressif. "
    "Tu réponds en français, avec un style clair, structuré et concis.\n"
    "Règles :\n"
    "1. Réponds d'abord directement à la question posée.\n"
    "2. Adapte la complexité de l'explication au niveau et au contexte du cours fourni.\n"
    "3. Privilégie les exemples concrets et les explications étape par étape.\n"
    "4. Définis les termes techniques avant de les employer en profondeur.\n"
    "5. Distingue explicitement ce qui vient du CONTENU DU COURS (source officielle) "
    "de tes compléments de connaissance générale.\n"
    "6. Si le contenu fourni ne suffit pas, dis-le clairement et signale que tu complètes "
    "avec des connaissances générales.\n"
    "7. Reste dans le périmètre pédagogique du bloc ; si la question est hors sujet, "
    "réponds brièvement puis ramène l'apprenant au contenu étudié.\n"
    "8. Ne donne jamais la solution d'une évaluation ou d'un exercice noté : propose des "
    "indices et un raisonnement guidé, sans contourner les règles d'évaluation.\n"
    "9. Encourage la compréhension et le raisonnement plutôt que la mémorisation.\n"
    "10. Ne prétends jamais avoir analysé une vidéo, un PDF, un audio ou un document dont "
    "le contenu ne t'est pas fourni.\n"
    "11. Sois concis (300 à 450 mots maximum sauf demande explicite) et évite les répétitions.\n"
    "Utilise du Markdown simple (titres courts, listes, gras, code) sans HTML brut."
)


def _nettoyer(texte: str, limite: int) -> str:
    texte = strip_tags(texte or "")
    texte = re.sub(r"[ \t]+", " ", texte)
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()[:limite]


def texte_du_bloc(bloc) -> str:
    """Extrait exploitable du bloc (texte, markdown, HTML, code, objectifs)."""
    morceaux = [bloc.titre or "", bloc.objectifs or ""]
    for champ in ("contenu_texte", "contenu_markdown"):
        valeur = getattr(bloc, champ, None)
        if valeur:
            morceaux.append(str(valeur))
    if getattr(bloc, "contenu_html", None):
        morceaux.append(str(bloc.contenu_html))
    if getattr(bloc, "code_source", None):
        langage = getattr(bloc, "langage_code", None) or "texte"
        morceaux.append(f"Code ({langage}) :\n{bloc.code_source}")
    return _nettoyer("\n".join(morceaux), MAX_CONTEXTE + 1)


def contexte_bloc(bloc) -> dict:
    """Contexte pédagogique minimal et réellement disponible pour le bloc."""
    sequence = bloc.sequence
    module = sequence.module
    cours = module.cours

    complet = texte_du_bloc(bloc)
    tronque = len(complet) > MAX_CONTEXTE

    ressources = []
    if getattr(bloc, "lien_externe", None):
        ressources.append("Lien externe (contenu non analysé)")
    if getattr(bloc, "video_url", None):
        ressources.append("Vidéo (contenu non analysé)")
    if getattr(bloc, "audio_url", None):
        ressources.append("Audio (contenu non analysé)")
    if getattr(bloc, "fichier", None):
        try:
            nom = str(bloc.fichier.name).split("/")[-1]
        except Exception:  # noqa: BLE001
            nom = "document"
        ressources.append(f"Document joint « {nom} » (contenu non analysé)")

    try:
        for res in sequence.ressources_sequences.all()[:5]:
            ressources.append(
                f"Ressource « {res.titre} » ({res.get_type_ressource_display()}) — contenu non analysé"
            )
    except Exception:  # noqa: BLE001
        pass

    return {
        "cours": cours.titre,
        "module": module.titre,
        "sequence": sequence.titre,
        "bloc": bloc.titre,
        "type_bloc": bloc.get_type_bloc_display(),
        "objectifs": (bloc.objectifs or "").strip()[:1200],
        "contenu": complet[:MAX_CONTEXTE],
        "contenu_disponible": bool(complet.strip()),
        "tronque": tronque,
        "ressources": ressources,
    }


def suggestions(bloc) -> list[str]:
    """Questions de démarrage contextuelles (adaptées au bloc)."""
    titre = (bloc.titre or "cette notion").strip()
    base = [
        f"Explique-moi « {titre} » avec des mots simples.",
        "Donne-moi un exemple concret.",
        "Quelles sont les erreurs à éviter ?",
        "Propose-moi un exercice pour vérifier ma compréhension.",
    ]
    if getattr(bloc, "type_bloc", "") == "code":
        base[1] = "Montre-moi un exemple de code équivalent, commenté."
    elif getattr(bloc, "type_bloc", "") == "video":
        base[1] = "Quels sont les points clés à retenir de cette notion ?"
    return base


def _prompt_utilisateur(ctx: dict, historique: list, question: str) -> str:
    lignes = [
        f"COURS : {ctx['cours']}",
        f"MODULE : {ctx['module']}",
        f"SÉQUENCE : {ctx['sequence']}",
        f"BLOC : {ctx['bloc']} ({ctx['type_bloc']})",
    ]
    if ctx["objectifs"]:
        lignes.append(f"OBJECTIFS : {ctx['objectifs']}")

    if ctx["contenu_disponible"]:
        lignes.append("CONTENU DU BLOC (source officielle du cours) :\n" + ctx["contenu"])
    else:
        lignes.append(
            "CONTENU DU BLOC : aucun texte exploitable (média ou fichier). "
            "Ne prétends pas l'avoir analysé ; réponds à partir du titre et des objectifs, "
            "en signalant la limite."
        )

    if ctx["ressources"]:
        lignes.append("RESSOURCES ASSOCIÉES : " + " ; ".join(ctx["ressources"]))

    if historique:
        lignes.append("HISTORIQUE RÉCENT DE LA CONVERSATION :")
        for message in historique:
            role = "Apprenant" if message.role == "user" else "Assistant"
            lignes.append(f"{role} : {message.contenu[:MAX_HISTORIQUE_MESSAGE]}")

    lignes.append("QUESTION DE L'APPRENANT :\n" + question)
    return "\n\n".join(lignes)


def repondre(conversation, question: str) -> dict:
    """Génère la réponse du tuteur. Retourne toujours un dict (jamais d'exception)."""
    ctx = contexte_bloc(conversation.bloc)

    historique = list(
        conversation.messages
        .filter(statut="termine")
        .exclude(role="systeme")
        .order_by("-cree_le", "-id")[:HISTORIQUE_MAX]
    )
    historique.reverse()

    debut = time.monotonic()
    try:
        resultat = call_llm(
            SYSTEM_PROMPT,
            _prompt_utilisateur(ctx, historique, question),
            json_mode=False,
            max_tokens=MAX_TOKENS,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[chat_tuteur] échec de l'appel LLM")
        return {
            "ok": False,
            "error": f"Erreur du fournisseur IA : {exc}",
            "provider": "",
            "model": "",
            "duree_ms": int((time.monotonic() - debut) * 1000),
            "contexte": ctx,
        }

    duree_ms = int((time.monotonic() - debut) * 1000)
    contenu = (resultat.get("content") or "").strip()
    erreur = resultat.get("error")

    if erreur or not contenu:
        return {
            "ok": False,
            "error": (erreur or "Réponse vide du fournisseur IA.")[:250],
            "provider": resultat.get("provider", "") or "",
            "model": resultat.get("model", "") or "",
            "duree_ms": duree_ms,
            "contexte": ctx,
        }

    return {
        "ok": True,
        "content": contenu,
        "provider": resultat.get("provider", "") or "",
        "model": resultat.get("model", "") or "",
        "degraded": bool(resultat.get("degraded")),
        "duree_ms": duree_ms,
        "contexte": ctx,
    }
