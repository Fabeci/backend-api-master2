# courses/services/progression.py
from django.utils import timezone
from courses.models import (
    BlocContenu, BlocProgress,
    SequenceProgress, ModuleProgress, CoursProgress,
)

def _required_blocs_qs(sequence):
    # Ajuste ici la règle métier : obligatoires + visibles
    return BlocContenu.objects.filter(
        sequence=sequence,
        est_visible=True,
        est_obligatoire=True,
    )

def recompute_sequence(apprenant, sequence):
    required_blocs = _required_blocs_qs(sequence)
    total = required_blocs.count()

    if total == 0:
        # si pas de blocs requis => on peut considérer terminé ou non, à toi de décider
        est_termine = True
    else:
        done = BlocProgress.objects.filter(
            apprenant=apprenant,
            bloc__in=required_blocs,
            est_termine=True
        ).count()
        est_termine = (done == total)

    sp, _ = SequenceProgress.objects.get_or_create(apprenant=apprenant, sequence=sequence)
    sp.est_termine = est_termine
    sp.completed_at = timezone.now() if est_termine else None
    sp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    return sp.est_termine

def recompute_module(apprenant, module):
    sequences = module.sequences.all()
    total = sequences.count()
    if total == 0:
        est_termine = True
    else:
        done = SequenceProgress.objects.filter(
            apprenant=apprenant,
            sequence__in=sequences,
            est_termine=True
        ).count()
        est_termine = (done == total)

    mp, _ = ModuleProgress.objects.get_or_create(apprenant=apprenant, module=module)
    mp.est_termine = est_termine
    mp.completed_at = timezone.now() if est_termine else None
    mp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    return mp.est_termine

def recompute_cours(apprenant, cours):
    modules = cours.modules.all()
    total = modules.count()
    if total == 0:
        est_termine = True
    else:
        done = ModuleProgress.objects.filter(
            apprenant=apprenant,
            module__in=modules,
            est_termine=True
        ).count()
        est_termine = (done == total)

    cp, _ = CoursProgress.objects.get_or_create(apprenant=apprenant, cours=cours)
    cp.est_termine = est_termine
    cp.completed_at = timezone.now() if est_termine else None
    cp.save(update_fields=["est_termine", "completed_at", "updated_at"])

    return cp.est_termine

def recompute_all_from_bloc(apprenant, bloc):
    sequence = bloc.sequence
    module = sequence.module
    cours = module.cours

    recompute_sequence(apprenant, sequence)
    recompute_module(apprenant, module)
    recompute_cours(apprenant, cours)
