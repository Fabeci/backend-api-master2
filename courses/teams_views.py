# courses/teams_views.py
# =============================================================================
# Endpoints Microsoft Teams (réunions en direct) via Microsoft Graph.
#
#   GET  /api/v1/teams/statut/                       → intégration configurée ?
#   POST /api/v1/sessions/<pk>/teams/creer/          → crée la réunion + lien
#   POST /api/v1/sessions/<pk>/teams/synchroniser/   → rapport de présence → présences
# =============================================================================

import logging
import re
import unicodedata

from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.views import APIView

from core.rbac import RBACPermission
from users.models import Apprenant

from courses.models import Participation
from courses.meet_views import _get_session
from courses.views import api_error, api_success

from . import teams_service as teams

logger = logging.getLogger(__name__)


def _norm(value: str) -> str:
    s = (value or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


class TeamsStatusAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return api_success("Statut Microsoft Teams", {"configure": teams.is_configured()}, status.HTTP_200_OK)


class SessionTeamsCreateAPIView(APIView):
    """Crée une réunion Microsoft Teams pour la session et enregistre le lien."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        session = _get_session(request, pk)

        try:
            reunion = teams.creer_reunion(session.titre, session.date_debut, session.date_fin)
        except teams.TeamsNotConfigured as exc:
            return api_error(
                "Microsoft Teams n'est pas configuré sur le serveur.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except teams.TeamsError as exc:
            return api_error(
                "Échec de la création de la réunion Microsoft Teams.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        session.teams_join_url = reunion.get("join_url", "")
        session.teams_meeting_id = reunion.get("id", "")
        session.visio_provider = "teams"
        session.save(update_fields=["teams_join_url", "teams_meeting_id", "visio_provider"])

        return api_success(
            "Réunion Microsoft Teams créée avec succès.",
            {
                "id": session.id,
                "teams_join_url": session.teams_join_url,
                "teams_meeting_id": session.teams_meeting_id,
            },
            status.HTTP_201_CREATED,
        )


class SessionTeamsSyncAPIView(APIView):
    """Rapport de présence Teams → présences des inscrits."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        session = _get_session(request, pk)

        if not session.teams_meeting_id:
            return api_error(
                "Aucune réunion Microsoft Teams n'est associée à cette session.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            participants = teams.lister_participants(session.teams_meeting_id)
        except teams.TeamsNotConfigured as exc:
            return api_error(
                "Microsoft Teams n'est pas configuré sur le serveur.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except teams.TeamsError as exc:
            return api_error(
                "Échec de la récupération du rapport de présence Teams.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        emails_presents = {(p.get("email") or "").strip().lower() for p in participants if p.get("email")}
        noms_presents = {_norm(p.get("display_name")) for p in participants if p.get("display_name")}

        inscrits = Apprenant.objects.filter(inscriptions_cours__cours=session.cours).distinct()

        presents = 0
        correspondances = []
        for apprenant in inscrits:
            email = (apprenant.email or "").strip().lower()
            nom_complet = _norm(f"{apprenant.prenom or ''} {apprenant.nom or ''}")
            est_present = (bool(email) and email in emails_presents) or (
                bool(nom_complet) and nom_complet in noms_presents
            )

            Participation.objects.update_or_create(
                session=session,
                apprenant=apprenant,
                defaults={
                    "statut": "present" if est_present else "absent",
                    "source": "auto",
                    "completed_at": timezone.now(),
                },
            )
            if est_present:
                presents += 1

            correspondances.append({
                "apprenant_id": apprenant.id,
                "nom": f"{apprenant.prenom or ''} {apprenant.nom or ''}".strip(),
                "email": apprenant.email or "",
                "present": est_present,
            })

        session.nb_presents = presents
        session.meet_derniere_sync = timezone.now()
        session.save(update_fields=["nb_presents", "meet_derniere_sync"])

        return api_success(
            "Présences synchronisées depuis Microsoft Teams.",
            {
                "presents": presents,
                "inscrits": inscrits.count(),
                "participants_google": len(participants),
                "participants": participants,
                "correspondances": correspondances,
                "meet_derniere_sync": session.meet_derniere_sync,
            },
            status.HTTP_200_OK,
        )
