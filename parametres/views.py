# parametres/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from .models import ParametresPlateforme, ParametresInstitution, PreferencesUtilisateur
from .serializers import (
    ParametresPlateformeSerializer,
    ParametresInstitutionSerializer,
    PreferencesUtilisateurSerializer,
)


def api_ok(data):
    return Response({'success': True, 'data': data}, status=status.HTTP_200_OK)


def api_err(msg, code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': msg}, status=code)


# ─── Helpers de rôle ──────────────────────────────────────────────────────────

def _role(user) -> str:
    return (user.role.name if user.role else '').lower()

def _is_superadmin(user) -> bool:
    return user.is_superuser or 'superadmin' in _role(user) or 'super_admin' in _role(user)

def _is_admin(user) -> bool:
    return _is_superadmin(user) or 'admin' in _role(user)


def _is_staff(user) -> bool:
    """Admin, SuperAdmin ou Responsable (gestion établissement)."""
    return _is_admin(user) or 'responsable' in _role(user)


# ─── Paramètres globaux (SuperAdmin) ─────────────────────────────────────────

class ParametresPlateformeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return api_err('Accès refusé', status.HTTP_403_FORBIDDEN)
        obj  = ParametresPlateforme.get_instance()
        data = ParametresPlateformeSerializer(obj).data
        return api_ok(data)

    def patch(self, request):
        if not _is_superadmin(request.user):
            return api_err('Réservé aux super-administrateurs', status.HTTP_403_FORBIDDEN)
        obj  = ParametresPlateforme.get_instance()
        ser  = ParametresPlateformeSerializer(obj, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return api_ok(ser.data)
        return api_err(str(ser.errors), status.HTTP_400_BAD_REQUEST)


# ─── Paramètres institution (Admin) ──────────────────────────────────────────

class ParametresInstitutionView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_institution(self, user):
        """Retourne l'institution du user, ou None."""
        return getattr(user, 'institution', None)

    def get(self, request):
        if not _is_staff(request.user):
            return api_err('Accès refusé', status.HTTP_403_FORBIDDEN)
        institution = self._get_institution(request.user)
        if not institution:
            return api_ok({})
        obj, _ = ParametresInstitution.objects.get_or_create(institution=institution)
        return api_ok(ParametresInstitutionSerializer(obj).data)

    def patch(self, request):
        if not _is_staff(request.user):
            return api_err('Accès refusé', status.HTTP_403_FORBIDDEN)
        institution = self._get_institution(request.user)
        if not institution:
            return api_err("Aucune institution associée à votre compte.", status.HTTP_400_BAD_REQUEST)
        obj, _ = ParametresInstitution.objects.get_or_create(institution=institution)
        ser = ParametresInstitutionSerializer(obj, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return api_ok(ser.data)
        return api_err(str(ser.errors), status.HTTP_400_BAD_REQUEST)


# ─── Intégrations (statut des connecteurs configurés côté serveur) ───────────

class IntegrationsStatusAPIView(APIView):
    """Statut des intégrations disponibles (configuration côté serveur)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import os
        from django.conf import settings

        if not _is_staff(request.user):
            return api_err('Accès refusé', status.HTTP_403_FORBIDDEN)

        try:
            from courses import meet_service
            meet_ok = bool(meet_service.is_configured())
        except Exception:
            meet_ok = False
        try:
            from courses import teams_service
            teams_ok = bool(teams_service.is_configured())
        except Exception:
            teams_ok = False

        ia_ok = bool(getattr(settings, 'ANTHROPIC_API_KEY', '') or os.environ.get('ANTHROPIC_API_KEY'))

        return api_ok({
            "google_meet": {
                "libelle": "Google Meet",
                "configure": meet_ok,
                "variables": ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REFRESH_TOKEN"],
            },
            "teams": {
                "libelle": "Microsoft Teams",
                "configure": teams_ok,
                "variables": ["TEAMS_TENANT_ID", "TEAMS_CLIENT_ID", "TEAMS_CLIENT_SECRET", "TEAMS_ORGANIZER"],
            },
            "jitsi": {
                "libelle": "Jitsi Meet",
                "configure": True,
                "variables": [],
                "note": "Intégré — aucune clé requise.",
            },
            "ia": {
                "libelle": "Assistant IA (Anthropic)",
                "configure": ia_ok,
                "variables": ["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"],
                "modele": getattr(settings, 'ANTHROPIC_MODEL', None),
            },
        })


# ─── Préférences utilisateur ──────────────────────────────────────────────────

class PreferencesUtilisateurView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        obj = PreferencesUtilisateur.get_or_create_for_user(request.user)
        return api_ok(PreferencesUtilisateurSerializer(obj).data)

    def patch(self, request):
        obj = PreferencesUtilisateur.get_or_create_for_user(request.user)
        ser = PreferencesUtilisateurSerializer(obj, data=request.data, partial=True)
        if ser.is_valid():
            ser.save()
            return api_ok(ser.data)
        return api_err(str(ser.errors), status.HTTP_400_BAD_REQUEST)
