# core/middleware.py
"""
Middleware pour gérer l'année scolaire active.

Principe :
- L'admin sélectionne une année scolaire active pour son établissement
- Cette année est stockée en session
- Toutes les actions de l'admin sont automatiquement rattachées à cette année
- Les autres utilisateurs voient automatiquement les données de l'année active
"""

from django.utils.deprecation import MiddlewareMixin
from django.core.cache import cache
from academics.models import AnneeScolaire
from users.models import Admin


class AnneeScolaireMiddleware(MiddlewareMixin):
    """
    Middleware pour gérer l'année scolaire active dans le contexte de la requête.
    """
    
    def process_request(self, request):
        """
        Ajoute l'année scolaire active au contexte de la requête.
        """
        # Ignorer pour les utilisateurs non authentifiés
        if not request.user or not request.user.is_authenticated:
            request.annee_scolaire_active = None
            return
        
        # Récupérer l'année scolaire de la session
        annee_id = request.session.get('annee_scolaire_active_id')
        
        if annee_id:
            try:
                request.annee_scolaire_active = AnneeScolaire.objects.get(id=annee_id)
                return
            except AnneeScolaire.DoesNotExist:
                # L'année en session n'existe plus, on la supprime
                del request.session['annee_scolaire_active_id']
        
        # Pas d'année en session : définir une année par défaut
        request.annee_scolaire_active = self._get_default_annee_scolaire(request.user)
        
        # Sauvegarder en session
        if request.annee_scolaire_active:
            request.session['annee_scolaire_active_id'] = request.annee_scolaire_active.id
    
    def _get_default_annee_scolaire(self, user):
        """
        Récupère l'année scolaire par défaut pour l'utilisateur.
        
        Logique :
        - Pour Admin : dernière année créée pour son établissement
        - Pour autres : année en cours (dernière créée globalement)
        """
        if isinstance(user, Admin) and user.institution:
            # Chercher la dernière année de l'établissement
            # (si vous avez un lien institution -> années, sinon prendre la dernière globale)
            return AnneeScolaire.objects.order_by('-date_debut').first()
        
        # Pour les autres utilisateurs : dernière année globale
        return AnneeScolaire.objects.order_by('-date_debut').first()


class InstitutionMiddleware(MiddlewareMixin):
    """
    Middleware pour ajouter l'établissement de l'utilisateur au contexte.
    """
    
    def process_request(self, request):
        """
        Ajoute l'établissement au contexte de la requête.
        """
        # Ignorer pour les utilisateurs non authentifiés
        if not request.user or not request.user.is_authenticated:
            request.user_institution = None
            return
        
        # Récupérer l'établissement selon le type d'utilisateur
        institution = None
        
        if hasattr(request.user, 'institution'):
            institution = request.user.institution
        elif hasattr(request.user, 'institutions'):
            # Pour Formateur : prendre le premier établissement
            # (vous pouvez améliorer cette logique)
            institution = request.user.institutions.first()
        
        request.user_institution = institution


# =============================================================================
# FONCTIONS UTILITAIRES POUR LES VUES
# =============================================================================

def get_annee_scolaire_active(request):
    """
    Récupère l'année scolaire active de la requête.
    
    Usage dans les vues :
        from core.middleware import get_annee_scolaire_active
        
        annee = get_annee_scolaire_active(request)
        if not annee:
            return api_error("Aucune année scolaire active")
    """
    return getattr(request, 'annee_scolaire_active', None)


def set_annee_scolaire_active(request, annee_scolaire):
    """
    Définit l'année scolaire active pour la session.
    
    Usage dans les vues (endpoint pour changer d'année) :
        from core.middleware import set_annee_scolaire_active
        
        annee = get_object_or_404(AnneeScolaire, id=annee_id)
        set_annee_scolaire_active(request, annee)
    """
    request.annee_scolaire_active = annee_scolaire
    request.session['annee_scolaire_active_id'] = annee_scolaire.id if annee_scolaire else None


def get_user_institution(request):
    """
    Récupère l'établissement de l'utilisateur.
    
    Usage dans les vues :
        from core.middleware import get_user_institution
        
        institution = get_user_institution(request)
        if not institution:
            return api_error("Aucun établissement associé")
    """
    return getattr(request, 'user_institution', None)


def filter_by_institution(queryset, request):
    """
    Filtre un queryset par l'établissement de l'utilisateur.
    
    Usage dans les vues :
        from core.middleware import filter_by_institution
        
        cours = Cours.objects.all()
        cours = filter_by_institution(cours, request)
    """
    institution = get_user_institution(request)
    if not institution:
        return queryset.none()
    
    # Tenter différents champs possibles
    if hasattr(queryset.model, 'institution'):
        return queryset.filter(institution=institution)
    elif hasattr(queryset.model, 'cours'):
        return queryset.filter(cours__institution=institution)
    elif hasattr(queryset.model, 'module'):
        return queryset.filter(module__cours__institution=institution)
    elif hasattr(queryset.model, 'sequence'):
        return queryset.filter(sequence__module__cours__institution=institution)
    
    return queryset


def filter_by_annee_scolaire(queryset, request):
    """
    Filtre un queryset par l'année scolaire active.
    
    Usage dans les vues :
        from core.middleware import filter_by_annee_scolaire
        
        cours = Cours.objects.all()
        cours = filter_by_annee_scolaire(cours, request)
    """
    annee = get_annee_scolaire_active(request)
    if not annee:
        return queryset.none()
    
    # Tenter différents champs possibles
    if hasattr(queryset.model, 'annee_scolaire'):
        return queryset.filter(annee_scolaire=annee)
    elif hasattr(queryset.model, 'cours'):
        return queryset.filter(cours__annee_scolaire=annee)
    elif hasattr(queryset.model, 'module'):
        return queryset.filter(module__cours__annee_scolaire=annee)
    elif hasattr(queryset.model, 'sequence'):
        return queryset.filter(sequence__module__cours__annee_scolaire=annee)
    
    return queryset


def filter_by_institution_and_annee(queryset, request):
    """
    Filtre un queryset par établissement ET année scolaire.
    
    Usage dans les vues :
        from core.middleware import filter_by_institution_and_annee
        
        cours = Cours.objects.all()
        cours = filter_by_institution_and_annee(cours, request)
    """
    queryset = filter_by_institution(queryset, request)
    queryset = filter_by_annee_scolaire(queryset, request)
    return queryset