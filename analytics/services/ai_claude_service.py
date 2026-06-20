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
    Appel Claude. Retourne :
      { 'content': str, 'tokens': int, 'error': str|None }
    """
    client = _get_client()
    if not client:
        msg = 'anthropic non installé' if not _anthropic_available else 'ANTHROPIC_API_KEY manquant'
        return {'content': '', 'tokens': 0, 'error': msg}

    try:
        response = client.messages.create(
            model=_get_model(),
            max_tokens=_get_max_tokens(),
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
        )
        content = response.content[0].text if response.content else ''
        tokens = response.usage.input_tokens + response.usage.output_tokens
        return {'content': content, 'tokens': tokens, 'error': None}
    except Exception as exc:
        logger.error('[ai_claude] Erreur : %s', exc)
        return {'content': '', 'tokens': 0, 'error': str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPTS — Personas pedagogoques par type de trigger
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_BLOC_SIMPLIFIE = """Tu es un assistant pédagogique expert en formation pour adultes.
Ton rôle : générer une explication ALTERNATIVE et SIMPLIFIÉE pour un apprenant
qui a passé beaucoup de temps sur un contenu sans le comprendre.

Règles :
- Répondre UNIQUEMENT en JSON valide (champ "contenu_json")
- Utiliser des analogies concrètes du quotidien
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
- Structurer en étapes progressives (difficile → facile)
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

SYSTEM_QUIZ = """Tu es un expert en évaluation pédagogique.
Tu crées des quiz de REMÉDIATION ciblés sur les concepts ratés.

Règles :
- Répondre UNIQUEMENT en JSON valide
- Questions cibler SPÉCIFIQUEMENT les concepts ratés
- Difficulté progressive (facile → exigeant)
- Inclure explication pour chaque bonne réponse
- Varier les types (QCM, vrai/faux, texte court)
- La langue est le FRANÇAIS

Format JSON :
{
  "contenu_json": {
    "titre": "Quiz de remédiation",
    "consigne": "texte d'introduction",
    "concepts_rates": ["concept1", "concept2"],
    "questions": [
      {
        "question": "texte",
        "type": "qcm" | "vrai_faux" | "texte_libre",
        "options": ["A", "B", "C", "D"],
        "bonne_reponse": "B",
        "explication": "pourquoi c'est correct"
      }
    ]
  }
}"""


# ══════════════════════════════════════════════════════════════════════════════════════
# FONCTIONS DE GÉNÉRATION PAR TYPE
# ══════════════════════════════════════════════════════════════════════════════════════

def generer_bloc_simplifie(context: dict) -> dict:
    """Génère un bloc simplifié (trigger: temps_long ou multi_reouverture)."""
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

Génère en JSON."""
    result = _call_claude(SYSTEM_BLOC_SIMPLIFIE, user_prompt)
    if result['error']:
        return None, result['error'], 0
    try:
        wrapper = json.loads(result['content'])
        data = wrapper.get('contenu_json', {})
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/bloc] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


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
        wrapper = json.loads(result['content'])
        data = wrapper.get('contenu_json', {})
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/seq] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


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
        wrapper = json.loads(result['content'])
        data = wrapper.get('contenu_json', {})
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_claude/mod] JSON invalide : %s', e)
        return None, f'JSON invalide : {e}', result['tokens']


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
        wrapper = json.loads(result['content'])
        data = wrapper.get('contenu_json', {})
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
    'sequence_complexe':   generer_sequence_adaptative,
    'module_difficile':    generer_module_revision,
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