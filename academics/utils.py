# academics/utils.py
"""
Utilitaires de filtrage pour l'application academics.

RÈGLES DE FILTRAGE PAR RÔLE :

1. SuperUser : Voit TOUT
2. Admin : Voit tout dans son institution
3. Responsable : Voit tout dans son institution
4. Formateur : 
   - Liste : Voit tout dans son institution (pour avoir une vue d'ensemble)
   - Détail : Voit uniquement les groupes/classes où il enseigne
5. Apprenant :
   - Liste : Voit tout dans son institution (pour explorer)
   - Détail : Voit uniquement sa classe/groupe et ses ressources
"""

from django.shortcuts import get_object_or_404



def get_user_academic_context(request):
    """
    Extrait le contexte académique de l'utilisateur.
    
    Returns:
        dict: {
            'bypass': bool,              # True pour SuperUser
            'institution_id': int|None,  # ID institution
            'role_name': str|None,       # Nom du rôle
            'user_classe_id': int|None,  # ID de la classe de l'apprenant
            'user_groupe_id': int|None,  # ID du groupe de l'apprenant
        }
    """
    user = request.user
    
    ctx = {
        "bypass": False,
        "institution_id": None,
        "role_name": None,
        "user_classe_id": None,
        "user_groupe_id": None,
    }
    
    # SuperUser : bypass
    if getattr(user, "is_superuser", False):
        ctx["bypass"] = True
        return ctx
    
    # Informations de base
    ctx["role_name"] = user.role.name if hasattr(user, 'role') and user.role else None
    ctx["institution_id"] = getattr(user, "institution_id", None)
    
    # Pour Apprenant : récupérer sa classe/groupe
    if ctx["role_name"] == 'Apprenant':
        # Classe depuis l'inscription
        from .models import Inscription
        inscription = Inscription.objects.filter(
            apprenant=user,
            statut="actif"
        ).select_related('classe').first()
        
        if inscription and inscription.classe:
            ctx["user_classe_id"] = inscription.classe_id
            
            # Groupe depuis la classe
            if hasattr(inscription.classe, 'groupes') and inscription.classe.groupes:
                ctx["user_groupe_id"] = inscription.classe.groupes_id
        
        # Groupe direct sur l'apprenant (fallback)
        if not ctx["user_groupe_id"] and hasattr(user, 'groupe_id'):
            ctx["user_groupe_id"] = user.groupe_id
    
    return ctx


def filter_academics_queryset(queryset, request, model_name, is_detail=False):
    """
    Filtre un queryset academics selon le rôle.
    
    Args:
        queryset: QuerySet Django
        request: Request Django
        model_name: 'Institution', 'Groupe', 'Classe', 'Inscription', etc.
        is_detail: True si c'est une vue détail (filtrage plus strict)
    
    Returns:
        QuerySet filtré
    """
    user = request.user
    ctx = get_user_academic_context(request)
    
    # 1. SuperUser : pas de filtrage
    if ctx.get("bypass"):
        return queryset
    
    role_name = ctx.get("role_name")
    institution_id = ctx.get("institution_id")
    
    # 2. Pas d'institution : rien (sauf pour certains modèles globaux)
    if not institution_id and model_name not in ['DomaineEtude', 'Matiere', 'Specialite']:
        return queryset.none()
    
    # ========================================================================
    # INSTITUTION : Filtrée ou toutes selon rôle
    # ========================================================================
    if model_name == 'Institution':
        # Admin/Responsable : leur institution uniquement
        if role_name in ['Admin', 'Responsable']:
            return queryset.filter(id=institution_id)
        
        # Formateur/Apprenant : leur institution
        if role_name in ['Formateur', 'Apprenant']:
            return queryset.filter(id=institution_id)
        
        # Par défaut : rien
        return queryset.none()
    
    # ========================================================================
    # GROUPE : Filtrage selon rôle et contexte (liste vs détail)
    # ========================================================================
    if model_name == 'Groupe':
        # Admin/Responsable : tous les groupes de l'institution
        if role_name in ['Admin', 'Responsable']:
            return queryset.filter(institution_id=institution_id)
        
        # Formateur
        if role_name == 'Formateur':
            if is_detail:
                # Détail : uniquement ses groupes
                return queryset.filter(
                    institution_id=institution_id,
                    enseignants=user
                )
            else:
                # Liste : tous les groupes de l'institution (vue d'ensemble)
                return queryset.filter(institution_id=institution_id)
        
        # Apprenant
        if role_name == 'Apprenant':
            if is_detail:
                # Détail : uniquement son groupe
                if ctx.get("user_groupe_id"):
                    return queryset.filter(id=ctx["user_groupe_id"])
                return queryset.none()
            else:
                # Liste : tous les groupes de l'institution (pour explorer)
                return queryset.filter(institution_id=institution_id)
    
    # ========================================================================
    # CLASSE : Filtrage selon rôle et contexte
    # ========================================================================
    if model_name == 'Classe':
        # Admin/Responsable : toutes les classes de l'institution
        if role_name in ['Admin', 'Responsable']:
            return queryset.filter(institution_id=institution_id)
        
        # Formateur
        if role_name == 'Formateur':
            if is_detail:
                # Détail : uniquement les classes de ses groupes
                from .models import Groupe
                groupes_ids = Groupe.objects.filter(
                    institution_id=institution_id,
                    enseignants=user
                ).values_list('id', flat=True)
                
                return queryset.filter(groupes_id__in=groupes_ids)
            else:
                # Liste : toutes les classes de l'institution
                return queryset.filter(institution_id=institution_id)
        
        # Apprenant
        if role_name == 'Apprenant':
            if is_detail:
                # Détail : uniquement sa classe
                if ctx.get("user_classe_id"):
                    return queryset.filter(id=ctx["user_classe_id"])
                return queryset.none()
            else:
                # Liste : toutes les classes de l'institution
                return queryset.filter(institution_id=institution_id)
    
    # ========================================================================
    # DEPARTEMENT : Filtrage par institution
    # ========================================================================
    if model_name == 'Departement':
        if role_name in ['Admin', 'Responsable', 'Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)
    
    # ========================================================================
    # FILIERE : Visible par tous dans l'institution
    # ========================================================================
    if model_name == 'Filiere':
        # Les filières sont souvent transversales
        # Admin/Responsable : toutes
        if role_name in ['Admin', 'Responsable']:
            return queryset.all()
        
        # Formateur/Apprenant : toutes aussi (pour explorer)
        if role_name in ['Formateur', 'Apprenant']:
            return queryset.all()
    
    # ========================================================================
    # INSCRIPTION : Filtrage strict
    # ========================================================================
    if model_name == 'Inscription':
        # Admin/Responsable : toutes les inscriptions de l'institution
        if role_name in ['Admin', 'Responsable']:
            return queryset.filter(institution_id=institution_id)
        
        # Formateur : inscriptions dans ses groupes/classes
        if role_name == 'Formateur':
            from .models import Groupe
            groupes_ids = Groupe.objects.filter(
                institution_id=institution_id,
                enseignants=user
            ).values_list('id', flat=True)
            
            return queryset.filter(
                institution_id=institution_id,
                classe__groupes_id__in=groupes_ids
            )
        
        # Apprenant : uniquement sa propre inscription
        if role_name == 'Apprenant':
            return queryset.filter(apprenant=user)
    
    # ========================================================================
    # MODÈLES GLOBAUX : Matiere, Specialite, DomaineEtude
    # ========================================================================
    if model_name in ["DomaineEtude", "Filiere", "Matiere", "Specialite", "AnneeScolaire"]:
        if role_name in ["Admin", "Responsable", "Formateur", "Apprenant"]:
            return queryset.filter(institution_id=institution_id)
        return queryset.none()
    
    # ========================================================================
    # Par défaut : filtrer par institution si le champ existe
    # ========================================================================
    if hasattr(queryset.model, 'institution'):
        return queryset.filter(institution_id=institution_id)
    
    # Sinon : tout visible
    return queryset.all()


def get_filtered_academic_object(model_class, pk, request, model_name):
    """
    Récupère un objet académique filtré par rôle (vue détail).
    
    Usage:
        groupe = get_filtered_academic_object(Groupe, groupe_id, request, 'Groupe')
    """
    qs = model_class.objects.all()
    qs = filter_academics_queryset(qs, request, model_name, is_detail=True)
    return get_object_or_404(qs, pk=pk)


def can_modify_academic_resource(user, obj, model_name):
    """
    Vérifie si l'utilisateur peut modifier une ressource académique.
    
    Args:
        user: Utilisateur
        obj: Objet à modifier
        model_name: Type de ressource
    
    Returns:
        bool: True si autorisé
    """
    # SuperUser : tout modifier
    if user.is_superuser:
        return True
    
    role_name = user.role.name if hasattr(user, 'role') and user.role else None
    
    # Admin/Responsable : peuvent modifier dans leur institution
    if role_name in ['Admin', 'Responsable']:
        if hasattr(obj, 'institution_id'):
            return obj.institution_id == user.institution_id
        return True
    
    # Formateur : ne peut PAS modifier les structures académiques
    # (sauf cas spécifiques que vous pouvez ajouter)
    if role_name == 'Formateur':
        # Exemple : peut modifier les groupes où il enseigne
        if model_name == 'Groupe':
            return obj.enseignants.filter(id=user.id).exists()
        return False
    
    # Apprenant : aucune modification
    return False


def get_user_groupes_ids(user):
    """
    Retourne les IDs des groupes où l'utilisateur enseigne (Formateur).
    Utile pour des requêtes complexes.
    """
    role_name = user.role.name if hasattr(user, 'role') and user.role else None
    
    if role_name == 'Formateur':
        from .models import Groupe
        return list(Groupe.objects.filter(
            enseignants=user,
            institution_id=user.institution_id
        ).values_list('id', flat=True))
    
    return []


def get_user_classe_id(user):
    """
    Retourne l'ID de la classe de l'apprenant.
    """
    role_name = user.role.name if hasattr(user, 'role') and user.role else None
    
    if role_name == 'Apprenant':
        from .models import Inscription
        inscription = Inscription.objects.filter(
            apprenant=user,
            statut="actif"
        ).select_related('classe').first()
        
        if inscription and inscription.classe:
            return inscription.classe_id
    
    return None