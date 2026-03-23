# courses/utils.py

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
    module = sequence.module
    cours = module.cours

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
        "departement_id": None,
        "strict": False,
        "role_name": None,
    }

    if getattr(user, "is_superuser", False):
        ctx["bypass"] = True
        return ctx

    _role = getattr(user, "role", None)
    if _role is None:
        ctx["role_name"] = None
    elif isinstance(_role, str):
        ctx["role_name"] = _role.strip() or None
    elif hasattr(_role, "name"):
        ctx["role_name"] = _role.name
    else:
        ctx["role_name"] = str(_role) or None

    if ctx["role_name"] in ("ResponsableAcademique", "Responsable académique"):
        ctx["role_name"] = "Responsable"

    if ctx["role_name"] is None:
        from users.models import Apprenant as _Apprenant
        if isinstance(user, _Apprenant):
            ctx["role_name"] = "Apprenant"

    if ctx["role_name"] == "Responsable":
        try:
            from users.models import ResponsableAcademique
            fresh = ResponsableAcademique.objects.filter(
                pk=user.pk
            ).values('departement_id', 'institution_id').first()
            if fresh:
                ctx["departement_id"] = fresh['departement_id']
                if fresh['institution_id']:
                    ctx["institution_id"] = fresh['institution_id']
        except Exception:
            ctx["departement_id"] = getattr(user, "departement_id", None)

    # ✅ Formateur : institution_id via M2M institutions
    if ctx["role_name"] == "Formateur":
        from users.models import Formateur as FormateurModel
        try:
            formateur_obj = FormateurModel.objects.get(pk=user.pk)
            inst_ids = list(formateur_obj.institutions.values_list('id', flat=True))
            if inst_ids:
                ctx["institution_id"] = inst_ids[0]
        except Exception:
            pass

    if ctx["role_name"] == "Apprenant" or (
        ctx["role_name"] is None and hasattr(user, "apprenant")
    ):
        from .models import InscriptionCours
        ctx["strict"] = True

        apprenant_obj = _get_apprenant_obj(user)
        if apprenant_obj is not None:
            inscription = (
                InscriptionCours.objects
                .filter(apprenant=apprenant_obj)
                .annotate(statut_l=Lower("statut"))
                .filter(statut_l__in=["inscrit", "en_cours", "en cours", "encours"])
                .select_related("institution", "annee_scolaire")
                .order_by("-id")
                .first()
            )
            if inscription:
                ctx["institution_id"] = inscription.institution_id
                ctx["annee_scolaire_id"] = inscription.annee_scolaire_id
                return ctx

        ctx["institution_id"] = getattr(user, "institution_id", None)
        ctx["annee_scolaire_id"] = getattr(user, "annee_scolaire_active_id", None)
        return ctx

    ctx["institution_id"] = getattr(user, "institution_id", None)
    ctx["annee_scolaire_id"] = getattr(user, "annee_scolaire_active_id", None)

    inst_param = (
        request.query_params.get("institution_id")
        or request.headers.get("X-Institution-ID")
    )
    annee_param = (
        request.query_params.get("annee_scolaire_id")
        or request.headers.get("X-Annee-Scolaire-ID")
    )

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

    active = ["inscrit", "en_cours", "en cours", "encours"]
    qs = (
        InscriptionCours.objects
        .filter(apprenant=apprenant)
        .annotate(statut_l=Lower("statut"))
        .filter(statut_l__in=active)
    )
    if institution_id:
        qs = qs.filter(institution_id=institution_id)
    return qs.values_list("cours_id", flat=True)


def filter_queryset_by_role(queryset, request, model_name="Cours"):
    user = request.user
    ctx = get_user_context(request)

    if ctx.get("bypass"):
        return queryset

    role_name = ctx.get("role_name")
    if role_name in ("ResponsableAcademique", "Responsable académique"):
        role_name = "Responsable"

    # ================================================================
    # APPRENANT
    # ================================================================
    if role_name == "Apprenant" or ctx.get("strict"):
        cours_ids = _get_apprenant_cours_ids(user, ctx.get("institution_id"))
        apprenant_obj = _get_apprenant_obj(user)

        if model_name == "Cours":
            return queryset.filter(id__in=cours_ids)
        if model_name == "Evaluation":
            return queryset.filter(cours_id__in=cours_ids, est_publiee=True)
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
            return queryset.filter(apprenant=apprenant_obj, cours_id__in=cours_ids)
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

    # ================================================================
    # PARENT
    # ================================================================
    if role_name == "Parent":
        from users.models import Apprenant, Parent as ParentModel
        from .models import InscriptionCours
        try:
            parent_obj = ParentModel.objects.get(pk=user.pk)
            enfant_ids = Apprenant.objects.filter(
                tuteur=parent_obj
            ).values_list("id", flat=True)
            cours_ids = (
                InscriptionCours.objects
                .filter(apprenant_id__in=enfant_ids)
                .values_list("cours_id", flat=True)
                .distinct()
            )
        except Exception:
            return queryset.none()

        if model_name == "Cours":
            return queryset.filter(id__in=cours_ids)
        if model_name == "Evaluation":
            return queryset.filter(cours_id__in=cours_ids, est_publiee=True)
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
            return queryset.filter(apprenant_id__in=enfant_ids)
        if model_name == "Suivi":
            return queryset.filter(apprenant_id__in=enfant_ids)
        if model_name == "Participation":
            return queryset.filter(session__cours_id__in=cours_ids)
        return queryset.none()

    # ================================================================
    # Sans institution → rien
    # ================================================================
    if not ctx.get("institution_id"):
        return queryset.none()

    institution_id = ctx["institution_id"]

    # ================================================================
    # ADMIN
    # ================================================================
    if role_name == "Admin":
        # Evaluation n'a pas institution_id direct → via cours
        if model_name == "Evaluation":
            return queryset.filter(cours__institution_id=institution_id)
        return queryset.filter(institution_id=institution_id)

    # ================================================================
    # RESPONSABLE
    # ================================================================
    if role_name == "Responsable":
        dept_id = ctx.get("departement_id")
        annee_id = ctx.get("annee_scolaire_id")

        if model_name == "Cours":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            if dept_id:
                f["departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "Evaluation":
            f = {"cours__institution_id": institution_id}
            if dept_id:
                f["cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "Module":
            f = {"cours__institution_id": institution_id}
            if annee_id:
                f["cours__annee_scolaire_id"] = annee_id
            if dept_id:
                f["cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "Sequence":
            f = {"module__cours__institution_id": institution_id}
            if annee_id:
                f["module__cours__annee_scolaire_id"] = annee_id
            if dept_id:
                f["module__cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "BlocContenu":
            f = {"sequence__module__cours__institution_id": institution_id}
            if dept_id:
                f["sequence__module__cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "RessourceSequence":
            f = {"sequence__module__cours__institution_id": institution_id}
            if dept_id:
                f["sequence__module__cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "Session":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            if dept_id:
                f["cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "InscriptionCours":
            f = {"cours__institution_id": institution_id}
            if annee_id:
                f["cours__annee_scolaire_id"] = annee_id
            if dept_id:
                f["cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "Suivi":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            if dept_id:
                f["cours__departement_id"] = dept_id
            return queryset.filter(**f)

        if model_name == "Participation":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            if dept_id:
                f["session__cours__departement_id"] = dept_id
            return queryset.filter(**f)

        return queryset.filter(institution_id=institution_id)

    # ================================================================
    # FORMATEUR
    # ================================================================
    if role_name == "Formateur":
        # ✅ Récupérer les institutions du formateur via M2M
        from users.models import Formateur as FormateurModel
        try:
            formateur_obj = FormateurModel.objects.get(pk=user.pk)
            formateur_inst_ids = list(
                formateur_obj.institutions.values_list('id', flat=True)
            )
        except FormateurModel.DoesNotExist:
            return queryset.none()

        if not formateur_inst_ids:
            return queryset.none()

        if model_name == "Cours":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                enseignant_id=user.pk
            )

        if model_name == "Evaluation":
            return queryset.filter(
                cours__institution_id__in=formateur_inst_ids,
                cours__enseignant_id=user.pk
            )

        if model_name == "Module":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                cours__enseignant_id=user.pk
            )

        if model_name == "Sequence":
            return queryset.filter(
                module__cours__institution_id__in=formateur_inst_ids,
                module__cours__enseignant_id=user.pk
            )

        if model_name == "BlocContenu":
            return queryset.filter(
                sequence__module__cours__institution_id__in=formateur_inst_ids,
                sequence__module__cours__enseignant_id=user.pk
            )

        if model_name == "RessourceSequence":
            return queryset.filter(
                sequence__module__cours__institution_id__in=formateur_inst_ids,
                sequence__module__cours__enseignant_id=user.pk
            )

        if model_name == "Session":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                cours__enseignant_id=user.pk
            )

        if model_name == "InscriptionCours":
            return queryset.filter(
                cours__institution_id__in=formateur_inst_ids,
                cours__enseignant_id=user.pk,
                institution_id__in=formateur_inst_ids 
            )

        if model_name == "Suivi":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                cours__enseignant_id=user.pk
            )

        if model_name == "Participation":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                session__cours__enseignant_id=user.pk
            )

        return queryset.filter(institution_id__in=formateur_inst_ids)
    return queryset.none()


def get_filtered_object(model_class, pk, request, model_name):
    qs = model_class.objects.all()
    qs = filter_queryset_by_role(qs, request, model_name)
    return get_object_or_404(qs, pk=pk)


def can_create_in_context(user, parent_obj=None):
    if user.is_superuser:
        return True

    role_name = user.role.name if hasattr(user, "role") and user.role else None

    if role_name in ["Admin", "Responsable", "ResponsableAcademique"]:
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