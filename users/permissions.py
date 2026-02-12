# users/permissions.py
"""
Permissions DRF personnalisées pour le système multi-tenant.

Hiérarchie des accès :
1. SuperUser : Accès total (toutes institutions, toutes années)
2. Admin : Accès à son institution (toutes années + cours sans année)
3. Responsable : Accès à son institution + son année uniquement
4. Formateur : Accès à son institution + son année uniquement
5. Apprenant : Accès uniquement aux cours inscrits dans son institution
"""

from rest_framework import permissions


class IsSuperUser(permissions.BasePermission):
    """
    Permission : Seuls les SuperUsers.
    Utilisé pour les endpoints d'administration globale.
    """
    message = "Seuls les SuperUsers peuvent accéder à cette ressource."
    
    def has_permission(self, request, view):
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.is_superuser
        )


class HasInstitution(permissions.BasePermission):
    """
    Permission : L'utilisateur DOIT avoir une institution (sauf SuperUser).
    """
    message = "Vous devez être rattaché à une institution pour accéder à cette ressource."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # SuperUser : toujours autorisé
        if request.user.is_superuser:
            return True
        
        # Autres : doivent avoir une institution
        return bool(request.user.institution)


class HasInstitutionAndYear(permissions.BasePermission):
    """
    Permission : L'utilisateur DOIT avoir institution + année scolaire (sauf SuperUser/Admin).
    Utilisé pour Responsable/Formateur/Apprenant.
    """
    message = "Vous devez avoir une institution et une année scolaire active."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # SuperUser : toujours autorisé
        if request.user.is_superuser:
            return True
        
        # Admin : institution suffit (peut voir cours sans année)
        role_name = request.user.role.name if request.user.role else None
        if role_name == 'Admin':
            return bool(request.user.institution)
        
        # Autres : institution + année requises
        return bool(
            request.user.institution and 
            request.user.annee_scolaire_active
        )


class IsStaffOrReadOnly(permissions.BasePermission):
    """
    Permission : 
    - Lecture : utilisateur authentifié
    - Écriture : staff uniquement
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user and 
            request.user.is_authenticated and 
            request.user.is_staff
        )


class CanAccessInstitutionResource(permissions.BasePermission):
    """
    Permission objet : Vérifie que l'utilisateur peut accéder à une ressource
    selon son institution.
    
    Règles :
    - SuperUser : toujours autorisé
    - Autres : l'objet doit appartenir à leur institution
    """
    message = "Vous ne pouvez pas accéder aux ressources d'une autre institution."
    
    def has_object_permission(self, request, view, obj):
        # SuperUser : accès total
        if request.user.is_superuser:
            return True
        
        # L'objet doit avoir un champ 'institution'
        if not hasattr(obj, 'institution'):
            return True  # Pas de restriction si pas de champ institution
        
        # Vérifier que l'institution correspond
        return obj.institution_id == request.user.institution_id


class CanAccessYearResource(permissions.BasePermission):
    """
    Permission objet : Vérifie que l'utilisateur peut accéder à une ressource
    selon son année scolaire.
    
    Règles :
    - SuperUser : toujours autorisé
    - Admin : peut accéder aux cours sans année (pour rattachement)
    - Autres : l'objet doit correspondre à leur année
    """
    message = "Vous ne pouvez pas accéder aux ressources d'une autre année scolaire."
    
    def has_object_permission(self, request, view, obj):
        # SuperUser : accès total
        if request.user.is_superuser:
            return True
        
        # L'objet doit avoir un champ 'annee_scolaire'
        if not hasattr(obj, 'annee_scolaire'):
            return True  # Pas de restriction
        
        # Admin : peut voir cours sans année
        role_name = request.user.role.name if request.user.role else None
        if role_name == 'Admin' and obj.annee_scolaire is None:
            return True
        
        # Vérifier que l'année correspond
        return obj.annee_scolaire_id == request.user.annee_scolaire_active_id


class CanAccessEnrolledCourses(permissions.BasePermission):
    """
    Permission pour Apprenants : 
    Ne peuvent accéder QU'aux cours dans lesquels ils sont inscrits.
    """
    message = "Vous ne pouvez accéder qu'aux cours dans lesquels vous êtes inscrit."
    
    def has_permission(self, request, view):
        # Cette permission ne s'applique qu'aux Apprenants
        if not request.user or not request.user.is_authenticated:
            return False
        
        # SuperUser/Admin/Responsable/Formateur : pas de restriction par inscription
        if request.user.is_superuser or not request.user.role:
            return True
        
        role_name = request.user.role.name
        if role_name in ['Admin', 'Responsable', 'Formateur']:
            return True
        
        # Pour Apprenant : vérification dans has_object_permission
        return True
    
    def has_object_permission(self, request, view, obj):
        # SuperUser : accès total
        if request.user.is_superuser:
            return True
        
        role_name = request.user.role.name if request.user.role else None
        
        # Apprenant : doit être inscrit au cours
        if role_name == 'Apprenant':
            from courses.models import InscriptionCours, Cours
            
            # Trouver le cours associé à l'objet
            cours = None
            if isinstance(obj, Cours):
                cours = obj
            elif hasattr(obj, 'cours'):
                cours = obj.cours
            elif hasattr(obj, 'module'):
                cours = obj.module.cours if hasattr(obj.module, 'cours') else None
            elif hasattr(obj, 'sequence'):
                if hasattr(obj.sequence, 'module'):
                    cours = obj.sequence.module.cours
            
            if cours:
                # Vérifier l'inscription
                return InscriptionCours.objects.filter(
                    apprenant=request.user,
                    cours=cours,
                    institution=request.user.institution
                ).exists()
            
            return False
        
        # Autres rôles : autorisé
        return True


class IsAdminOrHigher(permissions.BasePermission):
    """
    Permission : Admin, Responsable ou SuperUser.
    Utilisé pour les actions d'administration.
    """
    message = "Seuls les Admins, Responsables ou SuperUsers peuvent effectuer cette action."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        role_name = request.user.role.name if request.user.role else None
        return role_name in ['Admin', 'Responsable']


class IsFormateurOrHigher(permissions.BasePermission):
    """
    Permission : Formateur, Responsable, Admin ou SuperUser.
    Utilisé pour la création/modification de contenu pédagogique.
    """
    message = "Seuls les Formateurs, Responsables, Admins ou SuperUsers peuvent effectuer cette action."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        if request.user.is_superuser:
            return True
        
        role_name = request.user.role.name if request.user.role else None
        return role_name in ['Admin', 'Responsable', 'Formateur']


class CanModifyOwnInstitutionOnly(permissions.BasePermission):
    """
    Permission : L'utilisateur ne peut modifier que les ressources de son institution.
    """
    message = "Vous ne pouvez modifier que les ressources de votre institution."
    
    def has_object_permission(self, request, view, obj):
        # SuperUser : tout modifier
        if request.user.is_superuser:
            return True
        
        # Lecture : autorisé si accès déjà vérifié par d'autres permissions
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Modification : vérifier l'institution
        if hasattr(obj, 'institution'):
            return obj.institution_id == request.user.institution_id
        
        return True


# Combinaisons de permissions fréquentes

class FormateurCanCreateContent(permissions.BasePermission):
    """
    Permission combinée pour la création de contenu pédagogique :
    - Doit être Formateur/Responsable/Admin/SuperUser
    - Doit avoir institution + année (sauf SuperUser/Admin)
    """
    message = "Vous devez être Formateur ou supérieur avec une institution et année définies."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # SuperUser : toujours autorisé
        if request.user.is_superuser:
            return True
        
        role_name = request.user.role.name if request.user.role else None
        
        # Rôle approprié
        if role_name not in ['Admin', 'Responsable', 'Formateur']:
            return False
        
        # Admin : institution suffit
        if role_name == 'Admin':
            return bool(request.user.institution)
        
        # Formateur/Responsable : institution + année
        return bool(request.user.institution and request.user.annee_scolaire_active)


class ApprenantCanViewEnrolledOnly(permissions.BasePermission):
    """
    Permission combinée pour Apprenants :
    - Doit avoir institution
    - Ne voit que les cours inscrits
    """
    message = "Vous devez être inscrit à ce cours et avoir une institution définie."
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # SuperUser : accès total
        if request.user.is_superuser:
            return True
        
        # Apprenant : doit avoir institution
        role_name = request.user.role.name if request.user.role else None
        if role_name == 'Apprenant':
            return bool(request.user.institution)
        
        # Autres rôles : autorisé (autres permissions vérifieront)
        return True
    
    def has_object_permission(self, request, view, obj):
        return CanAccessEnrolledCourses().has_object_permission(request, view, obj)