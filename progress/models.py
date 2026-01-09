# progress/models.py

from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import Sum, Avg, Count, Q

from users.models import Apprenant
from courses.models import Cours, Module, Sequence
from evaluations.models import Quiz, Evaluation, PassageQuiz, PassageEvaluation


# ============================================================================
# PROGRESSION APPRENANT (Modèle principal)
# ============================================================================

class ProgressionApprenant(models.Model):
    """
    Progression globale d'un apprenant dans un cours.
    Lié à InscriptionCours pour garantir la cohérence.
    """
    
    STATUT_CHOICES = [
        ('non_commence', 'Non commencé'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('abandonne', 'Abandonné'),
        ('suspendu', 'Suspendu'),
    ]
    
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name='progressions_cours'
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='progressions_apprenants'
    )
    
    # Dates de suivi
    date_debut = models.DateTimeField(auto_now_add=True)
    date_derniere_activite = models.DateTimeField(auto_now=True)
    date_completion = models.DateTimeField(null=True, blank=True)
    
    # Métriques de progression
    pourcentage_completion = models.FloatField(
        default=0.0,
        help_text="Pourcentage de completion du cours (0-100)"
    )
    temps_total_minutes = models.IntegerField(
        default=0,
        help_text="Temps total passé sur le cours en minutes"
    )
    
    # Statut
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='non_commence'
    )
    
    # Dernière position
    derniere_sequence = models.ForeignKey(
        Sequence,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='progressions_en_cours',
        help_text="Dernière séquence consultée"
    )
    
    dernier_module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='progressions_en_cours',
        help_text="Dernier module consulté"
    )
    
    # Métriques de performance
    note_moyenne_evaluations = models.FloatField(
        null=True,
        blank=True,
        help_text="Note moyenne sur toutes les évaluations du cours"
    )
    taux_reussite_quiz = models.FloatField(
        default=0.0,
        help_text="Taux de réussite moyen sur les quiz"
    )
    
    class Meta:
        unique_together = ('apprenant', 'cours')
        verbose_name = "Progression de l'apprenant"
        verbose_name_plural = "Progressions des apprenants"
        ordering = ['-date_derniere_activite']
        indexes = [
            models.Index(fields=['apprenant', 'cours']),
            models.Index(fields=['statut']),
            models.Index(fields=['-date_derniere_activite']),
        ]
    
    def __str__(self):
        return f"{self.apprenant.prenom} {self.apprenant.nom} - {self.cours.titre} ({self.pourcentage_completion:.1f}%)"
    
    def clean(self):
        """Validation métier"""
        # Vérifier que l'apprenant est inscrit au cours
        from courses.models import InscriptionCours
        if not InscriptionCours.objects.filter(
            apprenant=self.apprenant,
            cours=self.cours
        ).exists():
            raise ValidationError(
                f"L'apprenant {self.apprenant} n'est pas inscrit au cours {self.cours}"
            )
        
        # Normaliser le pourcentage
        if self.pourcentage_completion < 0:
            self.pourcentage_completion = 0.0
        if self.pourcentage_completion > 100:
            self.pourcentage_completion = 100.0
    
    def save(self, *args, **kwargs):
        self.clean()
        
        # Mettre à jour le statut automatiquement
        if self.pourcentage_completion == 0:
            self.statut = 'non_commence'
        elif self.pourcentage_completion >= 100:
            self.statut = 'termine'
            if not self.date_completion:
                self.date_completion = timezone.now()
        elif self.pourcentage_completion > 0:
            if self.statut == 'non_commence':
                self.statut = 'en_cours'
        
        super().save(*args, **kwargs)
    
    def calculer_progression(self):
        """
        Calcule le pourcentage de completion du cours.
        Pondération : 60% modules, 30% quiz, 10% évaluations
        """
        # 1. Progression des modules (60%)
        total_modules = self.cours.modules.count()
        if total_modules > 0:
            modules_termines = self.progressions_modules.filter(
                est_termine=True
            ).count()
            progression_modules = (modules_termines / total_modules) * 60
        else:
            progression_modules = 0
        
        # 2. Progression des quiz (30%)
        total_quiz = Quiz.objects.filter(
            sequence__module__cours=self.cours
        ).count()
        
        if total_quiz > 0:
            quiz_reussis = self.progressions_quiz.filter(
                pourcentage_reussite__gte=50
            ).count()
            progression_quiz = (quiz_reussis / total_quiz) * 30
        else:
            progression_quiz = 0
        
        # 3. Progression des évaluations (10%)
        # On compte les évaluations soumises/corrigées
        total_evaluations = self.cours.evaluations.filter(
            est_publiee=True
        ).count()
        
        if total_evaluations > 0:
            evaluations_passees = PassageEvaluation.objects.filter(
                apprenant=self.apprenant,
                evaluation__cours=self.cours,
                statut__in=['soumis', 'corrige']
            ).count()
            progression_evaluations = (evaluations_passees / total_evaluations) * 10
        else:
            progression_evaluations = 0
        
        # Total
        self.pourcentage_completion = round(
            progression_modules + progression_quiz + progression_evaluations,
            2
        )
        self.save()
        return self.pourcentage_completion
    
    def calculer_note_moyenne_evaluations(self):
        """Calcule la note moyenne sur toutes les évaluations du cours"""
        passages = PassageEvaluation.objects.filter(
            apprenant=self.apprenant,
            evaluation__cours=self.cours,
            note__isnull=False
        )
        
        if not passages.exists():
            self.note_moyenne_evaluations = None
            self.save()
            return None
        
        # Calculer la moyenne pondérée par le barème
        total_notes = sum(float(p.note) for p in passages)
        total_baremes = sum(float(p.evaluation.bareme) for p in passages)
        
        if total_baremes == 0:
            self.note_moyenne_evaluations = None
        else:
            # Note sur 20
            self.note_moyenne_evaluations = round((total_notes / total_baremes) * 20, 2)
        
        self.save()
        return self.note_moyenne_evaluations
    
    def calculer_taux_reussite_quiz(self):
        """Calcule le taux de réussite moyen sur les quiz"""
        quiz_passes = self.progressions_quiz.all()
        
        if not quiz_passes.exists():
            self.taux_reussite_quiz = 0.0
            self.save()
            return 0.0
        
        moyenne = quiz_passes.aggregate(
            avg=Avg('pourcentage_reussite')
        )['avg'] or 0.0
        
        self.taux_reussite_quiz = round(moyenne, 2)
        self.save()
        return self.taux_reussite_quiz
    
    @property
    def temps_total_formate(self):
        """Retourne le temps total formaté"""
        heures = self.temps_total_minutes // 60
        minutes = self.temps_total_minutes % 60
        return f"{heures}h {minutes:02d}min"
    
    @property
    def est_termine(self):
        return self.statut == 'termine'
    
    @property
    def nombre_evaluations_reussies(self):
        """Nombre d'évaluations réussies (note >= 50% du barème)"""
        return PassageEvaluation.objects.filter(
            apprenant=self.apprenant,
            evaluation__cours=self.cours,
            note__isnull=False
        ).annotate(
            pourcentage=models.F('note') * 100.0 / models.F('evaluation__bareme')
        ).filter(
            pourcentage__gte=50
        ).count()


# ============================================================================
# PROGRESSION MODULE
# ============================================================================

class ProgressionModule(models.Model):
    """Progression d'un apprenant dans un module"""
    
    progression_apprenant = models.ForeignKey(
        ProgressionApprenant,
        on_delete=models.CASCADE,
        related_name='progressions_modules'
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='progressions'
    )
    
    date_debut = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    temps_passe_minutes = models.IntegerField(default=0)
    
    est_termine = models.BooleanField(default=False)
    pourcentage_completion = models.FloatField(default=0.0)
    
    class Meta:
        unique_together = ('progression_apprenant', 'module')
        verbose_name = "Progression dans un module"
        verbose_name_plural = "Progressions dans les modules"
        ordering = ['module__id']
    
    def __str__(self):
        return f"{self.progression_apprenant.apprenant.prenom} - {self.module.titre}"
    
    def calculer_progression(self):
        """Calcule le pourcentage de completion du module"""
        total_sequences = self.module.sequences.count()
        if total_sequences == 0:
            self.pourcentage_completion = 100.0
            self.est_termine = True
            return self.pourcentage_completion
        
        sequences_terminees = self.progressions_sequences.filter(
            est_terminee=True
        ).count()
        
        self.pourcentage_completion = round(
            (sequences_terminees / total_sequences) * 100,
            2
        )
        
        if self.pourcentage_completion >= 100:
            self.marquer_comme_termine()
        
        self.save()
        return self.pourcentage_completion
    
    def marquer_comme_termine(self):
        """Marque le module comme terminé"""
        if not self.est_termine:
            self.est_termine = True
            self.date_fin = timezone.now()
            self.pourcentage_completion = 100.0
            self.save()
            
            # Mettre à jour la progression globale
            self.progression_apprenant.calculer_progression()
    
    def enregistrer_temps(self, minutes):
        """Ajoute du temps passé sur le module"""
        self.temps_passe_minutes += minutes
        self.save()
        
        # Mettre à jour le temps total du cours
        self.progression_apprenant.temps_total_minutes += minutes
        self.progression_apprenant.save()


# ============================================================================
# PROGRESSION SEQUENCE
# ============================================================================

class ProgressionSequence(models.Model):
    """Progression d'un apprenant dans une séquence"""
    
    progression_module = models.ForeignKey(
        ProgressionModule,
        on_delete=models.CASCADE,
        related_name='progressions_sequences'
    )
    sequence = models.ForeignKey(
        Sequence,
        on_delete=models.CASCADE,
        related_name='progressions'
    )
    
    date_debut = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)
    temps_passe_minutes = models.IntegerField(default=0)
    
    est_terminee = models.BooleanField(default=False)
    pourcentage_completion = models.FloatField(default=0.0)
    
    # Nombre de consultations
    nombre_visites = models.IntegerField(default=0)
    
    class Meta:
        unique_together = ('progression_module', 'sequence')
        verbose_name = "Progression dans une séquence"
        verbose_name_plural = "Progressions dans les séquences"
        ordering = ['sequence__id']
    
    def __str__(self):
        apprenant = self.progression_module.progression_apprenant.apprenant
        return f"{apprenant.prenom} - {self.sequence.titre}"
    
    def marquer_comme_terminee(self):
        """Marque la séquence comme terminée"""
        if not self.est_terminee:
            self.est_terminee = True
            self.date_fin = timezone.now()
            self.pourcentage_completion = 100.0
            self.save()
            
            # Mettre à jour la progression du module
            self.progression_module.calculer_progression()
    
    def enregistrer_visite(self, duree_minutes=0):
        """Enregistre une visite de la séquence"""
        self.nombre_visites += 1
        if duree_minutes > 0:
            self.temps_passe_minutes += duree_minutes
            self.progression_module.enregistrer_temps(duree_minutes)
        self.save()


# ============================================================================
# PROGRESSION QUIZ
# ============================================================================

class ProgressionQuiz(models.Model):
    """
    Progression d'un apprenant dans un quiz.
    Note : Les quiz peuvent être refaits plusieurs fois.
    """
    
    progression_apprenant = models.ForeignKey(
        ProgressionApprenant,
        on_delete=models.CASCADE,
        related_name='progressions_quiz'
    )
    passage_quiz = models.OneToOneField(
        PassageQuiz,
        on_delete=models.CASCADE,
        related_name='progression'
    )
    
    date_passage = models.DateTimeField(auto_now_add=True)
    score = models.FloatField(default=0.0)
    temps_passe_minutes = models.IntegerField(default=0)
    pourcentage_reussite = models.FloatField(default=0.0)
    
    # Nombre de tentatives pour ce quiz (calculé)
    numero_tentative = models.IntegerField(default=1)
    
    class Meta:
        verbose_name = "Progression dans un quiz"
        verbose_name_plural = "Progressions dans les quiz"
        ordering = ['-date_passage']
    
    def __str__(self):
        apprenant = self.progression_apprenant.apprenant
        return f"{apprenant.prenom} - {self.passage_quiz.quiz.titre}"
    
    def save(self, *args, **kwargs):
        # Calculer le numéro de tentative
        if not self.pk:
            self.numero_tentative = ProgressionQuiz.objects.filter(
                progression_apprenant=self.progression_apprenant,
                passage_quiz__quiz=self.passage_quiz.quiz
            ).count() + 1
        
        super().save(*args, **kwargs)
    
    def calculer_pourcentage(self):
        """Calcule le pourcentage de réussite"""
        passage = self.passage_quiz
        total_points = sum(
            float(q.points) for q in passage.quiz.questions.all()
        )
        
        if total_points > 0:
            self.pourcentage_reussite = round(
                (float(passage.score) / total_points) * 100,
                2
            )
            self.score = float(passage.score)
        else:
            self.pourcentage_reussite = 0.0
            self.score = 0.0
        
        self.save()
        
        # Mettre à jour le taux de réussite global
        self.progression_apprenant.calculer_taux_reussite_quiz()
        
        return self.pourcentage_reussite


# ============================================================================
# HISTORIQUE ACTIVITE
# ============================================================================

class HistoriqueActivite(models.Model):
    """Historique de toutes les activités d'un apprenant"""
    
    TYPE_ACTIVITE_CHOICES = [
        ('connexion', 'Connexion'),
        ('deconnexion', 'Déconnexion'),
        ('consultation_cours', 'Consultation de cours'),
        ('consultation_module', 'Consultation de module'),
        ('consultation_sequence', 'Consultation de séquence'),
        ('debut_quiz', 'Début de quiz'),
        ('fin_quiz', 'Fin de quiz'),
        ('debut_evaluation', 'Début d\'évaluation'),
        ('soumission_evaluation', 'Soumission d\'évaluation'),
        ('telechargement_ressource', 'Téléchargement de ressource'),
        ('participation_session', 'Participation à une session'),
        ('autre', 'Autre activité'),
    ]
    
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name='historique_activites'
    )
    
    type_activite = models.CharField(
        max_length=50,
        choices=TYPE_ACTIVITE_CHOICES
    )
    
    # Référence générique
    objet_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type d'objet concerné (cours, quiz, etc.)"
    )
    objet_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="ID de l'objet concerné"
    )
    
    date_activite = models.DateTimeField(auto_now_add=True)
    duree_minutes = models.IntegerField(
        default=0,
        help_text="Durée de l'activité en minutes"
    )
    description = models.TextField(blank=True)
    
    # Données supplémentaires (JSON)
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Métadonnées supplémentaires"
    )
    
    class Meta:
        verbose_name = "Historique d'activité"
        verbose_name_plural = "Historiques d'activités"
        ordering = ['-date_activite']
        indexes = [
            models.Index(fields=['apprenant', '-date_activite']),
            models.Index(fields=['type_activite']),
            models.Index(fields=['objet_type', 'objet_id']),
        ]
    
    def __str__(self):
        return f"{self.apprenant.prenom} - {self.get_type_activite_display()} - {self.date_activite.strftime('%Y-%m-%d %H:%M')}"
    
    @classmethod
    def enregistrer_activite(cls, apprenant, type_activite, objet_type='', objet_id=None, 
                            duree_minutes=0, description='', **metadata):
        """Méthode utilitaire pour enregistrer une activité"""
        return cls.objects.create(
            apprenant=apprenant,
            type_activite=type_activite,
            objet_type=objet_type,
            objet_id=objet_id,
            duree_minutes=duree_minutes,
            description=description,
            metadata=metadata
        )


# ============================================================================
# PLAN D'ACTION
# ============================================================================

class PlanAction(models.Model):
    """Plan d'action personnalisé pour un apprenant"""
    
    STATUT_CHOICES = [
        ('a_faire', 'À faire'),
        ('en_cours', 'En cours'),
        ('termine', 'Terminé'),
        ('annule', 'Annulé'),
    ]
    
    PRIORITE_CHOICES = [
        ('basse', 'Basse'),
        ('moyenne', 'Moyenne'),
        ('haute', 'Haute'),
        ('urgente', 'Urgente'),
    ]
    
    apprenant = models.ForeignKey(
        Apprenant,
        on_delete=models.CASCADE,
        related_name='plans_action'
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='plans_action',
        null=True,
        blank=True,
        help_text="Cours associé (optionnel)"
    )
    
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_echeance = models.DateField(null=True, blank=True)
    date_completion = models.DateTimeField(null=True, blank=True)
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='a_faire'
    )
    priorite = models.CharField(
        max_length=20,
        choices=PRIORITE_CHOICES,
        default='moyenne'
    )
    
    # Créé par (formateur ou apprenant lui-même)
    cree_par = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='plans_action_crees'
    )
    
    class Meta:
        verbose_name = "Plan d'action"
        verbose_name_plural = "Plans d'action"
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.titre} - {self.apprenant.prenom} {self.apprenant.nom}"
    
    @property
    def pourcentage_completion(self):
        """Calcule le pourcentage de completion du plan"""
        total_objectifs = self.objectifs.count()
        if total_objectifs == 0:
            return 0.0
        
        objectifs_completes = self.objectifs.filter(est_complete=True).count()
        return round((objectifs_completes / total_objectifs) * 100, 2)
    
    @property
    def est_en_retard(self):
        """Vérifie si le plan est en retard"""
        if not self.date_echeance:
            return False
        return (
            self.statut not in ['termine', 'annule'] and 
            timezone.now().date() > self.date_echeance
        )
    
    def marquer_comme_termine(self):
        """Marque le plan comme terminé"""
        if self.statut != 'termine':
            self.statut = 'termine'
            self.date_completion = timezone.now()
            self.save()


class ObjectifPlanAction(models.Model):
    """Objectif individuel dans un plan d'action"""
    
    plan_action = models.ForeignKey(
        PlanAction,
        on_delete=models.CASCADE,
        related_name='objectifs'
    )
    
    titre = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    est_complete = models.BooleanField(default=False)
    date_completion = models.DateTimeField(null=True, blank=True)
    
    ordre = models.PositiveIntegerField(default=0)
    
    class Meta:
        verbose_name = "Objectif de plan d'action"
        verbose_name_plural = "Objectifs de plans d'action"
        ordering = ['ordre']
    
    def __str__(self):
        statut = '✓' if self.est_complete else '✗'
        return f"{statut} {self.titre}"
    
    def marquer_comme_complete(self):
        """Marque l'objectif comme complété"""
        if not self.est_complete:
            self.est_complete = True
            self.date_completion = timezone.now()
            self.save()
            
            # Vérifier si tous les objectifs sont complétés
            plan = self.plan_action
            if not plan.objectifs.filter(est_complete=False).exists():
                plan.marquer_comme_termine()
    
    def marquer_comme_incomplete(self):
        """Marque l'objectif comme incomplet"""
        if self.est_complete:
            self.est_complete = False
            self.date_completion = None
            self.save()