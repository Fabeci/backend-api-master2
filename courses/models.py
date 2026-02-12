# courses/models.py
from django.db import models
from django.forms import ValidationError
from django.utils import timezone
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.conf import settings
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
    

class BlocContenu(models.Model):
   
    TYPE_BLOC_CHOICES = [
        ('texte', 'Texte / Explication'),
        ('video', 'Vidéo'),
        ('audio', 'Audio'),
        ('image', 'Image'),
        ('code', 'Exemple de code'),
        ('exercice', 'Exercice pratique'),
        ('quiz', 'Quiz intégré'),
        ('lien', 'Lien externe'),
        ('pdf', 'Document PDF'),
        ('markdown', 'Contenu Markdown'),
    ]
    
    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name="blocs_contenu",
        help_text="Séquence parente"
    )
    
    titre = models.CharField(
        max_length=255,
        help_text="Titre du bloc (ex: 'Introduction aux variables')"
    )
    
    type_bloc = models.CharField(
        max_length=20,
        choices=TYPE_BLOC_CHOICES,
        default='texte'
    )
    
    ordre = models.PositiveIntegerField(
        default=0,
        help_text="Ordre d'affichage dans la séquence"
    )
    
    # Contenu textuel
    contenu_texte = models.TextField(
        blank=True,
        default="",
        help_text="Contenu texte brut"
    )
    
    contenu_html = models.TextField(
        blank=True,
        default="",
        help_text="Contenu HTML enrichi"
    )
    
    contenu_markdown = models.TextField(
        blank=True,
        default="",
        help_text="Contenu en Markdown"
    )
    
    # Médias
    video_url = models.URLField(
        null=True,
        blank=True,
        help_text="URL YouTube, Vimeo, etc."
    )
    
    audio_url = models.URLField(
        null=True,
        blank=True,
        help_text="URL fichier audio"
    )
    
    image = models.ImageField(
        upload_to='sequences/images/%Y/%m/',
        null=True,
        blank=True,
        help_text="Image illustrative"
    )
    
    fichier = models.FileField(
        upload_to='sequences/fichiers/%Y/%m/',
        null=True,
        blank=True,
        help_text="Fichier attaché (PDF, ZIP, etc.)"
    )
    
    lien_externe = models.URLField(
        null=True,
        blank=True,
        help_text="Lien vers une ressource externe"
    )
    
    # Code source
    code_source = models.TextField(
        blank=True,
        default="",
        help_text="Code source à afficher"
    )
    
    langage_code = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Langage du code (python, javascript, etc.)"
    )
    
    # Métadonnées
    objectifs = models.TextField(
        blank=True,
        default="",
        help_text="Objectifs pédagogiques de ce bloc"
    )
    
    duree_estimee_minutes = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Durée estimée pour ce bloc"
    )
    
    est_obligatoire = models.BooleanField(
        default=True,
        help_text="Ce bloc doit-il être consulté obligatoirement ?"
    )
    
    est_visible = models.BooleanField(
        default=True,
        help_text="Le bloc est-il visible pour les apprenants ?"
    )
    
    # Dates
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['sequence', 'ordre']
        verbose_name = "Bloc de contenu"
        verbose_name_plural = "Blocs de contenu"
        unique_together = [['sequence', 'ordre']]
        indexes = [
            models.Index(fields=['sequence', 'ordre']),
            models.Index(fields=['type_bloc']),
        ]
    
    def __str__(self):
        return f"{self.sequence.titre} - Bloc {self.ordre}: {self.titre}"
    
    @property
    def icone_type(self):
        """Retourne une icône selon le type de bloc"""
        icones = {
            'texte': '📝',
            'video': '🎥',
            'audio': '🎵',
            'image': '🖼️',
            'code': '💻',
            'exercice': '✏️',
            'quiz': '❓',
            'lien': '🔗',
            'pdf': '📄',
            'markdown': '📋',
        }
        return icones.get(self.type_bloc, '📦')


class RessourceSequence(models.Model):
    """
    Ressources (pièces jointes) liées à une séquence
    """
    TYPE_RESSOURCE_CHOICES = [
        ('cours', 'Support de cours'),
        ('exercice', 'Fichier d\'exercice'),
        ('correction', 'Correction'),
        ('supplementaire', 'Ressource supplémentaire'),
        ('reference', 'Document de référence'),
    ]
    
    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name='ressources_sequences',
        help_text="Séquence parente"
    )
    
    titre = models.CharField(
        max_length=255,
        help_text="Nom de la ressource"
    )
    
    description = models.TextField(
        blank=True,
        default="",
        help_text="Description de la ressource"
    )
    
    fichier = models.FileField(
        upload_to='sequences/ressources/%Y/%m/',
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    'pdf', 'doc', 'docx', 'ppt', 'pptx', 
                    'xls', 'xlsx', 'zip', 'rar', 
                    'jpg', 'jpeg', 'png', 'gif',
                    'txt', 'md', 'py', 'js', 'html', 'css'
                ]
            )
        ],
        help_text="Fichier de la ressource"
    )
    
    type_ressource = models.CharField(
        max_length=20,
        choices=TYPE_RESSOURCE_CHOICES,
        default='supplementaire'
    )
    
    taille_fichier = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Taille en octets (calculée automatiquement)"
    )
    
    est_telechargeable = models.BooleanField(
        default=True,
        help_text="Le fichier peut-il être téléchargé ?"
    )
    
    nombre_telechargements = models.IntegerField(
        default=0,
        help_text="Nombre de téléchargements"
    )
    
    ordre = models.PositiveIntegerField(
        default=0,
        help_text="Ordre d'affichage"
    )
    
    # Métadonnées
    date_ajout = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    ajoute_par = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ressources_sequences_ajoutees'
    )
    
    class Meta:
        ordering = ['sequence', 'ordre']
        verbose_name = "Ressource de séquence"
        verbose_name_plural = "Ressources de séquences"
        indexes = [
            models.Index(fields=['sequence', 'type_ressource']),
        ]
    
    def __str__(self):
        return f"{self.sequence.titre} - {self.titre}"
    
    def save(self, *args, **kwargs):
        """Calcule automatiquement la taille du fichier"""
        if self.fichier:
            self.taille_fichier = self.fichier.size
        super().save(*args, **kwargs)
    
    @property
    def taille_lisible(self):
        """Retourne la taille en format lisible"""
        if not self.taille_fichier:
            return "N/A"
        
        taille = self.taille_fichier
        for unit in ['octets', 'Ko', 'Mo', 'Go']:
            if taille < 1024.0:
                return f"{taille:.1f} {unit}"
            taille /= 1024.0
        return f"{taille:.1f} To"
    
    @property
    def extension(self):
        """Retourne l'extension du fichier"""
        import os
        return os.path.splitext(self.fichier.name)[1].lower()
    
    @property
    def icone_extension(self):
        """Retourne une icône selon l'extension"""
        ext = self.extension
        icones = {
            '.pdf': '📄',
            '.doc': '📝', '.docx': '📝',
            '.xls': '📊', '.xlsx': '📊',
            '.ppt': '📽️', '.pptx': '📽️',
            '.zip': '🗜️', '.rar': '🗜️',
            '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️',
            '.py': '🐍',
            '.js': '📜',
        }
        return icones.get(ext, '📎')
    
    def incrementer_telechargements(self):
        """Incrémente le compteur de téléchargements"""
        self.nombre_telechargements += 1
        self.save(update_fields=['nombre_telechargements'])


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


class SequenceContent(models.Model):
    sequence = models.OneToOneField(
        Sequence,
        on_delete=models.CASCADE,
        related_name="contenu"
    )
    contenu_texte = models.TextField(blank=True, default="")
    contenu_html = models.TextField(blank=True, default="")
    video_url = models.URLField(null=True, blank=True)
    lien_externe = models.URLField(null=True, blank=True)
    objectifs = models.TextField(blank=True, default="")
    duree_estimee_minutes = models.PositiveIntegerField(default=0)
    est_publie = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Contenu - {self.sequence.titre}"
    
class BlocProgress(models.Model):
    apprenant = models.ForeignKey(
        "users.Apprenant",
        on_delete=models.CASCADE,
        related_name="blocs_progress",
    )
    bloc = models.ForeignKey(
        "courses.BlocContenu",
        on_delete=models.CASCADE,
        related_name="progressions",
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["apprenant", "bloc"],
                name="uniq_progress_apprenant_bloc",
            )
        ]
        indexes = [
            models.Index(fields=["apprenant", "bloc"]),
            models.Index(fields=["apprenant", "est_termine"]),
        ]

    def clean(self):
        # Optionnel mais conseillé: bloc visible + apprenant inscrit au cours du bloc
        if self.bloc_id and self.apprenant_id:
            cours = self.bloc.sequence.module.cours
            if not InscriptionCours.objects.filter(apprenant=self.apprenant, cours=cours).exists():
                raise ValidationError("L'apprenant n'est pas inscrit au cours de ce bloc.")

    def mark_completed(self):
        self.est_termine = True
        self.completed_at = timezone.now()
        self.save(update_fields=["est_termine", "completed_at", "updated_at"])

    def mark_uncompleted(self):
        self.est_termine = False
        self.completed_at = None
        self.save(update_fields=["est_termine", "completed_at", "updated_at"])
    
class SequenceProgress(models.Model):
    apprenant = models.ForeignKey("users.Apprenant", on_delete=models.CASCADE, related_name="sequences_progress")
    sequence = models.ForeignKey(
        "courses.Sequence",
        on_delete=models.CASCADE,
        related_name="courses_progressions",       # ✅ unique
        related_query_name="courses_progression",  # ✅ optionnel mais propre
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

class ModuleProgress(models.Model):
    apprenant = models.ForeignKey("users.Apprenant", on_delete=models.CASCADE, related_name="modules_progress")
    module = models.ForeignKey(
        "courses.Module",
        on_delete=models.CASCADE,
        related_name="courses_progressions",       # ✅ unique
        related_query_name="courses_progression",
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class CoursProgress(models.Model):
    apprenant = models.ForeignKey("users.Apprenant", on_delete=models.CASCADE, related_name="cours_progress")
    cours = models.ForeignKey(
        "courses.Cours",
        on_delete=models.CASCADE,
        related_name="courses_progressions",       # ✅ unique
        related_query_name="courses_progression",
    )
    est_termine = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)



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
