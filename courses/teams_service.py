# courses/teams_service.py
# =============================================================================
# Microsoft Teams — intégration via Microsoft Graph (mode application).
#
# Variables d'environnement (backend-api-master2/.env) :
#   TEAMS_TENANT_ID      — ID du tenant Azure (Entra ID)
#   TEAMS_CLIENT_ID      — Application (client) ID
#   TEAMS_CLIENT_SECRET  — Client secret
#   TEAMS_ORGANIZER      — email/UPN ou id du compte au nom duquel créer les réunions
#
# Permission Graph (application) + consentement admin :
#   OnlineMeetings.ReadWrite.All        (créer la réunion)
#   OnlineMeetingArtifact.Read.All      (rapport de présence)
# =============================================================================

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_REQUIRED_ENV = ("TEAMS_TENANT_ID", "TEAMS_CLIENT_ID", "TEAMS_CLIENT_SECRET", "TEAMS_ORGANIZER")


class TeamsNotConfigured(Exception):
    """Identifiants Microsoft non fournis."""


class TeamsError(Exception):
    """Erreur renvoyée par Microsoft Graph."""


def is_configured() -> bool:
    return all(os.environ.get(k) for k in _REQUIRED_ENV)


def _get_token() -> str:
    if not is_configured():
        raise TeamsNotConfigured(
            "Microsoft Teams n'est pas configuré (TEAMS_TENANT_ID / TEAMS_CLIENT_ID / "
            "TEAMS_CLIENT_SECRET / TEAMS_ORGANIZER)."
        )

    tenant = os.environ["TEAMS_TENANT_ID"]
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    data = urllib.parse.urlencode({
        "client_id": os.environ["TEAMS_CLIENT_ID"],
        "client_secret": os.environ["TEAMS_CLIENT_SECRET"],
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode()

    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=20) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as exc:
        raise TeamsError(f"Auth: {exc.code} {exc.read().decode(errors='ignore')}") from exc
    except Exception as exc:  # pragma: no cover
        raise TeamsError(f"Auth: {exc}") from exc


def _graph(method: str, path: str, token: str, body: dict | None = None) -> dict:
    url = GRAPH_BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise TeamsError(f"{exc.code} {exc.read().decode(errors='ignore')}") from exc
    except Exception as exc:  # pragma: no cover
        raise TeamsError(str(exc)) from exc


def creer_reunion(sujet: str, date_debut, date_fin) -> dict:
    """Crée une réunion Teams pour l'organisateur. Retourne {id, join_url}."""
    from django.utils import timezone

    def _iso(dt):
        from datetime import timezone as dt_timezone
        if not dt:
            return None
        return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    token = _get_token()
    organizer = urllib.parse.quote(os.environ["TEAMS_ORGANIZER"], safe="")

    payload = {"subject": sujet or "Réunion"}
    if date_debut:
        payload["startDateTime"] = _iso(date_debut)
    if date_fin:
        payload["endDateTime"] = _iso(date_fin)

    res = _graph("POST", f"/users/{organizer}/onlineMeetings", token, payload)
    return {
        "id": res.get("id", ""),
        "join_url": res.get("joinUrl") or res.get("joinWebUrl") or "",
        "subject": res.get("subject", ""),
    }


def lister_participants(meeting_id: str) -> list[dict]:
    """Rapport de présence d'une réunion Teams (disponible après la fin)."""
    if not meeting_id:
        return []

    token = _get_token()
    organizer = urllib.parse.quote(os.environ["TEAMS_ORGANIZER"], safe="")
    base = f"/users/{organizer}/onlineMeetings/{meeting_id}"

    rapports = _graph("GET", f"{base}/attendanceReports", token).get("value", [])
    participants: list[dict] = []

    for rapport in rapports:
        rid = rapport.get("id")
        if not rid:
            continue
        records = _graph("GET", f"{base}/attendanceReports/{rid}/attendanceRecords", token).get("value", [])
        for rec in records:
            ident = rec.get("identity") or {}
            user = ident.get("user") or {}
            participants.append({
                "display_name": user.get("displayName") or ident.get("displayName") or "",
                "email": user.get("email") or rec.get("emailAddress") or "",
            })

    return participants
