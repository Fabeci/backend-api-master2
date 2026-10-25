# courses/signals.py
#
# Cohérence « qui voit quel cours » :
#   Le GROUPE est la référence. Un cours vise un groupe ; un élève appartient à
#   un groupe. Les accès aux cours (InscriptionCours) sont DÉRIVÉS et tenus à jour
#   automatiquement dans les deux sens :
#     · création / changement de groupe d'un cours  → on aligne les élèves
#     · création / changement de groupe d'un élève  → on aligne ses cours
#     · retrait (départ / diplômé)                  → on retire l'accès (doux)
#     · suppression d'inscription                   → idem
#   Retrait « doux » = statut passé à `abandonne` (aucune donnée supprimée).

from django.db import transaction
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver

from .models import Cours, InscriptionCours, BlocContenu, Session, Participation, Module, Sequence

# Statuts d'inscription-cours qui donnent l'ACCÈS
ACTIFS = ("inscrit", "en_cours", "en cours", "encours")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _apprenants_du_groupe(groupe_id, institution_id=None, annee_id=None):
    """Identifiants des élèves rattachés à ce groupe (filtres optionnels)."""
    if not groupe_id:
        return []
    from users.models import Apprenant
    qs = Apprenant.objects.filter(groupe_id=groupe_id)
    if institution_id:
        qs = qs.filter(institution_id=institution_id)
    if annee_id:
        qs = qs.filter(annee_scolaire_active_id=annee_id)
    return list(qs.values_list("id", flat=True))


def sync_cours(cours):
    """Aligne les accès au cours sur son groupe (ajout, réactivation, retrait doux)."""
    if not cours or not cours.groupe_id:
        return
    attendus = set(_apprenants_du_groupe(cours.groupe_id, cours.institution_id, cours.annee_scolaire_id))
    existants = {r.apprenant_id: r for r in InscriptionCours.objects.filter(cours=cours)}

    a_creer = []
    for aid in attendus:
        rec = existants.get(aid)
        if rec is None:
            a_creer.append(InscriptionCours(
                apprenant_id=aid, cours=cours, statut="inscrit",
                institution=cours.institution, annee_scolaire=cours.annee_scolaire,
            ))
        elif rec.statut not in ACTIFS:
            rec.statut = "inscrit"
            rec.save(update_fields=["statut"])
    if a_creer:
        InscriptionCours.objects.bulk_create(a_creer, ignore_conflicts=True)

    # Ceux qui ne sont plus dans le groupe perdent l'accès (sans suppression)
    for aid, rec in existants.items():
        if aid not in attendus and rec.statut in ACTIFS:
            rec.statut = "abandonne"
            rec.save(update_fields=["statut"])


def sync_apprenant(apprenant):
    """Aligne les accès de l'élève sur son groupe."""
    if not apprenant or not apprenant.groupe_id:
        return
    cours_qs = Cours.objects.filter(groupe_id=apprenant.groupe_id)
    if apprenant.institution_id:
        cours_qs = cours_qs.filter(institution_id=apprenant.institution_id)
    if apprenant.annee_scolaire_active_id:
        cours_qs = cours_qs.filter(annee_scolaire_id=apprenant.annee_scolaire_active_id)
    cible = {c.id: c for c in cours_qs}

    existants = {r.cours_id: r for r in InscriptionCours.objects.filter(apprenant=apprenant)}
    a_creer = []
    for cid, cours in cible.items():
        rec = existants.get(cid)
        if rec is None:
            a_creer.append(InscriptionCours(
                apprenant=apprenant, cours=cours, statut="inscrit",
                institution=cours.institution, annee_scolaire=cours.annee_scolaire,
            ))
        elif rec.statut not in ACTIFS:
            rec.statut = "inscrit"
            rec.save(update_fields=["statut"])
    if a_creer:
        InscriptionCours.objects.bulk_create(a_creer, ignore_conflicts=True)

    for cid, rec in existants.items():
        if cid not in cible and rec.statut in ACTIFS:
            rec.statut = "abandonne"
            rec.save(update_fields=["statut"])


def retirer_acces_apprenant(apprenant):
    """Retire l'accès de l'élève à tous ses cours (doux)."""
    if not apprenant:
        return
    InscriptionCours.objects.filter(apprenant=apprenant).exclude(statut="abandonne").update(statut="abandonne")


# ── Cours : création ou changement de groupe ────────────────────────────────

@receiver(pre_save, sender=Cours)
def _cours_capture_ancien_groupe(sender, instance, **kwargs):
    if instance.pk:
        instance._old_groupe_id = (
            Cours.objects.filter(pk=instance.pk).values_list("groupe_id", flat=True).first()
        )
    else:
        instance._old_groupe_id = None


@receiver(post_save, sender=Cours)
def _cours_sync_apres_save(sender, instance, created, **kwargs):
    if created or getattr(instance, "_old_groupe_id", None) != instance.groupe_id:
        transaction.on_commit(lambda: sync_cours(instance))


# ── Élève : création ou changement de groupe ────────────────────────────────

@receiver(pre_save, sender="users.Apprenant")
def _apprenant_capture_ancien_groupe(sender, instance, **kwargs):
    if instance.pk:
        from users.models import Apprenant
        instance._old_groupe_id = (
            Apprenant.objects.filter(pk=instance.pk).values_list("groupe_id", flat=True).first()
        )
    else:
        instance._old_groupe_id = None


@receiver(post_save, sender="users.Apprenant")
def _apprenant_sync_apres_save(sender, instance, created, **kwargs):
    if created or getattr(instance, "_old_groupe_id", None) != instance.groupe_id:
        transaction.on_commit(lambda: sync_apprenant(instance))


# ── Inscription administrative : actif → accès, retiré/diplômé → retrait ────

@receiver(post_save, sender="academics.Inscription")
def _inscription_sync(sender, instance, created, **kwargs):
    from users.models import Apprenant
    apprenant = Apprenant.objects.filter(pk=instance.apprenant_id).first()
    if not apprenant:
        return
    if instance.statut == "actif":
        transaction.on_commit(lambda: sync_apprenant(apprenant))
    else:
        transaction.on_commit(lambda: retirer_acces_apprenant(apprenant))


@receiver(post_delete, sender="academics.Inscription")
def _inscription_supprimee(sender, instance, **kwargs):
    from users.models import Apprenant
    apprenant = Apprenant.objects.filter(pk=instance.apprenant_id).first()
    if apprenant:
        transaction.on_commit(lambda: retirer_acces_apprenant(apprenant))


# ── Séance : prépare la feuille de présence (attendus) ──────────────────────

@receiver(post_save, sender=Session)
def _seance_preparer_presences(sender, instance, created, **kwargs):
    if not created or not instance.cours_id:
        return
    apprenant_ids = list(
        InscriptionCours.objects
        .filter(cours_id=instance.cours_id, statut__in=ACTIFS)
        .values_list("apprenant_id", flat=True)
    )
    if not apprenant_ids:
        return
    Participation.objects.bulk_create(
        [
            Participation(
                session=instance, apprenant_id=aid, statut="absent", source="auto",
                institution=instance.institution, annee_scolaire=instance.annee_scolaire,
            )
            for aid in apprenant_ids
        ],
        ignore_conflicts=True,
    )


# ── Automatismes existants (conservés) ──────────────────────────────────────

@receiver(pre_save, sender=Cours)
def auto_statut_cours(sender, instance, **kwargs):
    """Recalcule le statut d'après les dates — SAUF statut fixé manuellement (force) ou annulé."""
    if getattr(instance, "statut_force", False) or instance.statut == "annule":
        return
    if instance.date_debut or instance.date_fin:
        try:
            instance.statut = instance.statut_calcule
        except Exception:
            pass


@receiver(pre_save, sender=BlocContenu)
def auto_duree_estimee_bloc(sender, instance, **kwargs):
    """Pré-remplit la durée estimée d'un bloc si elle n'est pas fournie."""
    if not instance.duree_estimee_minutes:
        from .estimation import estimer_duree_minutes
        instance.duree_estimee_minutes = estimer_duree_minutes(instance)


# ── Cascade de publication : une action sur le MODULE se répercute sur ses
#    séquences et leurs blocs (uniquement quand l'état change). ───────────────

@receiver(pre_save, sender=Module)
def _module_capture_ancien_etat(sender, instance, **kwargs):
    if instance.pk:
        instance._old_etat_pub = (
            Module.objects.filter(pk=instance.pk).values_list("etat_publication", flat=True).first()
        )
    else:
        instance._old_etat_pub = None


@receiver(post_save, sender=Module)
def _module_cascade_publication(sender, instance, created, **kwargs):
    if created or getattr(instance, "_old_etat_pub", None) != instance.etat_publication:
        from .publication import appliquer_etat_module
        transaction.on_commit(lambda: appliquer_etat_module(instance))


@receiver(pre_save, sender=Sequence)
def _sequence_capture_ancien_etat(sender, instance, **kwargs):
    if instance.pk:
        instance._old_etat_pub = (
            Sequence.objects.filter(pk=instance.pk).values_list("etat_publication", flat=True).first()
        )
    else:
        instance._old_etat_pub = None


@receiver(post_save, sender=Sequence)
def _sequence_cascade_publication(sender, instance, created, **kwargs):
    if created or getattr(instance, "_old_etat_pub", None) != instance.etat_publication:
        from .publication import appliquer_etat_sequence
        transaction.on_commit(lambda: appliquer_etat_sequence(instance))
