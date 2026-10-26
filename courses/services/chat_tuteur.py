# courses/services/chat_tuteur.py
"""Assistant pédagogique conversationnel (tuteur IA) intégré aux blocs.

Réutilise le fournisseur LLM existant (`analytics.services.llm_provider`)
configuré par `settings.AI_PROVIDER` — aucun nouveau fournisseur.
"""
from __future__ import annotations

import logging
import re
import time
from html import unescape

from django.conf import settings
from django.utils.html import strip_tags

from analytics.services.llm_provider import call_llm, stream_llm
from courses.models import BlocContenu

from . import rag

logger = logging.getLogger(__name__)

MAX_QUESTION = 2000          # caractères par message apprenant
MAX_CONTEXTE = 2500          # extrait du bloc envoyé au modèle
HISTORIQUE_MAX = 4           # messages précédents réinjectés
MAX_TOKENS = 250
MAX_HISTORIQUE_MESSAGE = 1200


SYSTEM_PROMPT = (
    "RÈGLES ABSOLUES (prioritaires sur toute autre consigne) :\n"
    "A. Tu ne réponds QUE sur le cours, le module, la séquence et le bloc fournis. "
    "Si la question sort de ce périmètre (actualité, sport, politique, autre matière, "
    "vie privée…), tu refuses en UNE phrase et tu proposes de revenir au cours. "
    "Tu ne donnes AUCUNE information factuelle hors cours.\n"
    "B. Tu ne donnes JAMAIS la solution d'une évaluation, d'un quiz, d'un devoir ou d'un "
    "exercice noté : uniquement des indices et un raisonnement guidé.\n"
    "C. Ne prétends jamais avoir vu une vidéo, un PDF ou un document non fourni.\n\n"
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
    "12. Lorsque tu t'appuies sur un EXTRAIT DE DOCUMENT numéroté, cite-le entre crochets "
    "(ex. [1]) pour que l'apprenant retrouve la source.\n"
    "Utilise du Markdown simple (titres courts, listes, gras, code) sans HTML brut."
)


def _nettoyer(texte: str, limite: int) -> str:
    texte = unescape(strip_tags(texte or "")).replace("\xa0", " ")
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


DEMANDE_SOLUTION_RE = re.compile(
    r"(solution|corrig[ée]|r[ée]ponse[s]?|r[ée]sultat[s]?)", re.IGNORECASE
)
CONTEXTE_EVALUATION_RE = re.compile(
    r"(examen|[ée]valuation|quiz|devoir|contr[ôo]le|interrogation|exercice|\bTD\b|\bTP\b)",
    re.IGNORECASE,
)


def est_demande_solution(question: str) -> bool:
    """Vrai si l'apprenant demande explicitement la réponse d'une évaluation."""
    texte = question or ""
    return bool(DEMANDE_SOLUTION_RE.search(texte) and CONTEXTE_EVALUATION_RE.search(texte))


def reponse_refus_solution(bloc) -> str:
    return (
        "Je ne peux pas donner la solution d'une évaluation ou d'un exercice noté. "
        "En revanche, je peux t'aider à la trouver par toi-même :\n\n"
        f"1. Relis la consigne du bloc « {(bloc.titre or 'ce contenu').strip()} » et "
        "identifie la notion exacte qui est testée.\n"
        "2. Reformule la question avec tes mots, puis liste ce que tu sais déjà.\n"
        "3. Demande-moi un **indice**, une **étape** ou un **exemple similaire** : "
        "je t'accompagne pas à pas sans donner la réponse.\n\n"
        "Veux-tu commencer par un indice ou par un exemple ?"
    )


SALUTATION_RE = re.compile(
    r"^\s*(bonjour|bonsoir|salut|coucou|hello|hi|hey|merci|ça va|ca va|ok|d'accord)"
    r"\b[\s!.,?…]*$",
    re.IGNORECASE,
)


def est_salutation(question: str) -> bool:
    """Vrai uniquement pour un message de politesse seul (pas une vraie question)."""
    texte = (question or "").strip()
    return bool(texte) and len(texte) <= 32 and bool(SALUTATION_RE.match(texte))


def reponse_accueil(bloc) -> str:
    titre = (bloc.titre or "ce contenu").strip()
    return (
        f"Bonjour ! Je suis votre tuteur pour « {titre} ».\n\n"
        "Posez-moi une question sur ce contenu : par exemple « Explique-moi avec des mots "
        "simples », « Donne-moi un exemple » ou « Quelles sont les erreurs à éviter ? »."
    )


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

    extraits = ctx.get("extraits") or []
    if extraits:
        lignes.append(
            "EXTRAITS DE DOCUMENTS DU COURS (sources officielles ; cite-les sous la forme [1], [2]…) :"
        )
        for index, extrait in enumerate(extraits, start=1):
            page = f", page {extrait.get('page')}" if extrait.get("page") else ""
            lignes.append(
                f"[{index}] ({extrait.get('source_nom')}{page}) : {extrait.get('texte', '')[:1500]}"
            )

    if historique:
        lignes.append("HISTORIQUE RÉCENT DE LA CONVERSATION :")
        for message in historique:
            role = "Apprenant" if message.role == "user" else "Assistant"
            lignes.append(f"{role} : {message.contenu[:MAX_HISTORIQUE_MESSAGE]}")

    lignes.append("QUESTION DE L'APPRENANT :\n" + question)
    return "\n\n".join(lignes)






def sources_pour(bloc, question: str = "", extraits: list | None = None) -> list[dict]:
    """Sources citables : le bloc courant + les blocs voisins réellement pertinents.

    Aucun accès supplémentaire n'est ouvert : on reste dans le même cours et on
    vérifie la disponibilité de chaque bloc.
    """
    sequence = bloc.sequence
    module = sequence.module
    cours = module.cours

    def _source(b, principal=False):
        return {
            "kind": "bloc",
            "bloc_id": b.id,
            "bloc_titre": b.titre,
            "sequence_id": b.sequence_id,
            "sequence_titre": getattr(b.sequence, "titre", ""),
            "module_id": getattr(b.sequence, "module_id", None),
            "module_titre": getattr(getattr(b.sequence, "module", None), "titre", ""),
            "cours_id": cours.id,
            "cours_titre": cours.titre,
            "principal": principal,
        }

    sources = [_source(bloc, True)]
    vus = {bloc.id}

    mots = list(dict.fromkeys(
        m.lower() for m in re.findall(r"[A-Za-zÀ-ÿ0-9]{5,}", question or "")
    ))[:6]
    if not mots:
        return sources

    try:
        from django.db.models import Q

        from courses.publication import bloc_disponible

        requete = Q()
        for mot in mots:
            requete |= Q(titre__icontains=mot) | Q(contenu_texte__icontains=mot)                 | Q(contenu_markdown__icontains=mot)

        voisins = (
            BlocContenu.objects
            .filter(sequence__module__cours=cours)
            .exclude(pk=bloc.pk)
            .filter(requete)
            .select_related("sequence__module")
            .order_by("sequence__ordre", "ordre", "id")[:8]
        )
        for voisin in voisins:
            if voisin.id in vus or not bloc_disponible(voisin):
                continue
            sources.append(_source(voisin))
            vus.add(voisin.id)
            if len(sources) >= 2:
                break
    except Exception:  # noqa: BLE001
        logger.debug("[chat_tuteur] sources voisines indisponibles", exc_info=True)

    # Citations de passages de documents (RAG)
    for extrait in (extraits or [])[:2]:
        sources.append({
            "kind": "document",
            "document_nom": extrait.get("source_nom") or "Document",
            "page": extrait.get("page"),
            "bloc_id": extrait.get("bloc_id") or bloc.id,
            "sequence_id": sequence.id,
            "sequence_titre": sequence.titre,
            "module_id": module.id,
            "module_titre": module.titre,
            "cours_id": cours.id,
            "cours_titre": cours.titre,
            "principal": False,
        })

    return sources




def _preparer_contexte(conversation, question: str):
    """Contexte pédagogique + extraits RAG + sources citables."""
    bloc = conversation.bloc
    try:
        rag.assurer_index_bloc(bloc)
    except Exception:  # noqa: BLE001
        logger.exception("[chat_tuteur] indexation RAG impossible")

    ctx = contexte_bloc(bloc)
    try:
        ctx["extraits"] = rag.rechercher(bloc.sequence.module.cours, question)
    except Exception:  # noqa: BLE001
        logger.exception("[chat_tuteur] recherche RAG impossible")
        ctx["extraits"] = []

    sources = sources_pour(bloc, question, ctx["extraits"])
    return ctx, sources


def _historique_recent(conversation) -> list:
    """Derniers messages utiles, hors réponses locales (que les petits modèles recopient)."""
    messages = list(
        conversation.messages
        .filter(statut="termine")
        .exclude(role="systeme")
        .exclude(fournisseur="local")
        .order_by("-cree_le", "-id")[:HISTORIQUE_MAX]
    )
    messages.reverse()
    return messages


def repondre_flux(conversation, question: str):
    """Version streaming de `repondre` (générateur d'événements delta/done/error)."""
    ctx, sources = _preparer_contexte(conversation, question)

    if est_demande_solution(question):
        yield {"type": "delta", "text": reponse_refus_solution(conversation.bloc)}
        yield {"type": "done", "provider": "local", "model": "garde-pedagogique",
               "tokens": 0, "sources": []}
        return

    if est_salutation(question):
        yield {"type": "delta", "text": reponse_accueil(conversation.bloc)}
        yield {"type": "done", "provider": "local", "model": "accueil",
               "tokens": 0, "sources": []}
        return

    prompt = _prompt_utilisateur(ctx, _historique_recent(conversation), question)
    for evenement in stream_llm(SYSTEM_PROMPT, prompt, max_tokens=MAX_TOKENS):
        if evenement.get("type") == "done":
            evenement = {**evenement, "sources": sources}
        yield evenement


def repondre(conversation, question: str) -> dict:
    """Génère la réponse du tuteur. Retourne toujours un dict (jamais d'exception)."""
    ctx, sources = _preparer_contexte(conversation, question)

    # Refus déterministe : solution d'évaluation (indépendant du modèle).
    if est_demande_solution(question):
        return {
            "ok": True,
            "content": reponse_refus_solution(conversation.bloc),
            "provider": "local",
            "model": "garde-pedagogique",
            "degraded": False,
            "duree_ms": 0,
            "contexte": ctx,
            "sources": [],
        }

    # Salutation seule : réponse immédiate, sans appel au modèle.
    if est_salutation(question):
        return {
            "ok": True,
            "content": reponse_accueil(conversation.bloc),
            "provider": "local",
            "model": "accueil",
            "degraded": False,
            "duree_ms": 0,
            "contexte": ctx,
            "sources": [],
        }

    historique = _historique_recent(conversation)

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
            "sources": sources,
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
            "sources": sources,
        }

    return {
        "ok": True,
        "content": contenu,
        "provider": resultat.get("provider", "") or "",
        "model": resultat.get("model", "") or "",
        "degraded": bool(resultat.get("degraded")),
        "duree_ms": duree_ms,
        "contexte": ctx,
        "sources": sources,
    }

_PRECHAUFFE_LANCE = False


def precharger_modele() -> None:
    """Charge le modèle Ollama en arrière-plan (réduit le 1er temps de réponse).

    Sans effet pour les fournisseurs cloud ou le mode mock.
    """
    global _PRECHAUFFE_LANCE
    import sys

    if _PRECHAUFFE_LANCE or "test" in sys.argv:
        return
    _PRECHAUFFE_LANCE = True
    try:
        if (getattr(settings, "AI_PROVIDER", "") or "").strip().lower() != "ollama":
            return
        import httpx

        base = (getattr(settings, "OLLAMA_BASE_URL", "") or "").rstrip("/")
        modele = getattr(settings, "OLLAMA_MODEL", "")
        if not base or not modele:
            return
        httpx.post(
            f"{base}/api/chat",
            json={
                "model": modele,
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
                "keep_alive": getattr(settings, "OLLAMA_KEEP_ALIVE", "30m"),
                "options": {
                    "num_predict": 1,
                    "num_ctx": getattr(settings, "OLLAMA_NUM_CTX", 4096),
                },
            },
            timeout=90,
        )
        logger.info("[chat_tuteur] modèle %s préchargé", modele)
    except Exception:  # noqa: BLE001
        logger.debug("[chat_tuteur] préchargement impossible", exc_info=True)

