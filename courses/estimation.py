# courses/estimation.py
# ============================================================================
# ESTIMATION AUTOMATIQUE DE LA DURÉE D'UN BLOC DE CONTENU
#
# Heuristique volontairement simple et déterministe (pas d'IA) :
#   - texte / html / markdown : nombre de mots ÷ vitesse de lecture
#   - code source             : nombre de lignes ÷ vitesse de lecture de code
#   - média / lien            : durée de base selon le type
# Le résultat est borné pour éviter les valeurs aberrantes.
# ============================================================================
import math
import re

# Vitesses (ajustables sans migration).
MOTS_PAR_MINUTE       = 160   # lecture pédagogique (avec compréhension)
LIGNES_CODE_PAR_MINUTE = 15   # lecture de code

# Durées de base (minutes) pour les contenus non mesurables au mot.
DUREE_BASE_PAR_TYPE = {
    'video':   5,
    'audio':   4,
    'image':   2,
    'fichier': 4,
    'lien':    5,
}

# Socle de lecture/prise de notes (minutes) ajouté aux contenus textuels,
# indépendamment du volume : lire, comprendre, relire, noter.
SOCLE_TEXTUEL = 4
SOCLE_PAR_TYPE = {
    'texte':    SOCLE_TEXTUEL,
    'html':     SOCLE_TEXTUEL,
    'markdown': SOCLE_TEXTUEL,
    'code':     SOCLE_TEXTUEL,
}

DUREE_MIN = 3
DUREE_MAX = 180

_WORD_RE        = re.compile(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ][0-9A-Za-zÀ-ÖØ-öø-ÿ'’\-]*")
_TAG_RE         = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_ENTITY_RE      = re.compile(r"&[a-zA-Z]+;")


def _clean_html(html: str) -> str:
    if not html:
        return ''
    text = _SCRIPT_STYLE_RE.sub(' ', html)
    text = _TAG_RE.sub(' ', text)
    text = _ENTITY_RE.sub(' ', text)
    return text


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ''))


def estimer_duree_minutes(bloc) -> int:
    """Retourne une durée estimée (minutes) à partir du contenu réel du bloc."""
    type_bloc = (getattr(bloc, 'type_bloc', '') or '').strip().lower()

    # 1) Contenu textuel : on prend le champ le plus riche (pas de cumul).
    champs = (
        getattr(bloc, 'contenu_texte', '') or '',
        _clean_html(getattr(bloc, 'contenu_html', '') or ''),
        getattr(bloc, 'contenu_markdown', '') or '',
    )
    mots = max((_count_words(c) for c in champs), default=0)
    minutes_texte = math.ceil(mots / MOTS_PAR_MINUTE) if mots else 0

    # 2) Code source : lignes non vides.
    code = getattr(bloc, 'code_source', '') or ''
    lignes = sum(1 for line in code.splitlines() if line.strip())
    minutes_code = math.ceil(lignes / LIGNES_CODE_PAR_MINUTE) if lignes else 0

    # 3) Durée de base pour les médias / liens + socle pour le texte.
    base = DUREE_BASE_PAR_TYPE.get(type_bloc, 0) + SOCLE_PAR_TYPE.get(type_bloc, 0)

    total = base + minutes_texte + minutes_code
    if total <= 0:
        total = DUREE_MIN
    return max(DUREE_MIN, min(DUREE_MAX, int(total)))
