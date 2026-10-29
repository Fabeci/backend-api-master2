# courses/transcription.py
# =============================================================================
# Transcription locale optionnelle des vidéos et audios pour le RAG du tuteur.
#
# Dépendances :
#   - ffmpeg (système) pour le décodage audio ;
#   - faster-whisper + un modèle Whisper téléchargé localement.
#
# Si faster-whisper ou le modèle ne sont pas disponibles, le RAG continue
# normalement et se rabat sur le texte du bloc / les documents indexés.
# =============================================================================

from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_model = None
_model_key: tuple[str, str, str] | None = None

# Formats traités par Whisper (le fichier doit être accessible localement).
MEDIA_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
}


def disponible() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _setting(name: str, default: str) -> str:
    try:
        from django.conf import settings
        return str(getattr(settings, name, default) or default)
    except Exception:
        return os.environ.get(name, default)


def _get_model():
    global _model, _model_key
    from faster_whisper import WhisperModel

    model_name = _setting("WHISPER_MODEL", "tiny")
    device = _setting("WHISPER_DEVICE", "cpu")
    compute = _setting("WHISPER_COMPUTE_TYPE", "int8")
    key = (model_name, device, compute)

    with _lock:
        if _model is None or _model_key != key:
            cache_dir = _setting("WHISPER_CACHE_DIR", "")
            kwargs = {"device": device, "compute_type": compute}
            if cache_dir:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                kwargs["download_root"] = cache_dir
            logger.info(
                "[transcription] chargement Whisper model=%s device=%s compute=%s",
                model_name, device, compute,
            )
            _model = WhisperModel(model_name, **kwargs)
            _model_key = key
    return _model


def _duration_seconds(path: str) -> float | None:
    """Durée via ffprobe si disponible (pour éviter de transcrire des heures)."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return float((result.stdout or "").strip())
    except Exception:
        return None


def transcrire(path: str | Path) -> str:
    """Transcrit un fichier local en texte. Retourne '' si indisponible."""
    if not disponible():
        return ""

    fichier = Path(path)
    if not fichier.exists() or not fichier.is_file():
        return ""
    if fichier.suffix.lower() not in MEDIA_EXTENSIONS:
        return ""

    max_duration = int(_setting("WHISPER_MAX_DURATION", "900"))
    duration = _duration_seconds(str(fichier))
    if duration is not None and duration > max_duration:
        logger.info(
            "[transcription] média ignoré (%ss > %ss) : %s",
            int(duration), max_duration, fichier.name,
        )
        return ""

    try:
        model = _get_model()
        language = _setting("WHISPER_LANGUAGE", "fr")
        segments, info = model.transcribe(
            str(fichier),
            language=language or None,
            vad_filter=True,
            beam_size=1,
            condition_on_previous_text=False,
        )
        texte = " ".join((segment.text or "").strip() for segment in segments).strip()
        logger.info(
            "[transcription] %s : %s caractères (%s langue=%s)",
            fichier.name, len(texte), getattr(info, "duration", "?"),
            getattr(info, "language", "?"),
        )
        return texte
    except Exception:
        logger.exception("[transcription] échec de transcription : %s", fichier)
        return ""
