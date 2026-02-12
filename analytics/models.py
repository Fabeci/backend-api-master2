from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from courses.models import BlocContenu
from evaluations.models import Question
from users.models import Apprenant

class BlocAnalytics(models.Model):
    """Suivi détaillé de l'interaction avec un bloc"""
    apprenant = models.ForeignKey(
        Apprenant, 
        on_delete=models.CASCADE, 
        related_name='blocs_analytics'
    )
    bloc = models.ForeignKey(
        BlocContenu, 
        on_delete=models.CASCADE, 
        related_name='analytics'
    )
    
    # Temps passé
    temps_total_secondes = models.PositiveIntegerField(default=0)
    nombre_visites = models.PositiveIntegerField(default=0)
    
    # Engagement
    pourcentage_scroll = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    interactions = models.JSONField(default=dict, blank=True)
    
    # Compréhension
    score_comprehension = models.FloatField(null=True, blank=True)
    difficulte_percue = models.IntegerField(
        null=True, 
        blank=True,
        choices=[
            (1, 'Très facile'), 
            (2, 'Facile'), 
            (3, 'Moyen'), 
            (4, 'Difficile'), 
            (5, 'Très difficile')
        ]
    )
    
    # Timestamps
    premiere_visite = models.DateTimeField(auto_now_add=True)
    derniere_visite = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('apprenant', 'bloc')
        verbose_name = "Analytique de bloc"
        verbose_name_plural = "Analytiques de blocs"
        indexes = [
            models.Index(fields=['apprenant', 'temps_total_secondes']),
            models.Index(fields=['bloc', 'score_comprehension']),
        ]
    
    def __str__(self):
        return f"{self.apprenant.nom} - {self.bloc.titre} ({self.temps_total_secondes}s)"


class QuestionAnalytics(models.Model):
    """Analyse des erreurs sur une question"""
    apprenant = models.ForeignKey(
        Apprenant, 
        on_delete=models.CASCADE, 
        related_name='questions_analytics'
    )
    question = models.ForeignKey(
        Question, 
        on_delete=models.CASCADE, 
        related_name='analytics'
    )
    
    nombre_tentatives = models.PositiveIntegerField(default=0)
    nombre_echecs = models.PositiveIntegerField(default=0)
    temps_moyen_reponse_sec = models.FloatField(default=0.0)
    
    # Pour QCM : pattern d'erreurs
    erreurs_frequentes = models.JSONField(
        default=list, 
        blank=True,
        help_text="IDs des mauvaises réponses choisies"
    )
    
    # Concepts non maîtrisés
    concepts_fragiles = models.JSONField(
        default=list, 
        blank=True,
        help_text="Ex: ['boucles', 'variables']"
    )
    
    derniere_tentative = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('apprenant', 'question')
        verbose_name = "Analytique de question"
        verbose_name_plural = "Analytiques de questions"
    
    def __str__(self):
        return f"{self.apprenant.nom} - Q{self.question.id} (échecs: {self.nombre_echecs})"


class ContenuGenere(models.Model):
    """Contenu pédagogique généré par IA"""
    TYPE_GENERATION = [
        ('remediation', 'Remédiation (après échec)'),
        ('approfondissement', 'Approfondissement'),
        ('simplification', 'Simplification'),
        ('alternative', 'Approche alternative'),
    ]
    
    apprenant = models.ForeignKey(
        Apprenant, 
        on_delete=models.CASCADE, 
        related_name='contenus_generes'
    )
    bloc_source = models.ForeignKey(
        BlocContenu, 
        on_delete=models.CASCADE, 
        related_name='contenus_generes'
    )
    
    type_generation = models.CharField(max_length=20, choices=TYPE_GENERATION)
    
    # Contenu généré
    titre = models.CharField(max_length=255)
    contenu_html = models.TextField()
    contenu_markdown = models.TextField(blank=True, default="")
    
    # Métadonnées
    concepts_cibles = models.JSONField(
        default=list, 
        blank=True,
        help_text="Ex: ['variables', 'types']"
    )
    niveau_difficulte = models.IntegerField(
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    
    # Efficacité
    a_ete_consulte = models.BooleanField(default=False)
    a_aide = models.BooleanField(
        null=True, 
        blank=True,
        help_text="Feedback apprenant"
    )
    nombre_consultations = models.PositiveIntegerField(default=0)
    
    date_generation = models.DateTimeField(auto_now_add=True)
    date_derniere_consultation = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-date_generation']
        verbose_name = "Contenu généré"
        verbose_name_plural = "Contenus générés"
    
    def __str__(self):
        return f"{self.titre} (pour {self.apprenant.nom})"


class RecommandationPedagogique(models.Model):
    """Recommandations personnalisées pour l'apprenant"""
    TYPE_RECO = [
        ('bloc_revoir', 'Revoir un bloc'),
        ('quiz_supplementaire', 'Quiz supplémentaire'),
        ('pause', 'Pause recommandée'),
        ('changement_approche', 'Changer d\'approche'),
        ('contenu_alternatif', 'Contenu alternatif disponible'),
    ]
    
    apprenant = models.ForeignKey(
        Apprenant, 
        on_delete=models.CASCADE, 
        related_name='recommandations'
    )
    
    type_recommandation = models.CharField(max_length=30, choices=TYPE_RECO)
    message = models.TextField()
    
    # Cible
    bloc_cible = models.ForeignKey(
        BlocContenu, 
        null=True, 
        blank=True, 
        on_delete=models.CASCADE
    )
    contenu_genere = models.ForeignKey(
        ContenuGenere, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL
    )
    
    # Priorité & statut
    priorite = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1=haute priorité, 5=basse priorité"
    )
    est_vue = models.BooleanField(default=False)
    est_suivie = models.BooleanField(default=False)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_vue = models.DateTimeField(null=True, blank=True)
    date_expiration = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['priorite', '-date_creation']
        verbose_name = "Recommandation pédagogique"
        verbose_name_plural = "Recommandations pédagogiques"
        indexes = [
            models.Index(fields=['apprenant', 'est_vue', 'date_expiration']),
        ]
    
    def __str__(self):
        return f"{self.apprenant.nom} - {self.get_type_recommandation_display()}"