# core/permissions.py
"""
Système de permissions pour gérer les accès selon les profils utilisateurs.

Règles de gestion :
- Admin : gère uniquement son établissement et l'année scolaire active
- ResponsableAcademique : CRUD sur les cours de son établissement
- Formateur : organise le contenu des cours (modules, séquences, etc.)
- Apprenant : accès lecture seule à ses cours inscrits
- Parent : accès lecture seule aux données de ses enfants
"""

from rest_framework import permissions
from users.models import Admin, Apprenant, Parent, Formateur, ResponsableAcademique


class IsAdmin(permissions.BasePermission):
    """
    Permission pour les administrateurs.
    Accès uniquement à leur établissement.
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and isinstance(request.user, Admin)
        )
    
    def has_object_permission(self, request, view, obj):
        """Vérifie que l'objet appartient à l'établissement de l'admin"""
        if not isinstance(request.user, Admin):
            return False
        
        # Récupérer l'établissement de l'objet
        institution = self._get_institution_from_object(obj)
        if not institution:
            return True  # Pas d'établissement sur l'objet, on laisse passer
        
        return institution == request.user.institution
    
    def _get_institution_from_object(self, obj):
        """Extrait l'établissement d'un objet"""
        # Direct
        if hasattr(obj, 'institution'):
            return obj.institution
        
        # Via cours
        if hasattr(obj, 'cours'):
            return getattr(obj.cours, 'institution', None)
        
        # Via module
        if hasattr(obj, 'module'):
            return getattr(obj.module, 'institution', None)
        
        # Via sequence
        if hasattr(obj, 'sequence'):
            return getattr(obj.sequence, 'institution', None)
        
        return None


class IsResponsableAcademique(permissions.BasePermission):
    """
    Permission pour les responsables académiques.
    - CRUD complet sur les cours de leur établissement
    - Lecture sur le reste
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and isinstance(request.user, ResponsableAcademique)
        )
    
    def has_object_permission(self, request, view, obj):
        if not isinstance(request.user, ResponsableAcademique):
            return False
        
        # Lecture autorisée pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture : vérifier l'établissement
        institution = self._get_institution_from_object(obj)
        if not institution:
            return False
        
        return institution == request.user.institution
    
    def _get_institution_from_object(self, obj):
        """Extrait l'établissement d'un objet"""
        if hasattr(obj, 'institution'):
            return obj.institution
        if hasattr(obj, 'cours'):
            return getattr(obj.cours, 'institution', None)
        if hasattr(obj, 'module'):
            return getattr(obj.module, 'institution', None)
        if hasattr(obj, 'sequence'):
            return getattr(obj.sequence, 'institution', None)
        return None


class IsFormateur(permissions.BasePermission):
    """
    Permission pour les formateurs.
    - Peut organiser le contenu des cours dont il est responsable
    - Lecture sur ses cours
    - Pas de création de cours (réservé au ResponsableAcademique)
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and isinstance(request.user, Formateur)
        )
    
    def has_object_permission(self, request, view, obj):
        if not isinstance(request.user, Formateur):
            return False
        
        # Pour les cours : vérifier qu'il en est l'enseignant
        if hasattr(obj, 'enseignant'):
            return obj.enseignant == request.user
        
        # Pour les modules/séquences/blocs : vérifier via le cours
        cours = self._get_cours_from_object(obj)
        if cours:
            return cours.enseignant == request.user
        
        return False
    
    def _get_cours_from_object(self, obj):
        """Extrait le cours d'un objet"""
        if hasattr(obj, 'cours'):
            return obj.cours
        if hasattr(obj, 'module'):
            return getattr(obj.module, 'cours', None)
        if hasattr(obj, 'sequence'):
            module = getattr(obj.sequence, 'module', None)
            return getattr(module, 'cours', None) if module else None
        return None


class IsApprenant(permissions.BasePermission):
    """
    Permission pour les apprenants.
    - Lecture seule sur leurs cours inscrits
    - Peut marquer leur progression
    - Peut passer des évaluations
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and isinstance(request.user, Apprenant)
        )
    
    def has_object_permission(self, request, view, obj):
        if not isinstance(request.user, Apprenant):
            return False
        
        # Vérifier l'inscription au cours
        from courses.models import InscriptionCours
        
        cours = self._get_cours_from_object(obj)
        if not cours:
            return False
        
        return InscriptionCours.objects.filter(
            apprenant=request.user,
            cours=cours
        ).exists()
    
    def _get_cours_from_object(self, obj):
        """Extrait le cours d'un objet"""
        if hasattr(obj, 'cours'):
            return obj.cours
        if hasattr(obj, 'module'):
            return getattr(obj.module, 'cours', None)
        if hasattr(obj, 'sequence'):
            module = getattr(obj.sequence, 'module', None)
            return getattr(module, 'cours', None) if module else None
        if hasattr(obj, 'evaluation'):
            return getattr(obj.evaluation, 'cours', None)
        return None


class IsParent(permissions.BasePermission):
    """
    Permission pour les parents.
    - Lecture seule sur les données de leurs enfants
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and isinstance(request.user, Parent)
        )
    
    def has_object_permission(self, request, view, obj):
        if not isinstance(request.user, Parent):
            return False
        
        # Lecture seule
        if request.method not in permissions.SAFE_METHODS:
            return False
        
        # Vérifier que c'est son enfant
        apprenant = self._get_apprenant_from_object(obj)
        if not apprenant:
            return False
        
        return apprenant.tuteur == request.user
    
    def _get_apprenant_from_object(self, obj):
        """Extrait l'apprenant d'un objet"""
        if isinstance(obj, Apprenant):
            return obj
        if hasattr(obj, 'apprenant'):
            return obj.apprenant
        return None


# =============================================================================
# PERMISSIONS COMPOSÉES
# =============================================================================

class CanManageCours(permissions.BasePermission):
    """
    Peut gérer les cours (CRUD) :
    - ResponsableAcademique de l'établissement
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture uniquement pour ResponsableAcademique
        return isinstance(request.user, ResponsableAcademique)
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture : ResponsableAcademique du même établissement
        if isinstance(request.user, ResponsableAcademique):
            institution = getattr(obj, 'institution', None)
            return institution == request.user.institution
        
        return False


class CanOrganizeCours(permissions.BasePermission):
    """
    Peut organiser le contenu des cours (modules, séquences, blocs) :
    - Formateur responsable du cours
    - ResponsableAcademique de l'établissement
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous les utilisateurs authentifiés
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture pour Formateur ou ResponsableAcademique
        return isinstance(request.user, (Formateur, ResponsableAcademique))
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture
        if isinstance(request.user, Formateur):
            # Vérifier que c'est son cours
            cours = self._get_cours(obj)
            return cours and cours.enseignant == request.user
        
        if isinstance(request.user, ResponsableAcademique):
            # Vérifier l'établissement
            institution = self._get_institution(obj)
            return institution == request.user.institution
        
        return False
    
    def _get_cours(self, obj):
        """Extrait le cours d'un objet"""
        if hasattr(obj, 'cours'):
            return obj.cours
        if hasattr(obj, 'module'):
            return getattr(obj.module, 'cours', None)
        if hasattr(obj, 'sequence'):
            module = getattr(obj.sequence, 'module', None)
            return getattr(module, 'cours', None) if module else None
        return None
    
    def _get_institution(self, obj):
        """Extrait l'établissement d'un objet"""
        if hasattr(obj, 'institution'):
            return obj.institution
        cours = self._get_cours(obj)
        return getattr(cours, 'institution', None) if cours else None


class CanViewCours(permissions.BasePermission):
    """
    Peut voir les cours :
    - Tout utilisateur authentifié (filtre appliqué dans la vue)
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated


class CanManageEvaluation(permissions.BasePermission):
    """
    Peut gérer les évaluations :
    - Formateur du cours
    - ResponsableAcademique de l'établissement
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture pour Formateur ou ResponsableAcademique
        return isinstance(request.user, (Formateur, ResponsableAcademique))
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture
        if isinstance(request.user, Formateur):
            # Vérifier que c'est son cours
            cours = getattr(obj, 'cours', None)
            return cours and cours.enseignant == request.user
        
        if isinstance(request.user, ResponsableAcademique):
            # Vérifier l'établissement
            cours = getattr(obj, 'cours', None)
            institution = getattr(cours, 'institution', None) if cours else None
            return institution == request.user.institution
        
        return False


class CanTakeEvaluation(permissions.BasePermission):
    """
    Peut passer des évaluations :
    - Apprenant inscrit au cours
    """
    def has_permission(self, request, view):
        return (
            request.user 
            and request.user.is_authenticated 
            and isinstance(request.user, Apprenant)
        )
    
    def has_object_permission(self, request, view, obj):
        if not isinstance(request.user, Apprenant):
            return False
        
        from courses.models import InscriptionCours
        
        # Récupérer le cours de l'évaluation
        evaluation = getattr(obj, 'evaluation', obj)
        cours = getattr(evaluation, 'cours', None)
        
        if not cours:
            return False
        
        # Vérifier l'inscription
        return InscriptionCours.objects.filter(
            apprenant=request.user,
            cours=cours
        ).exists()


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission générique :
    - Admin : lecture/écriture sur son établissement
    - Autres : lecture seule
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture pour Admin uniquement
        return isinstance(request.user, Admin)
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Lecture pour tous
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Écriture : Admin du même établissement
        if isinstance(request.user, Admin):
            institution = getattr(obj, 'institution', None)
            return institution == request.user.institution
        
        return False