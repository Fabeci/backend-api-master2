# academics/utils.py

from django.shortcuts import get_object_or_404


def get_role_name(user):
    if hasattr(user, 'role') and user.role:
        return user.role.name
    return None


def get_parent_enfants_ids(user):
    from users.models import Apprenant
    return list(
        Apprenant.objects.filter(tuteur=user).values_list('id', flat=True)
    )

def get_user_academic_context(request):
    user = request.user

    ctx = {
        "bypass": False,
        "blocked": False,
        "institution_id": None,
        "departement_id": None,
        "role_name": None,
        "user_classe_id": None,
        "user_groupe_id": None,
        "enfants_ids": [],
    }

    if getattr(user, "is_superuser", False):
        ctx["bypass"] = True
        return ctx

    role_name = get_role_name(user)
    ctx["role_name"] = role_name
    ctx["institution_id"] = getattr(user, "institution_id", None)

    # ✅ CRITIQUE : pour les responsables, toujours recharger depuis la BD
    # user.departement_id peut être obsolète (cache session/ORM)
    if role_name in ['Responsable', 'ResponsableAcademique']:
        try:
            from users.models import ResponsableAcademique as RA
            fresh = RA.objects.filter(pk=user.pk).values(
                'departement_id', 'institution_id'
            ).first()
            if fresh:
                ctx["departement_id"] = fresh['departement_id']
                if fresh['institution_id']:
                    ctx["institution_id"] = fresh['institution_id']
            else:
                ctx["departement_id"] = getattr(user, 'departement_id', None)
        except Exception:
            ctx["departement_id"] = getattr(user, 'departement_id', None)
    else:
        ctx["departement_id"] = getattr(user, 'departement_id', None)

    if role_name == 'Parent':
        ctx["enfants_ids"] = get_parent_enfants_ids(user)
        return ctx

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

        if not ctx["user_groupe_id"] and hasattr(user, 'groupe_id'):
            ctx["user_groupe_id"] = user.groupe_id

    return ctx

def filter_academics_queryset(queryset, request, model_name, is_detail=False):
    user = request.user
    ctx = get_user_academic_context(request)

    # ================================================================
    # INSTITUTION
    # ================================================================
    if model_name == 'Institution':
        if ctx.get("bypass"):
            return queryset
        role_name = ctx.get("role_name")
        institution_id = ctx.get("institution_id")

        if role_name == 'Parent':
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

    # ================================================================
    # SuperAdmin bloqué sur tout le reste
    # ================================================================
    if ctx.get("bypass"):
        return queryset.none()

    role_name = ctx.get("role_name")
    institution_id = ctx.get("institution_id")
    dept_id = ctx.get("departement_id")

    # ================================================================
    # PARENT
    # ================================================================
    if role_name == 'Parent':
        return _filter_for_parent(queryset, model_name, ctx)

    # ================================================================
    # Sans institution → rien
    # ================================================================
    if not institution_id and model_name not in ['DomaineEtude', 'Matiere', 'Specialite']:
        return queryset.none()

    # ================================================================
    # DEPARTEMENT
    # SuperAdmin  : bloqué (géré au-dessus)
    # Admin       : tous les départements de l'institution
    # Responsable : uniquement son département
    # Formateur   : tous (lecture)
    # Apprenant   : tous (lecture)
    # Parent      : géré au-dessus
    # ================================================================
    if model_name == 'Departement':
        if role_name == 'Admin':
            return queryset.filter(institution_id=institution_id)

        if role_name in ['Responsable', 'ResponsableAcademique']:
            if dept_id:
                return queryset.filter(institution_id=institution_id, id=dept_id)
            return queryset.none()

        if role_name in ['Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # DOMAINE D'ETUDE
    # Admin       : tous les domaines de l'institution
    # Responsable : domaines de son département uniquement
    # Formateur   : tous (lecture)
    # Apprenant   : tous (lecture)
    # ================================================================
    if model_name == 'DomaineEtude':
        if role_name == 'Admin':
            return queryset.filter(institution_id=institution_id)

        if role_name in ['Responsable', 'ResponsableAcademique']:
            if dept_id:
                return queryset.filter(
                    institution_id=institution_id,
                    departement_id=dept_id
                )
            return queryset.none()

        if role_name in ['Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # FILIERE
    # Admin       : toutes les filières de l'institution
    # Responsable : filières dont le domaine → son département
    # Formateur   : toutes (lecture)
    # Apprenant   : toutes (lecture)
    # ================================================================
    if model_name == 'Filiere':
        if role_name == 'Admin':
            return queryset.filter(institution_id=institution_id)

        if role_name in ['Responsable', 'ResponsableAcademique']:
            if dept_id:
                return queryset.filter(
                    institution_id=institution_id,
                    domaine_etude__departement_id=dept_id
                )
            return queryset.none()

        if role_name in ['Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # CLASSE
    # Admin       : toutes les classes de l'institution
    # Responsable : classes liées aux filières de son département
    # Formateur   : toutes en liste / ses classes en détail
    # Apprenant   : toutes en liste / sa classe en détail
    # ================================================================
    if model_name == 'Classe':
        if role_name == 'Admin':
            return queryset.filter(institution_id=institution_id)

        if role_name in ['Responsable', 'ResponsableAcademique']:
            if dept_id:
                from .models import Filiere
                filiere_ids = Filiere.objects.filter(
                    institution_id=institution_id,
                    domaine_etude__departement_id=dept_id
                ).values_list('id', flat=True)
                return queryset.filter(
                    institution_id=institution_id,
                    filieres__id__in=filiere_ids
                ).distinct()
            return queryset.none()

        if role_name == 'Formateur':
            if is_detail:
                from .models import Groupe
                groupes_ids = Groupe.objects.filter(
                    institution_id=institution_id,
                    enseignants__id=user.pk
                ).values_list('id', flat=True)
                return queryset.filter(groupes__id__in=groupes_ids)
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Apprenant':
            if is_detail:
                if ctx.get("user_classe_id"):
                    return queryset.filter(id=ctx["user_classe_id"])
                return queryset.none()
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # GROUPE
    # Admin       : tous les groupes de l'institution
    # Responsable : groupes des classes de son département
    # Formateur   : tous en liste / ses groupes en détail
    # Apprenant   : tous en liste / son groupe en détail
    # ================================================================
    if model_name == 'Groupe':
        if role_name == 'Admin':
            return queryset.filter(institution_id=institution_id)

        if role_name in ['Responsable', 'ResponsableAcademique']:
            if dept_id:
                from .models import Filiere
                filiere_ids = Filiere.objects.filter(
                    institution_id=institution_id,
                    domaine_etude__departement_id=dept_id
                ).values_list('id', flat=True)
                return queryset.filter(
                    institution_id=institution_id,
                    classe__filieres__id__in=filiere_ids
                ).distinct()
            return queryset.none()

        if role_name == 'Formateur':
            if is_detail:
                return queryset.filter(
                    institution_id=institution_id,
                    enseignants__id=user.pk
                )
            return queryset.filter(institution_id=institution_id)

        if role_name == 'Apprenant':
            if is_detail:
                if ctx.get("user_groupe_id"):
                    return queryset.filter(id=ctx["user_groupe_id"])
                return queryset.none()
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # INSCRIPTION (academics — inscription scolaire)
    # Admin       : toutes les inscriptions de l'institution
    # Responsable : inscriptions des classes de son département
    # Formateur   : inscriptions dans ses groupes
    # Apprenant   : uniquement la sienne
    # ================================================================
    if model_name == 'Inscription':
        if role_name == 'Admin':
            return queryset.filter(institution_id=institution_id)

        if role_name in ['Responsable', 'ResponsableAcademique']:
            if dept_id:
                from .models import Filiere
                filiere_ids = Filiere.objects.filter(
                    institution_id=institution_id,
                    domaine_etude__departement_id=dept_id
                ).values_list('id', flat=True)
                return queryset.filter(
                    institution_id=institution_id,
                    classe__filieres__id__in=filiere_ids
                ).distinct()
            return queryset.none()

        if role_name == 'Formateur':
            from .models import Groupe
            groupes_ids = Groupe.objects.filter(
                institution_id=institution_id,
                enseignants__id=user.pk
            ).values_list('id', flat=True)
            return queryset.filter(
                institution_id=institution_id,
                classe__groupes__id__in=groupes_ids
            )

        if role_name == 'Apprenant':
            return queryset.filter(apprenant=user)

        return queryset.none()

    # ================================================================
    # MATIERE
    # Tous les rôles → toutes les matières de l'institution
    # (référentiel partagé)
    # ================================================================
    if model_name == 'Matiere':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique',
                         'Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # SPECIALITE
    # Tous les rôles → toutes les spécialités de l'institution
    # (référentiel partagé)
    # ================================================================
    if model_name == 'Specialite':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique',
                         'Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # ANNEE SCOLAIRE
    # Transversale à toute l'institution
    # ================================================================
    if model_name == 'AnneeScolaire':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique',
                         'Formateur', 'Apprenant']:
            return queryset.filter(institution_id=institution_id)

        return queryset.none()

    # ================================================================
    # Par défaut
    # ================================================================
    if hasattr(queryset.model, 'institution'):
        return queryset.filter(institution_id=institution_id)

    return queryset.all()


def _filter_for_parent(queryset, model_name, ctx):
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
        from .models import Inscription
        classe_ids = Inscription.objects.filter(
            apprenant_id__in=enfants_ids,
            statut='actif'
        ).values_list('classe_id', flat=True).distinct()
        from .models import Groupe
        groupe_ids = Groupe.objects.filter(
            classe_id__in=classe_ids
        ).values_list('id', flat=True).distinct()
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

    if model_name == 'Departement':
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(institution_id__in=inst_ids)

    if model_name == 'DomaineEtude':
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(institution_id__in=inst_ids)

    if model_name == 'Filiere':
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(institution_id__in=inst_ids)

    if model_name in ['Matiere', 'Specialite', 'AnneeScolaire']:
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(institution_id__in=inst_ids)

    if hasattr(queryset.model, 'institution'):
        from users.models import Apprenant
        inst_ids = Apprenant.objects.filter(
            id__in=enfants_ids
        ).values_list('institution_id', flat=True).distinct()
        return queryset.filter(institution_id__in=inst_ids)

    return queryset.none()


def get_filtered_academic_object(model_class, pk, request, model_name):
    qs = model_class.objects.all()
    qs = filter_academics_queryset(qs, request, model_name, is_detail=True)
    return get_object_or_404(qs, pk=pk)


def can_modify_academic_resource(user, obj, model_name):
    if getattr(user, 'is_superuser', False):
        return model_name == 'Institution'

    role_name = get_role_name(user)

    if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
        if hasattr(obj, 'institution_id'):
            return obj.institution_id == user.institution_id
        return True

    if role_name == 'Formateur':
        if model_name == 'Groupe':
            return obj.enseignants.filter(id=user.id).exists()
        return False

    return False


def get_user_groupes_ids(user):
    role_name = get_role_name(user)
    if role_name == 'Formateur':
        from .models import Groupe
        return list(Groupe.objects.filter(
            enseignants__id=user.pk,
            institution_id=user.institution_id
        ).values_list('id', flat=True))
    return []


def get_user_classe_id(user):
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


def _get_departement_id(user, role_name):
    if role_name not in ('Responsable', 'ResponsableAcademique'):
        return None
    return getattr(user, 'departement_id', None)