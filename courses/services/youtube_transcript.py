# courses/services/youtube_transcript.py
"""Transcription légère d'une vidéo YouTube (sans ffmpeg ni Whisper).

Le module s'appuie sur le paquet optionnel `youtube-transcript-api` : si la
vidéo expose des sous-titres, ils sont récupérés et renvoyés sous forme de
texte. Aucun média n'est téléchargé.

Un cache mémoire (1 h) évite de refaire l'appel à chaque question du tuteur.
En cas d'absence du paquet, de sous-titres indisponibles ou de réseau coupé,
la fonction retourne une chaîne vide : l'appelant garde son comportement de
repli (message « aucun texte disponible »).
"""
from __future__ import annotations

import logging
import re
import time
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 3600  # secondes
_MAX_CHARS = 60_000

_YOUTUBE_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtube-nocookie.com", "www.youtube-nocookie.com", "youtu.be",
}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")


def video_id(url: str | None) -> str | None:
    """Extrait l'identifiant d'une URL YouTube, sinon None."""
    if not url:
        return None
    try:
        parsed = urlparse(str(url).strip())
    except Exception:  # noqa: BLE001
        return None

    host = (parsed.netloc or "").lower().split(":")[0]
    if host not in _YOUTUBE_HOSTS:
        return None

    if host == "youtu.be":
        candidat = parsed.path.strip("/").split("/")[0]
    elif parsed.path.startswith(("/embed/", "/shorts/", "/live/")):
        morceaux = parsed.path.strip("/").split("/")
        candidat = morceaux[1] if len(morceaux) > 1 else ""
    else:
        candidat = (parse_qs(parsed.query).get("v") or [""])[0]

    return candidat if _ID_RE.fullmatch(candidat or "") else None


def _fetch(video: str, langues: tuple[str, ...]) -> str:
    """Appel brut à youtube-transcript-api (isolé pour les tests)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except Exception:  # noqa: BLE001
        logger.info("[youtube] paquet youtube-transcript-api absent")
        return ""

    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):  # v1.x
            try:
                segments = api.fetch(video, languages=list(langues))
            except Exception:  # noqa: BLE001 — repli : n'importe quelle langue
                segments = api.fetch(video)
            return " ".join(getattr(s, "text", "") for s in segments)

        # v0.x
        data = YouTubeTranscriptApi.get_transcript(video, languages=list(langues))
        return " ".join(s.get("text", "") for s in data)
    except Exception:  # noqa: BLE001
        logger.debug("[youtube] sous-titres indisponibles pour %s", video, exc_info=True)
        return ""


def recuperer(url: str | None, langues: tuple[str, ...] = ("fr", "en")) -> str:
    """Transcription texte d'une vidéo YouTube, ou '' si indisponible."""
    vid = video_id(url)
    if not vid:
        return ""

    maintenant = time.monotonic()
    cached = _CACHE.get(vid)
    if cached and maintenant - cached[0] < _CACHE_TTL:
        return cached[1]

    texte = re.sub(r"\s+", " ", _fetch(vid, langues)).strip()[:_MAX_CHARS]
    _CACHE[vid] = (maintenant, texte)
    if texte:
        logger.info("[youtube] transcription récupérée : %s (%s caractères)", vid, len(texte))
    return texte
