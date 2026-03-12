# notifications/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from courses.models import Cours, Module, Session, Participation
from evaluations.models import Evaluation, PassageEvaluation
from academics.models import Inscription
from users.models import User

from .models import (
    Notification,
    TypeNotification,
    PrioriteNotification,
    CanalNotification,
    EntityType,
)


def _notifier(recipient, type_notif, titre, message,
              priorite=PrioriteNotification.MOYENNE,
              sender=None, entity_type=None, entity_id=None,
              action_url=None, institution=None, annee_scolaire=None,
              groupe_dedup=None, **metadata):
    try:
        Notification.creer(
            recipient=recipient,
            type_notif=type_notif,
            titre=titre,
            message=message,
            canal=CanalNotification.IN_APP,
            priorite=priorite,
            sender=sender,
            entity_type=entity_type,
            entity_id=entity_id,
            action_url=action_url,
            institution=institution,
            annee_scolaire=annee_scolaire,
            groupe_deduplication=groupe_dedup,
            **metadata,
        )
    except Exception as e:
        print(f"[Notification signal error] {e}")


# ============================================================================
# COURS
# ============================================================================

@receiver(post_save, sender=Cours)
def on_cours_saved(sender, instance: Cours, created: bool, **kwargs):
    if not created:
        return

    responsables = User.objects.filter(
        responsableacademique__isnull=False,
        institution=instance.institution,
    )
    for resp in responsables:
        _notifier(
            recipient=resp,
            type_notif=TypeNotification.COURS_CREE,
            titre="Nouveau cours créé",
            message=f"Le cours « {instance.titre or instance.matiere.nom} » a été créé par {instance.enseignant.prenom} {instance.enseignant.nom}.",
            priorite=PrioriteNotification.BASSE,
            sender=instance.enseignant,
            entity_type=EntityType.COURS,
            entity_id=instance.pk,
            action_url=f"/cours/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
        )


# ============================================================================
# MODULE
# ============================================================================

@receiver(post_save, sender=Module)
def on_module_saved(sender, instance: Module, created: bool, **kwargs):
    if not created:
        return

    from courses.models import InscriptionCours
    apprenants = InscriptionCours.objects.filter(
        cours=instance.cours
    ).select_related('apprenant')

    for insc in apprenants:
        _notifier(
            recipient=insc.apprenant,
            type_notif=TypeNotification.MODULE_AJOUTE,
            titre="Nouveau module disponible",
            message=f"Le module « {instance.titre} » a été ajouté dans « {instance.cours.titre or instance.cours.matiere.nom} ».",
            priorite=PrioriteNotification.BASSE,
            sender=instance.cours.enseignant,
            entity_type=EntityType.MODULE,
            entity_id=instance.pk,
            action_url=f"/cours/{instance.cours.pk}/modules/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
            groupe_dedup=f"module_ajoute:{instance.pk}",
        )


# ============================================================================
# ÉVALUATION
# ============================================================================

@receiver(post_save, sender=Evaluation)
def on_evaluation_saved(sender, instance: Evaluation, created: bool, **kwargs):
    if not instance.est_publiee:
        return

    deja_notifie = Notification.objects.filter(
        groupe_deduplication=f"evaluation_publiee:{instance.pk}",
        type=TypeNotification.EVALUATION_PUBLIEE,
    ).exists()
    if deja_notifie:
        return

    from courses.models import InscriptionCours
    inscriptions = InscriptionCours.objects.filter(
        cours=instance.cours
    ).select_related('apprenant', 'apprenant__tuteur')

    for insc in inscriptions:
        apprenant = insc.apprenant

        _notifier(
            recipient=apprenant,
            type_notif=TypeNotification.EVALUATION_PUBLIEE,
            titre="Nouvelle évaluation publiée",
            message=f"L'évaluation « {instance.titre} » est disponible dans « {instance.cours.titre or instance.cours.matiere.nom} ».",
            priorite=PrioriteNotification.MOYENNE,
            sender=instance.enseignant,
            entity_type=EntityType.EVALUATION,
            entity_id=instance.pk,
            action_url=f"/evaluations/{instance.pk}",
            institution=instance.cours.institution,
            annee_scolaire=instance.cours.annee_scolaire,
            groupe_dedup=f"evaluation_publiee:{instance.pk}",
        )

        if apprenant.tuteur:
            _notifier(
                recipient=apprenant.tuteur,
                type_notif=TypeNotification.EVALUATION_PUBLIEE,
                titre="Nouvelle évaluation pour votre enfant",
                message=f"Une évaluation « {instance.titre} » a été publiée pour {apprenant.prenom} {apprenant.nom}.",
                priorite=PrioriteNotification.MOYENNE,
                sender=instance.enseignant,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.pk,
                action_url=f"/evaluations/{instance.pk}",
                institution=instance.cours.institution,
                annee_scolaire=instance.cours.annee_scolaire,
            )

    # Confirmation au formateur
    _notifier(
        recipient=instance.enseignant,
        type_notif=TypeNotification.EVALUATION_PUBLIEE,
        titre="Évaluation publiée avec succès",
        message=f"Votre évaluation « {instance.titre} » a bien été publiée.",
        priorite=PrioriteNotification.BASSE,
        entity_type=EntityType.EVALUATION,
        entity_id=instance.pk,
        action_url=f"/evaluations/{instance.pk}",
    )


# ============================================================================
# PASSAGE ÉVALUATION
# ============================================================================

@receiver(post_save, sender=PassageEvaluation)
def on_passage_evaluation_saved(sender, instance: PassageEvaluation, created: bool, **kwargs):

    if instance.statut == 'soumis':
        formateur = instance.evaluation.enseignant
        groupe = f"evaluation_soumise:{instance.evaluation.pk}"

        existing = Notification.objects.filter(
            groupe_deduplication=groupe,
            is_read=False,
            recipient=formateur,
        ).first()

        if existing:
            existing.nb_evenements_groupes += 1
            existing.message = f"{existing.nb_evenements_groupes} copies soumises pour « {instance.evaluation.titre} »."
            existing.save(update_fields=['nb_evenements_groupes', 'message'])
        else:
            _notifier(
                recipient=formateur,
                type_notif=TypeNotification.EVALUATION_SOUMISE,
                titre="Copie soumise",
                message=f"{instance.apprenant.prenom} {instance.apprenant.nom} a soumis « {instance.evaluation.titre} ».",
                priorite=PrioriteNotification.MOYENNE,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.evaluation.pk,
                action_url=f"/evaluations/{instance.evaluation.pk}/corrections",
                institution=instance.evaluation.cours.institution,
                groupe_dedup=groupe,
            )

    if instance.statut == 'corrige' and instance.note is not None:
        _notifier(
            recipient=instance.apprenant,
            type_notif=TypeNotification.EVALUATION_CORRIGEE,
            titre="Résultat disponible",
            message=f"Votre évaluation « {instance.evaluation.titre} » a été corrigée. Note : {instance.note}/{instance.evaluation.bareme}.",
            priorite=PrioriteNotification.HAUTE,
            entity_type=EntityType.EVALUATION,
            entity_id=instance.evaluation.pk,
            action_url=f"/evaluations/{instance.evaluation.pk}/resultat",
            institution=instance.evaluation.cours.institution,
            annee_scolaire=instance.evaluation.cours.annee_scolaire,
        )

        if instance.apprenant.tuteur:
            _notifier(
                recipient=instance.apprenant.tuteur,
                type_notif=TypeNotification.EVALUATION_CORRIGEE,
                titre="Résultat disponible pour votre enfant",
                message=f"{instance.apprenant.prenom} a obtenu {instance.note}/{instance.evaluation.bareme} à « {instance.evaluation.titre} ».",
                priorite=PrioriteNotification.HAUTE,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.evaluation.pk,
            )


# ============================================================================
# SESSION
# ============================================================================

@receiver(post_save, sender=Session)
def on_session_saved(sender, instance: Session, created: bool, **kwargs):
    if not created:
        return

    from courses.models import InscriptionCours
    inscriptions = InscriptionCours.objects.filter(
        cours=instance.cours
    ).select_related('apprenant', 'apprenant__tuteur')

    date_str = instance.date_debut.strftime('%d/%m/%Y à %Hh%M')

    for insc in inscriptions:
        apprenant = insc.apprenant

        _notifier(
            recipient=apprenant,
            type_notif=TypeNotification.SESSION_A_VENIR,
            titre="Nouvelle session planifiée",
            message=f"Une session « {instance.titre} » est prévue le {date_str}.",
            priorite=PrioriteNotification.MOYENNE,
            sender=instance.formateur,
            entity_type=EntityType.SESSION,
            entity_id=instance.pk,
            action_url=f"/sessions/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
            groupe_dedup=f"session_a_venir:{instance.pk}",
        )

        if apprenant.tuteur:
            _notifier(
                recipient=apprenant.tuteur,
                type_notif=TypeNotification.SESSION_A_VENIR,
                titre="Session planifiée pour votre enfant",
                message=f"Session prévue le {date_str} pour {apprenant.prenom}.",
                priorite=PrioriteNotification.BASSE,
                entity_type=EntityType.SESSION,
                entity_id=instance.pk,
            )


# ============================================================================
# PARTICIPATION
# ============================================================================

@receiver(post_save, sender=Participation)
def on_participation_saved(sender, instance: Participation, created: bool, **kwargs):
    if not created:
        return
    if instance.statut not in ('absent', 'retard'):
        return

    type_notif = (
        TypeNotification.ABSENCE_ENREGISTREE
        if instance.statut == 'absent'
        else TypeNotification.RETARD_ENREGISTRE
    )
    est_absent = instance.statut == 'absent'
    titre      = "Absence enregistrée" if est_absent else "Retard enregistré"
    mot        = "absent" if est_absent else "en retard"

    _notifier(
        recipient=instance.apprenant,
        type_notif=type_notif,
        titre=titre,
        message=f"Vous avez été marqué {mot} à la session « {instance.session.titre} ».",
        priorite=PrioriteNotification.HAUTE,
        entity_type=EntityType.SESSION,
        entity_id=instance.session.pk,
        action_url=f"/sessions/{instance.session.pk}",
        institution=instance.institution,
        annee_scolaire=instance.annee_scolaire,
    )

    if instance.apprenant.tuteur:
        _notifier(
            recipient=instance.apprenant.tuteur,
            type_notif=type_notif,
            titre=f"{titre} — {instance.apprenant.prenom} {instance.apprenant.nom}",
            message=f"Votre enfant {instance.apprenant.prenom} a été marqué {mot} à la session du {instance.session.date_debut.strftime('%d/%m/%Y')}.",
            priorite=PrioriteNotification.HAUTE,
            entity_type=EntityType.SESSION,
            entity_id=instance.session.pk,
        )


# ============================================================================
# INSCRIPTION
# ============================================================================

@receiver(post_save, sender=Inscription)
def on_inscription_saved(sender, instance: Inscription, created: bool, **kwargs):
    if not created:
        return

    _notifier(
        recipient=instance.apprenant,
        type_notif=TypeNotification.INSCRIPTION_COURS,
        titre="Inscription confirmée",
        message=f"Votre inscription en {instance.classe.nom if instance.classe else 'formation'} pour l'année {instance.annee_scolaire} a été confirmée.",
        priorite=PrioriteNotification.MOYENNE,
        entity_type=EntityType.INSCRIPTION,
        entity_id=instance.pk,
        action_url="/mon-espace",
        institution=instance.institution,
        annee_scolaire=instance.annee_scolaire,
    )