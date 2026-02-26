# shared/permissions.py
"""
Permissions DRF centralisées.
À placer dans un module partagé, par exemple : shared/permissions.py
Puis importer dans chaque app avec :
    from shared.permissions import IsSuperAdmin, IsAdmin, ...

RÔLES :
- SuperAdmin  : is_superuser=True  → Institution + User/Admin uniquement
- Admin       : role.name='Admin'  → Tout dans son institution
- Responsable : role.name='Responsable'
- Formateur   : role.name='Formateur'
- Apprenant   : role.name='Apprenant'
- Parent      : role.name='Parent'  → Lecture seule sur données de ses enfants
"""

from rest_framework.permissions import BasePermission


# ============================================================================
# HELPERS
# ============================================================================

def get_role_name(user):
    """Retourne le nom du rôle de l'utilisateur ou None."""
    if hasattr(user, 'role') and user.role:
        return user.role.name
    return None


def is_super_admin(user):
    return getattr(user, 'is_superuser', False)


def is_admin(user):
    return get_role_name(user) == 'Admin'


def is_responsable(user):
    return get_role_name(user) == 'Responsable'


def is_formateur(user):
    return get_role_name(user) == 'Formateur'


def is_apprenant(user):
    return get_role_name(user) == 'Apprenant'


def is_parent(user):
    return get_role_name(user) == 'Parent'


def is_admin_or_responsable(user):
    return get_role_name(user) in ('Admin', 'Responsable')


def is_staff_level(user):
    """Admin ou Responsable ou SuperAdmin."""
    return is_super_admin(user) or is_admin_or_responsable(user)


def same_institution(user, obj):
    """Vérifie que l'objet appartient à la même institution que l'utilisateur."""
    obj_institution_id = getattr(obj, 'institution_id', None)
    user_institution_id = getattr(user, 'institution_id', None)
    if obj_institution_id is None or user_institution_id is None:
        return False
    return obj_institution_id == user_institution_id


# ============================================================================
# PERMISSIONS GLOBALES
# ============================================================================

class IsSuperAdmin(BasePermission):
    """Seuls les SuperAdmins (is_superuser)."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_super_admin(request.user)


class IsAdminOfInstitution(BasePermission):
    """Admin dans son institution."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_admin(request.user)

    def has_object_permission(self, request, view, obj):
        return same_institution(request.user, obj)


class IsResponsable(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_responsable(request.user)

    def has_object_permission(self, request, view, obj):
        return same_institution(request.user, obj)


class IsFormateur(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_formateur(request.user)


class IsApprenant(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_apprenant(request.user)


class IsParent(BasePermission):
    """Parent : lecture seule uniquement sur les données de ses enfants."""
    def has_permission(self, request, view):
        from rest_framework.request import Request
        if not request.user.is_authenticated or not is_parent(request.user):
            return False
        # Parent ne peut jamais écrire
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return False
        return True

    def has_object_permission(self, request, view, obj):
        """Vérifie que l'objet concerne bien un des enfants du parent."""
        return _parent_can_access_object(request.user, obj)


# ============================================================================
# PERMISSIONS COMPOSÉES (CRUD par rôle)
# ============================================================================

class SuperAdminOnly(BasePermission):
    """Uniquement SuperAdmin pour toutes les opérations."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_super_admin(request.user)


class AdminOrResponsableOnly(BasePermission):
    """Admin ou Responsable uniquement."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and is_admin_or_responsable(request.user)

    def has_object_permission(self, request, view, obj):
        return same_institution(request.user, obj)


class ReadOnlyForLowerRoles(BasePermission):
    """
    - SuperAdmin : bloqué (ne gère pas les ressources internes)
    - Admin/Responsable : tout
    - Formateur : lecture + actions sur ses propres ressources
    - Apprenant : lecture seule
    - Parent : lecture seule sur données de ses enfants
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # SuperAdmin bloqué sur les ressources internes
        if is_super_admin(request.user):
            return False
        return True


# ============================================================================
# PERMISSION CRUD GRANULAIRE (utilisée dans les vues)
# ============================================================================

class RoleBasedPermission(BasePermission):
    """
    Permission générique basée sur les rôles.
    
    Usage dans une vue :
        permission_classes = [RoleBasedPermission]
        required_roles_write = ['Admin', 'Responsable']
        required_roles_read = ['Admin', 'Responsable', 'Formateur', 'Apprenant']
        block_superadmin = True  # Pour bloquer SuperAdmin sur ressources internes
    """

    # À surcharger dans la vue
    required_roles_write = ['Admin', 'Responsable']
    required_roles_read = ['Admin', 'Responsable', 'Formateur', 'Apprenant', 'Parent']
    block_superadmin = True  # True = SuperAdmin bloqué (ressources internes)
    allow_parent_read = True

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False

        if is_super_admin(user):
            return not getattr(view, 'block_superadmin', self.block_superadmin)

        role = get_role_name(user)
        if not role:
            return False

        # Parent : lecture seule
        if role == 'Parent':
            if not getattr(view, 'allow_parent_read', self.allow_parent_read):
                return False
            return request.method in ('GET', 'HEAD', 'OPTIONS')

        # Écriture
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            allowed_write = getattr(view, 'required_roles_write', self.required_roles_write)
            return role in allowed_write

        # Lecture
        allowed_read = getattr(view, 'required_roles_read', self.required_roles_read)
        return role in allowed_read

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = get_role_name(user)

        # SuperAdmin
        if is_super_admin(user):
            return not getattr(view, 'block_superadmin', self.block_superadmin)

        # Parent : vérifier que l'objet concerne son enfant
        if role == 'Parent':
            return _parent_can_access_object(user, obj)

        # Formateur : doit être dans la même institution + ressource liée à ses cours
        if role == 'Formateur':
            return same_institution(user, obj)

        # Apprenant : même institution
        if role == 'Apprenant':
            return same_institution(user, obj)

        # Admin/Responsable : même institution
        return same_institution(user, obj)


# ============================================================================
# HELPERS PARENT
# ============================================================================

def _parent_can_access_object(parent_user, obj):
    """
    Vérifie qu'un parent peut accéder à un objet.
    
    Un Parent peut accéder à tout objet qui concerne un de ses enfants.
    Les enfants sont liés via Apprenant.tuteur = parent_user.
    """
    from users.models import Apprenant

    # Récupérer les enfants du parent
    enfants_ids = list(
        Apprenant.objects.filter(tuteur=parent_user).values_list('id', flat=True)
    )
    if not enfants_ids:
        return False

    model_name = obj.__class__.__name__

    # Inscription scolaire
    if model_name == 'Inscription':
        return getattr(obj, 'apprenant_id', None) in enfants_ids

    # Classe / Groupe : via l'inscription de l'enfant
    if model_name == 'Classe':
        from academics.models import Inscription
        return Inscription.objects.filter(
            apprenant_id__in=enfants_ids,
            classe=obj,
            statut='actif'
        ).exists()

    if model_name == 'Groupe':
        from users.models import Apprenant as ApprenantModel
        return ApprenantModel.objects.filter(
            id__in=enfants_ids,
            groupe=obj
        ).exists()

    # Cours, Module, Sequence, BlocContenu, etc. : via InscriptionCours
    if model_name in ('Cours', 'Module', 'Sequence', 'BlocContenu', 'RessourceSequence'):
        from courses.models import InscriptionCours
        if model_name == 'Cours':
            return InscriptionCours.objects.filter(
                apprenant_id__in=enfants_ids,
                cours=obj,
                statut='inscrit'
            ).exists()
        # Pour Module/Sequence/Bloc : remonter au cours
        cours_id = _get_cours_id_from_obj(obj)
        if cours_id:
            return InscriptionCours.objects.filter(
                apprenant_id__in=enfants_ids,
                cours_id=cours_id,
                statut='inscrit'
            ).exists()
        return False

    # InscriptionCours
    if model_name == 'InscriptionCours':
        return getattr(obj, 'apprenant_id', None) in enfants_ids

    # Progression
    if model_name in ('BlocProgress', 'SequenceProgress', 'ModuleProgress', 'CoursProgress'):
        return getattr(obj, 'apprenant_id', None) in enfants_ids

    # Passages quiz/évaluation
    if model_name in ('PassageEvaluation', 'PassageQuiz', 'ReponseQuestion', 'ReponseQuiz'):
        if model_name == 'PassageEvaluation':
            return getattr(obj, 'apprenant_id', None) in enfants_ids
        if model_name == 'PassageQuiz':
            return getattr(obj, 'apprenant_id', None) in enfants_ids
        if model_name == 'ReponseQuestion':
            return getattr(obj.passage_evaluation, 'apprenant_id', None) in enfants_ids
        if model_name == 'ReponseQuiz':
            return getattr(obj.passage_quiz, 'apprenant_id', None) in enfants_ids

    # Suivi, Participation
    if model_name == 'Suivi':
        return getattr(obj, 'apprenant_id', None) in enfants_ids
    if model_name == 'Participation':
        return getattr(obj, 'apprenant_id', None) in enfants_ids

    # Session : parent peut voir les sessions de cours de ses enfants
    if model_name == 'Session':
        from courses.models import InscriptionCours
        cours_id = getattr(obj, 'cours_id', None)
        if cours_id:
            return InscriptionCours.objects.filter(
                apprenant_id__in=enfants_ids,
                cours_id=cours_id,
                statut='inscrit'
            ).exists()
        return False

    # Analytics (lecture seule pour parent sur les données de ses enfants)
    if model_name in ('BlocAnalytics', 'BlocAnalyticsSummary', 
                       'SequenceAnalyticsSummary', 'ModuleAnalyticsSummary'):
        return getattr(obj, 'apprenant_id', None) in enfants_ids

    # Par défaut : refusé
    return False


def _get_cours_id_from_obj(obj):
    """Remonte à l'ID du cours depuis un objet imbriqué."""
    model_name = obj.__class__.__name__

    if model_name == 'Module':
        return getattr(obj, 'cours_id', None)

    if model_name == 'Sequence':
        module = getattr(obj, 'module', None)
        return getattr(module, 'cours_id', None) if module else None

    if model_name in ('BlocContenu', 'RessourceSequence'):
        sequence = getattr(obj, 'sequence', None)
        if sequence:
            module = getattr(sequence, 'module', None)
            return getattr(module, 'cours_id', None) if module else None
    return None


# ============================================================================
# PERMISSIONS SPÉCIFIQUES PAR DOMAINE
# ============================================================================

class InstitutionPermission(BasePermission):
    """
    Institution :
    - SuperAdmin : CRUD complet
    - Admin : lecture + modification de son institution
    - Autres : lecture seule de leur institution
    - Parent : lecture seule de l'institution de son enfant
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        # SuperAdmin : tout autorisé
        if is_super_admin(request.user):
            return True
        role = get_role_name(request.user)
        # Parent : lecture seule
        if role == 'Parent':
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        # POST (création) : SuperAdmin uniquement
        if request.method == 'POST':
            return is_super_admin(request.user)
        return role in ('Admin', 'Responsable', 'Formateur', 'Apprenant')

    def has_object_permission(self, request, view, obj):
        user = request.user
        if is_super_admin(user):
            return True
        role = get_role_name(user)
        # DELETE : SuperAdmin uniquement
        if request.method == 'DELETE':
            return False
        # PUT/PATCH : Admin uniquement dans son institution
        if request.method in ('PUT', 'PATCH'):
            return role == 'Admin' and same_institution(user, obj)
        # GET : tout le monde dans son institution
        return same_institution(user, obj)


class CourseContentPermission(BasePermission):
    """
    Cours / Modules / Séquences / Blocs :
    - SuperAdmin : bloqué
    - Admin/Responsable : CRUD complet
    - Formateur : CRUD sur SES cours uniquement
    - Apprenant : lecture seule sur ses cours inscrits
    - Parent : lecture seule sur cours de ses enfants
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_super_admin(request.user):
            return False  # SuperAdmin bloqué sur ressources internes
        role = get_role_name(request.user)
        if role == 'Parent':
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        if role == 'Apprenant':
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        return role in ('Admin', 'Responsable', 'Formateur')

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = get_role_name(user)
        if role == 'Parent':
            return _parent_can_access_object(user, obj)
        if role == 'Apprenant':
            return same_institution(user, obj)
        if role == 'Formateur':
            # Écriture : vérifier que c'est son cours
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                return _formateur_owns_resource(user, obj)
            return same_institution(user, obj)
        return same_institution(user, obj)


class EvaluationPermission(BasePermission):
    """
    Quiz / Évaluations / Questions :
    - SuperAdmin : bloqué
    - Admin/Responsable : CRUD complet
    - Formateur : CRUD sur ses cours
    - Apprenant : lecture seule (sans les bonnes réponses)
    - Parent : bloqué
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_super_admin(request.user):
            return False
        role = get_role_name(request.user)
        if role == 'Parent':
            return False
        if role == 'Apprenant':
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        return role in ('Admin', 'Responsable', 'Formateur')


class PassagePermission(BasePermission):
    """
    PassageEvaluation / PassageQuiz / Réponses :
    - SuperAdmin : bloqué
    - Admin/Responsable : lecture + suppression
    - Formateur : lecture sur ses cours
    - Apprenant : CRUD sur SES passages uniquement
    - Parent : lecture sur passages de ses enfants
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_super_admin(request.user):
            return False
        role = get_role_name(request.user)
        if role == 'Parent':
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        if role == 'Apprenant':
            return True  # Filtré au niveau objet
        return role in ('Admin', 'Responsable', 'Formateur')

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = get_role_name(user)
        if role == 'Parent':
            return _parent_can_access_object(user, obj)
        if role == 'Apprenant':
            # Apprenant ne peut accéder qu'à SES passages
            apprenant_id = getattr(obj, 'apprenant_id', None)
            return apprenant_id == user.id
        if role == 'Formateur':
            return same_institution(user, obj)
        return same_institution(user, obj)


class ProgressPermission(BasePermission):
    """
    BlocProgress / SequenceProgress / ModuleProgress / CoursProgress :
    - SuperAdmin : bloqué
    - Admin/Responsable : lecture seule
    - Formateur : lecture seule
    - Apprenant : CRUD sur SA progression uniquement
    - Parent : lecture sur progression de ses enfants
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_super_admin(request.user):
            return False
        role = get_role_name(request.user)
        if role == 'Parent':
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        return True

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = get_role_name(user)
        if role == 'Parent':
            return _parent_can_access_object(user, obj)
        if role == 'Apprenant':
            return getattr(obj, 'apprenant_id', None) == user.id
        if role in ('Admin', 'Responsable', 'Formateur'):
            # Lecture seulement
            return request.method in ('GET', 'HEAD', 'OPTIONS')
        return False


class AnalyticsPermission(BasePermission):
    """
    Analytics : lecture seule, jamais modifiable manuellement.
    - SuperAdmin : bloqué
    - Admin/Responsable/Formateur : lecture (toute leur institution)
    - Apprenant : lecture sur ses propres analytics
    - Parent : lecture sur analytics de ses enfants
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_super_admin(request.user):
            return False
        # Analytics : jamais de création/modification/suppression manuelle
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            return False
        role = get_role_name(request.user)
        return role in ('Admin', 'Responsable', 'Formateur', 'Apprenant', 'Parent')

    def has_object_permission(self, request, view, obj):
        user = request.user
        role = get_role_name(user)
        if role == 'Parent':
            return _parent_can_access_object(user, obj)
        if role == 'Apprenant':
            return getattr(obj, 'apprenant_id', None) == user.id
        return same_institution(user, obj)


# ============================================================================
# HELPER FORMATEUR
# ============================================================================

def _formateur_owns_resource(formateur, obj):
    """Vérifie qu'un formateur est bien l'enseignant du cours lié à l'objet."""
    model_name = obj.__class__.__name__

    if model_name == 'Cours':
        return getattr(obj, 'enseignant_id', None) == formateur.id

    if model_name == 'Module':
        cours = getattr(obj, 'cours', None)
        return getattr(cours, 'enseignant_id', None) == formateur.id if cours else False

    if model_name == 'Sequence':
        module = getattr(obj, 'module', None)
        cours = getattr(module, 'cours', None) if module else None
        return getattr(cours, 'enseignant_id', None) == formateur.id if cours else False

    if model_name in ('BlocContenu', 'RessourceSequence'):
        cours_id = _get_cours_id_from_obj(obj)
        if cours_id:
            from courses.models import Cours
            return Cours.objects.filter(id=cours_id, enseignant=formateur).exists()
        return False

    if model_name == 'Session':
        return getattr(obj, 'formateur_id', None) == formateur.id

    if model_name in ('Quiz', 'Evaluation'):
        cours = getattr(obj, 'cours', None)
        return getattr(cours, 'enseignant_id', None) == formateur.id if cours else False

    return False