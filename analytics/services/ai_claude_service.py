# analytics/services/ai_claude_service.py
# ============================================================================
# SERVICE IA — Intégration Claude (Anthropic) pour génération adaptative
#
# Configuration dans settings.py :
#   ANTHROPIC_API_KEY = env('ANTHROPIC_API_KEY')
#   ANTHROPIC_MODEL  = 'claude-sonnet-4-20250514' (défaut)
#   ANTHROPIC_MAX_TOKENS = 4000
#
# Dans .env :
#   ANTHROPIC_API_KEY=sk-ant-...
# ============================================================================

import json
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    import anthropic
    _anthropic_available = True
except ImportError:
    anthropic = None
    _anthropic_available = False
    logger.warning('[ai_claude] anthropic non installé — pip install anthropic')

_client = None

def _get_client():
    """Retourne (ou crée) le client Claude."""
    global _client
    if _client is not None:
        return _client
    if not _anthropic_available:
        return None
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
    if not api_key:
        logger.error('[ai_claude] ANTHROPIC_API_KEY absent dans settings.py')
        return None
    try:
        _client = anthropic.Anthropic(api_key=api_key)
        return _client
    except Exception as e:
        logger.error('[ai_claude] Impossible de créer le client : %s', e)
        return None


def _get_model():
    return getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')

def _get_max_tokens():
    return getattr(settings, 'ANTHROPIC_MAX_TOKENS', 4000)


def _call_claude(system_prompt: str, user_prompt: str) -> dict:
    """
    Point de sortie unique vers le fournisseur LLM configuré.

    La sélection du fournisseur (Claude, Ollama local/hors-ligne, Gemini,
    OpenAI, Mistral, mode mock) est déléguée à analytics.services.llm_provider
    et pilotée par settings.AI_PROVIDER. La signature et la forme du retour
    sont conservées pour ne rien casser dans les générateurs ci-dessous.
    """
    from .llm_provider import call_llm
    result = call_llm(system_prompt, user_prompt, json_mode=True)
    return {
        'content': result.get('content', '') or '',
        'tokens': result.get('tokens', 0) or 0,
        'error': result.get('error'),
    }


def _loads(content: str):
    """
    Parse tolérant du JSON renvoyé par le LLM (gère les fences Markdown et le
    texte parasite quand on tombe en repli sans contrainte JSON).
    Retourne un dict, ou None.
    """
    import re
    t = (content or '').strip()
    if not t:
        return None
    candidates = [t]
    # fences ```json ... ```
    stripped = re.sub(r'^```[a-zA-Z]*\s*', '', t)
    stripped = re.sub(r'\s*```$', '', stripped).strip()
    candidates.append(stripped)
    # premier bloc { ... }
    m = re.search(r'\{.*\}', stripped, re.DOTALL)
    if m:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            return json.loads(c)
        except Exception:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS — Personas pedagogoques par type de trigger
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_BLOC_SIMPLIFIE = """Tu es un assistant pédagogique expert en formation pour adultes.
Ton rôle : générer une explication ALTERNATIVE et SIMPLIFIÉE pour un apprenant
qui a passé beaucoup de temps sur un contenu sans le comprendre.

Règles :
- Répondre UNIQUEMENT en JSON valide (champ "contenu_json")
- Appuie-toi STRICTEMENT sur le CONTENU ORIGINAL fourni : explique les notions,
  le vocabulaire et les exemples RÉELS du cours. N'invente aucun sujet.
- Si le contenu fourni est vide ou insuffisant, base-toi sur le titre du bloc et
  reste factuel, sans inventer de faits ni d'URL.
- Utiliser des analogies concrètes du quotidien en lien avec le sujet réel
- Structurer avec des titres (##, ###), listes, exemples
- Maximum 500 mots dans le contenu HTML
- La langue est le FRANÇAIS
- Utiliser un ton encourageant et bienveillant

Format JSON de réponse :
{
  "contenu_json": {
    "type_generation": "explication_simple" | "analogie" | "exemples" | "resume" | "faq",
    "titre": "titre accrocheur",
    "contenu_html": "<p>, <h3>, <ul>, <ol>, <strong>, <em> uniquement</h3></h3>",
    "concepts_cibles": ["concept1", "concept2"]
  }
}"""

SYSTEM_SEQUENCE = """Tu es un expert en ingénierie pédagogique.
Tu crées des plans de séquences adaptatifs pour aider des apprenants
en difficulté.

Règles :
- Répondre UNIQUEMENT en JSON valide
- Appuie-toi STRICTEMENT sur le CONTENU DE LA SÉQUENCE fourni : reprends les notions,
  le vocabulaire et les exemples RÉELS du cours. N'invente aucun sujet.
- Si le contenu fourni est vide ou insuffisant, base-toi sur le titre de la séquence
  et reste factuel, sans inventer de faits.
- N'invente JAMAIS d'URL ni de ressource. Laisse "ressources_alternatives": [] sauf si
  tu disposes de liens réellement pertinents.
- Structurer en étapes progressives (facile → difficile)
- Proposer des activités brèves (5-10 min)
- Inclure des vérifications de compréhension
- La langue est le FRANÇAIS

Format JSON :
{
  "contenu_json": {
    "titre": "titre de la séquence",
    "description": "résumé en 1-2 phrases",
    "objectifs": ["objectif1", "objectif2"],
    "duree_minutes": 20,
    "etapes": [
      {
        "titre": "titre de l'étape",
        "type": "lecture" | "exercice" | "quiz" | "video" | "activite",
        "duree_minutes": 5,
        "instructions": "texte bref"
      }
    ],
    "ressources_alternatives": ["url1", "url2"]
  }
}"""

SYSTEM_MODULE = """Tu es un concepteur pédagogique expert.
Tu crées des modules de révision adaptés au niveau de l'apprenant.

Règles :
- Répondre UNIQUEMENT en JSON valide
- Commencer par les prérequis ( concepts manquants)
- Progresser du simple au complexe
- Inclure des exemples gradués
- La langue est le FRANÇAIS

Format JSON :
{
  "contenu_json": {
    "titre": "Module de révision",
    "resume": "résumé du module",
    "competences_cibles": ["comp1", "comp2"],
    "sequence_id": 1,
    "sequence_niveau": "débutant" | "intermediaire" | "avance",
    "bloc_contents": [
      {
        "titre": "titre du bloc",
        "type_bloc": "texte",
        "contenu_html": "...",
        "duree_estimee_minutes": 5,
        "objectifs": ["obj1"]
      }
    ]
  }
}"""

SYSTEM_EXPLICATION = """Tu es un enseignant pédagogue expert.
Tu expliques un contenu de cours à un apprenant qui a des difficultés, de façon
CLAIRE, CONCRÈTE et utile (ce n'est PAS un plan d'action, c'est une explication).

Règles :
- Répondre UNIQUEMENT en JSON valide
- Appuie-toi STRICTEMENT sur le CONTENU DU COURS fourni (vocabulaire, exemples RÉELS).
  N'invente aucun sujet.
- Structure l'explication :
    1. Définition simple (ce que c'est)
    2. Analogie du quotidien
    3. Exemple concret détaillé (avec code si pertinent)
    4. Erreurs fréquentes / points d'attention
    5. Mini-récapitulatif
- N'invente JAMAIS d'URL ni de ressource.
- Reste factuel ; si une information manque, ne l'invente pas.
- Contenu HTML autorisé : <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>, <code>.
- Maximum ~600 mots. Langue : FRANÇAIS. Ton encourageant.

Format JSON de réponse :
{
  "contenu_json": {
    "titre": "titre clair de l'explication",
    "contenu_html": "<h3>...</h3><p>...</p>",
    "concepts_cibles": ["concept1", "concept2"]
  }
}"""

SYSTEM_COURS_ABANDONNE = """Tu es un coach pédagogique expert en re-motivation.
Tu conçois un PARCOURS DE REPRISE court pour un apprenant qui a abandonné un cours
(progression faible et inactivité prolongée).

Règles :
- Répondre UNIQUEMENT en JSON valide
- Réduire la charge cognitive : sessions de 10-15 minutes maximum
- Commencer par des victoires faciles pour restaurer la confiance
- Rappeler la finalité et le bénéfice concret du cours
- Proposer des étapes progressives et concrètes
- La langue est le FRANÇAIS

Format JSON :
{
  "contenu_json": {
    "titre": "parcours de reprise accrocheur",
    "resume": "résumé motivant en 1-2 phrases",
    "competences_cibles": ["comp1", "comp2"],
    "sequence_niveau": "debutant" | "intermediaire" | "avance",
    "duree_minutes": 30,
    "bloc_contents": [
      {
        "titre": "titre de l'étape",
        "type_bloc": "texte",
        "contenu_html": "...",
        "duree_estimee_minutes": 10,
        "objectifs": ["obj1"]
      }
    ]
  }
}"""

SYSTEM_QUIZ = """Tu es un expert en évaluation pédagogique.
Tu crées des quiz de REMÉDIATION ciblés sur les concepts ratés.

Règles :
- Répondre UNIQUEMENT en JSON valide
- Questions cibler SPÉCIFIQUEMENT les concepts ratés
- Difficulté progressive (facile → exigeant)
- Inclure explication pour chaque bonne réponse
- Varier les types (QCM, vrai/faux, texte court)
- La langue est le FRANÇAIS
- Pour un QCM : `options` contient les TEXTES des réponses possibles (jamais des lettres),
  et `bonne_reponse` doit être EXACTEMENT l'un de ces textes (copié à l'identique) —
  jamais « A »/« B »/« C », jamais un numéro.

Format JSON :
{
  "contenu_json": {
    "titre": "Quiz de remédiation",
    "consigne": "texte d'introduction",
    "concepts_rates": ["concept1", "concept2"],
    "questions": [
      {
        "question": "Que vaut 7 // 2 en Python ?",
        "type": "qcm",
        "options": ["3.5", "3", "4", "2"],
        "bonne_reponse": "3",
        "explication": "// est la division entière : 7 // 2 = 3"
      }
    ]
  }
}"""


# ══════════════════════════════════════════════════════════════════════════════════════
# FONCTIONS DE GÉNÉRATION PAR TYPE
# ══════════════════════════════════════════════════════════════════════════════════════

def generer_bloc_simplifie(context: dict) -> dict:
    """Génère un bloc simplifié (trigger: temps_long ou multi_reouverture)."""
    _var = int(context.get('variation') or 0)
    variation_hint = (
        f"C'est la tentative n°{_var + 1}. Propose une approche VRAIMENT DIFFÉRENTE "
        "des précédentes (autre angle, autre analogie, autre format).\n"
        if _var > 0 else ""
    )
    user_prompt = f"""
Génère une explication alternative pour ce bloc de formation :

TITRE : {context.get('bloc_titre', 'Inconnu')}
COURS : {context.get('cours_titre', '')}
SÉQUENCE : {context.get('sequence_titre', '')}

DONNÉES :
- Temps estimé : {context.get('duree_estimee_min', '?')} min
- Temps passé : {context.get('duree_passee_min', '?')} min
- Ratio : {context.get('ratio_pct', '?')}%
- Ouvertures : {context.get('nb_ouvertures', 1)}
- Scroll : {context.get('scroll_max_pct', 0)}%

CONTENU ORIGINAL :
---
{context.get('bloc_contenu', 'Non disponible')[:3000]}
---
{variation_hint}
Génère en JSON."""
    result = _call_claude(SYSTEM_BLOC_SIMPLIFIE, user_prompt)
    data = None
    if not result['error']:
        wrapper = _loads(result['content']) or {}
        data = wrapper.get('contenu_json', {}) or wrapper
    if data and data.get('contenu_html'):
        return data, None, result['tokens']
    # ✅ Repli extractif à partir du contenu réel du bloc
    fb = _fallback_help(context, 'bloc_contenu', 'bloc_titre')
    if fb:
        logger.info('[ai_claude/bloc] LLM indisponible → repli extractif')
        return fb, None, result['tokens']
    return None, (result['error'] or 'Contenu vide'), result['tokens']


def generer_sequence_adaptative(context: dict) -> dict:
    """Génère une séquence complète adaptée (trigger: module_difficile, sequence_complexe)."""
    user_prompt = f"""
Crée une séquence adaptative pour cet apprenant :

MODULE : {context.get('module_titre', 'Inconnu')}
COURS : {context.get('cours_titre', '')}
SÉQUENCE ORIGINALE : {context.get('sequence_titre', '')}

CONTEXTE DIFFICULTE :
- Ratio temps passé/estimé : {context.get('ratio_temps_pct', '?')}%
- Score moyen quiz : {context.get('score_moyen', '?')}%
- Concepts identifiés comme difficiles : {context.get('concepts_difficiles', [])}

CONTENU SÉQUENCE ORIGINALE :
---
{context.get('sequence_contenu', 'Non disponible')[:3000]}
---

Génère en JSON."""
    result = _call_claude(SYSTEM_SEQUENCE, user_prompt)
    if result['error']:
        return None, result['error'], 0
    try:
        wrapper = _loads(result['content']) or {}
        data = wrapper.get('contenu_json', {})
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/seq] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


SYSTEM_EXPLICATION_HTML = """Tu es un enseignant pédagogue.
Tu expliques un contenu de cours à un apprenant qui a des difficultés.

Règles STRICTES :
- Appuie-toi uniquement sur le CONTENU DU COURS fourni. N'invente rien.
- N'écris AUCUNE URL.
- Réponds UNIQUEMENT en HTML : aucune phrase d'introduction, aucun JSON, aucune
  balise ``` — directement les balises HTML.
- Structure : <h3>Définition</h3>, <h3>Analogie</h3>, <h3>Exemple concret</h3>,
  <h3>Erreurs fréquentes</h3>, <h3>À retenir</h3>.
- Balises autorisées : h3, h4, p, ul, ol, li, strong, em, code.
- Environ 300-450 mots. Langue : FRANÇAIS. Ton clair et encourageant."""


def _call_llm_text(system_prompt: str, user_prompt: str) -> dict:
    """Appel LLM en texte libre (pas de JSON), utilisé pour l'explication HTML."""
    from .llm_provider import call_llm
    r = call_llm(system_prompt, user_prompt, json_mode=False)
    return {
        'content': r.get('content', '') or '',
        'tokens':  r.get('tokens', 0) or 0,
        'error':   r.get('error'),
    }


def _clean_html(text: str) -> str:
    """Retire les fences Markdown et le texte parasite autour du HTML."""
    import re
    t = (text or '').strip()
    t = re.sub(r'^```[a-zA-Z]*\s*', '', t)
    t = re.sub(r'\s*```$', '', t)
    # Ne garde qu'à partir du premier <h3|<h4|<p|<ul|<ol
    m = re.search(r'<(h3|h4|p|ul|ol)\b', t, re.IGNORECASE)
    if m:
        t = t[m.start():]
    return t.strip()


def _fallback_help(context: dict, contenu_key: str = 'sequence_contenu', titre_key: str = 'sequence_titre') -> dict:
    """
    Repli DÉTERMINISTE (sans IA) : construit une aide à partir du VRAI contenu
    du cours, pour que « Générer une aide » produise toujours quelque chose
    d'utile même si le LLM échoue (sortie vide/tronquée).
    """
    import re
    txt = (context.get(contenu_key) or '').strip()
    titre = context.get(titre_key) or context.get('sequence_titre') or 'Aide'
    if len(txt) < 60:
        return None
    # Découpage en passages
    parts = [p.strip() for p in re.split(r'\n{2,}|(?<=[.!?])\s{2,}', txt) if p.strip()]
    if not parts:
        parts = [txt]
    items = ''.join(f'<li>{p[:300]}</li>' for p in parts[:8])
    html = (
        f"<h3>{titre} — l'essentiel</h3>"
        "<p>Voici les points clés du cours à retenir :</p>"
        f"<ul>{items}</ul>"
        "<h3>À faire</h3>"
        "<ul><li>Relis ces passages en surlignant les définitions.</li>"
        "<li>Refais le quiz de la séquence pour vérifier ta compréhension.</li></ul>"
    )
    return {'titre': f"{titre} — l'essentiel", 'contenu_html': html, 'concepts_cibles': []}


def generer_explication(context: dict) -> dict:
    """Génère une EXPLICATION HTML ancrée (trigger sequence_complexe)."""
    concepts = context.get('concepts_difficiles') or []
    concepts_str = ', '.join(str(c) for c in concepts) if concepts else 'Non identifiés'
    user_prompt = f"""
Explique la matière suivante à un apprenant, pour qu'il COMPRENNE (définition,
analogie, exemple concret, erreurs fréquentes). N'invente pas, pas d'URL, HTML direct.

COURS : {context.get('cours_titre', '')}
MODULE : {context.get('module_titre', '')}
SÉQUENCE : {context.get('sequence_titre', '')}
CONCEPTS À ÉCLAIRCIR : {concepts_str}

CONTENU DU COURS (la matière à expliquer) :
---
{context.get('sequence_contenu', 'Non disponible')[:2500]}
---
"""
    result = _call_llm_text(SYSTEM_EXPLICATION_HTML, user_prompt)
    html = _clean_html(result.get('content', '')) if not result.get('error') else ''
    if len(html) >= 200:
        return {
            'titre':          context.get('sequence_titre') or 'Explication du cours',
            'contenu_html':   html,
            'concepts_cibles': [],
        }, None, result.get('tokens', 0)

    # ✅ Repli extractif (garantit une aide utile même si le LLM échoue)
    fb = _fallback_help(context, 'sequence_contenu', 'sequence_titre')
    if fb:
        logger.info('[ai_claude/explication] LLM indisponible → repli extractif')
        return fb, None, result.get('tokens', 0)
    return None, (result.get('error') or 'Explication incomplète'), result.get('tokens', 0)


def _generer_explication_json_obsolete(context: dict) -> dict:
    """Génère une EXPLICATION ancrée du contenu (trigger sequence_complexe)."""
    concepts = context.get('concepts_difficiles') or []
    concepts_str = ', '.join(str(c) for c in concepts) if concepts else 'Non identifiés'
    user_prompt = f"""
Explique ce contenu de cours à un apprenant qui a des difficultés.
Tu dois l'AIDER À COMPRENDRE (définition, analogie, exemples concrets), pas lister des étapes.

COURS : {context.get('cours_titre', '')}
MODULE : {context.get('module_titre', '')}
SÉQUENCE : {context.get('sequence_titre', '')}
CONCEPTS À ÉCLAIRCIR : {concepts_str}

CONTENU DU COURS (la matière à expliquer) :
---
{context.get('sequence_contenu', 'Non disponible')[:3000]}
---

Explique cette matière en JSON."""
    # Jusqu'à 2 tentatives (le petit modèle tronque parfois sa sortie).
    for attempt in range(2):
        result = _call_claude(SYSTEM_EXPLICATION, user_prompt)
        if result['error']:
            logger.warning('[ai_claude/explication] tentative %s échouée : %s', attempt + 1, result['error'])
            continue
        wrapper = _loads(result['content']) or {}
        data = wrapper.get('contenu_json', {}) or wrapper
        html = (data.get('contenu_html') or '').strip()
        if len(html) >= 250:
            return data, None, result['tokens']
        logger.warning('[ai_claude/explication] sortie trop courte (%s car.) → nouvelle tentative', len(html))
    return None, 'Explication incomplète (sortie tronquée par le modèle)', 0


def generer_module_revision(context: dict) -> dict:
    """Génère un module de révision complet (trigger: module_difficile, cours_abandonne)."""
    user_prompt = f"""
Crée un module de révision pour cet apprenant en difficulté :

MODULE ORIGINEL : {context.get('module_titre', 'Inconnu')}
COURS : {context.get('cours_titre', '')}

DONNÉES PERFORMANCE :
- Score moyen : {context.get('score_moyen', '?')}%
- Temps total : {context.get('temps_total_min', '?')} min
- Ratio temps : {context.get('ratio_temps_pct', '?')}%
- Échecs concepts : {context.get('concepts_rates', [])}

PRÉREQUIS À REVOIR :
{context.get('prerequis', 'Non identifiés')[:1000]}

Génère en JSON."""
    result = _call_claude(SYSTEM_MODULE, user_prompt)
    if result['error']:
        return None, result['error'], 0
    try:
        wrapper = _loads(result['content']) or {}
        data = wrapper.get('contenu_json', {})
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/mod] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


def generer_module_reprise(context: dict) -> dict:
    """Génère un parcours de reprise pour un cours abandonné (trigger: cours_abandonne)."""
    modules = context.get('modules_non_termines', []) or []
    modules_str = ', '.join(str(m) for m in modules) if modules else 'Non identifiés'
    user_prompt = f"""
Crée un parcours de reprise pour cet apprenant qui a abandonné son cours :

COURS : {context.get('cours_titre', 'Inconnu')}
DESCRIPTION : {context.get('cours_description', '')}
PROGRESSION : {context.get('ratio_completion_pct', '?')}% du cours terminé
INACTIVITÉ : {context.get('jours_inactivite', '?')} jours sans activité
MODULES NON TERMINÉS : {modules_str}

Objectif : redonner envie et proposer un plan de reprise réaliste et progressif.

Génère en JSON."""
    result = _call_claude(SYSTEM_COURS_ABANDONNE, user_prompt)
    if result['error']:
        return None, result['error'], 0
    try:
        wrapper = _loads(result['content']) or {}
        data = wrapper.get('contenu_json', {})
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/reprise] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


def _resolve_bonne_reponse(q: dict) -> str:
    """Ramène `bonne_reponse` au TEXTE exact de l'option (si l'IA a répondu par lettre/indice)."""
    options = q.get('options') or []
    br = str(q.get('bonne_reponse') or '').strip()
    if not options or not br:
        return br
    low = [str(o).strip().lower() for o in options]
    b = br.lower()
    if b in low:
        return options[low.index(b)]
    if b in ('true', 'vrai', 'v'):
        return 'Vrai' if 'vrai' in low else options[0]
    if b in ('false', 'faux', 'f'):
        return 'Faux' if 'faux' in low else options[-1]
    if len(b) == 1 and 'a' <= b <= 'z':
        i = ord(b) - 97
        if 0 <= i < len(options):
            return options[i]
    if b.isdigit():
        n = int(b)
        if 1 <= n <= len(options):
            return options[n - 1]
        if 0 <= n < len(options):
            return options[n]
    for o in options:
        if b in str(o).lower() or str(o).lower() in b:
            return o
    return br


def _normalize_quiz_questions(data: dict) -> dict:
    for q in (data.get('questions') or []):
        if isinstance(q, dict):
            q['bonne_reponse'] = _resolve_bonne_reponse(q)
    return data


def generer_quiz_remediation(context: dict) -> dict:
    """Génère un quiz de remédiation (trigger: quiz_rate)."""
    questions_str = '\n'.join([
        f"  - Q : {q.get('question', '')}\n"
        f"    Bonne : {q.get('bonne_reponse', '')}\n"
        f"    Apprenant : {q.get('reponse_apprenant', 'non répondu')}\n"
        f"    Explication : {q.get('explication', '')}"
        for q in context.get('questions_ratees', [])
    ])
    user_prompt = f"""
Crée un quiz de REMÉDIATION :

QUIZ : {context.get('quiz_titre', 'Inconnu')}
COURS : {context.get('cours_titre', '')}
SCORE : {context.get('score_obtenu', '?')}%
TENTATIVES : {context.get('nb_tentatives', 1)}

QUESTIONS RATÉES :
{questions_str or 'Données non disponibles'}

Génère 4-6 questions en JSON."""
    result = _call_claude(SYSTEM_QUIZ, user_prompt)
    if result['error']:
        return None, result['error'], 0
    try:
        wrapper = _loads(result['content']) or {}
        data = wrapper.get('contenu_json', {}) or wrapper
        # ✅ Refuser un quiz sans questions (sortie vide/mock) → pas de « 0 question ».
        if not data.get('questions'):
            return None, 'Quiz vide (aucune question générée)', result['tokens']
        # ✅ Cohérence : bonne_reponse = texte exact de l'option (jamais une lettre).
        data = _normalize_quiz_questions(data)
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/quiz] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE — appelé depuis les views
# ══════════════════════════════════════════════════════════════════════════════

TRIGGER_HANDLERS = {
    'temps_long':           generer_bloc_simplifie,
    'multi_reouverture':   generer_bloc_simplifie,
    # ✅ On génère une EXPLICATION (utile pour comprendre) plutôt qu'un plan.
    'sequence_complexe':   generer_explication,
    'module_difficile':    generer_module_revision,
    'cours_abandonne':     generer_module_reprise,
    'quiz_rate':          generer_quiz_remediation,
}

def traiter_demande_ai(ai_request) -> bool:
    """
    Traite une AIAnalysisRequest avec Claude.
    Retourne True si succès.
    """
    handler = TRIGGER_HANDLERS.get(ai_request.trigger)
    if not handler:
        ai_request.status = 'skipped'
        ai_request.error_message = f'Trigger non géré : {ai_request.trigger}'
        ai_request.save(update_fields=['status', 'error_message'])
        return False

    data, error, tokens = handler(ai_request.prompt_context)
    ai_request.tokens_used = tokens
    ai_request.completed_at = timezone.now()

    if error or not data:
        ai_request.status = 'error'
        ai_request.error_message = error or 'Données vides'
        ai_request.save(update_fields=['status', 'error_message', 'tokens_used', 'completed_at'])
        return False

    ai_request.gpt_response = json.dumps(data, ensure_ascii=False)
    ai_request.status = 'success'
    ai_request.save(update_fields=['status', 'gpt_response', 'tokens_used', 'completed_at'])
    return True