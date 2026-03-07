# courses/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Cours, InscriptionCours


@receiver(post_save, sender=Cours)
def inscrire_apprenants_groupe(sender, instance, created, **kwargs):
    """
    Après la création d'un cours, inscrit automatiquement
    tous les apprenants de la classe du groupe associé.
    """
    if not created:
        return

    groupe = instance.groupe
    if not groupe:
        return

    classe = getattr(groupe, 'classe', None)
    if not classe:
        return

    from academics.models import Inscription

    filtres = {'classe': classe}
    if instance.annee_scolaire:
        filtres['annee_scolaire'] = instance.annee_scolaire
    if instance.institution:
        filtres['institution'] = instance.institution

    apprenants_ids = Inscription.objects.filter(
        **filtres
    ).values_list('apprenant_id', flat=True)

    if not apprenants_ids:
        return

    InscriptionCours.objects.bulk_create(
        [
            InscriptionCours(
                apprenant_id=apprenant_id,
                cours=instance,
                statut='inscrit',
                institution=instance.institution,
                annee_scolaire=instance.annee_scolaire,
            )
            for apprenant_id in apprenants_ids
        ],
        ignore_conflicts=True
    )


@receiver(post_save, sender='academics.Inscription')
def inscrire_apprenant_aux_cours_de_la_classe(sender, instance, created, **kwargs):
    """
    Après l'inscription d'un apprenant dans une classe,
    l'inscrit automatiquement à tous les cours de cette classe
    (via les groupes de la classe).
    """
    if not created:
        return

    classe = instance.classe
    if not classe:
        return

    # Récupérer tous les cours liés aux groupes de cette classe,
    # filtrés par institution et année scolaire
    filtres = {'groupe__classe': classe}
    if instance.annee_scolaire:
        filtres['annee_scolaire'] = instance.annee_scolaire
    if instance.institution:
        filtres['institution'] = instance.institution

    cours_ids = Cours.objects.filter(**filtres).values_list('id', 'institution_id', 'annee_scolaire_id')

    if not cours_ids:
        return

    InscriptionCours.objects.bulk_create(
        [
            InscriptionCours(
                apprenant_id=instance.apprenant_id,
                cours_id=cours_id,
                statut='inscrit',
                institution_id=institution_id,
                annee_scolaire_id=annee_scolaire_id,
            )
            for cours_id, institution_id, annee_scolaire_id in cours_ids
        ],
        ignore_conflicts=True
    )