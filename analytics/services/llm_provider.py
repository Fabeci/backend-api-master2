# analytics/services/llm_provider.py
# ============================================================================
# COUCHE D'ABSTRACTION LLM — un seul point de sortie pour tous les fournisseurs.
#
# Objectif : pouvoir fonctionner 100 % HORS-LIGNE (Ollama local) sans toucher
# aux générateurs pédagogiques, tout en gardant Claude / Gemini / OpenAI /
# Mistral en options. Tout est piloté par variables d'environnement.
#
# Configuration dans .env :
#   AI_PROVIDER=ollama                     # ollama | claude | gemini | openai | mistral | mock
#   OLLAMA_BASE_URL=http://127.0.0.1:11434
#   OLLAMA_MODEL=qwen2.5:3b-instruct
#   GEMINI_API_KEY=...                     # optionnel
#   GEMINI_MODEL=gemini-2.0-flash
#   MISTRAL_API_KEY=...                    # optionnel
#   MISTRAL_MODEL=mistral-small-latest
#   AI_TIMEOUT=60
#   AI_OFFLINE_FALLBACK=False              # True = repli "mock" si le fournisseur échoue
#
# Aucune dépendance obligatoire : Ollama/Gemini/OpenAI/Mistral passent par
# httpx (déjà présent) ; Claude utilise le SDK `anthropic` s'il est installé.
# ============================================================================

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None


# ── Utilitaires ─────────────────────────────────────────────────────────────

def _err(msg: str) -> dict:
    return {'content': '', 'tokens': 0, 'error': msg}


def _norm(result: dict, provider: str, model: str, degraded: bool = False) -> dict:
    return {
        'content': (result.get('content') or ''),
        'tokens': int(result.get('tokens') or 0),
        'error': result.get('error'),
        'provider': provider,
        'model': model,
        'degraded': degraded,
    }


def _extract_json_block(text: str) -> str:
    """Retire les éventuelles fences Markdown ```json ... ```."""
    if not text:
        return ''
    t = text.strip()
    if t.startswith('```'):
        t = re.sub(r'^```[a-zA-Z]*\s*', '', t)
        t = re.sub(r'\s*```$', '', t)
    return t.strip()


# ── Fournisseurs ────────────────────────────────────────────────────────────

def _call_ollama(system_prompt, user_prompt, json_mode, max_tokens):
    """LLM 100 % local / hors-ligne via l'API HTTP d'Ollama."""
    if httpx is None:
        return _err('httpx non installé')
    base = (getattr(settings, 'OLLAMA_BASE_URL', 'http://127.0.0.1:11434') or '').rstrip('/')
    model = getattr(settings, 'OLLAMA_MODEL', 'qwen2.5:3b-instruct')
    timeout = getattr(settings, 'AI_TIMEOUT', 60)

    # NB : on n'active volontairement PAS `format: 'json'` pour Ollama. Sa
    # grammaire JSON plante (HTTP 500) ou TRONQUE la sortie sur les longs
    # prompts. On demande le JSON via le prompt et on parse tolérant (_loads).
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'stream': False,
        # Évite le rechargement du modèle (3 s) entre deux messages.
        'keep_alive': getattr(settings, 'OLLAMA_KEEP_ALIVE', '30m'),
        'options': {
            'temperature': 0.4,
            'num_predict': max_tokens,
            'num_ctx': getattr(settings, 'OLLAMA_NUM_CTX', 8192),
        },
    }

    try:
        r = httpx.post(f'{base}/api/chat', json=payload, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.error('[llm/ollama] %s', exc)
        return _err(f'Ollama injoignable ({base}) : {exc}')

    if data.get('error'):
        return _err(f"Ollama: {data['error']}")
    content = (data.get('message') or {}).get('content', '')
    tokens = int(data.get('prompt_eval_count', 0)) + int(data.get('eval_count', 0))
    return {'content': content, 'tokens': tokens, 'error': None}


def _call_claude(system_prompt, user_prompt, json_mode, max_tokens):
    if anthropic is None:
        return _err('anthropic non installé')
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '') or ''
    if not api_key:
        return _err('ANTHROPIC_API_KEY manquant')
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-20250514'),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}],
        )
        content = resp.content[0].text if resp.content else ''
        tokens = resp.usage.input_tokens + resp.usage.output_tokens
        return {'content': content, 'tokens': tokens, 'error': None}
    except Exception as exc:  # noqa: BLE001
        logger.error('[llm/claude] %s', exc)
        return _err(str(exc))


def _call_openai_compatible(base_url, api_key, model, system_prompt,
                             user_prompt, json_mode, max_tokens):
    """OpenAI et Mistral partagent l'API /chat/completions."""
    if httpx is None:
        return _err('httpx non installé')
    if not api_key:
        return _err('clé API manquante')
    timeout = getattr(settings, 'AI_TIMEOUT', 60)
    payload = {
        'model': model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': 0.4,
        'max_tokens': max_tokens,
    }
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    try:
        r = httpx.post(
            f'{base_url.rstrip("/")}/chat/completions',
            headers={'Authorization': f'Bearer {api_key}'},
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        j = r.json()
        content = j['choices'][0]['message']['content']
        tokens = (j.get('usage') or {}).get('total_tokens', 0)
        return {'content': content, 'tokens': tokens, 'error': None}
    except Exception as exc:  # noqa: BLE001
        logger.error('[llm/openai-compatible:%s] %s', base_url, exc)
        return _err(str(exc))


def _call_gemini(system_prompt, user_prompt, json_mode, max_tokens):
    if httpx is None:
        return _err('httpx non installé')
    api_key = getattr(settings, 'GEMINI_API_KEY', '') or getattr(settings, 'GOOGLE_API_KEY', '')
    if not api_key:
        return _err('GEMINI_API_KEY manquant')
    model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash')
    timeout = getattr(settings, 'AI_TIMEOUT', 60)
    url = (
        'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{model}:generateContent?key={api_key}'
    )
    payload = {
        'systemInstruction': {'parts': [{'text': system_prompt}]},
        'contents': [{'role': 'user', 'parts': [{'text': user_prompt}]}],
        'generationConfig': {'temperature': 0.4, 'maxOutputTokens': max_tokens},
    }
    if json_mode:
        payload['generationConfig']['responseMimeType'] = 'application/json'
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        content = j['candidates'][0]['content']['parts'][0]['text']
        tokens = (j.get('usageMetadata') or {}).get('totalTokenCount', 0)
        return {'content': content, 'tokens': tokens, 'error': None}
    except Exception as exc:  # noqa: BLE001
        logger.error('[llm/gemini] %s', exc)
        return _err(str(exc))


def _call_mock(system_prompt, user_prompt, json_mode, max_tokens):
    """Repli déterministe (aucun réseau) — évite les 500 et dégrade proprement."""
    if not json_mode:
        # Chat libre (tuteur) : renvoyer un texte lisible, pas du JSON.
        question = ""
        if user_prompt:
            marqueur = "QUESTION DE L'APPRENANT :"
            question = user_prompt.split(marqueur)[-1].strip() if marqueur in user_prompt else user_prompt
            question = question.strip()[:300]
        return {
            "content": (
                "**Mode démonstration — aucun fournisseur IA n'est configuré.**\n\n"
                "Je ne peux pas produire une réponse pédagogique réelle pour le moment. "
                "Pour activer le tuteur, renseignez `AI_PROVIDER` et la clé correspondante "
                "(ou un serveur Ollama) dans le fichier `.env` du backend.\n\n"
                + (f"Votre question : « {question} »" if question else "")
            ),
            "tokens": 0,
            "error": None,
        }
    payload = json.dumps({
        'contenu_json': {
            'type_generation': 'indisponible',
            'titre': 'Contenu temporairement indisponible',
            'contenu_html': (
                "<p>Le générateur de contenu local n'est pas disponible pour "
                "le moment. Réessayez plus tard.</p>"
            ),
            'concepts_cibles': [],
            'questions': [],
            'etapes': [],
            'bloc_contents': [],
        }
    }, ensure_ascii=False)
    return {'content': payload, 'tokens': 0, 'error': None}


_PROVIDERS = {
    'claude': _call_claude,
    'ollama': _call_ollama,
    'gemini': _call_gemini,
    'mock': _call_mock,
}

# Modèle associé à chaque fournisseur (pour l'observabilité).
_MODEL_ATTR = {
    'claude': ('ANTHROPIC_MODEL', 'claude-sonnet-4-20250514'),
    'ollama': ('OLLAMA_MODEL', 'qwen2.5:3b-instruct'),
    'gemini': ('GEMINI_MODEL', 'gemini-2.0-flash'),
    'openai': ('OPENAI_MODEL', 'gpt-4o-mini'),
    'mistral': ('MISTRAL_MODEL', 'mistral-small-latest'),
    'mock': ('', 'fallback'),
}


def _model_for(provider: str) -> str:
    attr, default = _MODEL_ATTR.get(provider, ('', provider))
    return getattr(settings, attr, default) if attr else default


def call_llm(system_prompt: str, user_prompt: str,
             json_mode: bool = True, max_tokens: int = None) -> dict:
    """
    Appelle le fournisseur LLM configuré (settings.AI_PROVIDER).

    Retourne toujours un dict :
      {
        'content': str, 'tokens': int, 'error': str | None,
        'provider': str, 'model': str, 'degraded': bool
      }
    """
    provider = (getattr(settings, 'AI_PROVIDER', 'claude') or 'claude').strip().lower()
    max_tokens = max_tokens or getattr(settings, 'ANTHROPIC_MAX_TOKENS', 4000)
    fallback_enabled = getattr(settings, 'AI_OFFLINE_FALLBACK', False)

    # Fournisseurs OpenAI-compatibles
    if provider == 'openai':
        model = _model_for('openai')
        return _norm(
            _call_openai_compatible('https://api.openai.com/v1',
                                    getattr(settings, 'OPENAI_API_KEY', ''),
                                    model, system_prompt, user_prompt, json_mode, max_tokens),
            'openai', model,
        )
    if provider == 'mistral':
        model = _model_for('mistral')
        return _norm(
            _call_openai_compatible('https://api.mistral.ai/v1',
                                    getattr(settings, 'MISTRAL_API_KEY', ''),
                                    model, system_prompt, user_prompt, json_mode, max_tokens),
            'mistral', model,
        )

    fn = _PROVIDERS.get(provider)
    if fn is None:
        logger.warning('[llm] fournisseur inconnu "%s" → repli claude', provider)
        provider = 'claude'
        fn = _call_claude

    model = _model_for(provider)
    result = fn(system_prompt, user_prompt, json_mode, max_tokens)

    # Repli local si le fournisseur échoue (utile quand le réseau est instable).
    if result.get('error') and provider != 'mock' and fallback_enabled:
        logger.warning('[llm] %s a échoué (%s) → repli mock', provider, result['error'])
        return _norm(_call_mock(system_prompt, user_prompt, json_mode, max_tokens),
                     'mock', 'fallback', degraded=True)

    return _norm(result, provider, model)


def get_provider_info() -> dict:
    """Petit utilitaire de diagnostic (endpoint debug, logs…)."""
    provider = (getattr(settings, 'AI_PROVIDER', 'claude') or 'claude').lower()
    return {
        'provider': provider,
        'model': _model_for(provider),
        'offline_fallback': getattr(settings, 'AI_OFFLINE_FALLBACK', False),
        'ollama_base_url': getattr(settings, 'OLLAMA_BASE_URL', ''),
    }
