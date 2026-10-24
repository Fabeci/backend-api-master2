# core/rbac.py
# ============================================================================
# RBAC SOMAPRO — source de vérité côté API.
#
# Principe : Rôle → Permission → Ressource → Action (+ périmètre/scope).
# La matrice ci-dessous reflète `permissions.config.ts` (frontend) ; l'API
# reste l'autorité : masquer un bouton ne protège rien.
#
# Usage dans une vue / un ViewSet :
#     rbac_resource = 'parents'
#     permission_classes = [IsAuthenticated, RBACPermission]
#
# Actions de base mappées depuis l'action DRF :
#   list/retrieve      → view
#   create             → create
#   update/partial_upd → edit
#   destroy            → delete
# Actions métier : déclarer `rbac_action_map = {'publier': 'publish', ...}`.
# ============================================================================

from rest_framework import permissions

# ── Rôles ────────────────────────────────────────────────────────────────────
_CANON = {
    'superadmin': 'SuperAdmin', 'admin': 'Admin',
    'responsable': 'Responsable', 'responsableacademique': 'Responsable',
    'formateur': 'Formateur', 'apprenant': 'Apprenant', 'parent': 'Parent',
}


def role_key(user) -> str | None:
    role = getattr(user, "role", None)
    name = getattr(role, "name", None)
    if not name:
        return None
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


def display_role(user) -> str | None:
    # MONO-ÉTABLISSEMENT : plus de rôle SuperAdmin. Un éventuel superuser
    # technique est traité comme Admin de l'établissement unique.
    if getattr(user, "is_superuser", False):
        return "Admin"
    return _CANON.get(role_key(user) or "")


# ── Matrice de base : ressource → action → rôles ─────────────────────────────
_SUPER = []  # MONO-ÉTABLISSEMENT : plus de SuperAdmin
_ADMIN_SA = ["Admin"]
_STAFF = ["Admin", "Responsable"]
_CONTENT_MAKERS = ["Formateur"]  # ✅ Responsable = LECTURE SEULE (spec)

ROLE_PERMISSIONS: dict = {
    "admins":      {"view": _ADMIN_SA, "create": _ADMIN_SA, "edit": _ADMIN_SA, "delete": _ADMIN_SA},
    "users":       {"view": _ADMIN_SA, "create": _ADMIN_SA, "edit": _ADMIN_SA, "delete": _ADMIN_SA},
    "responsables": {"view": _ADMIN_SA, "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "formateurs":  {"view": _STAFF + ["Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "apprenants":  {"view": ["SuperAdmin", "Admin", "Responsable", "Formateur", "Apprenant", "Parent"],
                    "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "parents":     {"view": _STAFF + ["Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},

    # Lecture : tous les profils voient LEUR établissement (le queryset reste
    # filtré par établissement → aucune fuite). Écriture : Admin/SuperAdmin.
    "etablissements": {"view": _SUPER + ["Admin", "Responsable", "Formateur", "Apprenant", "Parent"],
                       "create": _SUPER, "edit": _SUPER + ["Admin"], "delete": _SUPER},
    "annees_scolaires": {"view": _ADMIN_SA, "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "departements": {"view": ["Admin", "Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "filieres":     {"view": ["Admin", "Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "matieres":     {"view": ["Admin", "Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "classes":      {"view": _ADMIN_SA + ["Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "groupes":      {"view": _ADMIN_SA + ["Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "specialites":  {"view": ["Admin", "Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "domaines_etudes": {"view": ["Admin", "Responsable", "Formateur"], "create": ["Admin"], "edit": ["Admin"], "delete": ["Admin"]},
    "inscriptions": {"view": _ADMIN_SA + _STAFF + ["Formateur", "Apprenant", "Parent"],
                     "create": ["SuperAdmin", "Admin"], "edit": ["SuperAdmin", "Admin"], "delete": ["SuperAdmin", "Admin"]},

    # ✅ Affectations d'enseignement : le Responsable PEUT les gérer (son périmètre).
    "affectations": {"view": _STAFF + ["Formateur"], "create": _STAFF, "edit": _STAFF, "delete": _STAFF},
    "semestres":   {"view": _STAFF + ["Formateur"], "create": _STAFF, "edit": _STAFF, "delete": _STAFF},
    "ues":         {"view": _STAFF + ["Formateur"], "create": _STAFF, "edit": _STAFF, "delete": _STAFF},
    "cours":      {"view": _ADMIN_SA + ["Responsable", "Formateur", "Apprenant", "Parent"],
                   "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": _CONTENT_MAKERS},
    "modules":    {"view": _ADMIN_SA + ["Responsable", "Formateur", "Apprenant", "Parent"],
                   "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": _CONTENT_MAKERS},
    "sequences":  {"view": _ADMIN_SA + ["Responsable", "Formateur", "Apprenant", "Parent"],
                   "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": _CONTENT_MAKERS},
    "sessions":   {"view": _ADMIN_SA + ["Responsable", "Formateur", "Apprenant", "Parent"], "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": _CONTENT_MAKERS},
    "suivi":      {"view": _ADMIN_SA + ["Responsable", "Formateur", "Apprenant", "Parent"],
                   "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": ["Admin"]},
    "participations": {"view": _ADMIN_SA + _STAFF + ["Formateur", "Apprenant", "Parent"],
                       "create": _ADMIN_SA + _CONTENT_MAKERS, "edit": _ADMIN_SA + _CONTENT_MAKERS, "delete": _ADMIN_SA + _CONTENT_MAKERS},
    "progression": {"view": _ADMIN_SA + _STAFF + ["Formateur", "Apprenant", "Parent"],
                    "create": _ADMIN_SA + _CONTENT_MAKERS + ["Apprenant"],
                    "edit":   _ADMIN_SA + _CONTENT_MAKERS + ["Apprenant"],
                    "delete": _ADMIN_SA + ["Formateur"]},
    "historique":  {"view": _ADMIN_SA + _STAFF + ["Formateur", "Apprenant", "Parent"],
                    "create": _ADMIN_SA + _CONTENT_MAKERS + ["Apprenant"],
                    "edit":   _ADMIN_SA + ["Formateur"],
                    "delete": _ADMIN_SA + ["Formateur"]},
    # ✅ Admin exclu (gestion des plans d'action interdite à ce profil).
    "planAction":  {"view": ["SuperAdmin", "Responsable", "Formateur", "Apprenant", "Parent"],
                    "create": ["SuperAdmin", "Formateur"], "edit": ["SuperAdmin", "Formateur"], "delete": ["SuperAdmin", "Formateur"]},
    "evaluations": {"view": ["SuperAdmin", "Responsable", "Formateur", "Apprenant", "Parent"],  # ✅ Admin exclu
                    "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": _CONTENT_MAKERS},
    "quiz":       {"view": ["SuperAdmin", "Responsable", "Formateur", "Apprenant"],  # ✅ Admin exclu
                   "create": _CONTENT_MAKERS, "edit": _CONTENT_MAKERS, "delete": _CONTENT_MAKERS},
    "resultats":  {"view": ["SuperAdmin", "Responsable", "Formateur", "Apprenant", "Parent"],  # ✅ Admin exclu
                   "create": ["Apprenant"], "edit": _CONTENT_MAKERS, "delete": ["Admin"]},
}

# ── Actions métier : « resource.action » → rôles ─────────────────────────────
BUSINESS_RULES: dict = {
    "cours.publish":            _ADMIN_SA + _CONTENT_MAKERS,
    "cours.manage":             _CONTENT_MAKERS,
    "cours.validate":           _ADMIN_SA + _CONTENT_MAKERS,
    "evaluations.evaluate":     _ADMIN_SA + _CONTENT_MAKERS,
    "evaluations.publish":      _ADMIN_SA + _CONTENT_MAKERS,
    "resultats.grade":          _ADMIN_SA + _CONTENT_MAKERS,
    "apprenants.enroll":        _ADMIN_SA + _STAFF,
    "inscriptions.enroll":      _ADMIN_SA + _STAFF,
    "rapports.view_reports":    _ADMIN_SA + _STAFF,
    "rapports.export":          _ADMIN_SA + _STAFF + ["Formateur"],
    "users.manage_permissions": _SUPER + ["Admin"],
    "users.import":             _SUPER + ["Admin"],
    "users.export":             _SUPER + ["Admin"],
}

# ── Périmètre (scope) par rôle ───────────────────────────────────────────────
SCOPE_BY_ROLE = {
    "SuperAdmin": "all", "Admin": "establishment", "Responsable": "establishment",
    "Formateur": "assigned", "Apprenant": "self", "Parent": "children",
}


def get_scope(user) -> str:
    return SCOPE_BY_ROLE.get(display_role(user) or "", "none")


def _role_override(role: str, resource: str, action: str):
    """Surcharge DB (RolePermissionOverride) → bool, ou None si absente."""
    try:
        from users.models import RolePermissionOverride
        obj = RolePermissionOverride.objects.filter(
            role=role, resource=resource, action=action
        ).first()
        return obj.allowed if obj is not None else None
    except Exception:
        return None


def has_permission(user, resource: str, action: str) -> bool:
    """Vérifie une permission (resource, action) pour un utilisateur."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True

    # Permissions explicites additives ("resource.action")
    explicit = getattr(user, "permissions", None) or []
    if f"{resource}.{action}" in explicit:
        return True

    role = display_role(user)
    if role is None:
        return False
    # Surcharges en base (prioritaires sur la matrice par défaut)
    override = _role_override(role, resource, action)
    if override is not None:
        return override

    matrix = ROLE_PERMISSIONS.get(resource)
    if matrix and action in matrix:
        return role in matrix[action]

    rule = BUSINESS_RULES.get(f"{resource}.{action}")
    if rule:
        return role in rule

    return False


# ── Vue → ressource (par nom de classe, si `rbac_resource` non déclaré) ──────
VIEW_RESOURCE = {
    "AdminViewSet": "admins",
    "UserViewSet": "users",
    "ParentViewSet": "parents",
    "ApprenantViewSet": "apprenants",
    "FormateurViewSet": "formateurs",
    "ResponsableAcademiqueViewSet": "responsables",
}

# ── Classe → ressource (généralisation). Toute classe ABSENTE = neutre (allow).
#    On n'inclut QUE les classes où ressource+action sont sans ambiguïté ;
#    les flux apprenant (progression, passages, réponses, corrections) sont
#    volontairement exclus pour ne rien casser.
CLASS_RESOURCE = {
    # courses — contenu
    "AffectationEnseignementViewSet": "affectations",
    "SemestreViewSet": "semestres", "UEViewSet": "ues",
    "CoursListCreateAPIView": "cours", "CoursDetailAPIView": "cours", "CoursModulesAPIView": "cours",
    "CoursIndicateursAPIView": "cours",
    "ModuleListCreateAPIView": "modules", "ModuleDetailAPIView": "modules", "ModuleSequencesAPIView": "modules",
    "SequenceListCreateAPIView": "sequences", "SequenceDetailAPIView": "sequences",
    "SequenceBlocsAPIView": "sequences", "SequenceRessourcesAPIView": "sequences",
    "BlocContenuListCreateAPIView": "modules", "BlocContenuDetailAPIView": "modules", "BlocContenuUploadView": "modules",
    "SessionListCreateAPIView": "sessions", "SessionDetailAPIView": "sessions", "SessionParticipantsAPIView": "sessions",
    # ✅ Ressources / estimation / visio : sortis du « neutre » (trou de sécurité)
    "RessourceSequenceListCreateAPIView": "sequences", "RessourceSequenceDetailAPIView": "sequences",
    "RessourceTelechargementAPIView": "sequences",
    "BlocContenuEstimerAPIView": "modules",
    "SessionMeetCreateAPIView": "sessions", "SessionMeetSyncAPIView": "sessions",
    "SessionJitsiCreateAPIView": "sessions",
    "SessionTeamsCreateAPIView": "sessions", "SessionTeamsSyncAPIView": "sessions",
    "SessionInviteListCreateAPIView": "sessions", "SessionInviteDetailAPIView": "sessions",
    # (inscriptions / suivis / participations : écriture possible côté apprenant → laissés neutres)
    # academics
    "InstitutionAPIView": "etablissements", "InstitutionLogoUploadAPIView": "etablissements",
    "GroupeListCreateAPIView": "groupes", "GroupeDetailAPIView": "groupes",
    "ClasseListCreateAPIView": "classes", "ClasseDetailAPIView": "classes",
    "FiliereListCreateAPIView": "filieres", "FiliereDetailAPIView": "filieres",
    "DepartementListCreateAPIView": "departements", "DepartementDetailAPIView": "departements",
    "InscriptionListCreateAPIView": "inscriptions", "InscriptionDetailAPIView": "inscriptions",
    "InscriptionCoursDetailAPIView": "inscriptions",
    # evaluations — structure (hors passage/correction)
    "QuizListCreateAPIView": "quiz", "QuizDetailAPIView": "quiz",
    "QuestionListCreateAPIView": "quiz", "QuestionDetailAPIView": "quiz",
    "ReponseListCreateAPIView": "quiz", "ReponseDetailAPIView": "quiz",
    "EvaluationListCreateAPIView": "evaluations", "EvaluationDetailAPIView": "evaluations",
}

_VIEWSET_ACTION = {
    "list": "view", "retrieve": "view", "create": "create",
    "update": "edit", "partial_update": "edit", "destroy": "delete",
}
_METHOD_ACTION = {
    "GET": "view", "HEAD": "view", "OPTIONS": "view",
    "POST": "create", "PUT": "edit", "PATCH": "edit", "DELETE": "delete",
}


class RBACPermission(permissions.BasePermission):
    """
    Permission DRF RBAC. Lit `view.rbac_resource` (ou la table VIEW_RESOURCE),
    déduit l'action (action ViewSet → méthode HTTP), puis autorise.
    Si l'action est une action métier personnalisée non déclarée, on n'impose
    pas de contrainte RBAC (les autres permissions s'appliquent).
    """
    message = "Vous n'avez pas la permission requise pour cette action."

    def _resource(self, view) -> str | None:
        return (
            getattr(view, "rbac_resource", None)
            or VIEW_RESOURCE.get(view.__class__.__name__)
            or CLASS_RESOURCE.get(view.__class__.__name__)
        )

    def _action(self, request, view) -> str | None:
        mapping = getattr(view, "rbac_action_map", None) or {}
        vaction = getattr(view, "action", None)
        if vaction in mapping:
            return mapping[vaction]
        if vaction in _VIEWSET_ACTION:
            return _VIEWSET_ACTION[vaction]
        if vaction is not None:
            return None  # action personnalisée non mappée
        return _METHOD_ACTION.get(request.method)

    def has_permission(self, request, view) -> bool:
        resource = self._resource(view)
        if not resource:
            return True
        action = self._action(request, view)
        if not action:
            return True
        allowed = has_permission(request.user, resource, action)
        if not allowed:
            self.message = f"Permission refusée : {resource}.{action}."
        return allowed

    def has_object_permission(self, request, view, obj) -> bool:
        """Périmètre objet : institution (et année si présente)."""
        user = request.user
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_superuser", False):
            return True

        if hasattr(obj, "institution_id") and getattr(user, "institution_id", None):
            if obj.institution_id and obj.institution_id != user.institution_id:
                return False
        return True
