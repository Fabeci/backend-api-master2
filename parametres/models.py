# parametres/models.py
from django.db import models


class ParametresPlateforme(models.Model):
    """Paramètres globaux (singleton) — modifiables par SuperAdmin uniquement."""

    # ── Évaluations ───────────────────────────────────────────────────
    evaluation_note_passage_pct     = models.IntegerField(default=60)
    evaluation_tentatives_max       = models.IntegerField(default=3)
    evaluation_duree_defaut_min     = models.IntegerField(default=30)
    evaluation_shuffle_questions    = models.BooleanField(default=False)
    evaluation_afficher_correction  = models.BooleanField(default=True)

    # ── Progression ───────────────────────────────────────────────────
    progression_seuil_completion_pct = models.IntegerField(default=80)
    progression_retention_jours      = models.IntegerField(default=7)

    # ── Sécurité ──────────────────────────────────────────────────────
    securite_mdp_longueur_min       = models.IntegerField(default=8)
    securite_session_expiration_h   = models.IntegerField(default=24)
    securite_tentatives_login_max   = models.IntegerField(default=5)
    securite_mdp_complexite         = models.BooleanField(default=True)

    # ── Général / identité plateforme ─────────────────────────────────
    langue_defaut                   = models.CharField(max_length=5, default='fr')
    fuseau_horaire                  = models.CharField(max_length=64, default='Africa/Ndjamena')

    # ── Notifications (règles générales) ──────────────────────────────
    # NB : l'envoi e-mail pédagogique n'est pas encore implémenté ; ces
    # règles piloteront l'envoi lorsque le canal e-mail sera branché.
    notif_email_actif               = models.BooleanField(default=False)
    notif_rappel_seance             = models.BooleanField(default=True)
    notif_absence                   = models.BooleanField(default=True)
    notif_publication_evaluation    = models.BooleanField(default=True)
    notif_correction_disponible     = models.BooleanField(default=True)
    notif_rappel_echeance           = models.BooleanField(default=True)
    notif_rappel_seance_heures      = models.IntegerField(default=24)

    class Meta:
        verbose_name = 'Paramètres plateforme'
        verbose_name_plural = 'Paramètres plateforme'

    def __str__(self):
        return 'Paramètres globaux'

    @classmethod
    def get_instance(cls):
        """Singleton — crée l'enregistrement s'il n'existe pas encore."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ParametresInstitution(models.Model):
    """Surcharges par établissement — champs nullable = hériter du global."""

    institution = models.OneToOneField(
        'academics.Institution',
        on_delete=models.CASCADE,
        related_name='parametres',
    )

    # ── Évaluations (nullable = hériter) ──────────────────────────────
    evaluation_note_passage_pct     = models.IntegerField(null=True, blank=True)
    evaluation_tentatives_max       = models.IntegerField(null=True, blank=True)
    evaluation_duree_defaut_min     = models.IntegerField(null=True, blank=True)
    evaluation_shuffle_questions    = models.BooleanField(null=True, blank=True)

    # ── Progression (nullable = hériter) ──────────────────────────────
    progression_seuil_completion_pct = models.IntegerField(null=True, blank=True)
    progression_retention_jours      = models.IntegerField(null=True, blank=True)

    # ── Sécurité (nullable = hériter) ─────────────────────────────────
    securite_mdp_longueur_min       = models.IntegerField(null=True, blank=True)
    securite_mdp_complexite         = models.BooleanField(null=True, blank=True)
    securite_tentatives_login_max   = models.IntegerField(null=True, blank=True)
    securite_session_expiration_h   = models.IntegerField(null=True, blank=True)

    # ── Apparence ─────────────────────────────────────────────────────
    couleur_principale  = models.CharField(max_length=20, default='#0E71B4')
    langue_defaut       = models.CharField(max_length=5, default='fr')
    logo_url            = models.URLField(blank=True, default='')

    # ── Général / Notifications (surcharges, null = hériter du global) ─
    fuseau_horaire                  = models.CharField(max_length=64, blank=True, default='')
    notif_email_actif               = models.BooleanField(null=True, blank=True)
    notif_rappel_seance             = models.BooleanField(null=True, blank=True)
    notif_absence                   = models.BooleanField(null=True, blank=True)
    notif_publication_evaluation    = models.BooleanField(null=True, blank=True)
    notif_correction_disponible     = models.BooleanField(null=True, blank=True)
    notif_rappel_echeance           = models.BooleanField(null=True, blank=True)
    notif_rappel_seance_heures      = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = 'Paramètres institution'
        verbose_name_plural = 'Paramètres institutions'

    def __str__(self):
        return f'Paramètres — {self.institution}'


class PreferencesUtilisateur(models.Model):
    """Préférences personnelles d'un utilisateur."""

    user = models.OneToOneField(
        'users.User',
        on_delete=models.CASCADE,
        related_name='preferences',
    )
    recevoir_aide_ia        = models.BooleanField(default=True)
    notifications_activees  = models.BooleanField(default=True)
    langue                  = models.CharField(max_length=5, default='fr')
    theme                   = models.CharField(
        max_length=10,
        choices=[('clair', 'Clair'), ('sombre', 'Sombre')],
        default='clair',
    )

    class Meta:
        verbose_name = 'Préférences utilisateur'
        verbose_name_plural = 'Préférences utilisateurs'

    def __str__(self):
        return f'Préférences — {self.user}'

    @classmethod
    def get_or_create_for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj
