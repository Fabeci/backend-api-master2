# academics/utils.py
"""
Utilitaires de filtrage pour l'application academics.

RÈGLES DE FILTRAGE PAR RÔLE :

1. SuperAdmin   : Voit UNIQUEMENT les institutions
2. Admin        : Voit tout dans son institution, filtrable par année
3. Responsable  : Voit tout dans son institution, filtrable par année
4. Formateur    :
   - Liste   : Voit tout dans son institution, filtrable par année
   - Détail  : Voit uniquement les groupes/classes où il enseigne
5. Apprenant    :
   - Liste   : Voit tout dans son institution (pour explorer)
   - Détail  : Voit uniquement sa classe/groupe et ses ressources
6. Parent       : Lecture seule sur tout ce qui concerne son/ses enfant(s)
"""

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


def _to_int(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _apply_annee_filter(qs, annee_scolaire_id):
    """
    Applique le filtre annee_scolaire_id uniquement si le modèle
    possède ce champ et si une valeur est fournie.
    """
    if not annee_scolaire_id:
        return qs
    field_names = {f.name for f in qs.model._meta.get_fields()}
    if "annee_scolaire" in field_names:
        return qs.filter(annee_scolaire_id=annee_scolaire_id)
    return qs


def get_user_academic_context(request):
    """
    Extrait le contexte académique de l'utilisateur.

    Priorité pour annee_scolaire_id :
      1. Header X-Annee-Scolaire-ID  (sélecteur front)
      2. Query param annee_scolaire_id
      3. Attribut utilisateur (annee_scolaire_active_id)

    Returns:
        dict: {
            'bypass': bool,
            'blocked': bool,
            'institution_id': int|None,
            'annee_scolaire_id': int|None,
            'role_name': str|None,
            'user_classe_id': int|None,
            'user_groupe_id': int|None,
            'enfants_ids': list,
        }
    """
    user = request.user

    ctx = {
        "bypass": False,
        "blocked": False,
        "institution_id": None,
        "annee_scolaire_id": None,
        "role_name": None,
        "user_classe_id": None,
        "user_groupe_id": None,
        "enfants_ids": [],
    }

    # SuperAdmin : bypass pour Institution uniquement, bloqué ailleurs
    if getattr(user, "is_superuser", False):
        ctx["bypass"] = True
        return ctx

    role_name = get_role_name(user)
    ctx["role_name"] = role_name
    ctx["institution_id"] = getattr(user, "institution_id", None)

    # ── Résolution de l'année scolaire ────────────────────────────────────
    # Priorité : header > query param > attribut profil
    annee_header = request.headers.get("X-Annee-Scolaire-ID")
    annee_param  = request.query_params.get("annee_scolaire_id")
    annee_profil = getattr(user, "annee_scolaire_active_id", None)

    ctx["annee_scolaire_id"] = (
        _to_int(annee_header)
        or _to_int(annee_param)
        or _to_int(annee_profil)
    )

    # Parent : récupérer les enfants (pas de filtre année sur le contexte parent)
    if role_name == 'Parent':
        ctx["enfants_ids"] = get_parent_enfants_ids(user)
        return ctx

    # Apprenant : récupérer sa classe/groupe depuis l'inscription active
    if role_name == 'Apprenant':
        from .models import Inscription
        inscription = Inscription.objects.filter(
            apprenant=user,
            statut="actif"
        ).select_related('classe').first()

        if inscription and inscription.classe:
            ctx["user_classe_id"] = inscription.classe_id
            # Filtrer le groupe par année si une année est sélectionnée
            groupes_qs = inscription.classe.groupes
            if ctx["annee_scolaire_id"]:
                groupes_qs = groupes_qs.filter(annee_scolaire_id=ctx["annee_scolaire_id"])
            premier_groupe = groupes_qs.first()
            if premier_groupe:
                ctx["user_groupe_id"] = premier_groupe.id

        # Fallback groupe direct
        if not ctx["user_groupe_id"] and hasattr(user, 'groupe_id'):
            ctx["user_groupe_id"] = user.groupe_id

    return ctx


def filter_academics_queryset(queryset, request, model_name, is_detail=False):
    """
    Filtre un queryset academics selon le rôle et l'année scolaire sélectionnée.
    """
    user = request.user
    ctx = get_user_academic_context(request)

    annee_scolaire_id = ctx.get("annee_scolaire_id")

    # ── INSTITUTION ──────────────────────────────────────────────────────
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

    # ── SuperAdmin BLOQUÉ sur ressources internes ────────────────────────
    if ctx.get("bypass"):
        return queryset.none()

    role_name = ctx.get("role_name")
    institution_id = ctx.get("institution_id")

    # ── PARENT ───────────────────────────────────────────────────────────
    if role_name == 'Parent':
        return _filter_for_parent(queryset, model_name, ctx)

    # ── Sans institution → rien ──────────────────────────────────────────
    if not institution_id and model_name not in ['DomaineEtude', 'Matiere', 'Specialite']:
        return queryset.none()

    # ── GROUPE ───────────────────────────────────────────────────────────
    if model_name == 'Groupe':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
            qs = queryset.filter(institution_id=institution_id)
            # ✅ Filtre par année scolaire si sélectionnée
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

        if role_name == 'Formateur':
            if is_detail:
                qs = queryset.filter(institution_id=institution_id, formateurs=user)
            else:
                qs = queryset.filter(institution_id=institution_id)
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

        if role_name == 'Apprenant':
            if is_detail:
                if ctx.get("user_groupe_id"):
                    return queryset.filter(id=ctx["user_groupe_id"])
                return queryset.none()
            qs = queryset.filter(institution_id=institution_id)
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

    # ── CLASSE ───────────────────────────────────────────────────────────
    if model_name == 'Classe':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
            qs = queryset.filter(institution_id=institution_id)
            # ✅ Filtre par année scolaire si sélectionnée
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

        if role_name == 'Formateur':
            if is_detail:
                from .models import Groupe
                groupes_ids = Groupe.objects.filter(
                    institution_id=institution_id,
                    formateurs=user
                ).values_list('id', flat=True)
                qs = queryset.filter(groupes__id__in=groupes_ids)
            else:
                qs = queryset.filter(institution_id=institution_id)
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

        if role_name == 'Apprenant':
            if is_detail:
                if ctx.get("user_classe_id"):
                    return queryset.filter(id=ctx["user_classe_id"])
                return queryset.none()
            qs = queryset.filter(institution_id=institution_id)
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

    # ── DEPARTEMENT ──────────────────────────────────────────────────────
    if model_name == 'Departement':
        if role_name in ['Admin', 'Responsable', 'Formateur', 'ResponsableAcademique']:
            return queryset.filter(institution_id=institution_id)
        return queryset.none()

    # ── FILIERE ──────────────────────────────────────────────────────────
    if model_name == 'Filiere':
        if role_name in ['Admin', 'Responsable', 'Formateur', 'Apprenant', 'ResponsableAcademique']:
            return queryset.all()
        return queryset.none()

    # ── INSCRIPTION ──────────────────────────────────────────────────────
    if model_name == 'Inscription':
        if role_name in ['Admin', 'Responsable', 'ResponsableAcademique']:
            qs = queryset.filter(institution_id=institution_id)
            # ✅ Filtre par année scolaire si sélectionnée
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

        if role_name == 'Formateur':
            from .models import Groupe
            groupes_ids = Groupe.objects.filter(
                institution_id=institution_id,
                formateurs=user
            ).values_list('id', flat=True)
            qs = queryset.filter(
                institution_id=institution_id,
                classe__groupes__id__in=groupes_ids
            )
            qs = _apply_annee_filter(qs, annee_scolaire_id)
            return qs

        if role_name == 'Apprenant':
            return queryset.filter(apprenant=user)

    # ── MODÈLES GLOBAUX (DomaineEtude, Matiere, Specialite, AnneeScolaire) ─
    if model_name in ["DomaineEtude", "Matiere", "Specialite"]:
        # Référentiels stables — pas de filtre par année
        if role_name in ["Admin", "Responsable", "Formateur", "Apprenant", "ResponsableAcademique"]:
            return queryset.filter(institution_id=institution_id)
        return queryset.none()

    if model_name == "AnneeScolaire":
        # La liste des années n'est PAS filtrée par année — c'est le sélecteur lui-même
        if role_name in ["Admin", "Responsable", "Formateur", "Apprenant", "ResponsableAcademique"]:
            return queryset.filter(institution_id=institution_id)
        return queryset.none()

    # ── Fallback : filtrer par institution si le champ existe ────────────
    if hasattr(queryset.model, 'institution'):
        qs = queryset.filter(institution_id=institution_id)
        qs = _apply_annee_filter(qs, annee_scolaire_id)
        return qs

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
            return obj.formateurs.filter(id=user.id).exists()
        return False

    return False


def get_user_groupes_ids(user):
    role_name = get_role_name(user)
    if role_name == 'Formateur':
        from .models import Groupe
        return list(Groupe.objects.filter(
            formateurs=user,
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