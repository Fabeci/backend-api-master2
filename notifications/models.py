# notifications/models.py

from django.db import models
from django.utils import timezone


class TypeNotification(models.TextChoices):
    ACTIVATION_COMPTE       = "activation_compte",       "Activation de compte"
    REINITIALISATION_MDP    = "reinitialisation_mdp",    "Réinitialisation de mot de passe"
    COMPTE_SUSPENDU         = "compte_suspendu",         "Compte suspendu"
    TENTATIVE_SUSPECTE      = "tentative_suspecte",      "Tentative suspecte sur compte"
    INSCRIPTION_COURS       = "inscription_cours",       "Inscription à un cours"
    INSCRIPTION_PROBLEME    = "inscription_probleme",    "Problème d'inscription"
    CREATION_RESSOURCE      = "creation_ressource",      "Nouvelle ressource académique"
    MODIFICATION_RESSOURCE  = "modification_ressource",  "Ressource académique modifiée"
    SUPPRESSION_RESSOURCE   = "suppression_ressource",   "Ressource académique supprimée"
    COURS_CREE              = "cours_cree",              "Cours créé"
    COURS_MODIFIE           = "cours_modifie",           "Cours modifié"
    MODULE_AJOUTE           = "module_ajoute",           "Nouveau module ajouté"
    SEQUENCE_AJOUTEE        = "sequence_ajoutee",        "Nouvelle séquence ajoutée"
    RESSOURCE_PEDAGOGIQUE   = "ressource_pedagogique",   "Nouvelle ressource pédagogique"
    CONTENU_PUBLIE          = "contenu_publie",          "Contenu publié / modifié"
    EVALUATION_PUBLIEE      = "evaluation_publiee",      "Évaluation publiée"
    EVALUATION_SOUMISE      = "evaluation_soumise",      "Évaluation soumise"
    EVALUATION_CORRIGEE     = "evaluation_corrigee",     "Résultat / Correction disponible"
    COPIES_A_CORRIGER       = "copies_a_corriger",       "Copies à corriger"
    RAPPEL_EVALUATION       = "rappel_evaluation",       "Rappel d'évaluation imminente"
    SESSION_A_VENIR         = "session_a_venir",         "Session à venir"
    SESSION_ANNULEE         = "session_annulee",         "Session annulée"
    SESSION_DEPLACEE        = "session_deplacee",        "Session déplacée"
    RAPPEL_SESSION          = "rappel_session",          "Rappel de session"
    ABSENCE_ENREGISTREE     = "absence_enregistree",     "Absence enregistrée"
    RETARD_ENREGISTRE       = "retard_enregistre",       "Retard enregistré"
    ABSENCES_REPETEES       = "absences_repetees",       "Absences répétées"
    PROGRESSION_FAIBLE      = "progression_faible",      "Alerte progression faible"
    PROGRESSION_ANORMALE    = "progression_anormale",    "Progression anormale détectée"
    COURS_TERMINE           = "cours_termine",           "Cours terminé"
    ENCOURAGEMENT           = "encouragement",           "Encouragement"
    ASSIGNATION_COURS       = "assignation_cours",       "Assignation à un cours / groupe"
    CHANGEMENT_PLANNING     = "changement_planning",     "Changement d'emploi du temps"
    PAIEMENT_DU             = "paiement_du",             "Paiement / Échéance à venir"
    PAIEMENT_REJETE         = "paiement_rejete",         "Paiement rejeté"
    FACTURE_EMISE           = "facture_emise",           "Facture émise"
    INCIDENT_SECURITE       = "incident_securite",       "Incident de sécurité"
    INCIDENT_SYSTEME        = "incident_systeme",        "Incident système majeur"
    ALERTE_EXPLOITATION     = "alerte_exploitation",     "Alerte générale d'exploitation"
    ANNONCE_ADMINISTRATIVE  = "annonce_administrative",  "Annonce administrative"


class PrioriteNotification(models.TextChoices):
    BASSE    = "basse",    "Basse"
    MOYENNE  = "moyenne",  "Moyenne"
    HAUTE    = "haute",    "Haute"
    CRITIQUE = "critique", "Critique"


class CanalNotification(models.TextChoices):
    IN_APP = "in_app", "In-App"
    EMAIL  = "email",  "Email"
    PUSH   = "push",   "Push mobile"
    SMS    = "sms",    "SMS / WhatsApp"


class EntityType(models.TextChoices):
    COURS         = "cours",         "Cours"
    MODULE        = "module",        "Module"
    SEQUENCE      = "sequence",      "Séquence"
    EVALUATION    = "evaluation",    "Évaluation"
    QUIZ          = "quiz",          "Quiz"
    SESSION       = "session",       "Session"
    INSCRIPTION   = "inscription",   "Inscription"
    PARTICIPATION = "participation", "Participation"
    CLASSE        = "classe",        "Classe"
    GROUPE        = "groupe",        "Groupe"
    INSTITUTION   = "institution",   "Institution"
    PAIEMENT      = "paiement",      "Paiement"
    USER          = "user",          "Utilisateur"
    AUTRE         = "autre",         "Autre"


# ============================================================================
# NOTIFICATION
# ============================================================================

class Notification(models.Model):

    # ── Destinataire & expéditeur ────────────────────────────────────────────
    recipient = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name="Destinataire",
    )
    sender = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="notifications_envoyees",
        verbose_name="Expéditeur",
        help_text="Null = notification système automatique",
    )

    # ── Classification ───────────────────────────────────────────────────────
    type = models.CharField(
        max_length=50,
        choices=TypeNotification.choices,
        verbose_name="Type",
    )
    priorite = models.CharField(
        max_length=10,
        choices=PrioriteNotification.choices,
        default=PrioriteNotification.MOYENNE,
        verbose_name="Priorité",
    )
    canal = models.CharField(
        max_length=10,
        choices=CanalNotification.choices,
        default=CanalNotification.IN_APP,
        verbose_name="Canal",
    )

    # ── Contenu ──────────────────────────────────────────────────────────────
    titre   = models.CharField(max_length=255, verbose_name="Titre", default="")
    message = models.TextField(verbose_name="Message", default="")

    # ── Entité liée ──────────────────────────────────────────────────────────
    entity_type = models.CharField(
        max_length=20,
        choices=EntityType.choices,
        blank=True, null=True,
        verbose_name="Type d'entité liée",
    )
    entity_id = models.PositiveIntegerField(
        blank=True, null=True,
        verbose_name="ID de l'entité liée",
    )
    action_url = models.CharField(
        max_length=500,
        blank=True, null=True,
        verbose_name="URL d'action",
        help_text="Route frontend vers l'entité concernée",
    )

    # ── Contexte institutionnel ──────────────────────────────────────────────
    institution = models.ForeignKey(
        "academics.Institution",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="notifications",
        verbose_name="Institution",
    )
    annee_scolaire = models.ForeignKey(
        "academics.AnneeScolaire",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="notifications",
        verbose_name="Année scolaire",
    )

    # ── Déduplication / groupement ───────────────────────────────────────────
    groupe_deduplication = models.CharField(
        max_length=255,
        blank=True, null=True,
        verbose_name="Clé de déduplication",
        help_text="Ex: 'evaluation_soumise:42' — regroupe les notifs similaires",
        db_index=True,
    )
    nb_evenements_groupes = models.PositiveIntegerField(
        default=1,
        verbose_name="Événements groupés",
        help_text="Nombre d'événements fusionnés dans cette notification",
    )

    # ── État de lecture ──────────────────────────────────────────────────────
    is_read = models.BooleanField(default=False, verbose_name="Lu")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="Lu le")

    # ── État d'envoi ─────────────────────────────────────────────────────────
    statut_envoi = models.CharField(
        max_length=10,
        choices=[
            ("pending",  "En attente"),
            ("sent",     "Envoyé"),
            ("failed",   "Échec"),
            ("skipped",  "Ignoré"),
        ],
        default="pending",
        verbose_name="Statut d'envoi",
    )
    sent_at    = models.DateTimeField(null=True, blank=True, verbose_name="Envoyé le")
    send_error = models.TextField(blank=True, verbose_name="Erreur d'envoi")

    # ── Programmation & expiration ───────────────────────────────────────────
    scheduled_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Programmée pour le",
        help_text="Si renseigné, n'envoyer qu'à partir de cette date (Celery)",
    )
    expires_at = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Expire le",
        help_text="Passé cette date, la notification est considérée obsolète",
    )

    # ── Métadonnées libres ───────────────────────────────────────────────────
    metadata = models.JSONField(
        default=dict, blank=True,
        verbose_name="Métadonnées",
    )

    # ── Horodatage ───────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créée le")

    class Meta:
        verbose_name        = "Notification"
        verbose_name_plural = "Notifications"
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["type"]),
            models.Index(fields=["canal"]),
            models.Index(fields=["priorite"]),
            models.Index(fields=["statut_envoi"]),
            models.Index(fields=["entity_type", "entity_id"]),
            models.Index(fields=["institution", "-created_at"]),
            models.Index(fields=["scheduled_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"[{self.get_canal_display()}] {self.recipient} — {self.titre}"

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def est_expiree(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def est_prete_a_envoyer(self):
        """True si la date de programmation est atteinte (ou absente)."""
        if self.scheduled_at and timezone.now() < self.scheduled_at:
            return False
        return self.statut_envoi == "pending"

    # ── Méthodes ─────────────────────────────────────────────────────────────

    def marquer_comme_lue(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])

    def marquer_comme_envoyee(self):
        self.statut_envoi = "sent"
        self.sent_at      = timezone.now()
        self.send_error   = ""
        self.save(update_fields=["statut_envoi", "sent_at", "send_error"])

    def enregistrer_erreur_envoi(self, message: str):
        self.statut_envoi = "failed"
        self.send_error   = message
        self.save(update_fields=["statut_envoi", "send_error"])

    @classmethod
    def creer(
        cls,
        recipient,
        type_notif: str,
        titre: str,
        message: str,
        canal: str                = CanalNotification.IN_APP,
        priorite: str             = PrioriteNotification.MOYENNE,
        sender=None,
        entity_type: str          = None,
        entity_id: int            = None,
        action_url: str           = None,
        institution               = None,
        annee_scolaire            = None,
        groupe_deduplication: str = None,
        scheduled_at              = None,
        expires_at                = None,
        **metadata,
    ) -> "Notification":
        return cls.objects.create(
            recipient            = recipient,
            sender               = sender,
            type                 = type_notif,
            titre                = titre,
            message              = message,
            canal                = canal,
            priorite             = priorite,
            entity_type          = entity_type,
            entity_id            = entity_id,
            action_url           = action_url,
            institution          = institution,
            annee_scolaire       = annee_scolaire,
            groupe_deduplication = groupe_deduplication,
            scheduled_at         = scheduled_at,
            expires_at           = expires_at,
            metadata             = metadata or {},
        )


# ============================================================================
# PRÉFÉRENCES DE NOTIFICATION
# ============================================================================

class PreferenceNotification(models.Model):
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="preferences_notifications",
        verbose_name="Utilisateur",
    )
    type = models.CharField(
        max_length=50,
        choices=TypeNotification.choices,
        verbose_name="Type de notification",
    )
    canal = models.CharField(
        max_length=10,
        choices=CanalNotification.choices,
        verbose_name="Canal",
    )
    est_active = models.BooleanField(default=True, verbose_name="Activée")

    class Meta:
        verbose_name        = "Préférence de notification"
        verbose_name_plural = "Préférences de notifications"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "type", "canal"],
                name="uniq_preference_user_type_canal",
            )
        ]

    def __str__(self):
        statut = "✓" if self.est_active else "✗"
        return f"{statut} {self.user} — {self.type} via {self.canal}"


# ============================================================================
# DIGEST QUOTIDIEN
# ============================================================================

class DigestNotification(models.Model):
    FREQUENCE_CHOICES = [
        ("quotidien",    "Quotidien"),
        ("hebdomadaire", "Hebdomadaire"),
    ]

    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="digests",
        verbose_name="Utilisateur",
    )
    frequence = models.CharField(
        max_length=15,
        choices=FREQUENCE_CHOICES,
        default="quotidien",
        verbose_name="Fréquence",
    )
    notifications = models.ManyToManyField(
        Notification,
        related_name="digests",
        blank=True,
        verbose_name="Notifications regroupées",
    )
    envoye    = models.BooleanField(default=False, verbose_name="Envoyé")
    envoye_le = models.DateTimeField(null=True, blank=True, verbose_name="Envoyé le")

    periode_debut = models.DateTimeField(verbose_name="Début de la période")
    periode_fin   = models.DateTimeField(verbose_name="Fin de la période")
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "Digest de notifications"
        verbose_name_plural = "Digests de notifications"
        ordering            = ["-created_at"]

    def __str__(self):
        return f"Digest {self.frequence} — {self.user} ({self.periode_debut.date()})"

    def marquer_comme_envoye(self):
        self.envoye    = True
        self.envoye_le = timezone.now()
        self.save(update_fields=["envoye", "envoye_le"])