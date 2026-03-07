# courses/utils.py — VERSION FIX INSCRIT/Inscrit + fallback apprenant
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models.functions import Lower

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

    # ---- SEQUENCE DONE ?
    blocs_ids = sequence.blocs_contenu.filter(est_visible=True).values_list("id", flat=True)
    total_blocs = len(blocs_ids)

    if total_blocs == 0:
        seq_done = True
    else:
        done_blocs = BlocProgress.objects.filter(
            apprenant=apprenant, bloc_id__in=blocs_ids, est_termine=True
        ).count()
        seq_done = (done_blocs == total_blocs)

    sp, _ = SequenceProgress.objects.get_or_create(apprenant=apprenant, sequence=sequence)
    _set_done_flag(sp, seq_done)
    sp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    # ---- MODULE DONE ?
    seq_ids = module.sequences.values_list("id", flat=True)
    total_seq = module.sequences.count()
    if total_seq == 0:
        mod_done = True
    else:
        done_seq = SequenceProgress.objects.filter(
            apprenant=apprenant, sequence_id__in=seq_ids, est_termine=True
        ).count()
        mod_done = (done_seq == total_seq)

    mp, _ = ModuleProgress.objects.get_or_create(apprenant=apprenant, module=module)
    _set_done_flag(mp, mod_done)
    mp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    # ---- COURS DONE ?
    mod_ids = cours.modules.values_list("id", flat=True)
    total_mod = cours.modules.count()
    if total_mod == 0:
        cours_done = True
    else:
        done_mod = ModuleProgress.objects.filter(
            apprenant=apprenant, module_id__in=mod_ids, est_termine=True
        ).count()
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

    # Résolution du rôle (string ou FK role.name)
    _role = getattr(user, "role", None)
    if _role is None:
        ctx["role_name"] = None
    elif isinstance(_role, str):
        ctx["role_name"] = _role.strip() or None
    elif hasattr(_role, "name"):
        ctx["role_name"] = _role.name
    else:
        ctx["role_name"] = str(_role) or None

    # Fallback héritage multi-table
    if ctx["role_name"] is None:
        from users.models import Apprenant as _Apprenant
        if isinstance(user, _Apprenant):
            ctx["role_name"] = "Apprenant"

    # APPRENANT
    if ctx["role_name"] == "Apprenant" or (ctx["role_name"] is None and hasattr(user, "apprenant")):
        from .models import InscriptionCours

        ctx["strict"] = True

    # ✅ FIX : priorité à l'inscription active
    # user.annee_scolaire_active_id=1 mais inscription.annee_scolaire_id=2
    apprenant_obj = _get_apprenant_obj(user)
    if apprenant_obj is not None:
        inscription = (
            InscriptionCours.objects
            .filter(apprenant=apprenant_obj)
            .annotate(statut_l=Lower("statut"))
            .filter(statut_l__in=["inscrit", "en_cours", "en cours", "encours", "Inscrit"])
            .select_related("institution", "annee_scolaire")
            .order_by("-id")
            .first()
        )
        if inscription:
            ctx["institution_id"] = inscription.institution_id
            ctx["annee_scolaire_id"] = inscription.annee_scolaire_id
            return ctx

    # fallback si pas d'inscription trouvée
        ctx["institution_id"] = getattr(user, "institution_id", None)
        ctx["annee_scolaire_id"] = getattr(user, "annee_scolaire_active_id", None)
        return ctx

    # autres rôles
    ctx["institution_id"] = getattr(user, "institution_id", None)
    ctx["annee_scolaire_id"] = getattr(user, "annee_scolaire_active_id", None)

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


def _get_apprenant_obj(user):
    """
    Résout l'objet Apprenant depuis un User Django (héritage multi-table).
    """
    from users.models import Apprenant

    if isinstance(user, Apprenant):
        return user

    try:
        return Apprenant.objects.get(pk=user.pk)
    except Apprenant.DoesNotExist:
        return None
    except Exception:
        return None


def _get_apprenant_cours_ids(user, institution_id=None):
    from .models import InscriptionCours

    apprenant = _get_apprenant_obj(user)
    if apprenant is None:
        return InscriptionCours.objects.none().values_list("cours_id", flat=True)

    # ✅ Ajout des variantes avec majuscule pour couvrir les anciennes données
    active = ["inscrit", "en_cours", "en cours", "encours", "Inscrit", "En_cours", "En cours"]

    qs = (
        InscriptionCours.objects
        .filter(apprenant=apprenant)
        .annotate(statut_l=Lower("statut"))
        .filter(statut_l__in=[s.lower() for s in active])
    )
    return qs.values_list("cours_id", flat=True)


def filter_queryset_by_role(queryset, request, model_name="Cours"):
    user = request.user
    ctx = get_user_context(request)

    if ctx.get("bypass"):
        return queryset

    role_name = ctx.get("role_name")

    # APPRENANT
    if role_name == "Apprenant" or ctx.get("strict"):
        cours_ids = _get_apprenant_cours_ids(user, ctx.get("institution_id"))

        apprenant_obj = _get_apprenant_obj(user)

        if model_name == "Cours":
            return queryset.filter(id__in=cours_ids)

        if model_name == "Module":
            return queryset.filter(cours_id__in=cours_ids)

        if model_name == "Sequence":
            return queryset.filter(module__cours_id__in=cours_ids)

        if model_name == "BlocContenu":
            return queryset.filter(sequence__module__cours_id__in=cours_ids)

        if model_name == "RessourceSequence":
            return queryset.filter(sequence__module__cours_id__in=cours_ids)

        if model_name == "Session":
            return queryset.filter(cours_id__in=cours_ids)

        if model_name == "InscriptionCours":
            if apprenant_obj is None:
                return queryset.none()
            return queryset.filter(apprenant=apprenant_obj)

        if model_name == "Participation":
            return queryset.filter(session__cours_id__in=cours_ids)

        if model_name == "Suivi":
            if apprenant_obj is None:
                return queryset.none()
            return queryset.filter(apprenant=apprenant_obj)

        if model_name == "BlocProgress":
            if apprenant_obj is None:
                return queryset.none()
            return queryset.filter(apprenant=apprenant_obj)

        if model_name == "SequenceProgress":
            if apprenant_obj is None:
                return queryset.none()
            return queryset.filter(apprenant=apprenant_obj)

        if model_name == "ModuleProgress":
            if apprenant_obj is None:
                return queryset.none()
            return queryset.filter(apprenant=apprenant_obj)

        if model_name == "CoursProgress":
            if apprenant_obj is None:
                return queryset.none()
            return queryset.filter(apprenant=apprenant_obj)

        return queryset.none()

    # autres rôles: institution obligatoire
    if not ctx.get("institution_id"):
        return queryset.none()

    institution_id = ctx["institution_id"]

    if role_name == "Admin":
        return queryset.filter(institution_id=institution_id)

    if role_name == "Responsable":
        filters = {"institution_id": institution_id}
        if ctx.get("annee_scolaire_id"):
            filters["annee_scolaire_id"] = ctx["annee_scolaire_id"]
        return queryset.filter(**filters)

    if role_name == "Formateur":
        filters = {"institution_id": institution_id}
        if ctx.get("annee_scolaire_id"):
            filters["annee_scolaire_id"] = ctx["annee_scolaire_id"]

        if model_name == "Cours":
            filters["enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "Module":
            filters["cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "Sequence":
            filters["module__cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "BlocContenu":
            filters["sequence__module__cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "RessourceSequence":
            filters["sequence__module__cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "Session":
            filters["cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "InscriptionCours":
            filters["cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "Suivi":
            filters["cours__enseignant"] = user
            return queryset.filter(**filters)

        if model_name == "Participation":
            filters["session__cours__enseignant"] = user
            return queryset.filter(**filters)

        return queryset.filter(**filters)

    return queryset.none()


def get_filtered_object(model_class, pk, request, model_name):
    qs = model_class.objects.all()
    qs = filter_queryset_by_role(qs, request, model_name)
    return get_object_or_404(qs, pk=pk)


def can_create_in_context(user, parent_obj=None):
    if user.is_superuser:
        return True

    role_name = user.role.name if hasattr(user, "role") and user.role else None

    if role_name in ["Admin", "Responsable"]:
        return True

    if role_name == "Formateur":
        if parent_obj is None:
            return True

        cours = None
        if hasattr(parent_obj, "enseignant"):
            cours = parent_obj
        elif hasattr(parent_obj, "cours"):
            cours = parent_obj.cours
        elif hasattr(parent_obj, "module"):
            cours = parent_obj.module.cours if hasattr(parent_obj.module, "cours") else None
        elif hasattr(parent_obj, "sequence"):
            if hasattr(parent_obj.sequence, "module"):
                cours = parent_obj.sequence.module.cours

        if cours and hasattr(cours, "enseignant"):
            return cours.enseignant_id == user.id

        return False

    return False