from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from courses.models import (
    BlocContenu, Sequence, Module, Cours,
    BlocProgress, SequenceProgress, ModuleProgress, CoursProgress
)

def _set_done_flag(obj, done: bool):
    if done:
        obj.est_termine = True
        obj.completed_at = obj.completed_at or timezone.now()
    else:
        obj.est_termine = False
        obj.completed_at = None

@transaction.atomic
def recompute_cascade(apprenant, sequence: Sequence):
    """
    Recalcule l'état terminé pour:
      sequence -> module -> cours
    pour un apprenant donné.
    """
    module = sequence.module
    cours = module.cours

    # ---- SEQUENCE DONE ? (tous les blocs de la séquence terminés)
    blocs_ids = sequence.blocs_contenu.filter(est_visible=True).values_list("id", flat=True)
    total_blocs = len(blocs_ids)

    if total_blocs == 0:
        seq_done = True  # à toi de décider; sinon False
    else:
        done_blocs = BlocProgress.objects.filter(
            apprenant=apprenant, bloc_id__in=blocs_ids, est_termine=True
        ).count()
        seq_done = (done_blocs == total_blocs)

    sp, _ = SequenceProgress.objects.get_or_create(apprenant=apprenant, sequence=sequence)
    _set_done_flag(sp, seq_done)
    sp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    # ---- MODULE DONE ? (toutes les séquences du module terminées)
    seq_ids = module.sequences.values_list("id", flat=True)
    total_seq = module.sequences.count()
    if total_seq == 0:
        mod_done = True
    else:
        done_seq = SequenceProgress.objects.filter(apprenant=apprenant, sequence_id__in=seq_ids, est_termine=True).count()
        mod_done = (done_seq == total_seq)

    mp, _ = ModuleProgress.objects.get_or_create(apprenant=apprenant, module=module)
    _set_done_flag(mp, mod_done)
    mp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    # ---- COURS DONE ? (tous les modules terminés)
    mod_ids = cours.modules.values_list("id", flat=True)
    total_mod = cours.modules.count()
    if total_mod == 0:
        cours_done = True
    else:
        done_mod = ModuleProgress.objects.filter(apprenant=apprenant, module_id__in=mod_ids, est_termine=True).count()
        cours_done = (done_mod == total_mod)

    cp, _ = CoursProgress.objects.get_or_create(apprenant=apprenant, cours=cours)
    _set_done_flag(cp, cours_done)
    cp.save(update_fields=["est_termine", "completed_at", "updated_at"])


def get_user_context(request):
    user = request.user
    
    ctx = {
        "bypass": False,
        "institution_id": None,
        "annee_scolaire_id": None,
        "strict": False,
        "role_name": None,
    }
    
    # SuperUser : bypass complet
    if getattr(user, "is_superuser", False):
        ctx["bypass"] = True
        return ctx
    
    # Récupérer le rôle
    ctx["role_name"] = user.role.name if hasattr(user, 'role') and user.role else None
    
    # Apprenant : contexte via InscriptionCours
    if ctx["role_name"] == 'Apprenant' or hasattr(user, "apprenant"):
        from .models import InscriptionCours
        
        inscription = (
            InscriptionCours.objects
            .filter(apprenant=user, statut__in=["inscrit", "en_cours"])
            .select_related("institution", "annee_scolaire")
            .order_by("-id")
            .first()
        )
        
        ctx["strict"] = True
        if inscription:
            ctx["institution_id"] = inscription.institution_id
            ctx["annee_scolaire_id"] = inscription.annee_scolaire_id
        
        return ctx
    
    # Autres rôles : contexte via user.institution
    ctx["institution_id"] = getattr(user, "institution_id", None)
    ctx["annee_scolaire_id"] = getattr(user, "annee_scolaire_active_id", None)
    
    # Fallback query params / headers (pour changer d'année côté UI)
    inst_param = request.query_params.get("institution_id") or request.headers.get("X-Institution-ID")
    annee_param = request.query_params.get("annee_scolaire_id") or request.headers.get("X-Annee-Scolaire-ID")
    
    def to_int(v):
        if v is None:
            return None
        if isinstance(v, int):
            return v
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return None
    
    if inst_param:
        ctx["institution_id"] = to_int(inst_param)
    if annee_param:
        ctx["annee_scolaire_id"] = to_int(annee_param)
    
    return ctx


def filter_queryset_by_role(queryset, request, model_name='Cours'):
    """
    Filtre un queryset selon le rôle de l'utilisateur.
    
    RÈGLES STRICTES :
    - SuperUser : TOUT
    - Admin : Son institution (toutes années)
    - Responsable : Son institution + son année
    - Formateur : SES cours uniquement (enseignant=user) + institution + année
    - Apprenant : Cours inscrits uniquement
    
    Args:
        queryset: QuerySet Django
        request: Request Django
        model_name: 'Cours', 'Module', 'Sequence', 'BlocContenu', etc.
    
    Returns:
        QuerySet filtré
    
    Usage:
        qs = Cours.objects.all()
        qs = filter_queryset_by_role(qs, request, 'Cours')
    """
    user = request.user
    ctx = get_user_context(request)
    
    # 1. SuperUser : pas de filtrage
    if ctx.get("bypass"):
        return queryset
    
    # 2. Pas d'institution : rien (sauf SuperUser)
    if not ctx.get("institution_id"):
        if ctx.get("strict"):
            # Apprenant sans inscription : rien
            return queryset.none()
        # Autres sans institution : rien
        return queryset.none()
    
    role_name = ctx.get("role_name")
    
    # 3. ADMIN : Toute son institution (avec ou sans année)
    if role_name == 'Admin':
        return queryset.filter(institution_id=ctx["institution_id"])
    
    # 4. RESPONSABLE : Institution + Année
    if role_name == 'Responsable':
        filters = {'institution_id': ctx["institution_id"]}
        if ctx.get("annee_scolaire_id"):
            filters['annee_scolaire_id'] = ctx["annee_scolaire_id"]
        return queryset.filter(**filters)
    
    # 5. FORMATEUR : SES cours uniquement (FILTRAGE STRICT)
    if role_name == 'Formateur':
        filters = {'institution_id': ctx["institution_id"]}
        if ctx.get("annee_scolaire_id"):
            filters['annee_scolaire_id'] = ctx["annee_scolaire_id"]
        
        # Filtrage selon le modèle
        if model_name == 'Cours':
            # Direct : cours dont il est l'enseignant
            filters['enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'Module':
            # Via relation : modules de SES cours
            filters['cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'Sequence':
            # Via relations : séquences de SES cours
            filters['module__cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'BlocContenu':
            # Via relations : blocs de SES séquences
            filters['sequence__module__cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'RessourceSequence':
            # Via relations : ressources de SES séquences
            filters['sequence__module__cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'Session':
            # Sessions de SES cours
            filters['cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'InscriptionCours':
            # Inscriptions dans SES cours
            filters['cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'Suivi':
            # Suivis dans SES cours
            filters['cours__enseignant'] = user
            return queryset.filter(**filters)
        
        elif model_name == 'Participation':
            # Participations dans SES sessions
            filters['session__cours__enseignant'] = user
            return queryset.filter(**filters)
        
        # Par défaut : filtrer par institution + année (sans cours)
        return queryset.filter(**filters)
    
    # 6. APPRENANT : Cours inscrits uniquement
    if role_name == 'Apprenant':
        from .models import InscriptionCours
        
        if model_name == 'Cours':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"],
            ).values_list('cours_id', flat=True)
            return queryset.filter(id__in=cours_ids)
        
        elif model_name == 'Module':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            ).values_list('cours_id', flat=True)
            return queryset.filter(cours_id__in=cours_ids)
        
        elif model_name == 'Sequence':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            ).values_list('cours_id', flat=True)
            return queryset.filter(module__cours_id__in=cours_ids)
        
        elif model_name == 'BlocContenu':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            ).values_list('cours_id', flat=True)
            return queryset.filter(sequence__module__cours_id__in=cours_ids)
        
        elif model_name == 'RessourceSequence':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            ).values_list('cours_id', flat=True)
            return queryset.filter(sequence__module__cours_id__in=cours_ids)
        
        elif model_name == 'Session':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            ).values_list('cours_id', flat=True)
            return queryset.filter(cours_id__in=cours_ids)
        
        elif model_name == 'InscriptionCours':
            return queryset.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            )
        
        elif model_name == 'Participation':
            cours_ids = InscriptionCours.objects.filter(
                apprenant=user,
                institution_id=ctx["institution_id"]
            ).values_list('cours_id', flat=True)
            return queryset.filter(session__cours_id__in=cours_ids)
    
    # Défaut : rien
    return queryset.none()


def get_filtered_object(model_class, pk, request, model_name):
    """
    Récupère un objet filtré par rôle ou lève Http404.
    
    Usage:
        cours = get_filtered_object(Cours, cours_id, request, 'Cours')
    """
    qs = model_class.objects.all()
    qs = filter_queryset_by_role(qs, request, model_name)
    return get_object_or_404(qs, pk=pk)


def can_create_in_context(user, parent_obj=None):
    """
    Vérifie si l'utilisateur peut créer une ressource.
    
    Pour Formateur : peut créer uniquement si parent_obj.enseignant == user
    
    Args:
        user: Utilisateur connecté
        parent_obj: Objet parent (Cours, Module, Sequence, etc.)
    
    Returns:
        bool: True si autorisé
    """
    # SuperUser : toujours autorisé
    if user.is_superuser:
        return True
    
    role_name = user.role.name if hasattr(user, 'role') and user.role else None
    
    # Admin/Responsable : autorisé dans leur institution
    if role_name in ['Admin', 'Responsable']:
        return True
    
    # Formateur : autorisé seulement si c'est SON cours
    if role_name == 'Formateur':
        if parent_obj is None:
            # Création de cours : autorisé (sera auto-assigné comme enseignant)
            return True
        
        # Trouver le cours parent
        cours = None
        if hasattr(parent_obj, 'enseignant'):
            # C'est un cours
            cours = parent_obj
        elif hasattr(parent_obj, 'cours'):
            # Module ou Session
            cours = parent_obj.cours
        elif hasattr(parent_obj, 'module'):
            # Sequence
            cours = parent_obj.module.cours if hasattr(parent_obj.module, 'cours') else None
        elif hasattr(parent_obj, 'sequence'):
            # BlocContenu ou RessourceSequence
            if hasattr(parent_obj.sequence, 'module'):
                cours = parent_obj.sequence.module.cours
        
        # Vérifier que c'est SON cours
        if cours and hasattr(cours, 'enseignant'):
            return cours.enseignant_id == user.id
        
        return False
    
    # Apprenant : pas de création
    return False
