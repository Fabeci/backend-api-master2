# notifications/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from courses.models import Cours, Module, Session, Participation
from evaluations.models import Evaluation, PassageEvaluation
from academics.models import (
    Inscription, Classe, Groupe,
    Matiere, Specialite, AnneeScolaire,
)
from users.models import User, Apprenant
from progress.models import ProgressionApprenant

from .models import (
    Notification,
    TypeNotification,
    PrioriteNotification,
    CanalNotification,
    EntityType,
)


# ============================================================================
# UTILITAIRES
# ============================================================================

def _notifier(recipient, type_notif, titre, message,
              priorite=PrioriteNotification.MOYENNE,
              sender=None, entity_type=None, entity_id=None,
              action_url=None, institution=None, annee_scolaire=None,
              groupe_dedup=None, **metadata):
    """Crée une notification in-app. Silencieux en cas d'erreur."""
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


def _get_admins(institution):
    """Admins d'une institution (queryset mis en cache par appelant)."""
    if not institution:
        return User.objects.none()
    return User.objects.filter(
        admin__isnull=False,
        institution=institution,
    ).select_related()


def _get_responsables(institution):
    """Responsables académiques d'une institution."""
    if not institution:
        return User.objects.none()
    return User.objects.filter(
        responsableacademique__isnull=False,
        institution=institution,
    ).select_related()


def _compter_absences(apprenant, cours):
    """Nombre d'absences d'un apprenant dans un cours."""
    return Participation.objects.filter(
        apprenant=apprenant,
        session__cours=cours,
        statut='absent',
    ).count()


def _notifier_admins_et_responsables(institution, type_notif, titre,
                                      message, priorite, entity_type=None,
                                      entity_id=None, action_url=None,
                                      annee_scolaire=None, groupe_dedup=None):
    """Helper : notifie tous les admins ET responsables d'une institution."""
    destinataires = list(_get_admins(institution)) + list(_get_responsables(institution))
    for dest in destinataires:
        _notifier(
            recipient=dest,
            type_notif=type_notif,
            titre=titre,
            message=message,
            priorite=priorite,
            entity_type=entity_type,
            entity_id=entity_id,
            action_url=action_url,
            institution=institution,
            annee_scolaire=annee_scolaire,
            groupe_dedup=f"{groupe_dedup}:{dest.pk}" if groupe_dedup else None,
        )


# ============================================================================
# COMPTE UTILISATEUR
# ============================================================================

@receiver(post_save, sender=User)
def on_user_created(sender, instance: User, created: bool, **kwargs):
    """
    Nouveau compte créé → Admin notifié.
    NB : le signal d'activation de compte est géré séparément
         dans votre vue d'activation (code OTP).
    """
    if not created:
        return
    if not instance.institution:
        return

    for admin in _get_admins(instance.institution):
        _notifier(
            recipient=admin,
            type_notif=TypeNotification.CREATION_RESSOURCE,
            titre="Nouveau compte créé",
            message=f"Nouveau compte : {instance.prenom} {instance.nom} ({instance.email}).",
            priorite=PrioriteNotification.BASSE,
            entity_type=EntityType.USER,
            entity_id=instance.pk,
            action_url=f"/users/{instance.pk}",
            institution=instance.institution,
            groupe_dedup=f"new_user:{instance.institution_id}",
        )


@receiver(post_save, sender=Apprenant)
def on_apprenant_active(sender, instance: Apprenant, created: bool, **kwargs):
    """
    Apprenant activé (is_active passe à True) → notifier l'apprenant
    et son parent que le compte est prêt.
    """
    if created:
        return
    # Détecter le passage à is_active=True
    # On utilise update_fields si disponible
    update_fields = kwargs.get('update_fields')
    if update_fields and 'is_active' not in update_fields:
        return
    if not instance.is_active:
        return

    # Anti-doublon : ne notifier qu'une seule fois
    deja = Notification.objects.filter(
        recipient=instance,
        type=TypeNotification.ACTIVATION_COMPTE,
    ).exists()
    if deja:
        return

    # Notifier l'apprenant
    _notifier(
        recipient=instance,
        type_notif=TypeNotification.ACTIVATION_COMPTE,
        titre="Bienvenue sur SomaPro !",
        message="Votre compte a été activé. Vous pouvez maintenant accéder à tous vos cours.",
        priorite=PrioriteNotification.MOYENNE,
        action_url="/dashboard",
    )

    # Notifier le parent
    if instance.tuteur:
        _notifier(
            recipient=instance.tuteur,
            type_notif=TypeNotification.ACTIVATION_COMPTE,
            titre="Compte activé pour votre enfant",
            message=f"Le compte de {instance.prenom} {instance.nom} a été activé sur SomaPro.",
            priorite=PrioriteNotification.MOYENNE,
            action_url="/dashboard",
        )


# ============================================================================
# ANNÉE SCOLAIRE
# ============================================================================

@receiver(post_save, sender=AnneeScolaire)
def on_annee_scolaire_saved(sender, instance: AnneeScolaire, created: bool, **kwargs):
    """
    Nouvelle année scolaire créée ou activée
    → Admin + Responsable notifiés.
    """
    if not instance.institution:
        return

    if created:
        titre   = "Nouvelle année scolaire créée"
        message = f"L'année scolaire {instance.annee_format_classique or instance} a été créée."
    elif instance.est_active:
        titre   = "Année scolaire activée"
        message = f"L'année scolaire {instance.annee_format_classique or instance} est maintenant active."
    else:
        return

    _notifier_admins_et_responsables(
        institution=instance.institution,
        type_notif=TypeNotification.ANNONCE_ADMINISTRATIVE,
        titre=titre,
        message=message,
        priorite=PrioriteNotification.MOYENNE,
        action_url=f"/annees-scolaires/{instance.pk}",
        groupe_dedup=f"annee_scolaire:{instance.pk}",
    )


# ============================================================================
# RESSOURCES ACADÉMIQUES — Classe, Groupe, Matière, Spécialité
# ============================================================================

@receiver(post_save, sender=Classe)
def on_classe_saved(sender, instance: Classe, created: bool, **kwargs):
    if not created or not instance.institution:
        return

    for resp in _get_responsables(instance.institution):
        _notifier(
            recipient=resp,
            type_notif=TypeNotification.CREATION_RESSOURCE,
            titre="Nouvelle classe créée",
            message=f"La classe « {instance.nom} » a été créée pour l'année {instance.annee_scolaire}.",
            priorite=PrioriteNotification.BASSE,
            entity_type=EntityType.CLASSE,
            entity_id=instance.pk,
            action_url=f"/classes/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
        )


@receiver(post_save, sender=Groupe)
def on_groupe_saved(sender, instance: Groupe, created: bool, **kwargs):
    if not created or not instance.institution:
        return

    for resp in _get_responsables(instance.institution):
        _notifier(
            recipient=resp,
            type_notif=TypeNotification.CREATION_RESSOURCE,
            titre="Nouveau groupe créé",
            message=f"Le groupe « {instance.nom} » a été créé.",
            priorite=PrioriteNotification.BASSE,
            entity_type=EntityType.GROUPE,
            entity_id=instance.pk,
            action_url=f"/groupes/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
        )


@receiver(post_save, sender=Matiere)
def on_matiere_saved(sender, instance: Matiere, created: bool, **kwargs):
    if not created or not instance.institution:
        return

    _notifier_admins_et_responsables(
        institution=instance.institution,
        type_notif=TypeNotification.CREATION_RESSOURCE,
        titre="Nouvelle matière créée",
        message=f"La matière « {instance.nom} » a été ajoutée.",
        priorite=PrioriteNotification.BASSE,
        action_url=f"/matieres/{instance.pk}",
        groupe_dedup=f"matiere_created:{instance.pk}",
    )


@receiver(post_save, sender=Specialite)
def on_specialite_saved(sender, instance: Specialite, created: bool, **kwargs):
    if not created or not instance.institution:
        return

    _notifier_admins_et_responsables(
        institution=instance.institution,
        type_notif=TypeNotification.CREATION_RESSOURCE,
        titre="Nouvelle spécialité créée",
        message=f"La spécialité « {instance.nom} » a été ajoutée.",
        priorite=PrioriteNotification.BASSE,
        action_url=f"/specialites/{instance.pk}",
        groupe_dedup=f"specialite_created:{instance.pk}",
    )


# ============================================================================
# COURS
# ============================================================================

@receiver(post_save, sender=Cours)
def on_cours_saved(sender, instance: Cours, created: bool, **kwargs):
    if not created:
        return

    # Formateur — assignation
    _notifier(
        recipient=instance.enseignant,
        type_notif=TypeNotification.ASSIGNATION_COURS,
        titre="Nouveau cours assigné",
        message=f"Vous avez été assigné au cours « {instance.titre or instance.matiere.nom} » pour le groupe {instance.groupe.nom}.",
        priorite=PrioriteNotification.MOYENNE,
        entity_type=EntityType.COURS,
        entity_id=instance.pk,
        action_url=f"/cours/{instance.pk}",
        institution=instance.institution,
        annee_scolaire=instance.annee_scolaire,
    )

    # Responsables + Admins
    _notifier_admins_et_responsables(
        institution=instance.institution,
        type_notif=TypeNotification.COURS_CREE,
        titre="Nouveau cours créé",
        message=f"Cours « {instance.titre or instance.matiere.nom} » créé par {instance.enseignant.prenom} {instance.enseignant.nom} pour le groupe {instance.groupe.nom}.",
        priorite=PrioriteNotification.BASSE,
        entity_type=EntityType.COURS,
        entity_id=instance.pk,
        action_url=f"/cours/{instance.pk}",
        annee_scolaire=instance.annee_scolaire,
        groupe_dedup=f"cours_created:{instance.pk}",
    )


# ============================================================================
# MODULE
# ============================================================================

@receiver(post_save, sender=Module)
def on_module_saved(sender, instance: Module, created: bool, **kwargs):
    if not created:
        return

    from courses.models import InscriptionCours
    inscriptions = InscriptionCours.objects.filter(
        cours=instance.cours
    ).select_related('apprenant', 'apprenant__tuteur')

    for insc in inscriptions:
        apprenant = insc.apprenant

        # Apprenant
        _notifier(
            recipient=apprenant,
            type_notif=TypeNotification.MODULE_AJOUTE,
            titre="Nouveau module disponible",
            message=f"Le module « {instance.titre} » est disponible dans « {instance.cours.titre or instance.cours.matiere.nom} ».",
            priorite=PrioriteNotification.BASSE,
            sender=instance.cours.enseignant,
            entity_type=EntityType.MODULE,
            entity_id=instance.pk,
            action_url=f"/cours/{instance.cours.pk}/modules/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
            groupe_dedup=f"module_ajoute:{instance.pk}",
        )

        # Parent (optionnel)
        if apprenant.tuteur:
            _notifier(
                recipient=apprenant.tuteur,
                type_notif=TypeNotification.MODULE_AJOUTE,
                titre="Nouveau contenu pour votre enfant",
                message=f"Module « {instance.titre} » disponible pour {apprenant.prenom} dans « {instance.cours.titre or instance.cours.matiere.nom} ».",
                priorite=PrioriteNotification.BASSE,
                entity_type=EntityType.MODULE,
                entity_id=instance.pk,
            )

    # Confirmation formateur
    _notifier(
        recipient=instance.cours.enseignant,
        type_notif=TypeNotification.CONTENU_PUBLIE,
        titre="Module ajouté avec succès",
        message=f"Le module « {instance.titre} » a bien été ajouté.",
        priorite=PrioriteNotification.BASSE,
        entity_type=EntityType.MODULE,
        entity_id=instance.pk,
        action_url=f"/cours/{instance.cours.pk}/modules/{instance.pk}",
    )


# ============================================================================
# ÉVALUATION
# ============================================================================

@receiver(post_save, sender=Evaluation)
def on_evaluation_saved(sender, instance: Evaluation, created: bool, **kwargs):
    if not instance.est_publiee:
        return

    # Anti-doublon
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

        # Apprenant
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

        # Parent
        if apprenant.tuteur:
            _notifier(
                recipient=apprenant.tuteur,
                type_notif=TypeNotification.EVALUATION_PUBLIEE,
                titre="Nouvelle évaluation pour votre enfant",
                message=f"Évaluation « {instance.titre} » publiée pour {apprenant.prenom} {apprenant.nom}.",
                priorite=PrioriteNotification.MOYENNE,
                sender=instance.enseignant,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.pk,
                action_url=f"/evaluations/{instance.pk}",
                institution=instance.cours.institution,
                annee_scolaire=instance.cours.annee_scolaire,
            )

    # Confirmation formateur
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

    # Supervision responsables
    for resp in _get_responsables(instance.cours.institution):
        _notifier(
            recipient=resp,
            type_notif=TypeNotification.EVALUATION_PUBLIEE,
            titre="Nouvelle évaluation publiée",
            message=f"Évaluation « {instance.titre} » publiée par {instance.enseignant.prenom} {instance.enseignant.nom}.",
            priorite=PrioriteNotification.BASSE,
            sender=instance.enseignant,
            entity_type=EntityType.EVALUATION,
            entity_id=instance.pk,
            action_url=f"/evaluations/{instance.pk}",
            institution=instance.cours.institution,
            groupe_dedup=f"eval_publiee_resp:{instance.pk}",
        )


# ============================================================================
# PASSAGE ÉVALUATION
# ============================================================================

@receiver(post_save, sender=PassageEvaluation)
def on_passage_evaluation_saved(sender, instance: PassageEvaluation, created: bool, **kwargs):

    # ── Soumission ────────────────────────────────────────────────────────────
    if instance.statut == 'soumis':
        formateur = instance.evaluation.enseignant
        groupe    = f"evaluation_soumise:{instance.evaluation.pk}"

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

        # Copies à corriger (groupé)
        _notifier(
            recipient=formateur,
            type_notif=TypeNotification.COPIES_A_CORRIGER,
            titre="Copies à corriger",
            message=f"Des copies attendent votre correction pour « {instance.evaluation.titre} ».",
            priorite=PrioriteNotification.MOYENNE,
            entity_type=EntityType.EVALUATION,
            entity_id=instance.evaluation.pk,
            action_url=f"/evaluations/{instance.evaluation.pk}/corrections",
            groupe_dedup=f"copies_a_corriger:{instance.evaluation.pk}",
        )

    # ── Résultat disponible ───────────────────────────────────────────────────
    if instance.statut == 'corrige' and instance.note is not None:

        # Apprenant
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

        # Parent
        if instance.apprenant.tuteur:
            _notifier(
                recipient=instance.apprenant.tuteur,
                type_notif=TypeNotification.EVALUATION_CORRIGEE,
                titre="Résultat disponible pour votre enfant",
                message=f"{instance.apprenant.prenom} a obtenu {instance.note}/{instance.evaluation.bareme} à « {instance.evaluation.titre} ».",
                priorite=PrioriteNotification.HAUTE,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.evaluation.pk,
                action_url=f"/evaluations/{instance.evaluation.pk}/resultat",
            )

        # Alerte progression faible < 50%
        pourcentage = (float(instance.note) / float(instance.evaluation.bareme)) * 100
        if pourcentage < 50:

            _notifier(
                recipient=instance.apprenant,
                type_notif=TypeNotification.PROGRESSION_FAIBLE,
                titre="Résultat en dessous de la moyenne",
                message=f"Vous avez obtenu {pourcentage:.0f}% à « {instance.evaluation.titre} ». N'hésitez pas à revoir le cours.",
                priorite=PrioriteNotification.MOYENNE,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.evaluation.pk,
                action_url=f"/evaluations/{instance.evaluation.pk}/resultat",
            )

            # Parent alerté si progression faible
            if instance.apprenant.tuteur:
                _notifier(
                    recipient=instance.apprenant.tuteur,
                    type_notif=TypeNotification.PROGRESSION_FAIBLE,
                    titre="Risque académique — votre enfant",
                    message=f"{instance.apprenant.prenom} a obtenu {pourcentage:.0f}% à « {instance.evaluation.titre} ».",
                    priorite=PrioriteNotification.MOYENNE,
                    entity_type=EntityType.EVALUATION,
                    entity_id=instance.evaluation.pk,
                )

            # Responsable alerté
            for resp in _get_responsables(instance.evaluation.cours.institution):
                _notifier(
                    recipient=resp,
                    type_notif=TypeNotification.PROGRESSION_FAIBLE,
                    titre="Performance faible détectée",
                    message=f"{instance.apprenant.prenom} {instance.apprenant.nom} : {pourcentage:.0f}% à « {instance.evaluation.titre} ».",
                    priorite=PrioriteNotification.BASSE,
                    entity_type=EntityType.EVALUATION,
                    entity_id=instance.evaluation.pk,
                    institution=instance.evaluation.cours.institution,
                    groupe_dedup=f"perf_faible_resp:{instance.evaluation.pk}:{instance.apprenant.pk}",
                )

        # Encouragement si >= 80%
        elif pourcentage >= 80:
            _notifier(
                recipient=instance.apprenant,
                type_notif=TypeNotification.ENCOURAGEMENT,
                titre="Excellent résultat ! 🎉",
                message=f"Félicitations ! Vous avez obtenu {pourcentage:.0f}% à « {instance.evaluation.titre} ».",
                priorite=PrioriteNotification.BASSE,
                entity_type=EntityType.EVALUATION,
                entity_id=instance.evaluation.pk,
                action_url=f"/evaluations/{instance.evaluation.pk}/resultat",
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

        # Apprenant
        _notifier(
            recipient=apprenant,
            type_notif=TypeNotification.SESSION_A_VENIR,
            titre="Nouvelle session planifiée",
            message=f"Session « {instance.titre} » prévue le {date_str}.",
            priorite=PrioriteNotification.MOYENNE,
            sender=instance.formateur,
            entity_type=EntityType.SESSION,
            entity_id=instance.pk,
            action_url=f"/sessions/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
            groupe_dedup=f"session_a_venir:{instance.pk}",
        )

        # Parent
        if apprenant.tuteur:
            _notifier(
                recipient=apprenant.tuteur,
                type_notif=TypeNotification.SESSION_A_VENIR,
                titre="Session planifiée pour votre enfant",
                message=f"Session « {instance.titre} » prévue le {date_str} pour {apprenant.prenom}.",
                priorite=PrioriteNotification.BASSE,
                entity_type=EntityType.SESSION,
                entity_id=instance.pk,
                action_url=f"/sessions/{instance.pk}",
            )

    # Confirmation formateur
    _notifier(
        recipient=instance.formateur,
        type_notif=TypeNotification.SESSION_A_VENIR,
        titre="Session créée avec succès",
        message=f"Session « {instance.titre} » du {date_str} créée.",
        priorite=PrioriteNotification.BASSE,
        entity_type=EntityType.SESSION,
        entity_id=instance.pk,
        action_url=f"/sessions/{instance.pk}",
    )

    # Responsables
    for resp in _get_responsables(instance.institution):
        _notifier(
            recipient=resp,
            type_notif=TypeNotification.SESSION_A_VENIR,
            titre="Nouvelle session planifiée",
            message=f"Session « {instance.titre} » le {date_str} par {instance.formateur.prenom} {instance.formateur.nom}.",
            priorite=PrioriteNotification.BASSE,
            sender=instance.formateur,
            entity_type=EntityType.SESSION,
            entity_id=instance.pk,
            institution=instance.institution,
            groupe_dedup=f"session_resp:{instance.pk}",
        )


# ============================================================================
# PARTICIPATION — Absence / Retard
# ============================================================================

@receiver(post_save, sender=Participation)
def on_participation_saved(sender, instance: Participation, created: bool, **kwargs):
    if not created:
        return
    if instance.statut not in ('absent', 'retard'):
        return

    est_absent = instance.statut == 'absent'
    type_notif = TypeNotification.ABSENCE_ENREGISTREE if est_absent else TypeNotification.RETARD_ENREGISTRE
    titre      = "Absence enregistrée" if est_absent else "Retard enregistré"
    mot        = "absent" if est_absent else "en retard"
    date_str   = instance.session.date_debut.strftime('%d/%m/%Y')

    # Apprenant
    _notifier(
        recipient=instance.apprenant,
        type_notif=type_notif,
        titre=titre,
        message=f"Vous avez été marqué {mot} à la session « {instance.session.titre} » du {date_str}.",
        priorite=PrioriteNotification.HAUTE,
        entity_type=EntityType.SESSION,
        entity_id=instance.session.pk,
        action_url=f"/sessions/{instance.session.pk}",
        institution=instance.institution,
        annee_scolaire=instance.annee_scolaire,
    )

    # Parent
    if instance.apprenant.tuteur:
        _notifier(
            recipient=instance.apprenant.tuteur,
            type_notif=type_notif,
            titre=f"{titre} — {instance.apprenant.prenom} {instance.apprenant.nom}",
            message=f"Votre enfant {instance.apprenant.prenom} a été marqué {mot} à la session du {date_str}.",
            priorite=PrioriteNotification.HAUTE,
            entity_type=EntityType.SESSION,
            entity_id=instance.session.pk,
            action_url=f"/sessions/{instance.session.pk}",
        )

    # Confirmation formateur (groupée)
    _notifier(
        recipient=instance.session.formateur,
        type_notif=type_notif,
        titre=f"Présence enregistrée",
        message=f"{instance.apprenant.prenom} {instance.apprenant.nom} marqué {mot} à « {instance.session.titre} ».",
        priorite=PrioriteNotification.BASSE,
        entity_type=EntityType.SESSION,
        entity_id=instance.session.pk,
        groupe_dedup=f"formateur_presence:{instance.session.pk}",
    )

    # Absences répétées (seuil 3) → Responsable + Admin
    if est_absent:
        nb_absences = _compter_absences(instance.apprenant, instance.session.cours)

        if nb_absences >= 3:
            cours = instance.session.cours
            nom_cours = cours.titre or cours.matiere.nom

            for resp in _get_responsables(instance.institution):
                _notifier(
                    recipient=resp,
                    type_notif=TypeNotification.ABSENCES_REPETEES,
                    titre="Absences répétées détectées",
                    message=f"{instance.apprenant.prenom} {instance.apprenant.nom} cumule {nb_absences} absences dans « {nom_cours} ».",
                    priorite=PrioriteNotification.HAUTE,
                    entity_type=EntityType.SESSION,
                    entity_id=instance.session.pk,
                    institution=instance.institution,
                    groupe_dedup=f"abs_rep_resp:{instance.apprenant.pk}:{cours.pk}",
                )

            for admin in _get_admins(instance.institution):
                _notifier(
                    recipient=admin,
                    type_notif=TypeNotification.ABSENCES_REPETEES,
                    titre="Absences répétées — Signalement",
                    message=f"{instance.apprenant.prenom} {instance.apprenant.nom} : {nb_absences} absences dans « {nom_cours} ».",
                    priorite=PrioriteNotification.HAUTE,
                    entity_type=EntityType.SESSION,
                    entity_id=instance.session.pk,
                    institution=instance.institution,
                    groupe_dedup=f"abs_rep_admin:{instance.apprenant.pk}:{cours.pk}",
                )


# ============================================================================
# PROGRESSION APPRENANT — Alerte faible / anormale / cours terminé
# ============================================================================

@receiver(post_save, sender=ProgressionApprenant)
def on_progression_saved(sender, instance: ProgressionApprenant, created: bool, **kwargs):

    # Cours terminé → encouragement
    if instance.statut == 'termine' and instance.pourcentage_completion >= 100:
        deja = Notification.objects.filter(
            recipient=instance.apprenant,
            type=TypeNotification.COURS_TERMINE,
            entity_id=instance.cours.pk,
            entity_type=EntityType.COURS,
        ).exists()
        if not deja:
            _notifier(
                recipient=instance.apprenant,
                type_notif=TypeNotification.COURS_TERMINE,
                titre="Cours terminé ! 🎓",
                message=f"Félicitations, vous avez terminé le cours « {instance.cours.titre or instance.cours.matiere.nom} » !",
                priorite=PrioriteNotification.MOYENNE,
                entity_type=EntityType.COURS,
                entity_id=instance.cours.pk,
                action_url=f"/cours/{instance.cours.pk}",
            )

    # Progression anormale → Responsable alerté
    if instance.pourcentage_completion > 0 and instance.pourcentage_completion < 10:
        update_fields = kwargs.get('update_fields')
        if update_fields and 'pourcentage_completion' in update_fields:
            for resp in _get_responsables(instance.cours.institution):
                _notifier(
                    recipient=resp,
                    type_notif=TypeNotification.PROGRESSION_ANORMALE,
                    titre="Progression anormale détectée",
                    message=f"{instance.apprenant.prenom} {instance.apprenant.nom} est à seulement {instance.pourcentage_completion:.0f}% dans « {instance.cours.titre or instance.cours.matiere.nom} ».",
                    priorite=PrioriteNotification.MOYENNE,
                    entity_type=EntityType.COURS,
                    entity_id=instance.cours.pk,
                    institution=instance.cours.institution,
                    groupe_dedup=f"prog_anormale:{instance.apprenant.pk}:{instance.cours.pk}",
                )


# ============================================================================
# INSCRIPTION — Apprenant + Parent + Admin + Formateurs concernés
# ============================================================================

@receiver(post_save, sender=Inscription)
def on_inscription_saved(sender, instance: Inscription, created: bool, **kwargs):
    if not created:
        return

    nom_classe = instance.classe.nom if instance.classe else "formation"

    # Apprenant
    _notifier(
        recipient=instance.apprenant,
        type_notif=TypeNotification.INSCRIPTION_COURS,
        titre="Inscription confirmée",
        message=f"Votre inscription en {nom_classe} pour l'année {instance.annee_scolaire} est confirmée.",
        priorite=PrioriteNotification.MOYENNE,
        entity_type=EntityType.INSCRIPTION,
        entity_id=instance.pk,
        action_url="/mon-espace",
        institution=instance.institution,
        annee_scolaire=instance.annee_scolaire,
    )

    # Parent
    if instance.apprenant.tuteur:
        _notifier(
            recipient=instance.apprenant.tuteur,
            type_notif=TypeNotification.INSCRIPTION_COURS,
            titre="Inscription de votre enfant confirmée",
            message=f"{instance.apprenant.prenom} a été inscrit(e) en {nom_classe} pour {instance.annee_scolaire}.",
            priorite=PrioriteNotification.MOYENNE,
            entity_type=EntityType.INSCRIPTION,
            entity_id=instance.pk,
            action_url="/mon-espace",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
        )

    # Admins (groupé par année)
    for admin in _get_admins(instance.institution):
        _notifier(
            recipient=admin,
            type_notif=TypeNotification.INSCRIPTION_COURS,
            titre="Nouvelle inscription",
            message=f"{instance.apprenant.prenom} {instance.apprenant.nom} inscrit(e) en {nom_classe}.",
            priorite=PrioriteNotification.BASSE,
            entity_type=EntityType.INSCRIPTION,
            entity_id=instance.pk,
            action_url=f"/inscriptions/{instance.pk}",
            institution=instance.institution,
            annee_scolaire=instance.annee_scolaire,
            groupe_dedup=f"inscription_admin:{instance.institution_id}:{instance.annee_scolaire_id}",
        )

    # Formateurs des cours du groupe de l'apprenant
    if instance.apprenant.groupe and instance.annee_scolaire:
        from courses.models import Cours as CoursModel
        cours_du_groupe = CoursModel.objects.filter(
            groupe=instance.apprenant.groupe,
            annee_scolaire=instance.annee_scolaire,
        ).select_related('enseignant')

        for cours in cours_du_groupe:
            _notifier(
                recipient=cours.enseignant,
                type_notif=TypeNotification.INSCRIPTION_COURS,
                titre="Nouvelle inscription dans votre cours",
                message=f"{instance.apprenant.prenom} {instance.apprenant.nom} a rejoint « {cours.titre or cours.matiere.nom} ».",
                priorite=PrioriteNotification.BASSE,
                entity_type=EntityType.COURS,
                entity_id=cours.pk,
                action_url=f"/cours/{cours.pk}",
                institution=instance.institution,
                groupe_dedup=f"inscription_formateur:{cours.pk}:{instance.annee_scolaire_id}",
            )
            
# ============================================================================
# SESSION ANNULÉE / DÉPLACÉE — détection de modification post-création
# ============================================================================

@receiver(post_save, sender=Session)
def on_session_modifiee(sender, instance: Session, created: bool, **kwargs):
    """
    Détecte une annulation ou un déplacement de session après sa création.
    On surveille update_fields pour ne pas re-déclencher à chaque save.
    """
    if created:
        return

    update_fields = kwargs.get('update_fields') or []

    # Annulation
    if hasattr(instance, 'statut') and instance.statut == 'annulee':
        groupe = f"session_annulee:{instance.pk}"
        deja = Notification.objects.filter(groupe_deduplication=groupe).exists()
        if deja:
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
                type_notif=TypeNotification.SESSION_ANNULEE,
                titre="Session annulée",
                message=f"La session « {instance.titre} » prévue le {date_str} a été annulée.",
                priorite=PrioriteNotification.HAUTE,
                sender=instance.formateur,
                entity_type=EntityType.SESSION,
                entity_id=instance.pk,
                action_url=f"/sessions/{instance.pk}",
                institution=instance.institution,
                groupe_dedup=groupe,
            )

            if apprenant.tuteur:
                _notifier(
                    recipient=apprenant.tuteur,
                    type_notif=TypeNotification.SESSION_ANNULEE,
                    titre=f"Session annulée — {apprenant.prenom}",
                    message=f"La session « {instance.titre} » du {date_str} a été annulée pour {apprenant.prenom}.",
                    priorite=PrioriteNotification.HAUTE,
                    entity_type=EntityType.SESSION,
                    entity_id=instance.pk,
                )

        # Notifier les responsables
        for resp in _get_responsables(instance.institution):
            _notifier(
                recipient=resp,
                type_notif=TypeNotification.SESSION_ANNULEE,
                titre="Session annulée",
                message=f"La session « {instance.titre} » du {date_str} a été annulée par {instance.formateur.prenom} {instance.formateur.nom}.",
                priorite=PrioriteNotification.HAUTE,
                sender=instance.formateur,
                entity_type=EntityType.SESSION,
                entity_id=instance.pk,
                institution=instance.institution,
                groupe_dedup=f"session_annulee_resp:{instance.pk}",
            )

    # Déplacement (date_debut a changé)
    if 'date_debut' in update_fields or 'date_fin' in update_fields:
        groupe = f"session_deplacee:{instance.pk}"
        deja = Notification.objects.filter(groupe_deduplication=groupe).exists()
        if deja:
            return

        from courses.models import InscriptionCours
        inscriptions = InscriptionCours.objects.filter(
            cours=instance.cours
        ).select_related('apprenant', 'apprenant__tuteur')

        nouvelle_date = instance.date_debut.strftime('%d/%m/%Y à %Hh%M')

        for insc in inscriptions:
            apprenant = insc.apprenant

            _notifier(
                recipient=apprenant,
                type_notif=TypeNotification.SESSION_DEPLACEE,
                titre="Session déplacée",
                message=f"La session « {instance.titre} » a été déplacée au {nouvelle_date}.",
                priorite=PrioriteNotification.HAUTE,
                sender=instance.formateur,
                entity_type=EntityType.SESSION,
                entity_id=instance.pk,
                action_url=f"/sessions/{instance.pk}",
                institution=instance.institution,
                groupe_dedup=groupe,
            )

            if apprenant.tuteur:
                _notifier(
                    recipient=apprenant.tuteur,
                    type_notif=TypeNotification.SESSION_DEPLACEE,
                    titre=f"Session déplacée — {apprenant.prenom}",
                    message=f"Session « {instance.titre} » déplacée au {nouvelle_date} pour {apprenant.prenom}.",
                    priorite=PrioriteNotification.MOYENNE,
                    entity_type=EntityType.SESSION,
                    entity_id=instance.pk,
                )


# ============================================================================
# INSCRIPTION DIRECTE AU COURS (InscriptionCours)
# ============================================================================

@receiver(post_save, sender='courses.InscriptionCours')
def on_inscription_cours_saved(sender, instance, created: bool, **kwargs):
    """
    Notifie l'apprenant et le formateur lors d'une inscription directe à un cours.
    Couvre le cas où l'inscription se fait par InscriptionCours (pas Inscription académique).
    """
    if not created:
        return

    cours = instance.cours
    apprenant = instance.apprenant

    # Apprenant
    _notifier(
        recipient=apprenant,
        type_notif=TypeNotification.INSCRIPTION_COURS,
        titre="Inscription au cours confirmée",
        message=f"Vous êtes inscrit(e) au cours « {cours.titre or cours.matiere.nom} ».",
        priorite=PrioriteNotification.MOYENNE,
        entity_type=EntityType.COURS,
        entity_id=cours.pk,
        action_url=f"/cours/{cours.pk}",
        institution=cours.institution,
        annee_scolaire=cours.annee_scolaire,
    )

    # Parent
    if apprenant.tuteur:
        _notifier(
            recipient=apprenant.tuteur,
            type_notif=TypeNotification.INSCRIPTION_COURS,
            titre="Inscription de votre enfant",
            message=f"{apprenant.prenom} a été inscrit(e) au cours « {cours.titre or cours.matiere.nom} ».",
            priorite=PrioriteNotification.MOYENNE,
            entity_type=EntityType.COURS,
            entity_id=cours.pk,
            action_url=f"/cours/{cours.pk}",
        )

    # Formateur
    _notifier(
        recipient=cours.enseignant,
        type_notif=TypeNotification.INSCRIPTION_COURS,
        titre="Nouvelle inscription dans votre cours",
        message=f"{apprenant.prenom} {apprenant.nom} a rejoint « {cours.titre or cours.matiere.nom} ».",
        priorite=PrioriteNotification.BASSE,
        entity_type=EntityType.COURS,
        entity_id=cours.pk,
        action_url=f"/cours/{cours.pk}",
        institution=cours.institution,
        groupe_dedup=f"inscription_formateur_cours:{cours.pk}:{cours.annee_scolaire_id}",
    )


# ============================================================================
# RESSOURCE PÉDAGOGIQUE (modèle Ressource, différent de Module)
# ============================================================================

try:
    from resources.models import Ressource

    @receiver(post_save, sender=Ressource)
    def on_ressource_saved(sender, instance, created: bool, **kwargs):
        if not created:
            return

        # Récupérer le cours lié à la ressource
        cours = getattr(instance, 'cours', None) or getattr(instance, 'module', None)
        if not cours:
            return

        # Si la ressource est liée à un module, remonter au cours
        if hasattr(cours, 'cours'):
            cours = cours.cours

        from courses.models import InscriptionCours
        inscriptions = InscriptionCours.objects.filter(
            cours=cours
        ).select_related('apprenant')

        for insc in inscriptions:
            _notifier(
                recipient=insc.apprenant,
                type_notif=TypeNotification.RESSOURCE_PEDAGOGIQUE,
                titre="Nouvelle ressource disponible",
                message=f"Une nouvelle ressource « {instance.titre or instance.nom} » a été ajoutée.",
                priorite=PrioriteNotification.BASSE,
                entity_type=EntityType.COURS,
                entity_id=cours.pk,
                action_url=f"/cours/{cours.pk}",
                groupe_dedup=f"ressource:{instance.pk}",
            )

except ImportError:
    pass  # Le modèle Ressource n'est pas encore disponible


# ============================================================================
# QUIZ SOUMIS
# ============================================================================

try:
    from evaluations.models import PassageQuiz

    @receiver(post_save, sender=PassageQuiz)
    def on_passage_quiz_saved(sender, instance, created: bool, **kwargs):

        if instance.statut == 'soumis':
            formateur = instance.quiz.cours.enseignant if hasattr(instance.quiz, 'cours') else None
            if not formateur:
                return

            groupe = f"quiz_soumis:{instance.quiz.pk}"
            existing = Notification.objects.filter(
                groupe_deduplication=groupe,
                is_read=False,
                recipient=formateur,
            ).first()

            if existing:
                existing.nb_evenements_groupes += 1
                existing.message = f"{existing.nb_evenements_groupes} quiz soumis pour « {instance.quiz.titre} »."
                existing.save(update_fields=['nb_evenements_groupes', 'message'])
            else:
                _notifier(
                    recipient=formateur,
                    type_notif=TypeNotification.EVALUATION_SOUMISE,
                    titre="Quiz soumis",
                    message=f"{instance.apprenant.prenom} {instance.apprenant.nom} a soumis le quiz « {instance.quiz.titre} ».",
                    priorite=PrioriteNotification.BASSE,
                    entity_type=EntityType.QUIZ,
                    entity_id=instance.quiz.pk,
                    groupe_dedup=groupe,
                )

        if instance.statut == 'corrige' and instance.score is not None:
            _notifier(
                recipient=instance.apprenant,
                type_notif=TypeNotification.EVALUATION_CORRIGEE,
                titre="Résultat de quiz disponible",
                message=f"Votre quiz « {instance.quiz.titre} » a été noté : {instance.score}/{instance.quiz.total_points}.",
                priorite=PrioriteNotification.MOYENNE,
                entity_type=EntityType.QUIZ,
                entity_id=instance.quiz.pk,
            )

except ImportError:
    pass  # PassageQuiz pas encore disponible