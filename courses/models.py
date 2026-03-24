# -*- coding: utf-8 -*-
# courses/models.py

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from academics.models import Groupe, Matiere, Institution, AnneeScolaire
from users.models import Apprenant, Formateur
from django.utils import timezone


# ============================================================================
# COURS
# ============================================================================

class Cours(models.Model):
    titre = models.CharField(max_length=255, null=True, blank=True)
    groupe = models.ForeignKey(Groupe, on_delete=models.CASCADE, related_name="cours")
    enseignant = models.ForeignKey(Formateur, on_delete=models.CASCADE, related_name="cours_enseignes")
    matiere = models.ForeignKey(Matiere, on_delete=models.CASCADE, related_name="cours")
    volume_horaire = models.IntegerField(default=0, help_text="Volume horaire prévu en minutes")
    date_debut = models.DateField(null=True, blank=True)
    date_fin = models.DateField(null=True, blank=True)
    statut = models.CharField(
        max_length=20,
        choices=[
            ("en_cours", "En cours"),
            ("termine", "Terminé"),
            ("planifie", "Planifié"),
        ],
        default="planifie",
    )

    # Nouveaux champs pour rattachement
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="cours",
        null=True, blank=True,
        help_text="Établissement auquel ce cours est rattaché"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="cours",
        null=True, blank=True,
        help_text="Année scolaire à laquelle ce cours est rattaché"
    )
    departement = models.ForeignKey(
        'academics.Departement',
        on_delete=models.SET_NULL,
        related_name="cours",
        null=True, blank=True,
        help_text="Département hérité du groupe/classe"
    )
    
    @property
    def statut_calcule(self) -> str:
        """
        Calcule le statut en fonction des dates.
        Priorité : date_debut / date_fin > statut manuel.
        """
        today = timezone.localdate()

        if self.date_debut and self.date_fin:
            if today < self.date_debut:
                return "planifie"
            elif self.date_debut <= today <= self.date_fin:
                return "en_cours"
            else:
                return "termine"

        if self.date_debut and not self.date_fin:
            return "en_cours" if today >= self.date_debut else "planifie"

        if self.date_fin and not self.date_debut:
            return "termine" if today > self.date_fin else "en_cours"

        # Aucune date → conserver le statut manuel existant
        return self.statut or "planifie"
    
    def save(self, *args, **kwargs):
        if self.date_debut or self.date_fin:
            self.statut = self.statut_calcule
        if self.groupe and not self.departement_id:
            self._auto_set_departement()
        super().save(*args, **kwargs)
    
    def _auto_set_departement(self):
        try:
            classe = self.groupe.classe
            if classe:
                filiere = classe.filieres.exclude(
                    domaine_etude__departement=None
                ).select_related('domaine_etude__departement').first()
                if filiere and filiere.domaine_etude.departement_id:
                    self.departement_id = filiere.domaine_etude.departement_id
        except Exception:
            pass

    class Meta:
        verbose_name = "Cours"
        verbose_name_plural = "Cours"
        ordering = ["-date_debut"]
        constraints = [
            models.UniqueConstraint(
                fields=["groupe", "matiere", "enseignant", "annee_scolaire"],
                name="unique_cours_per_year"
            )
        ]

    def __str__(self):
        return self.titre or f"Cours {self.matiere.nom} - {self.groupe.nom}"

    @property
    def total_minutes_realises(self):
        """Calcule le total des minutes de sessions réalisées"""
        return sum(s.duree_minutes or 0 for s in self.sessions.all())

    @property
    def total_heures_realisees(self):
        """Convertit les minutes en heures"""
        return round(self.total_minutes_realises / 60, 2)

    @property
    def taux_execution(self):
        """Pourcentage d'exécution par rapport au volume horaire prévu"""
        if not self.volume_horaire:
            return 0.0
        return round((self.total_minutes_realises / self.volume_horaire) * 100, 2)


# ============================================================================
# MODULES
# ============================================================================

class Module(models.Model):
    titre = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    cours = models.ForeignKey(Cours, on_delete=models.CASCADE, related_name="modules")

    # Rattachement automatique via le cours
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="modules",
        null=True, blank=True,
        help_text="Hérité du cours parent"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="modules",
        help_text="Hérité du cours parent"
    )

    class Meta:
        verbose_name = "Module"
        verbose_name_plural = "Modules"
        ordering = ["id"]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        # Héritage automatique depuis le cours
        if self.cours:
            self.institution = self.cours.institution
            self.annee_scolaire = self.cours.annee_scolaire
        super().save(*args, **kwargs)


# ============================================================================
# SÉQUENCES
# ============================================================================

class Sequence(models.Model):
    titre = models.CharField(max_length=255)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="sequences")

    # Rattachement automatique via le module
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="sequences",
        null=True, blank=True,
        help_text="Hérité du module parent"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="sequences",
        null=True, blank=True,
        help_text="Hérité du module parent"
    )

    class Meta:
        verbose_name = "Séquence"
        verbose_name_plural = "Séquences"
        ordering = ["id"]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        # Héritage automatique depuis le module
        if self.module:
            self.institution = self.module.institution
            self.annee_scolaire = self.module.annee_scolaire
        super().save(*args, **kwargs)


# ============================================================================
# CONTENU DE SÉQUENCE (ANCIEN)
# ============================================================================

class SequenceContent(models.Model):
    sequence = models.OneToOneField(
        Sequence,
        on_delete=models.CASCADE,
        related_name="contenu",
    )
    contenu_texte = models.TextField(blank=True, null=True)
    contenu_html = models.TextField(blank=True, null=True)
    video_url = models.URLField(blank=True, null=True)
    lien_externe = models.URLField(blank=True, null=True)
    objectifs = models.TextField(blank=True, null=True)
    duree_estimee_minutes = models.IntegerField(default=0)
    est_publie = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contenu de séquence"
        verbose_name_plural = "Contenus de séquences"

    def __str__(self):
        return f"Contenu de {self.sequence.titre}"


# ============================================================================
# BLOCS DE CONTENU (NOUVEAU SYSTÈME MODULAIRE)
# ============================================================================

class BlocContenu(models.Model):
    TYPE_BLOC_CHOICES = [
        ("texte", "Texte"),
        ("html", "HTML"),
        ("markdown", "Markdown"),
        ("video", "Vidéo"),
        ("audio", "Audio"),
        ("image", "Image"),
        ("fichier", "Fichier"),
        ("lien", "Lien externe"),
        ("code", "Code source"),
    ]

    LANGAGE_CODE_CHOICES = [
        ("python", "Python"),
        ("javascript", "JavaScript"),
        ("java", "Java"),
        ("c", "C"),
        ("cpp", "C++"),
        ("csharp", "C#"),
        ("php", "PHP"),
        ("ruby", "Ruby"),
        ("go", "Go"),
        ("rust", "Rust"),
        ("sql", "SQL"),
        ("html", "HTML"),
        ("css", "CSS"),
        ("other", "Autre"),
    ]

    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name="blocs_contenu",
        verbose_name="Séquence"
    )
    titre = models.CharField(max_length=255, verbose_name="Titre du bloc")
    type_bloc = models.CharField(
        max_length=20,
        choices=TYPE_BLOC_CHOICES,
        verbose_name="Type de bloc"
    )
    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )

    # Contenu textuel
    contenu_texte = models.TextField(blank=True, null=True, verbose_name="Contenu texte")
    contenu_html = models.TextField(blank=True, null=True, verbose_name="Contenu HTML")
    contenu_markdown = models.TextField(blank=True, null=True, verbose_name="Contenu Markdown")

    # Média
    video_url = models.URLField(blank=True, null=True, verbose_name="URL de la vidéo")
    audio_url = models.URLField(blank=True, null=True, verbose_name="URL de l'audio")
    image = models.ImageField(
        upload_to="blocs_contenu/images/",
        blank=True,
        null=True,
        verbose_name="Image"
    )
    fichier = models.FileField(
        upload_to="blocs_contenu/fichiers/",
        blank=True,
        null=True,
        verbose_name="Fichier"
    )

    # Lien externe
    lien_externe = models.URLField(blank=True, null=True, verbose_name="Lien externe")

    # Code source
    code_source = models.TextField(blank=True, null=True, verbose_name="Code source")
    langage_code = models.CharField(
        max_length=20,
        choices=LANGAGE_CODE_CHOICES,
        blank=True,
        null=True,
        verbose_name="Langage de programmation"
    )

    # Métadonnées
    objectifs = models.TextField(blank=True, null=True, verbose_name="Objectifs pédagogiques")
    duree_estimee_minutes = models.PositiveIntegerField(
        default=0,
        verbose_name="Durée estimée (minutes)"
    )

    # Gestion
    est_obligatoire = models.BooleanField(default=True, verbose_name="Contenu obligatoire")
    est_visible = models.BooleanField(default=True, verbose_name="Visible pour les apprenants")

    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Bloc de contenu"
        verbose_name_plural = "Blocs de contenu"
        ordering = ["sequence", "ordre"]

    def __str__(self):
        return f"{self.titre} ({self.get_type_bloc_display()})"

    @property
    def icone_type(self):
        """Retourne une icône suggérée selon le type de bloc"""
        icones = {
            "texte": "📄",
            "html": "💻",
            "markdown": "📝",
            "video": "🎥",
            "audio": "🎵",
            "image": "🖼️",
            "fichier": "📎",
            "lien": "🔗",
            "code": "⚙️",
        }
        return icones.get(self.type_bloc, "📄")


# ============================================================================
# RESSOURCES / PIÈCES JOINTES
# ============================================================================

class RessourceSequence(models.Model):
    TYPE_RESSOURCE_CHOICES = [
        ("document", "Document"),
        ("presentation", "Présentation"),
        ("tableur", "Tableur"),
        ("pdf", "PDF"),
        ("archive", "Archive"),
        ("autre", "Autre"),
    ]

    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name="ressources_sequences",
        verbose_name="Séquence"
    )
    titre = models.CharField(max_length=255, verbose_name="Titre de la ressource")
    description = models.TextField(blank=True, null=True, verbose_name="Description")
    fichier = models.FileField(
        upload_to="ressources_sequences/",
        verbose_name="Fichier"
    )
    type_ressource = models.CharField(
        max_length=20,
        choices=TYPE_RESSOURCE_CHOICES,
        default="autre",
        verbose_name="Type de ressource"
    )

    # Métadonnées fichier
    taille_fichier = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Taille du fichier (octets)"
    )

    # Gestion
    est_telechargeable = models.BooleanField(
        default=True,
        verbose_name="Autoriser le téléchargement"
    )
    nombre_telechargements = models.PositiveIntegerField(
        default=0,
        verbose_name="Nombre de téléchargements"
    )
    ordre = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordre d'affichage"
    )

    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    ajoute_par = models.ForeignKey(
        "users.Formateur",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ressources_ajoutees",
        verbose_name="Ajouté par"
    )

    class Meta:
        verbose_name = "Ressource de séquence"
        verbose_name_plural = "Ressources de séquences"
        ordering = ["sequence", "ordre"]

    def __str__(self):
        return self.titre

    def save(self, *args, **kwargs):
        # Calculer automatiquement la taille du fichier
        if self.fichier and not self.taille_fichier:
            self.taille_fichier = self.fichier.size
        super().save(*args, **kwargs)

    @property
    def taille_lisible(self):
        """Retourne la taille du fichier dans un format lisible"""
        if not self.taille_fichier:
            return "Inconnu"

        taille = float(self.taille_fichier)
        for unite in ["o", "Ko", "Mo", "Go"]:
            if taille < 1024.0:
                return f"{taille:.1f} {unite}"
            taille /= 1024.0
        return f"{taille:.1f} To"

    @property
    def extension(self):
        """Retourne l'extension du fichier"""
        if self.fichier:
            return self.fichier.name.split(".")[-1].lower()
        return None

    @property
    def icone_extension(self):
        """Retourne une icône selon l'extension"""
        ext = self.extension
        icones = {
            "pdf": "📄",
            "doc": "📘", "docx": "📘",
            "xls": "📊", "xlsx": "📊",
            "ppt": "📊", "pptx": "📊",
            "zip": "🗜️", "rar": "🗜️",
            "jpg": "🖼️", "jpeg": "🖼️", "png": "🖼️",
        }
        return icones.get(ext, "📎")


# ============================================================================
# INSCRIPTIONS COURS
# ============================================================================

class InscriptionCours(models.Model):
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="inscriptions_cours"
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="inscriptions"
    )
    date_inscription = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(
        max_length=20,
        choices=[
            ("inscrit", "Inscrit"),
            ("en_cours", "En cours"),
            ("termine", "Terminé"),
            ("abandonne", "Abandonné"),
        ],
        default="inscrit",
    )

    # Rattachement automatique via le cours
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="inscriptions_cours",
        null=True, blank=True,
        help_text="Hérité du cours"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name="inscriptions_cours",
        help_text="Hérité du cours"
    )

    class Meta:
        verbose_name = "Inscription cours"
        verbose_name_plural = "Inscriptions cours"
        unique_together = ("apprenant", "cours")

    def __str__(self):
        return f"{self.apprenant} - {self.cours}"

    def save(self, *args, **kwargs):
        # Héritage automatique depuis le cours
        if self.cours:
            self.institution = self.cours.institution
            self.annee_scolaire = self.cours.annee_scolaire
        super().save(*args, **kwargs)


# ============================================================================
# SUIVI
# ============================================================================

class Suivi(models.Model):
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="suivis"
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="suivis"
    )
    date_debut = models.DateTimeField(auto_now_add=True)
    progression = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True
    )
    commentaires = models.TextField(null=True, blank=True)

    # Rattachement automatique via le cours
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="suivis",
        null=True, blank=True,
        help_text="Hérité du cours"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="suivis",
        null=True, blank=True,
        help_text="Hérité du cours"
    )

    class Meta:
        verbose_name = "Suivi"
        verbose_name_plural = "Suivis"
        unique_together = ("apprenant", "cours")

    def __str__(self):
        return f"Suivi {self.apprenant} - {self.cours}"

    def save(self, *args, **kwargs):
        # Héritage automatique depuis le cours
        if self.cours:
            self.institution = self.cours.institution
            self.annee_scolaire = self.cours.annee_scolaire
        super().save(*args, **kwargs)


# ============================================================================
# SESSIONS
# ============================================================================

class Session(models.Model):
    titre = models.CharField(max_length=255)
    date_debut = models.DateTimeField()
    date_fin = models.DateTimeField()
    formateur = models.ForeignKey(
        Formateur,
        on_delete=models.CASCADE,
        related_name="sessions_animees"
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="sessions"
    )
    participation_mode = models.CharField(
        max_length=20,
        choices=[
            ("presentiel", "Présentiel"),
            ("distanciel", "Distanciel"),
            ("hybride", "Hybride"),
        ],
        default="presentiel",
    )

    # Rattachement automatique via le cours
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="sessions",
        null=True, blank=True,
        help_text="Hérité du cours"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="sessions",
        null=True, blank=True,
        help_text="Hérité du cours"
    )

    class Meta:
        verbose_name = "Session"
        verbose_name_plural = "Sessions"
        ordering = ["-date_debut"]

    def __str__(self):
        return f"{self.titre} - {self.date_debut.strftime('%d/%m/%Y')}"

    @property
    def duree_minutes(self):
        """Calcule la durée de la session en minutes"""
        if self.date_fin and self.date_debut:
            delta = self.date_fin - self.date_debut
            return int(delta.total_seconds() / 60)
        return 0

    def save(self, *args, **kwargs):
        # Héritage automatique depuis le cours
        if self.cours:
            self.institution = self.cours.institution
            self.annee_scolaire = self.cours.annee_scolaire
        super().save(*args, **kwargs)


# ============================================================================
# PARTICIPATIONS
# ============================================================================

class Participation(models.Model):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="participations"
    )
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="participations"
    )
    source = models.CharField(
        max_length=20,
        choices=[
            ("manuelle", "Manuelle"),
            ("auto", "Automatique"),
        ],
        default="manuelle",
    )
    statut = models.CharField(
        max_length=20,
        choices=[
            ("present", "Présent"),
            ("absent", "Absent"),
            ("retard", "Retard"),
            ("excuse", "Excusé"),
        ],
        default="present",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Rattachement automatique via la session
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="participations",
        null=True, blank=True,
        help_text="Hérité de la session"
    )
    annee_scolaire = models.ForeignKey(
        AnneeScolaire,
        on_delete=models.CASCADE,
        related_name="participations",
        null=True, blank=True,
        help_text="Hérité de la session"
    )

    class Meta:
        verbose_name = "Participation"
        verbose_name_plural = "Participations"
        unique_together = ("session", "apprenant")

    def __str__(self):
        return f"{self.apprenant} - {self.session} ({self.statut})"

    def save(self, *args, **kwargs):
        # Héritage automatique depuis la session
        if self.session:
            self.institution = self.session.institution
            self.annee_scolaire = self.session.annee_scolaire
        super().save(*args, **kwargs)


# ============================================================================
# PROGRESSION
# ============================================================================

class BlocProgress(models.Model):
    """Progression sur un bloc de contenu"""
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="blocs_progress"
    )
    bloc = models.ForeignKey(
        BlocContenu,
        on_delete=models.CASCADE,
        related_name="progress_records"
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Progression bloc"
        verbose_name_plural = "Progressions blocs"
        unique_together = ("apprenant", "bloc")

    def __str__(self):
        return f"{self.apprenant} - {self.bloc.titre}"


class SequenceProgress(models.Model):
    """Progression sur une séquence"""
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="sequences_progress"
    )
    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name="progress_records"
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Progression séquence"
        verbose_name_plural = "Progressions séquences"
        unique_together = ("apprenant", "sequence")

    def __str__(self):
        return f"{self.apprenant} - {self.sequence.titre}"


class ModuleProgress(models.Model):
    """Progression sur un module"""
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="modules_progress"
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="progress_records"
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Progression module"
        verbose_name_plural = "Progressions modules"
        unique_together = ("apprenant", "module")

    def __str__(self):
        return f"{self.apprenant} - {self.module.titre}"


class CoursProgress(models.Model):
    """Progression sur un cours"""
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name="cours_progress"
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name="progress_records"
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Progression cours"
        verbose_name_plural = "Progressions cours"
        unique_together = ("apprenant", "cours")

    def __str__(self):
        return f"{self.apprenant} - {self.cours}"
