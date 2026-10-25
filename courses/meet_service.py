# courses/meet_service.py
# =============================================================================
# Google Meet / Calendar — création d'une réunion DATÉE (avec invités) et
# récupération des participants pour alimenter les présences.
#
# Variables d'environnement (backend-api-master2/.env) :
#   GOOGLE_OAUTH_CLIENT_ID       — Client ID OAuth2 (Google Cloud)
#   GOOGLE_OAUTH_CLIENT_SECRET   — Client Secret OAuth2
#   GOOGLE_OAUTH_REFRESH_TOKEN   — Refresh token (voir docs/google-meet.md)
#
# Portées nécessaires :
#   - https://www.googleapis.com/auth/calendar.events         (créer l'événement + Meet + invités)
#   - https://www.googleapis.com/auth/meetings.space.readonly (lire les participants)
# =============================================================================

import os
import uuid
import logging

logger = logging.getLogger(__name__)

MEET_SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/meetings.space.created",
    "https://www.googleapis.com/auth/meetings.space.readonly",
]

_REQUIRED_ENV = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "GOOGLE_OAUTH_REFRESH_TOKEN",
)


class GoogleMeetNotConfigured(Exception):
    """Levée quand les identifiants Google ne sont pas fournis."""


class GoogleMeetError(Exception):
    """Erreur renvoyée par l'API Google."""


def is_configured() -> bool:
    return all(os.environ.get(key) for key in _REQUIRED_ENV)


def _credentials():
    if not is_configured():
        raise GoogleMeetNotConfigured(
            "Google n'est pas configuré (GOOGLE_OAUTH_CLIENT_ID / "
            "GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REFRESH_TOKEN)."
        )
    try:
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover
        raise GoogleMeetNotConfigured(
            "Bibliothèques Google non installées (google-api-python-client, google-auth)."
        ) from exc

    return Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=MEET_SCOPES,
    )


def _build(api: str, version: str):
    from googleapiclient.discovery import build
    return build(api, version, credentials=_credentials(), cache_discovery=False)


def _iso(dt) -> str | None:
    from datetime import timezone as dt_timezone
    if not dt:
        return None
    return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_meeting_code(url: str) -> str:
    if not url:
        return ""
    return url.rstrip("/").split("/")[-1].split("?")[0]


def creer_evenement_meet(sujet: str, date_debut, date_fin,
                         description: str = "", invites: list[str] | None = None) -> dict:
    """
    Crée un événement Google Agenda DATÉ avec un lien Meet rattaché (et invite
    les participants). Retourne { event_id, join_url, meeting_code }.
    """
    try:
        calendar = _build("calendar", "v3")
    except GoogleMeetNotConfigured:
        raise
    except Exception as exc:  # pragma: no cover
        raise GoogleMeetError(f"Init Calendar: {exc}") from exc

    body = {
        "summary": sujet or "Séance",
        "description": description or "",
        "start": {"dateTime": _iso(date_debut), "timeZone": "UTC"},
        "end":   {"dateTime": _iso(date_fin),   "timeZone": "UTC"},
        "conferenceData": {
            "createRequest": {
                "requestId": uuid.uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    emails = sorted({e.strip() for e in (invites or []) if e and "@" in e})
    if emails:
        body["attendees"] = [{"email": e} for e in emails]

    try:
        event = calendar.events().insert(
            calendarId="primary",
            conferenceDataVersion=1,
            sendUpdates="all",
            body=body,
        ).execute()
    except Exception as exc:  # pragma: no cover
        logger.error("Échec création événement Calendar : %s", exc)
        raise GoogleMeetError(str(exc)) from exc

    conf = event.get("conferenceData", {}) or {}
    join_url = event.get("hangoutLink") or ""
    if not join_url:
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                join_url = ep.get("uri", "")
                break

    return {
        "event_id": event.get("id", ""),
        "join_url": join_url,
        "meeting_code": conf.get("conferenceId") or _extract_meeting_code(join_url),
    }


def creer_pour_session(session) -> dict:
    """Crée l'événement Meet daté d'une séance et invite les inscrits + le formateur."""
    emails: list[str] = []
    try:
        from courses.models import InscriptionCours
        emails += list(
            InscriptionCours.objects
            .filter(cours=session.cours)
            .values_list("apprenant__email", flat=True)
        )
    except Exception:
        pass

    formateur = getattr(session, "formateur", None)
    if formateur is not None and getattr(formateur, "email", None):
        emails.append(formateur.email)

    # Invités externes ajoutés manuellement
    try:
        emails += list(session.invites_externes.values_list("email", flat=True))
    except Exception:
        pass

    return creer_evenement_meet(
        sujet=getattr(session, "titre", "") or "Séance",
        date_debut=getattr(session, "date_debut", None),
        date_fin=getattr(session, "date_fin", None),
        description=getattr(session, "description", "") or "",
        invites=emails,
    )


def list_participants(space_name: str) -> list[dict]:
    """
    Participants d'une conférence Meet.
    `space_name` peut être un nom d'espace ('spaces/xxx') OU un code de réunion
    ('abc-defg-hij') — les deux sont acceptés.
    """
    if not space_name:
        return []

    try:
        service = _build("meet", "v2")
    except GoogleMeetNotConfigured:
        raise
    except Exception as exc:  # pragma: no cover
        raise GoogleMeetError(f"Init Meet: {exc}") from exc

    if str(space_name).startswith("spaces/"):
        filtre = f'space.name="{space_name}"'
    else:
        filtre = f'space.meeting_code="{space_name}"'

    participants: list[dict] = []
    try:
        records = (
            service.conferenceRecords().list(filter=filtre).execute().get("conferenceRecords", [])
        )
        for record in records:
            record_name = record.get("name")
            if not record_name:
                continue
            rows = (
                service.conferenceRecords().participants()
                .list(parent=record_name).execute().get("participants", [])
            )
            for row in rows:
                user = row.get("signedinUser") or row.get("anonymousUser") or {}
                participants.append({
                    "display_name": row.get("displayName") or user.get("displayName") or "",
                    "email": user.get("user") or "",
                })
    except Exception as exc:  # pragma: no cover
        logger.error("Échec list_participants Meet : %s", exc)
        raise GoogleMeetError(str(exc)) from exc

    return participants
