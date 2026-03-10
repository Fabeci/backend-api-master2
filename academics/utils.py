# academics/utils.py
"""
Utilitaires de filtrage pour l'application academics.

RÈGLES DE FILTRAGE PAR RÔLE :

1. SuperAdmin   : Voit UNIQUEMENT les institutions et peut gérer les admins
                  → Bloqué sur toutes les ressources internes (AnneeScolaire, Classe, etc.)
2. Admin        : Voit tout dans son institution
3. Responsable  : Voit tout dans son institution
4. Formateur    :
   - Liste   : Voit tout dans son institution (pour avoir une vue d'ensemble)
   - Détail  : Voit uniquement les groupes/classes où il enseigne
5. Apprenant    :
   - Liste   : Voit tout dans son institution (pour explorer)
   - Détail  : Voit uniquement sa classe/groupe et ses ressources
6. Parent       : Lecture seule sur tout ce qui concerne son/ses enfant(s)
"""

from django.shortcuts import get_object_or_404


def get_role_name(user):
    """Retourne le nom du rôle de l'utilisateur."""
    if hasattr(user, 'role') and user.role:
        return user.role.name
    return None


def get_parent_enfants_ids(user):
    """Retourne les IDs des enfants d'un parent."""
    from users.models import Apprenant
    return list(
        Apprenant.objects.filter(tuteur=user).values_list('id', flat=True)
    )


def get_user_academic_context(request):
    """
    Extrait le contexte académique de l'utilisateur.

    Returns:
        dict: {
            'bypass': bool,              # True pour SuperAdmin (Institution seulement)
            'blocked': bool,             # True pour SuperAdmin sur ressources internes
            'institution_id': int|None,
            'role_name': str|None,
            'user_classe_id': int|None,
            'user_groupe_id': int|None,
            'enfants_ids': list,         # Pour Parent
        }
    """
    user = request.user

    ctx = {
        "bypass": False,
        "blocked": False,
        "institution_id": None,
        "role_name": None,
        "user_classe_id": None,
        "user_groupe_id": None,
        "enfants_ids": [],
    }

    # SuperAdmin : bypass pour Institution uniquement, bloqué ailleurs
    if getattr(user, "is_superuser", False):
        ctx["bypass"] = True   # géré au cas par cas dans filter_academics_queryset
        return ctx

    role_name = get_role_name(user)
    ctx["role_name"] = role_name
    ctx["institution_id"] = getattr(user, "institution_id", None)

    # Parent : récupérer les enfants
    if role_name == 'Parent':
        ctx["enfants_ids"] = get_parent_enfants_ids(user)
        return ctx

    # Apprenant : récupérer sa classe/groupe
    if role_name == 'Apprenant':
        from .models import Inscription
        inscription = Inscription.objects.filter(
            apprenant=user,
            statut="actif"
        ).select_related('classe').first()

        if inscription and inscription.classe:
            ctx["user_classe_id"] = inscription.classe_id
            premier_groupe = inscription.classe.groupes.first()
            if premier_groupe:
                ctx["user_groupe_id"] = premier_groupe.id

        # Fallback groupe direct
        if not ctx["user_groupe_id"] and hasattr(user, 'groupe_id'):
            ctx["user_groupe_id"] = user.groupe_id

    return ctx


def filter_academics_queryset(queryset, request, model_name, is_detail=False):
    """
    Filtre un queryset academics selon le rôle.

    Args:
        queryset   : QuerySet Django
        request    : Request Django
        model_name : 'Institution', 'Groupe', 'Classe', 'Inscription', etc.
        is_detail  : True si c'est une vue détail (filtrage plus strict)

    Returns:
        QuerySet filtré
    """
    user = request.user
    ctx = get_user_academic_context(request)

    # ====================================================================
    # 1. INSTITUTION → SuperAdmin voit tout, les autres voient la leur
    # ====================================================================
    if model_name == 'Institution':
        if ctx.get("bypass"):
            return queryset  # SuperAdmin : toutes les institutions
        role_name = ctx.get("role_name")
        institution_id = ctx.get("institution_id")

        if role_name == 'Parent':
            # Parent voit l'institution de ses enfants
            enfants_ids = ctx.get("enfants_ids", [])
            if not enfants_ids:
                return queryset.none()
            from users.models import Apprenant
            inst_ids = Apprenant.objects.filter(
                id__in=enfants_ids
            ).values_list('institution_id', flat=True).distinct()
            return queryset.filter(id__in=inst_ids)

        if institution_id:
            return queryset.filter(id=institution_id)
        return queryset.none()

    # ====================================================================
    # 2. SuperAdmin BLOQUÉ sur toutes les ressources internes
    # ====================================================================
    if ctx.get("bypass"):
        return queryset.none()

    role_name = ctx.get("role_name")
    institution_id = ctx.get("institution_id")

    # ====================================================================
    # 3. PARENT : lecture seule sur les données de ses enfants
    # ====================================================================
    if role_name == 'Parent':
        return _filter_for_parent(queryset, model_name, ctx)

    # ====================================================================
    # 4. Sans institution → rien
    # ====================================================================
    if not institution_id and model_name not in ['DomaineEtude', 'Matiere', 'Specialite']:
        return queryset.none()

    # ====================================================================
    # GROUPE
    # ====================================================================
    if model_name == 'Groupe':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Formateur':
            if is_detail:
                return queryset.filter(
                    institution_id=institution_id,
                    formateurs=user
                )
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Apprenant':
            if is_detail:
                if ctx.get("user_groupe_id"):
                    return queryset.filter(id=ctx["user_groupe_id"])
                return queryset.none()
            return queryset.filter(institution_id=institution_id)

    # ====================================================================
    # CLASSE
    # ====================================================================
    if model_name == 'Classe':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Formateur':
            if is_detail:
                from .models import Groupe
                groupes_ids = Groupe.objects.filter(
                    institution_id=institution_id,
                    formateurs=user
                ).values_list('id', flat=True)
                return queryset.filter(groupes__id__in=groupes_ids)
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Apprenant':
            if is_detail:
                if ctx.get("user_classe_id"):
                    return queryset.filter(id=ctx["user_classe_id"])
                return queryset.none()
            return queryset.filter(institution_id=institution_id)

    # ====================================================================
    # DEPARTEMENT
    # ====================================================================
    if model_name == 'Departement':
        if role_name in ['Admin', 'Responsable', 'Formateur', 'ResponsableAcademique']:
            return queryset.filter(institution_id=institution_id)
        return queryset.none()

    # ====================================================================
    # FILIERE
    # ====================================================================
    if model_name == 'Filiere':
        if role_name in ['Admin', 'Responsable', 'Formateur', 'Apprenant', 'ResponsableAcademique']:
            return queryset.all()
        return queryset.none()

    # ====================================================================
    # INSCRIPTION
    # ====================================================================
    if model_name == 'Inscription':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Formateur':
            from .models import Groupe
            groupes_ids = Groupe.objects.filter(
                institution_id=institution_id,
                formateurs=user
            ).values_list('id', flat=True)
            return queryset.filter(
                institution_id=institution_id,
                classe__groupes__id__in=groupes_ids
            )

        if role_name == 'Apprenant':
            return queryset.filter(apprenant=user)

    # ====================================================================
    # MODÈLES GLOBAUX (filtrage par institution)
    # ====================================================================
    if model_name in ["DomaineEtude", "Filiere", "Matiere", "Specialite", "AnneeScolaire"]:
        if role_name in ["Admin", "Responsable", "Formateur", "Apprenant", "ResponsableAcademique"]:
            return queryset.filter(institution_id=institution_id)
        return queryset.none()

    # ====================================================================
    # Par défaut : filtrer par institution si le champ existe
    # ====================================================================
    if hasattr(queryset.model, 'institution'):
        return queryset.filter(institution_id=institution_id)

    return queryset.all()


def _filter_for_parent(queryset, model_name, ctx):
    """Filtre un queryset pour un parent (données de ses enfants uniquement)."""
    enfants_ids = ctx.get("enfants_ids", [])
    if not enfants_ids:
        return queryset.none()

    if model_name == 'Inscription':
        return queryset.filter(apprenant_id__in=enfants_ids)

    if model_name == 'Classe':
        from .models import Inscription
        classe_ids = Inscription.objects.filter(
            apprenant_id__in=enfants_ids,
            statut='actif'
        ).values_list('classe_id', flat=True).distinct()
        return queryset.filter(id__in=classe_ids)

    if model_name == 'Groupe':
        from users.models import Apprenant
        groupe_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('groupe_id', flat=True).distinct()
        return queryset.filter(id__in=groupe_ids)

    if model_name == 'AnneeScolaire':
        from .models import Inscription
        annee_ids = Inscription.objects.filter(
            apprenant_id__in=enfants_ids,
            statut='actif'
        ).values_list('annee_scolaire_id', flat=True).distinct()
        return queryset.filter(id__in=annee_ids)

    if model_name == 'Institution':
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(id__in=inst_ids)

    # Pour les autres modèles : filtre générique par institution de l'enfant
    if hasattr(queryset.model, 'institution'):
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(institution_id__in=inst_ids)

    return queryset.none()


def get_filtered_academic_object(model_class, pk, request, model_name):
    """
    Récupère un objet académique filtré par rôle (vue détail).
    """
    qs = model_class.objects.all()
    qs = filter_academics_queryset(qs, request, model_name, is_detail=True)
    return get_object_or_404(qs, pk=pk)


def can_modify_academic_resource(user, obj, model_name):
    """
    Vérifie si l'utilisateur peut modifier une ressource académique.
    
    SuperAdmin : peut modifier Institution uniquement
    Admin/Responsable : peuvent modifier dans leur institution
    Formateur : peut modifier les groupes où il enseigne
    Apprenant/Parent : aucune modification
    """
    if getattr(user, 'is_superuser', False):
        # SuperAdmin : uniquement Institution
        return model_name == 'Institution'

    role_name = get_role_name(user)

    if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
        if hasattr(obj, 'institution_id'):
            return obj.institution_id == user.institution_id
        return True

    if role_name == 'Formateur':
        if model_name == 'Groupe':
            return obj.formateurs.filter(id=user.id).exists()
        return False

    # Apprenant et Parent : aucune modification
    return False


def get_user_groupes_ids(user):
    """Retourne les IDs des groupes où le formateur enseigne."""
    role_name = get_role_name(user)
    if role_name == 'Formateur':
        from .models import Groupe
        return list(Groupe.objects.filter(
            formateurs=user,
            institution_id=user.institution_id
        ).values_list('id', flat=True))
    return []


def get_user_classe_id(user):
    """Retourne l'ID de la classe de l'apprenant."""
    role_name = get_role_name(user)
    if role_name == 'Apprenant':
        from .models import Inscription
        inscription = Inscription.objects.filter(
            apprenant=user,
            statut="actif"
        ).select_related('classe').first()
        if inscription and inscription.classe:
            return inscription.classe_id
    return None