# courses/ai_service.py
# ============================================================================
# SERVICE IA — Intégration ChatGPT pour la génération de contenu adaptatif
#
# Installation :
#   pip install openai
#
# Configuration dans settings.py :
#   OPENAI_API_KEY = env('OPENAI_API_KEY')   # ou os.environ.get(...)
#   OPENAI_MODEL   = 'gpt-4o'                # ou 'gpt-4-turbo', 'gpt-3.5-turbo'
#   OPENAI_MAX_TOKENS = 2000
#
# Dans .env :
#   OPENAI_API_KEY=sk-proj-...
# ============================================================================

import json
import logging
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI as _OpenAIClass
    _openai_available = True
except ImportError:
    _OpenAIClass = None
    _openai_available = False
    logger.warning('[ai_service] openai non installé — pip install openai')

# Lazy — instancié à la première requête pour ne pas crasher au démarrage
# si OPENAI_API_KEY est absent ou vide au moment de l'import.
_client = None

def _get_client():
    """Retourne (ou crée) le client OpenAI. Retourne None si non configuré."""
    global _client
    if _client is not None:
        return _client
    if not _openai_available:
        return None
    api_key = getattr(settings, 'OPENAI_API_KEY', '') or ''
    if not api_key:
        logger.error(
            '[ai_service] OPENAI_API_KEY absent dans settings.py. '
            'Ajouter : OPENAI_API_KEY = env("OPENAI_API_KEY") ou os.environ.get(...)'
        )
        return None
    try:
        _client = _OpenAIClass(api_key=api_key)
        return _client
    except Exception as e:
        logger.error('[ai_service] Impossible de créer le client OpenAI : %s', e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _get_model():
    return getattr(settings, 'OPENAI_MODEL', 'gpt-4o')

def _get_max_tokens():
    return getattr(settings, 'OPENAI_MAX_TOKENS', 2000)


def _call_gpt(system_prompt: str, user_prompt: str) -> dict:
    """
    Appel ChatGPT brut. Retourne :
      { 'content': str, 'tokens': int, 'error': str|None }
    """
    client = _get_client()
    if not client:
        msg = 'openai non installé' if not _openai_available else 'OPENAI_API_KEY manquant dans settings.py'
        return {'content': '', 'tokens': 0, 'error': msg}

    try:
        response = client.chat.completions.create(
            model=_get_model(),
            max_tokens=_get_max_tokens(),
            temperature=0.7,
            response_format={"type": "json_object"},   # force JSON valide
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ''
        tokens  = response.usage.total_tokens if response.usage else 0
        return {'content': content, 'tokens': tokens, 'error': None}

    except Exception as exc:
        logger.error('[ai_service] Erreur OpenAI : %s', exc)
        return {'content': '', 'tokens': 0, 'error': str(exc)}


# ══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION DE BLOC SIMPLIFIÉ (trigger : temps_long)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_BLOC = """
Tu es un assistant pédagogique expert. Tu aides des apprenants qui peinent à comprendre
un contenu de formation.

Ton rôle : générer une explication ALTERNATIVE et SIMPLIFIÉE d'un bloc de cours,
adaptée à un apprenant qui a passé beaucoup de temps dessus sans comprendre.

Règles STRICTES :
- Répondre UNIQUEMENT en JSON valide (pas de texte avant/après)
- Le contenu HTML doit être propre, lisible, sans balises inutiles
- Utiliser des analogies concrètes et du quotidien
- Structurer avec des titres h3, listes ul/ol, et exemples
- Maximum 600 mots dans le contenu HTML
- La langue est le FRANÇAIS
"""

def generer_bloc_simplifie(context: dict) -> dict:
    """
    Génère un bloc de cours simplifié pour un apprenant qui a trop de temps
    passé sur le bloc original.

    context = {
        'bloc_titre': str,
        'bloc_contenu': str,          # texte brut ou HTML du bloc original
        'duree_estimee_min': int,
        'duree_passee_min': int,
        'ratio_pct': int,             # ex: 180 = 180% du temps estimé
        'nb_ouvertures': int,
        'scroll_max_pct': int,
        'cours_titre': str,
        'sequence_titre': str,
    }

    Retourne :
    {
        'type_generation': str,
        'titre': str,
        'contenu_html': str,
        'concepts_cibles': list[str],
    }
    """
    user_prompt = f"""
Un apprenant rencontre des difficultés avec ce bloc de formation :

TITRE DU BLOC : {context.get('bloc_titre', 'Inconnu')}
COURS : {context.get('cours_titre', '')}
SÉQUENCE : {context.get('sequence_titre', '')}

DONNÉES ANALYTICS :
- Temps estimé pour ce bloc : {context.get('duree_estimee_min', '?')} minutes
- Temps réellement passé : {context.get('duree_passee_min', '?')} minutes
- Ratio temps passé/estimé : {context.get('ratio_pct', '?')}%
- Nombre de fois ouvert : {context.get('nb_ouvertures', 1)}
- Pourcentage du bloc lu (scroll) : {context.get('scroll_max_pct', 0)}%

CONTENU ORIGINAL DU BLOC (à simplifier) :
---
{context.get('bloc_contenu', 'Contenu non disponible')[:3000]}
---

Génère une explication alternative SIMPLIFIÉE de ce bloc.
Réponds en JSON avec exactement ces champs :
{{
  "type_generation": "explication_simple" | "analogie" | "exemples" | "resume" | "faq",
  "titre": "titre accrocheur de l'explication alternative",
  "contenu_html": "contenu HTML complet avec h3, ul/ol, p, strong...",
  "concepts_cibles": ["concept1", "concept2", "concept3"]
}}
"""
    result = _call_gpt(SYSTEM_BLOC, user_prompt)
    if result['error']:
        return None, result['error'], 0

    try:
        data = json.loads(result['content'])
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_service/bloc] JSON invalide : %s\n%s', e, result['content'][:500])
        return None, f'JSON invalide : {e}', result['tokens']


# ══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION DE QUIZ DE REMÉDIATION (trigger : quiz_rate)
# ══════════════════════════════════════════════════════════════════════════════

SYSTEM_QUIZ = """
Tu es un expert en évaluation pédagogique. Tu crées des quiz de REMÉDIATION
pour aider les apprenants à consolider des notions qu'ils n'ont pas maîtrisées.

Règles STRICTES :
- Répondre UNIQUEMENT en JSON valide
- Les questions doivent cibler SPÉCIFIQUEMENT les concepts ratés
- Proposer des explications détaillées pour chaque bonne réponse
- Varier les types (QCM, vrai/faux, réponse courte)
- Difficulté progressive (commencer facile, finir plus exigeant)
- La langue est le FRANÇAIS
"""

def generer_quiz_remediation(context: dict) -> dict:
    """
    Génère un quiz de remédiation ciblé sur les concepts ratés.

    context = {
        'quiz_titre': str,
        'quiz_description': str,
        'score_obtenu': int,          # 0-100
        'questions_ratees': list[{    # questions du quiz original ratées
            'question': str,
            'bonne_reponse': str,
            'reponse_apprenant': str,
            'explication': str,
        }],
        'cours_titre': str,
        'sequence_titre': str,
        'nb_tentatives': int,
    }

    Retourne :
    {
        'titre': str,
        'consigne': str,
        'concepts_rates': list[str],
        'questions': list[{
            'question': str,
            'type': 'qcm'|'vrai_faux'|'texte_libre',
            'options': list[str],       # vide si texte_libre
            'bonne_reponse': str,
            'explication': str,
        }]
    }
    """
    questions_str = '\n'.join([
        f"  - Question : {q.get('question', '')}\n"
        f"    Bonne réponse : {q.get('bonne_reponse', '')}\n"
        f"    Réponse de l'apprenant : {q.get('reponse_apprenant', 'non répondu')}\n"
        f"    Explication : {q.get('explication', '')}"
        for q in context.get('questions_ratees', [])
    ])

    user_prompt = f"""
Un apprenant a échoué à ce quiz de formation :

QUIZ : {context.get('quiz_titre', 'Inconnu')}
COURS : {context.get('cours_titre', '')}
SÉQUENCE : {context.get('sequence_titre', '')}
SCORE OBTENU : {context.get('score_obtenu', '?')}%
NOMBRE DE TENTATIVES : {context.get('nb_tentatives', 1)}

QUESTIONS RATÉES :
{questions_str if questions_str else 'Données des questions non disponibles'}

Génère un quiz de REMÉDIATION avec 4 à 6 nouvelles questions ciblant
spécifiquement les concepts ratés.

Réponds en JSON avec exactement ces champs :
{{
  "titre": "titre du quiz de remédiation",
  "consigne": "texte d'introduction motivant pour l'apprenant",
  "concepts_rates": ["concept1", "concept2"],
  "questions": [
    {{
      "question": "texte de la question",
      "type": "qcm",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "bonne_reponse": "Option B",
      "explication": "Explication détaillée de pourquoi c'est la bonne réponse"
    }}
  ]
}}
"""
    result = _call_gpt(SYSTEM_QUIZ, user_prompt)
    if result['error']:
        return None, result['error'], 0

    try:
        data = json.loads(result['content'])
        return data, None, result['tokens']
    except json.JSONDecodeError as e:
        logger.error('[ai_service/quiz] JSON invalide : %s\n%s', e, result['content'][:500])
        return None, f'JSON invalide : {e}', result['tokens']


# ══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL — appelé depuis les views
# ══════════════════════════════════════════════════════════════════════════════

def traiter_demande_ai(ai_request) -> bool:
    """
    Traite une AIAnalysisRequest et génère le contenu approprié.
    Met à jour ai_request.status en base.
    Retourne True si succès.
    """
    from .models_ai import BlocGenere, QuizGenere

    ai_request.status = 'pending'
    ai_request.save(update_fields=['status'])

    if ai_request.trigger == 'temps_long':
        data, error, tokens = generer_bloc_simplifie(ai_request.prompt_context)

    elif ai_request.trigger == 'quiz_rate':
        data, error, tokens = generer_quiz_remediation(ai_request.prompt_context)

    else:
        ai_request.status        = 'skipped'
        ai_request.error_message = f'Trigger non géré : {ai_request.trigger}'
        ai_request.completed_at  = timezone.now()
        ai_request.save(update_fields=['status', 'error_message', 'completed_at'])
        return False

    ai_request.tokens_used  = tokens
    ai_request.completed_at = timezone.now()

    if error or not data:
        ai_request.status        = 'error'
        ai_request.error_message = error or 'Données vides'
        ai_request.save(update_fields=['status', 'error_message', 'tokens_used', 'completed_at'])
        return False

    ai_request.gpt_response = json.dumps(data, ensure_ascii=False)
    ai_request.status       = 'success'
    ai_request.save(update_fields=['status', 'gpt_response', 'tokens_used', 'completed_at'])

    # Créer l'objet généré
    if ai_request.trigger == 'temps_long':
        BlocGenere.objects.create(
            ai_request      = ai_request,
            apprenant       = ai_request.apprenant,
            bloc_source     = ai_request.bloc,
            type_generation = data.get('type_generation', 'explication_simple'),
            titre           = data.get('titre', 'Explication simplifiée'),
            contenu_html    = data.get('contenu_html', ''),
            concepts_cibles = data.get('concepts_cibles', []),
        )

    elif ai_request.trigger == 'quiz_rate':
        QuizGenere.objects.create(
            ai_request    = ai_request,
            apprenant     = ai_request.apprenant,
            quiz_source   = ai_request.quiz,
            titre         = data.get('titre', 'Quiz de remédiation'),
            consigne      = data.get('consigne', ''),
            questions     = data.get('questions', []),
            concepts_rates= data.get('concepts_rates', []),
        )

    return True