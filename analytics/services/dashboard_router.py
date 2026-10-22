# analytics/services/dashboard_router.py
"""
DashboardRouter — détecte automatiquement le rôle de l'utilisateur
connecté et délègue au service Dashboard approprié.

Utilisé par le endpoint unifié GET /api/v1/dashboard/
"""
from __future__ import annotations

import logging

from .dashboard_context import (
    DashboardContext,
    PermissionDenied,
    ROLE_SUPER_ADMIN,
    ROLE_ADMIN,
    ROLE_RESPONSABLE,
    ROLE_FORMATEUR,
    ROLE_APPRENANT,
    ROLE_PARENT,
)

logger = logging.getLogger(__name__)

# Mapping role → service class (import paresseux dans __call__)
_SERVICE_MAP: dict = {
    ROLE_SUPER_ADMIN: 'analytics.services.dashboard_superadmin.DashboardSuperAdminService',
    ROLE_ADMIN:       'analytics.services.dashboard_admin.DashboardAdminService',
    ROLE_RESPONSABLE: 'analytics.services.dashboard_responsable.DashboardResponsableService',
    ROLE_FORMATEUR:   'analytics.services.dashboard_formateur.DashboardFormateurService',
    ROLE_APPRENANT:   'analytics.services.dashboard_apprenant.DashboardApprenantService',
    ROLE_PARENT:      'analytics.services.dashboard_parent.DashboardParentService',
}


def _import_service(dotted: str):
    """Importe dynamiquement une classe de service."""
    module_path, cls_name = dotted.rsplit('.', 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)


class DashboardRouter:
    """
    Point d'entrée unique pour tous les dashboards.

    Usage:
        ctx    = DashboardContext(request.user, request.query_params)
        router = DashboardRouter()
        data   = router.route(ctx)
    """

    def route(self, ctx: DashboardContext) -> dict:
        """
        Résout le service adapté au rôle du contexte et appelle build().
        Lève PermissionDenied si le rôle est inconnu.
        """
        role = ctx.role_name
        if role not in _SERVICE_MAP:
            raise PermissionDenied(f"Rôle inconnu ou non configuré : {role!r}")

        service_cls = _import_service(_SERVICE_MAP[role])
        service     = service_cls(ctx)
        try:
            return service.build(ctx.filters)
        except Exception as exc:
            logger.exception("DashboardRouter.route — role=%s user=%s", role, ctx.user.pk)
            # Retourne un payload vide plutôt que de laisser l'exception remonter
            # (les vues individuelles gèrent le log, pas le router)
            raise
