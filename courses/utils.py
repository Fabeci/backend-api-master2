from django.db import transaction
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
