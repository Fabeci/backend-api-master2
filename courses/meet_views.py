# courses/meet_views.py
# =============================================================================
# Endpoints Google Meet pour les sessions en direct.
#
#   GET  /api/v1/meet/statut/                       → l'intégration est-elle configurée ?
#   POST /api/v1/sessions/<pk>/meet/creer/          → crée un espace Meet + enregistre le lien
#   POST /api/v1/sessions/<pk>/meet/synchroniser/   → récupère les participants → présences
# =============================================================================

import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.views import APIView

from core.rbac import RBACPermission
from users.models import Apprenant

from courses.models import InscriptionCours, Participation, Session
from courses.utils import get_user_context
from courses.views import _apply_context_filter, api_error, api_success

from . import meet_service as gm

logger = logging.getLogger(__name__)


def _get_session(request, pk) -> Session:
    """Session filtrée selon le périmètre (rôle/institution/année) de l'utilisateur."""
    context = get_user_context(request)
    qs = Session.objects.select_related("formateur", "cours", "institution", "annee_scolaire")
    qs = _apply_context_filter(qs, context)
    session = get_object_or_404(qs, pk=pk)

    # ✅ PÉRIMÈTRE : un formateur n'agit que sur les séances de SES cours
    #    (Meet / Teams / Jitsi / invités partagent tous ce helper).
    if (context or {}).get("role_name") == "Formateur":
        from .utils import can_manage_cours
        if not session.cours_id or not can_manage_cours(request.user, session.cours):
            from django.http import Http404
            raise Http404("Séance introuvable.")
    return session


class GoogleMeetStatusAPIView(APIView):
    """Indique si l'intégration Google Meet est configurée côté serveur."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return api_success(
            "Statut Google Meet",
            {"configure": gm.is_configured()},
            status.HTTP_200_OK,
        )


class SessionMeetCreateAPIView(APIView):
    """Crée un espace Google Meet pour une session et enregistre le lien."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        session = _get_session(request, pk)

        try:
            ev = gm.creer_pour_session(session)
        except gm.GoogleMeetNotConfigured as exc:
            return api_error(
                "Google n'est pas configuré sur le serveur.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except gm.GoogleMeetError as exc:
            return api_error(
                "Échec de la création de la réunion Google Meet.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        session.lien_visio = ev.get("join_url", "")
        session.meet_space_name = ev.get("meeting_code", "")
        session.save(update_fields=["lien_visio", "meet_space_name"])

        return api_success(
            "Réunion Google Meet créée avec succès (datée + invités).",
            {
                "id": session.id,
                "lien_visio": session.lien_visio,
                "meet_space_name": session.meet_space_name,
                "meeting_code": ev.get("meeting_code", ""),
                "event_id": ev.get("event_id", ""),
            },
            status.HTTP_201_CREATED,
        )


class SessionMeetSyncAPIView(APIView):
    """Récupère les participants Google Meet et met à jour les présences."""

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        session = _get_session(request, pk)

        if not session.meet_space_name:
            return api_error(
                "Aucune réunion Google Meet n'est associée à cette session.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            participants = gm.list_participants(session.meet_space_name)
        except gm.GoogleMeetNotConfigured as exc:
            return api_error(
                "Google Meet n'est pas configuré sur le serveur.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except gm.GoogleMeetError as exc:
            return api_error(
                "Échec de la récupération des participants Google Meet.",
                errors={"detail": str(exc)},
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        # Normalisation : email (minuscule) + nom (sans accents, espaces réduits).
        def _norm(value: str) -> str:
            import re
            import unicodedata
            s = (value or "").strip().lower()
            s = unicodedata.normalize("NFKD", s)
            s = "".join(c for c in s if not unicodedata.combining(c))
            return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())

        emails_presents = {
            (p.get("email") or "").strip().lower()
            for p in participants if p.get("email")
        }
        noms_presents = {
            _norm(p.get("display_name"))
            for p in participants if p.get("display_name")
        }

        # Apprenants inscrits au cours de la session.
        inscrits = (
            Apprenant.objects
            .filter(inscriptions_cours__cours=session.cours)
            .distinct()
        )

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
            "Présences synchronisées depuis Google Meet.",
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


class SessionJitsiCreateAPIView(APIView):
    """
    Crée (ou réutilise) une salle Jitsi embarquable dans SOMAPRO pour la session.
    La salle est stable (stockée sur `Session.lien_jitsi`).
    """

    permission_classes = [permissions.IsAuthenticated, RBACPermission]

    def post(self, request, pk):
        import secrets
        from django.conf import settings

        session = _get_session(request, pk)

        if not session.lien_jitsi:
            domain = getattr(settings, "SESSION_JITSI_DOMAIN", "meet.jit.si")
            room = f"SOMAPRO-{session.id}-{secrets.token_urlsafe(6)}"
            session.lien_jitsi = f"https://{domain}/{room}"
            session.save(update_fields=["lien_jitsi"])

        return api_success(
            "Salle de réunion prête.",
            {"id": session.id, "lien_jitsi": session.lien_jitsi},
            status.HTTP_200_OK,
        )
