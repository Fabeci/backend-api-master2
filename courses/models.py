# courses/models.py
from django.db import models
from django.forms import ValidationError
from django.utils import timezone

from academics.models import Groupe, Matiere


class Cours(models.Model):
    """
    Cours = programmation d’une matière :
    - 1 matière
    - 1 groupe (ou classe si tu changes plus tard)
    - 1 enseignant responsable
    - 1 volume horaire prévu
    - N modules
    - N sessions (séances)
    """
    titre = models.CharField(null=True, max_length=255)
    groupe = models.ForeignKey(
        Groupe,
        on_delete=models.CASCADE,
        related_name="cours",
    )
    enseignant = models.ForeignKey(
        "users.Formateur",
        on_delete=models.CASCADE,
        related_name="cours_responsable",
    )
    matiere = models.ForeignKey(
        Matiere,
        on_delete=models.CASCADE,
        related_name="cours",
    )

    # Volume horaire prévu (macro)
    volume_horaire = models.PositiveIntegerField(
        default=0,
        help_text="Volume horaire total prévu pour ce cours (en heures).",
    )

    # Période de référence (optionnelle)
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)

    # Statut (optionnel)
    statut = models.CharField(
        max_length=30,
        choices=[
            ("planifie", "Planifié"),
            ("en_cours", "En cours"),
            ("termine", "Terminé"),
            ("annule", "Annulé"),
        ],
        default="planifie",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["groupe", "matiere", "enseignant"],
                name="uniq_cours_groupe_matiere_enseignant",
            )
        ]

    def __str__(self):
        return f"{self.matiere} • {self.groupe} • {self.enseignant}"

    @property
    def total_minutes_realises(self) -> int:
        return sum(s.duree_minutes for s in self.sessions.all())

    @property
    def total_heures_realisees(self) -> float:
        return round(self.total_minutes_realises / 60.0, 2)

    @property
    def taux_execution(self) -> float:
        if not self.volume_horaire:
            return 0.0
        return round((self.total_heures_realisees / float(self.volume_horaire)) * 100.0, 2)


class Module(models.Model):
    """
    Module = chapitre/bloc pédagogique appartenant à un cours.
    """
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="modules",
    )

    def __str__(self):
        return self.titre


class Sequence(models.Model):
    """
    Sequence = sous-partie d’un module.
    """
    titre = models.CharField(max_length=255)
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="sequences",
    )

    def __str__(self):
        return self.titre


class Session(models.Model):
    """
    Session = séance réelle (à l'école).
    - liée à un Cours
    - porte la planification (date_debut/date_fin)
    - gère le mode de participation : auto vs manuel
    """
    PARTICIPATION_MODE_CHOICES = (
        ("auto", "Automatique"),
        ("manuel", "Manuel"),
    )

    titre = models.CharField(max_length=255)
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()

    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    # Gardé pour permettre remplacements/intervenants
    formateur = models.ForeignKey(
        "users.Formateur",
        on_delete=models.CASCADE,
        related_name="sessions",
    )

    participation_mode = models.CharField(
        max_length=10,
        choices=PARTICIPATION_MODE_CHOICES,
        default="manuel",
        help_text="auto = participation créée automatiquement à la fin; manuel = saisie volontaire",
    )

    class Meta:
        ordering = ["-date_debut"]

    def clean(self):
        if self.date_fin and self.date_debut and self.date_fin <= self.date_debut:
            raise ValidationError("date_fin doit être strictement supérieure à date_debut.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def duree_minutes(self) -> int:
        if not self.date_debut or not self.date_fin:
            return 0
        delta = self.date_fin - self.date_debut
        return max(0, int(delta.total_seconds() // 60))

    def __str__(self):
        return f"{self.titre} • {self.cours} ({self.date_debut} - {self.date_fin})"


class InscriptionCours(models.Model):
    """
    InscriptionCours = pivot N-N Apprenant <-> Cours
    """
    apprenant = models.ForeignKey(
        "users.Apprenant",
        on_delete=models.CASCADE,
        related_name="inscriptions_cours",
        related_query_name="inscription_cours",
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="inscriptions",
    )
    date_inscription = models.DateField(auto_now_add=True)
    statut = models.CharField(
        max_length=50,
        default="en_cours",
        help_text="Ex: suivi, en_cours, complete, annule",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["apprenant", "cours"],
                name="uniq_apprenant_par_cours",
            )
        ]

    def __str__(self):
        return f"{self.apprenant.nom} {self.apprenant.prenom} inscrit à {self.cours}"


class Suivi(models.Model):
    """
    Suivi = progression/notes/commentaires d'un apprenant sur un cours.
    1 suivi par apprenant par cours (recommandé).
    """
    apprenant = models.ForeignKey(
        "users.Apprenant",
        on_delete=models.CASCADE,
        related_name="suivis",
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="suivis",
    )
    date_debut = models.DateField(auto_now_add=True)
    progression = models.FloatField(default=0.0)  # 0-100
    note = models.FloatField(null=True, blank=True)
    commentaires = models.TextField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["apprenant", "cours"],
                name="uniq_suivi_apprenant_cours",
            )
        ]

    def __str__(self):
        return f"Suivi de {self.apprenant.nom} pour {self.cours}"

    def clean(self):
        # Normaliser progression
        if self.progression < 0:
            self.progression = 0.0
        if self.progression > 100:
            self.progression = 100.0

        # Règle métier : doit être inscrit au cours
        if not InscriptionCours.objects.filter(apprenant=self.apprenant, cours=self.cours).exists():
            raise ValidationError(f"L'apprenant {self.apprenant} n'est pas inscrit à ce cours.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class Participation(models.Model):
    """
    Participation = présence/participation d’un apprenant à une session.

    2 modes:
    - session.participation_mode == 'auto'  : participation auto à la fin (completed)
    - session.participation_mode == 'manuel': l’apprenant (ou admin) choisit/valide
    """
    SOURCE_CHOICES = (
        ("auto", "Automatique"),
        ("manuel", "Manuel"),
    )
    STATUS_CHOICES = (
        ("en_attente", "En attente"),
        ("terminee", "Terminée"),
        ("annulee", "Annulée"),
    )

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="participations",
    )
    apprenant = models.ForeignKey(
        "users.Apprenant",
        on_delete=models.CASCADE,
        related_name="participations",
    )

    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default="manuel",
        help_text="auto ou manuel",
    )
    statut = models.CharField(
        max_length=15,
        choices=STATUS_CHOICES,
        default="en_attente",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "apprenant"],
                name="uniq_participation_session_apprenant",
            )
        ]

    def clean(self):
        # Reco: vérifier que l’apprenant est inscrit au cours de la session
        if self.session_id and self.apprenant_id:
            cours = self.session.cours
            if not InscriptionCours.objects.filter(apprenant=self.apprenant, cours=cours).exists():
                raise ValidationError(
                    f"L'apprenant {self.apprenant} n'est pas inscrit au cours de cette session."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def mark_completed(self, source: str | None = None):
        if source in ("auto", "manuel"):
            self.source = source
        self.statut = "terminee"
        self.completed_at = timezone.now()
        self.save(update_fields=["source", "statut", "completed_at"])

    def __str__(self):
        return f"{self.apprenant.nom} {self.apprenant.prenom} • {self.session.titre} • {self.statut}"
