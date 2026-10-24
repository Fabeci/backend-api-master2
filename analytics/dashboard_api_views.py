# analytics/dashboard_api_views.py
"""
Dashboard API Views — vues minces (thin controllers).

Chaque vue :
1. Vérifie les permissions (rôle, auth)
2. Construit un DashboardContext
3. Délègue à son service dédié
4. Retourne la Response

Toute la logique métier et le filtrage SQL sont dans analytics/services/.
"""
import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from users.permissions import IsSuperUser
from .services.dashboard_context import DashboardContext, PermissionDenied
from .services.dashboard_router import DashboardRouter

logger = logging.getLogger(__name__)


# ── Helpers de backward compat (conservés pour éviter les imports cassés) ──────

def _role_name(user):
    return user.role.name if getattr(user, 'role', None) else None


def _check_role(request, *allowed_roles):
    if request.user.is_superuser:
        return None
    if _role_name(request.user) not in allowed_roles:
        return Response(
            {'error': f"Accès refusé. Rôle requis : {', '.join(allowed_roles)}."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _empty(title: str) -> dict:
    """Payload vide retourné en cas d'erreur non bloquante."""
    from django.utils import timezone
    return {
        'title': title, 'description': '', 'kpis': [],
        'charts': [], 'alerts': [], 'last_updated': timezone.now().isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Endpoint unifié — détection automatique du rôle
# GET /api/v1/dashboard/
# ══════════════════════════════════════════════════════════════════════════════

class UnifiedDashboardAPIView(APIView):
    """
    Endpoint universel : le backend identifie le rôle de l'utilisateur
    et retourne le dashboard adapté sans que le frontend n'ait à choisir.

    Paramètres optionnels (query string) :
      - annee_scolaire_id : restreint les données à une année spécifique
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            ctx    = DashboardContext(request.user, dict(request.query_params))
            router = DashboardRouter()
            data   = router.route(ctx)
            data['_role'] = ctx.role_name   # info de débogage visible côté frontend
            return Response(data)
        except PermissionDenied as exc:
            logger.warning('UnifiedDashboardAPIView — PermissionDenied: %s', exc)
            return Response({'error': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            logger.exception('UnifiedDashboardAPIView')
            return Response(_empty('Dashboard'), status=status.HTTP_200_OK)


# ══════════════════════════════════════════════════════════════════════════════
# Vues dédiées (backward compat — conservées pour les routes existantes)
# ══════════════════════════════════════════════════════════════════════════════

class AdminDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _check_role(request, 'Admin')
        if denied:
            return denied
        try:
            from .services.dashboard_admin import DashboardAdminService
            ctx     = DashboardContext(request.user, dict(request.query_params))
            service = DashboardAdminService(ctx)
            return Response(service.build(ctx.filters))
        except Exception:
            logger.exception('AdminDashboardAPIView')
            return Response(_empty('Dashboard Admin'))


class FormateurDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _check_role(request, 'Formateur')
        if denied:
            return denied
        try:
            from .services.dashboard_formateur import DashboardFormateurService
            ctx     = DashboardContext(request.user, dict(request.query_params))
            # Vérification que le profil Formateur existe
            if ctx.profile is ctx.user:
                return Response(_empty('Dashboard Formateur'))
            service = DashboardFormateurService(ctx)
            return Response(service.build(ctx.filters))
        except Exception:
            logger.exception('FormateurDashboardAPIView')
            return Response(_empty('Dashboard Formateur'))


class ResponsableDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _check_role(request, 'Responsable', 'ResponsableAcademique')
        if denied:
            return denied
        try:
            from .services.dashboard_responsable import DashboardResponsableService
            ctx     = DashboardContext(request.user, dict(request.query_params))
            service = DashboardResponsableService(ctx)
            return Response(service.build(ctx.filters))
        except Exception:
            logger.exception('ResponsableDashboardAPIView')
            return Response(_empty('Dashboard Responsable Académique'))


class ApprenantDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _check_role(request, 'Apprenant')
        if denied:
            return denied
        try:
            from .services.dashboard_apprenant import DashboardApprenantService
            ctx     = DashboardContext(request.user, dict(request.query_params))
            service = DashboardApprenantService(ctx)
            return Response(service.build(ctx.filters))
        except Exception:
            logger.exception('ApprenantDashboardAPIView')
            return Response(_empty('Mon Dashboard'))


class ParentDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _check_role(request, 'Parent')
        if denied:
            return denied
        try:
            from .services.dashboard_parent import DashboardParentService
            ctx     = DashboardContext(request.user, dict(request.query_params))
            service = DashboardParentService(ctx)
            return Response(service.build(ctx.filters))
        except Exception:
            logger.exception('ParentDashboardAPIView')
            return Response(_empty('Dashboard Parent'))
