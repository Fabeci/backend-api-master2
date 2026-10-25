# courses/utils.py

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models.functions import Lower

from courses.models import (
    BlocContenu, Sequence, Module, Cours,
    BlocProgress, SequenceProgress, ModuleProgress, CoursProgress
)

# Statuts d'inscription actifs (terminé = cours consultable).
INSCRIPTION_ACTIVE_STATUSES = ("inscrit", "en_cours", "en cours", "encours", "termine", "terminé")


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
    """Contexte MONO-ÉTABLISSEMENT (institution 27 par défaut).

    - Aucun `institution_id` / `X-Institution-ID` n'est accepté : le périmètre
      est toujours l'institution de référence.
    - L'année scolaire peut être choisie, mais uniquement dans cette institution.
    """
    from core.tenant import default_institution_id, default_annee_scolaire

    user = request.user
    iid = default_institution_id()
    default_annee = default_annee_scolaire()

    ctx = {
        "bypass": False,
        "institution_id": iid,
        "annee_scolaire_id": getattr(default_annee, "id", None),
        "departement_id": None,
        "strict": False,
        "role_name": None,
    }

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

    # Un éventuel superuser technique est traité comme Admin de l'établissement
    # unique : plus aucun bypass global.
    if getattr(user, "is_superuser", False) and not ctx["role_name"]:
        ctx["role_name"] = "Admin"

    if ctx["role_name"] == "Responsable":
        try:
            from users.models import ResponsableAcademique
            fresh = ResponsableAcademique.objects.filter(pk=user.pk).values(
                'departement_id'
            ).first()
            if fresh:
                ctx["departement_id"] = fresh['departement_id']
        except Exception:
            ctx["departement_id"] = getattr(user, "departement_id", None)

    if ctx["role_name"] == "Apprenant" or (
        ctx["role_name"] is None and hasattr(user, "apprenant")
    ):
        from .models import InscriptionCours
        ctx["strict"] = True

        apprenant_obj = _get_apprenant_obj(user)
        if apprenant_obj is not None and iid:
            inscription = (
                InscriptionCours.objects
                .filter(apprenant=apprenant_obj, institution_id=iid)
                .annotate(statut_l=Lower("statut"))
                .filter(statut_l__in=["inscrit", "en_cours", "en cours", "encours"])
                .select_related("annee_scolaire")
                .order_by("-id")
                .first()
            )
            if inscription and inscription.annee_scolaire_id:
                ctx["annee_scolaire_id"] = inscription.annee_scolaire_id

    # Année : autorisée seulement si elle appartient à l'institution par défaut.
    annee_param = (
        request.query_params.get("annee_scolaire_id")
        or request.headers.get("X-Annee-Scolaire-ID")
    )
    try:
        annee_id = int(str(annee_param).strip()) if annee_param else None
    except (TypeError, ValueError):
        annee_id = None

    if annee_id and iid:
        from academics.models import AnneeScolaire
        if not AnneeScolaire.objects.filter(pk=annee_id, institution_id=iid).exists():
            annee_id = None

    if annee_id:
        ctx["annee_scolaire_id"] = annee_id
    else:
        user_annee = getattr(user, "annee_scolaire_active_id", None)
        if user_annee and iid:
            from academics.models import AnneeScolaire
            if AnneeScolaire.objects.filter(pk=user_annee, institution_id=iid).exists():
                ctx["annee_scolaire_id"] = user_annee

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

    # ✅ Statuts considérés comme « visibles » pour l'apprenant.
    # On INCLUT « termine » : un cours terminé doit rester consultable
    # (l'interface propose explicitement « Revoir le cours »). Sans cela, les
    # apprenants dont les inscriptions sont passées à « termine » ne voyaient
    # plus AUCUN cours.
    active = ["inscrit", "en_cours", "en cours", "encours", "termine", "terminé"]
    qs = (
        InscriptionCours.objects
        .filter(apprenant=apprenant)
        .annotate(statut_l=Lower("statut"))
        .filter(statut_l__in=active)
    )
    if institution_id:
        qs = qs.filter(institution_id=institution_id)
    return qs.values_list("cours_id", flat=True)



def _formateur_cours_ids(user):
    """Cours enseignés par un formateur : en tant qu'enseignant du cours OU
    enseignant d'un GROUPE du cours (sinon il ne « voyait » aucun contenu)."""
    from .models import Cours
    from django.db.models import Q
    return (
        Cours.objects
        .filter(Q(enseignant_id=user.pk) | Q(groupe__enseignants__id=user.pk))
        .values_list("id", flat=True)
        .distinct()
    )



def is_supervision_admin(user) -> bool:
    """Admin d'établissement : supervision.
    Il consulte la LISTE des cours, mais n'accède PAS au détail d'un cours ni
    aux ressources pédagogiques internes (séquences, blocs, ressources).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return False
    role = user.role.name if hasattr(user, "role") and user.role else None
    return role == "Admin"


def _filter_by_role_impl(queryset, request, model_name="Cours"):
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
        # Modèles SANS `institution_id` : on passe par la relation.
        # (BlocContenu et RessourceSequence n'ont pas d'établissement direct →
        #  séquence → module → cours ; sinon erreur 500 « Cannot resolve
        #  keyword 'institution_id' ».)
        if model_name == "Evaluation":
            return queryset.filter(cours__institution_id=institution_id)
        if model_name == "BlocContenu":
            return queryset.filter(sequence__module__cours__institution_id=institution_id)
        if model_name == "RessourceSequence":
            return queryset.filter(sequence__module__cours__institution_id=institution_id)
        return queryset.filter(institution_id=institution_id)

    # ================================================================
    # RESPONSABLE
    # ================================================================
    if role_name == "Responsable":
        dept_id = ctx.get("departement_id")
        annee_id = ctx.get("annee_scolaire_id")

        def _dept_q(prefix: str = ""):
            """Département du responsable OU contenu NON AFFECTÉ (NULL).

            Les cours importés sans département (groupe sans filière) ne doivent
            pas disparaître des listes du responsable : ils restent visibles au
            niveau de l'établissement.
            """
            return (
                Q(**{f"{prefix}departement_id": dept_id})
                | Q(**{f"{prefix}departement__isnull": True})
            )

        if model_name == "Cours":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q(""))
            return qs

        if model_name == "Evaluation":
            qs = queryset.filter(cours__institution_id=institution_id)
            if dept_id:
                qs = qs.filter(_dept_q("cours__"))
            return qs

        if model_name == "Module":
            f = {"cours__institution_id": institution_id}
            if annee_id:
                f["cours__annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q("cours__"))
            return qs

        if model_name == "Sequence":
            f = {"module__cours__institution_id": institution_id}
            if annee_id:
                f["module__cours__annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q("module__cours__"))
            return qs

        if model_name == "BlocContenu":
            qs = queryset.filter(sequence__module__cours__institution_id=institution_id)
            if dept_id:
                qs = qs.filter(_dept_q("sequence__module__cours__"))
            return qs

        if model_name == "RessourceSequence":
            qs = queryset.filter(sequence__module__cours__institution_id=institution_id)
            if dept_id:
                qs = qs.filter(_dept_q("sequence__module__cours__"))
            return qs

        if model_name == "Session":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q("cours__"))
            return qs

        if model_name == "InscriptionCours":
            f = {"cours__institution_id": institution_id}
            if annee_id:
                f["cours__annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q("cours__"))
            return qs

        if model_name == "Suivi":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q("cours__"))
            return qs

        if model_name == "Participation":
            f = {"institution_id": institution_id}
            if annee_id:
                f["annee_scolaire_id"] = annee_id
            qs = queryset.filter(**f)
            if dept_id:
                qs = qs.filter(_dept_q("session__cours__"))
            return qs

        return queryset.filter(institution_id=institution_id)

    # ================================================================
    # FORMATEUR
    # ================================================================
    if role_name == "Formateur":
        # ✅ MONO-ÉTABLISSEMENT : le formateur opère sur l'institution par défaut
        formateur_inst_ids = [institution_id]
        cours_ids = _formateur_cours_ids(user)

        if model_name == "Cours":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                id__in=cours_ids
            )

        if model_name == "Evaluation":
            return queryset.filter(
                cours__institution_id__in=formateur_inst_ids,
                cours_id__in=cours_ids
            )

        if model_name == "Module":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                cours_id__in=cours_ids
            )

        if model_name == "Sequence":
            return queryset.filter(
                module__cours__institution_id__in=formateur_inst_ids,
                module__cours_id__in=cours_ids
            )

        if model_name == "BlocContenu":
            return queryset.filter(
                sequence__module__cours__institution_id__in=formateur_inst_ids,
                sequence__module__cours_id__in=cours_ids
            )

        if model_name == "RessourceSequence":
            return queryset.filter(
                sequence__module__cours__institution_id__in=formateur_inst_ids,
                sequence__module__cours_id__in=cours_ids
            )

        if model_name == "Session":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                cours_id__in=cours_ids
            )

        if model_name == "InscriptionCours":
            return queryset.filter(
                cours__institution_id__in=formateur_inst_ids,
                cours_id__in=cours_ids,
                institution_id__in=formateur_inst_ids 
            )

        if model_name == "Suivi":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                cours_id__in=cours_ids
            )

        if model_name == "Participation":
            return queryset.filter(
                institution_id__in=formateur_inst_ids,
                session__cours_id__in=cours_ids
            )

        return queryset.filter(institution_id__in=formateur_inst_ids)
    return queryset.none()


def get_filtered_object(model_class, pk, request, model_name):
    qs = model_class.objects.all()
    qs = filter_queryset_by_role(qs, request, model_name)
    return get_object_or_404(qs, pk=pk)


def can_create_in_context(user, parent_obj=None, allow_admin=False):
    """
    Retourne True si l'utilisateur peut créer/modifier/supprimer du contenu.

    Règle métier LMS :
      - SuperAdmin      → toujours autorisé
      - Responsable     → autorisé (dans son périmètre)
      - Formateur       → autorisé sur ses propres cours uniquement
      - Admin           → REFUSÉ (supervision lecture seule) SAUF si
                          `allow_admin=True` (tâches administratives :
                          inscriptions, suivis)
      - Apprenant/Parent→ REFUSÉ
    """
    if user.is_superuser:
        return True

    role_name = user.role.name if hasattr(user, "role") and user.role else None

    # Admin : supervision uniquement — pas de contenu pédagogique, mais les
    # tâches d'administration (inscriptions, suivis) restent autorisées.
    if role_name == "Admin":
        return bool(allow_admin)

    if role_name in ["Responsable", "ResponsableAcademique"]:
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


def can_manage_cours(user, cours):
    """Autorise la gestion du contenu d'un cours (séances, blocs…).

    Variante PERMISSIVE de `can_create_in_context`, destinée aux contrôles de
    propriété ajoutés après coup : elle ne doit JAMAIS retirer un accès qui
    fonctionnait auparavant.

      - SuperAdmin / Admin / Responsable → oui (comme avant) ;
      - Formateur → oui s'il est l'enseignant du cours OU enseignant d'un
        groupe du cours ;
      - pas de cours / contexte inconnu → oui (on ne bloque pas par défaut) ;
      - autres rôles → laissé au RBAC et au filtrage de données.
    """
    if user is None or cours is None:
        return True
    if getattr(user, "is_superuser", False):
        return True

    role_name = user.role.name if hasattr(user, "role") and user.role else None
    if role_name in ("Admin", "Responsable", "ResponsableAcademique"):
        return True

    if role_name == "Formateur":
        if getattr(cours, "enseignant_id", None) == user.id:
            return True
        groupe = getattr(cours, "groupe", None)
        if groupe is not None:
            try:
                if groupe.enseignants.filter(id=user.id).exists():
                    return True
            except Exception:
                pass
        return False

    # Apprenant / Parent : ne pas bloquer ici (RBAC + scoping s'en chargent).
    return True

def filter_queryset_by_role(queryset, request, model_name="Cours", inclure_indisponibles=False):
    """Filtre par rôle PUIS par DISPONIBILITÉ pour les profils apprenant/parent.

    ✅ Séparation autorisation / disponibilité : l'encadrement garde un accès
    complet (brouillons et programmés inclus) ; seuls apprenant et parent sont
    restreints aux contenus effectivement disponibles.

    `inclure_indisponibles=True` (endpoints de STRUCTURE) : on conserve les
    contenus non publiés/programmés pour que l'apprenant voie le PLAN du cours
    (ils sont marqués verrouillés) — l'accès au CONTENU reste bloqué ailleurs
    (bloc_disponible).
    """
    qs = _filter_by_role_impl(queryset, request, model_name)
    if inclure_indisponibles:
        return qs
    try:
        ctx = get_user_context(request)
    except Exception:
        return qs
    role = ctx.get("role_name")
    if role in ("Apprenant", "Parent"):
        from .publication import filter_disponibles
        qs = filter_disponibles(qs, model_name)
    return qs
