# core/rbac_api.py
# ============================================================================
# API RBAC — administration des rôles & permissions (réservé users.manage_permissions).
# ============================================================================
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from academics.views import api_success, api_error
from users.models import User, RolePermissionOverride
from core.rbac import (
    ROLE_PERMISSIONS, BUSINESS_RULES, display_role, has_permission, get_scope, SCOPE_BY_ROLE,
)

import logging

logger = logging.getLogger("somapro.rbac")

BASE_ACTIONS = ["view", "create", "edit", "delete"]

# ✅ Garde-fous : rôles, ressources et actions modifiables via l'API.
KNOWN_ROLES = {"SuperAdmin", "Admin", "Responsable", "Formateur", "Apprenant", "Parent"}
VALID_RESOURCES = set(ROLE_PERMISSIONS.keys()) | {k.split(".", 1)[0] for k in BUSINESS_RULES}
VALID_ACTIONS = set(BASE_ACTIONS) | {k.split(".", 1)[1] for k in BUSINESS_RULES}


def _require_manager(request):
    if not has_permission(request.user, "users", "manage_permissions"):
        return api_error(
            "Vous n'avez pas la permission de gérer les permissions.",
            http_status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _matrix_for_role(role: str) -> dict:
    """{ resource: { view: bool, create: bool, edit: bool, delete: bool } } + overrides."""
    overrides = {
        (o.resource, o.action): o.allowed
        for o in RolePermissionOverride.objects.filter(role=role)
    }
    resources = set(ROLE_PERMISSIONS.keys())
    matrix: dict = {}
    for resource in sorted(resources):
        row = {}
        for action in BASE_ACTIONS:
            if (resource, action) in overrides:
                row[action] = overrides[(resource, action)]
            else:
                row[action] = role in (ROLE_PERMISSIONS.get(resource, {}).get(action) or [])
        matrix[resource] = row
    # actions métier
    business = {}
    for key, roles in BUSINESS_RULES.items():
        resource, _, action = key.partition('.')
        if (resource, action) in overrides:
            business[key] = overrides[(resource, action)]
        else:
            business[key] = role in roles
    return {"base": matrix, "business": business}


class RolesListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_manager(request)
        if denied:
            return denied

        counts = {}
        for u in User.objects.select_related('role').all():
            r = display_role(u) or "Utilisateur"
            counts[r] = counts.get(r, 0) + 1

        known = ["SuperAdmin", "Admin", "Responsable", "Formateur", "Apprenant", "Parent"]
        roles = [{"name": r, "users": counts.get(r, 0), "scope": SCOPE_BY_ROLE.get(r, "none")} for r in known]
        # rôles supplémentaires éventuels
        for name, n in counts.items():
            if name not in known:
                roles.append({"name": name, "users": n, "scope": "none"})

        return api_success("Rôles récupérés", data=roles)


class RolePermissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, role):
        denied = _require_manager(request)
        if denied:
            return denied
        return api_success(
            f"Permissions du rôle {role}",
            data={"role": role, "scope": get_scope_role(role), **_matrix_for_role(role)},
        )

    def put(self, request, role):
        denied = _require_manager(request)
        if denied:
            return denied

        # ✅ Le rôle cible doit être connu.
        if role not in KNOWN_ROLES:
            return api_error("Rôle inconnu.", http_status=status.HTTP_400_BAD_REQUEST)

        # ✅ Seul un Super administrateur peut modifier le rôle SuperAdmin
        #    (empêche un Admin de s'octroyer/altérer les droits suprêmes).
        if role == "SuperAdmin" and display_role(request.user) != "SuperAdmin":
            return api_error(
                "Seul un Super administrateur peut modifier le rôle SuperAdmin.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        overrides = request.data.get("overrides", {})
        if not isinstance(overrides, dict):
            return api_error("Format attendu : { overrides: { 'resource.action': bool } }",
                             http_status=status.HTTP_400_BAD_REQUEST)

        # ✅ Validation préalable de TOUTES les clés (avant toute écriture).
        for key in overrides.keys():
            resource, _, action = str(key).partition(".")
            if not resource or not action:
                return api_error(f"Clé de permission invalide : « {key} ».", http_status=status.HTTP_400_BAD_REQUEST)
            if resource not in VALID_RESOURCES:
                return api_error(f"Ressource inconnue : « {resource} ».", http_status=status.HTTP_400_BAD_REQUEST)
            if action not in VALID_ACTIONS:
                return api_error(f"Action inconnue : « {action} ».", http_status=status.HTTP_400_BAD_REQUEST)

        updated = 0
        for key, allowed in overrides.items():
            resource, _, action = str(key).partition(".")
            value = bool(allowed)

            # ✅ Anti-verrouillage : un non-SuperAdmin ne peut pas retirer la
            #    gestion des permissions (sinon plus personne ne peut revenir).
            if (resource, action) == ("users", "manage_permissions") and not value \
                    and display_role(request.user) != "SuperAdmin":
                return api_error(
                    "Impossible de retirer la gestion des permissions (réservé au Super administrateur).",
                    http_status=status.HTTP_403_FORBIDDEN,
                )

            RolePermissionOverride.objects.update_or_create(
                role=role, resource=resource, action=action,
                defaults={"allowed": value},
            )
            updated += 1

        # ✅ Traçabilité (audit).
        logger.warning(
            "[RBAC] %s a modifié les permissions du rôle %s : %s",
            getattr(request.user, "email", request.user.pk), role,
            {k: bool(v) for k, v in overrides.items()},
        )

        return api_success(f"{updated} permission(s) mise(s) à jour.",
                           data=_matrix_for_role(role))


def get_scope_role(role: str) -> str:
    return SCOPE_BY_ROLE.get(role, "none")


# ── Libellés & regroupements (présentation « fonctionnalités accessibles ») ──
RESOURCE_LABELS = {
    "admins": "Administrateurs", "users": "Utilisateurs", "responsables": "Responsables",
    "formateurs": "Formateurs", "apprenants": "Apprenants", "parents": "Parents",
    "etablissements": "Établissements", "annees_scolaires": "Années scolaires",
    "departements": "Départements", "domaines_etudes": "Domaines d'études",
    "filieres": "Filières", "matieres": "Matières", "specialites": "Spécialités",
    "classes": "Classes", "groupes": "Groupes", "inscriptions": "Inscriptions",
    "cours": "Cours", "modules": "Modules / Séquences / Blocs",
    "sessions": "Sessions & participations", "suivi": "Suivi de progression",
    "evaluations": "Évaluations", "quiz": "Quiz / Questions / Réponses",
    "resultats": "Résultats & passages", "rapports": "Rapports & statistiques",
}
RESOURCE_GROUPS = [
    {"domain": "Établissement & structure",
     "resources": ["etablissements", "annees_scolaires", "classes", "groupes", "inscriptions"]},
    {"domain": "Référentiels",
     "resources": ["departements", "domaines_etudes", "filieres", "matieres", "specialites"]},
    {"domain": "Utilisateurs",
     "resources": ["users", "admins", "responsables", "formateurs", "apprenants", "parents"]},
    {"domain": "Pédagogie",
     "resources": ["cours", "modules", "sessions", "evaluations", "quiz", "resultats", "suivi"]},
]
ACTION_LABELS = {"view": "Consulter", "create": "Créer", "edit": "Modifier", "delete": "Supprimer"}
BUSINESS_LABELS = {
    "cours.publish": "Publier un cours", "cours.manage": "Gérer les cours",
    "cours.validate": "Valider un cours", "modules.manage": "Gérer les modules",
    "sessions.manage": "Gérer les sessions", "sessions.assign": "Affecter des sessions",
    "evaluations.evaluate": "Évaluer", "evaluations.publish": "Publier une évaluation",
    "resultats.grade": "Noter les résultats", "apprenants.enroll": "Inscrire des apprenants",
    "inscriptions.enroll": "Gérer les inscriptions", "rapports.view_reports": "Consulter les rapports",
    "rapports.export": "Exporter des rapports", "users.manage_permissions": "Gérer les permissions",
    "users.import": "Importer des utilisateurs", "users.export": "Exporter des utilisateurs",
}


class RoleFeaturesView(APIView):
    """Fonctionnalités accessibles (lisibles) pour un rôle."""
    permission_classes = [IsAuthenticated]

    def get(self, request, role):
        denied = _require_manager(request)
        if denied:
            return denied

        m = _matrix_for_role(role)
        base, business = m["base"], m["business"]

        groups = []
        for g in RESOURCE_GROUPS:
            items = []
            for res in g["resources"]:
                row = base.get(res) or {}
                acts = [ACTION_LABELS[a] for a in BASE_ACTIONS if row.get(a)]
                if acts:
                    items.append({"label": RESOURCE_LABELS.get(res, res), "actions": acts})
            if items:
                groups.append({"domain": g["domain"], "items": items})

        biz = [BUSINESS_LABELS.get(k, k) for k, v in business.items() if v]

        return api_success(
            f"Fonctionnalités du rôle {role}",
            data={"role": role, "scope": get_scope_role(role), "groups": groups, "business": biz},
        )
