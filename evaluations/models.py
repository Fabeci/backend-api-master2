from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from courses.models import Sequence, Cours


# ============================================================================
# QUIZ (Évaluations formatives dans les séquences)
# ============================================================================

class Quiz(models.Model):
    titre = models.CharField(max_length=255)
    sequence = models.ForeignKey(
        Sequence, 
        on_delete=models.CASCADE, 
        related_name='quizz'
    )
    description = models.TextField(blank=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Quizzes"
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.titre} - {self.sequence.titre}"


# ============================================================================
# ÉVALUATIONS (Évaluations sommatives du cours)
# ============================================================================

class Evaluation(models.Model):
    TYPE_CHOICES = [
        ('simple', 'Évaluation simple (texte ou fichier unique)'),
        ('structuree', 'Évaluation structurée (plusieurs questions)'),
    ]
    
    cours = models.ForeignKey(
        Cours, 
        on_delete=models.CASCADE, 
        related_name='evaluations'
    )
    enseignant = models.ForeignKey(
        'users.Formateur',
        on_delete=models.CASCADE,
        related_name='evaluations_creees',
        default=1
    )
    
    titre = models.CharField(max_length=255, null=True)
    type_evaluation = models.CharField(
        max_length=20, 
        choices=TYPE_CHOICES,
        default='structuree'
    )
    bareme = models.FloatField(help_text="Note maximale possible")
    duree_minutes = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Durée limite en minutes (optionnel)"
    )
    
    # Pour les évaluations simples
    consigne_texte = models.TextField(
        blank=True,
        help_text="Consigne de l'évaluation (pour type simple)"
    )
    fichier_sujet = models.FileField(
        upload_to='evaluations/sujets/%Y/%m/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'docx', 'doc', 'txt', 'jpg', 'jpeg', 'png']
        )],
        help_text="Fichier sujet (pour type simple)"
    )
    
    date_debut = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de début de disponibilité"
    )
    date_fin = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de fin de disponibilité"
    )
    
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    est_publiee = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date_creation']

    def clean(self):
        if self.type_evaluation == 'simple':
            if not self.consigne_texte and not self.fichier_sujet:
                raise ValidationError(
                    "Une évaluation simple doit avoir soit une consigne texte, soit un fichier sujet."
                )
        
        if self.date_debut and self.date_fin:
            if self.date_fin <= self.date_debut:
                raise ValidationError(
                    "La date de fin doit être postérieure à la date de début."
                )

    def __str__(self):
        return f"{self.titre} - {self.cours.titre} ({self.get_type_evaluation_display()})"

    @property
    def nombre_questions(self):
        """Retourne le nombre de questions (pour évaluations structurées)"""
        return self.questions.count() if self.type_evaluation == 'structuree' else 0

    def est_accessible(self):
        """Vérifie si l'évaluation est accessible pour passer"""
        if not self.est_publiee:
            return False
        
        now = timezone.now()
        
        if self.date_debut and now < self.date_debut:
            return False
        
        if self.date_fin and now > self.date_fin:
            return False
        
        return True

    def peut_soumettre(self):
        """Vérifie si on peut encore soumettre (respecte date_fin)"""
        if not self.est_publiee:
            return False
        
        now = timezone.now()
        
        if self.date_fin and now > self.date_fin:
            return False
        
        return True

    def est_auto_corrigeable(self):
        """Détermine si l'évaluation est 100% auto-corrigeable (QCM uniquement)"""
        if self.type_evaluation == 'simple':
            return False
        
        questions = self.questions.all()
        if not questions.exists():
            return False
        
        # Vérifie que TOUTES les questions sont des QCM
        return all(
            q.type_question in ['choix_unique', 'choix_multiple'] 
            for q in questions
        )


# ============================================================================
# QUESTIONS (Pour Quiz et Évaluations structurées)
# ============================================================================

class Question(models.Model):
    TYPE_CHOICES_QUIZ = [
        ('choix_unique', 'Choix unique (QCM)'),
        ('choix_multiple', 'Choix multiple (QCM)'),
    ]
    
    TYPE_CHOICES_EVALUATION = [
        ('choix_unique', 'Choix unique (QCM)'),
        ('choix_multiple', 'Choix multiple (QCM)'),
        ('texte_court', 'Réponse textuelle courte'),
        ('texte_long', 'Réponse textuelle longue (dissertation)'),
        ('fichier', 'Réponse en fichier'),
        ('texte_ou_fichier', 'Réponse textuelle ou fichier'),
    ]
    
    MODE_CORRECTION = [
        ('automatique', 'Correction automatique'),
        ('manuelle', 'Correction manuelle'),
    ]
    
    # Appartenance (mutuellement exclusive)
    quiz = models.ForeignKey(
        Quiz, 
        on_delete=models.CASCADE, 
        related_name='questions', 
        null=True, 
        blank=True
    )
    evaluation = models.ForeignKey(
        Evaluation, 
        on_delete=models.CASCADE, 
        related_name='questions', 
        null=True, 
        blank=True
    )
    
    # Contenu de la question
    enonce_texte = models.TextField()
    fichier_enonce = models.FileField(
        upload_to='questions/enonces/%Y/%m/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'docx', 'doc', 'jpg', 'jpeg', 'png', 'gif']
        )],
        help_text="Fichier annexe à l'énoncé (image, document...)"
    )
    
    type_question = models.CharField(max_length=30, choices=TYPE_CHOICES_EVALUATION)
    mode_correction = models.CharField(
        max_length=20, 
        choices=MODE_CORRECTION,
        default='automatique',
    )
    
    points = models.FloatField(
        default=1.0, 
        help_text="Nombre de points pour cette question"
    )
    ordre = models.PositiveIntegerField(
        default=0, 
        help_text="Ordre d'affichage"
    )
    
    # Pour les réponses textuelles/fichiers
    indication_reponse = models.TextField(
        blank=True,
        help_text="Indication pour guider l'apprenant (éléments attendus, format...)"
    )

    class Meta:
        ordering = ['ordre']

    @classmethod
    def get_type_choices_for_context(cls, quiz=None, evaluation=None):
        """Retourne les choix de type_question selon le contexte"""
        if quiz:
            return cls.TYPE_CHOICES_QUIZ
        elif evaluation:
            return cls.TYPE_CHOICES_EVALUATION
        else:
            return cls.TYPE_CHOICES_EVALUATION

    def get_allowed_type_choices(self):
        """Retourne les choix de type_question autorisés pour cette instance"""
        return self.get_type_choices_for_context(self.quiz, self.evaluation)

    def clean(self):
        """Validation complète de la question"""
        
        # 1. Vérifier l'appartenance exclusive
        if not self.quiz and not self.evaluation:
            raise ValidationError(
                "Une question doit être associée à un quiz ou une évaluation."
            )
        if self.quiz and self.evaluation:
            raise ValidationError(
                "Une question ne peut pas être associée à la fois à un quiz et une évaluation."
            )
        
        # 2. Vérifier que le type est autorisé selon le contexte
        allowed_choices = self.get_allowed_type_choices()
        allowed_values = [choice[0] for choice in allowed_choices]
        
        if self.type_question not in allowed_values:
            if self.quiz:
                raise ValidationError({
                    'type_question': 
                    f"Les quiz n'acceptent que les questions à choix (QCM). "
                    f"Type '{self.get_type_question_display()}' non autorisé."
                })
        
        # 3. Validation spécifique pour les quiz
        if self.quiz and self.type_question not in ['choix_unique', 'choix_multiple']:
            raise ValidationError({
                'type_question': 
                "Les quiz n'acceptent que les questions à choix unique ou multiple."
            })
        
        # 4. Vérifier la cohérence type/correction
        types_auto = ['choix_unique', 'choix_multiple']
        types_manuels = ['texte_court', 'texte_long', 'fichier', 'texte_ou_fichier']
        
        if self.type_question in types_auto and self.mode_correction == 'manuelle':
            raise ValidationError(
                "Les questions à choix doivent avoir une correction automatique."
            )
        
        if self.type_question in types_manuels and self.mode_correction == 'automatique':
            raise ValidationError(
                "Les questions textuelles/fichiers nécessitent une correction manuelle."
            )

    def save(self, *args, **kwargs):
        """Sauvegarde avec définition automatique du mode de correction"""
        
        # Définir automatiquement le mode de correction AVANT la validation
        if self.type_question in ['choix_unique', 'choix_multiple']:
            self.mode_correction = 'automatique'
        else:
            self.mode_correction = 'manuelle'
        
        # Valider
        self.full_clean()
        
        # Sauvegarder
        super().save(*args, **kwargs)

    def __str__(self):
        try:
            parent = self.quiz or self.evaluation
            return f"[{self.get_type_question_display()}] {self.enonce_texte[:50]}... ({parent})"
        except:
            return f"Question {self.id if self.id else 'nouvelle'}"

    @property
    def necessite_correction_manuelle(self):
        """Indique si la question nécessite une correction manuelle"""
        return self.mode_correction == 'manuelle'
    
    @property
    def est_qcm(self):
        """Indique si la question est un QCM"""
        return self.type_question in ['choix_unique', 'choix_multiple']
    
    @property
    def accepte_reponses_predefinies(self):
        """Indique si la question peut avoir des réponses prédéfinies"""
        return self.est_qcm


# ============================================================================
# RÉPONSES PRÉDÉFINIES (Pour QCM uniquement)
# ============================================================================

class Reponse(models.Model):
    question = models.ForeignKey(
        Question, 
        on_delete=models.CASCADE, 
        related_name='reponses_predefinies'
    )
    texte = models.TextField()
    est_correcte = models.BooleanField(
        default=False,
        help_text="Indique si cette réponse est correcte"
    )
    ordre = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['ordre']
        verbose_name = "Réponse prédéfinie"
        verbose_name_plural = "Réponses prédéfinies"

    def clean(self):
        # Vérifier que la question est bien un QCM
        if self.question.type_question not in ['choix_unique', 'choix_multiple']:
            raise ValidationError(
                "Les réponses prédéfinies ne sont valables que pour les questions à choix."
            )
        
        # Vérifier qu'il n'y a qu'une seule bonne réponse pour choix unique
        if self.question.type_question == 'choix_unique' and self.est_correcte:
            autres_correctes = Reponse.objects.filter(
                question=self.question, 
                est_correcte=True
            ).exclude(pk=self.pk)
            
            if autres_correctes.exists():
                raise ValidationError(
                    "Une question à choix unique ne peut avoir qu'une seule réponse correcte."
                )

    def __str__(self):
        statut = "✓" if self.est_correcte else "✗"
        return f"{statut} {self.texte[:50]}..."


# ============================================================================
# PASSAGES D'ÉVALUATIONS PAR LES APPRENANTS
# ============================================================================

class PassageEvaluation(models.Model):
    """
    Statuts clarifiés selon nouvelle logique:
    - en_cours: L'apprenant a démarré, peut sauvegarder et reprendre
    - soumis: L'apprenant a soumis, plus aucune modification possible
    - corrige: La note finale est validée (automatique ou enseignant)
    """
    STATUT_CHOICES = [
        ('en_cours', 'En cours'),
        ('soumis', 'Soumis'),
        ('corrige', 'Corrigé'),
    ]
    
    apprenant = models.ForeignKey(
        'users.Apprenant', 
        on_delete=models.CASCADE, 
        related_name='evaluations_passees'
    )
    evaluation = models.ForeignKey(
        Evaluation, 
        on_delete=models.CASCADE, 
        related_name='passages'
    )
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='en_cours'
    )
    
    # Pour évaluation simple
    reponse_texte = models.TextField(
        blank=True,
        help_text="Réponse textuelle (pour évaluation simple)"
    )
    fichier_reponse = models.FileField(
        upload_to='evaluations/reponses/%Y/%m/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'docx', 'doc', 'txt', 'zip', 'jpg', 'jpeg', 'png']
        )],
        help_text="Fichier réponse (pour évaluation simple)"
    )
    
    # Notation
    note = models.FloatField(
        null=True,
        blank=True,
        help_text="Note finale obtenue"
    )
    commentaire_enseignant = models.TextField(
        blank=True,
        help_text="Commentaire général de l'enseignant"
    )
    
    # Dates
    date_debut = models.DateTimeField(auto_now_add=True)
    date_soumission = models.DateTimeField(null=True, blank=True)
    date_correction = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('apprenant', 'evaluation')
        verbose_name = "Passage d'évaluation"
        verbose_name_plural = "Passages d'évaluations"
        ordering = ['-date_debut']

    def clean(self):
        if self.note is not None:
            if self.note < 0:
                raise ValidationError("La note ne peut pas être négative.")
            if self.note > self.evaluation.bareme:
                raise ValidationError(
                    f"La note ({self.note}) ne peut pas dépasser le barème ({self.evaluation.bareme})."
                )
        
        # Pour évaluation simple soumise, il faut au moins une réponse
        if self.evaluation.type_evaluation == 'simple' and self.statut == 'soumis':
            if not self.reponse_texte and not self.fichier_reponse:
                raise ValidationError(
                    "Une réponse (texte ou fichier) est requise pour soumettre l'évaluation."
                )

    def pourcentage(self):
        """Calcule le pourcentage de réussite"""
        if self.note is None or self.evaluation.bareme == 0:
            return None
        return round((self.note / self.evaluation.bareme) * 100, 2)

    def __str__(self):
        note_str = f"{self.note}/{self.evaluation.bareme}" if self.note is not None else "Non corrigé"
        return f"{self.apprenant} - {self.evaluation.titre} - {note_str}"

    @property
    def est_corrige(self):
        return self.statut == 'corrige'

    @property
    def necessite_correction(self):
        """Vérifie si l'évaluation nécessite une correction manuelle"""
        if self.evaluation.type_evaluation == 'simple':
            return True
        
        # Pour évaluations structurées, vérifier si au moins une question nécessite correction manuelle
        return self.reponses_questions.filter(
            question__mode_correction='manuelle'
        ).exists()

    def peut_etre_repris(self):
        """Détermine si le passage peut être repris (statut en_cours + dans la fenêtre)"""
        if self.statut != 'en_cours':
            return False
        
        return self.evaluation.peut_soumettre()

    def peut_etre_soumis(self):
        """Détermine si le passage peut être soumis"""
        if self.statut != 'en_cours':
            return False
        
        return self.evaluation.peut_soumettre()

    def auto_corriger(self):
        """
        Auto-correction pour les évaluations 100% QCM
        Retourne True si l'auto-correction a été effectuée, False sinon
        """
        if not self.evaluation.est_auto_corrigeable():
            return False
        
        # Auto-corriger toutes les questions QCM
        for reponse in self.reponses_questions.all():
            if reponse.question.mode_correction == 'automatique':
                reponse.calculer_points_automatique()
        
        # Calculer la note finale
        total_points = sum(
            float(r.points_obtenus or 0) 
            for r in self.reponses_questions.all()
        )
        
        self.note = total_points
        self.statut = 'corrige'
        self.date_correction = timezone.now()
        self.save()
        
        return True

    def auto_corriger_qcm_uniquement(self):
        """Auto-corriger uniquement les QCM (pour évaluations mixtes)"""
        for reponse in self.reponses_questions.filter(
            question__mode_correction='automatique'
        ):
            reponse.calculer_points_automatique()


# ============================================================================
# RÉPONSES AUX QUESTIONS (Pour évaluations structurées)
# ============================================================================

class ReponseQuestion(models.Model):
    """
    Statuts clarifiés:
    - non_repondu: Question pas encore traitée
    - repondu: Question répondue mais pas encore corrigée
    - corrige: Question corrigée (auto ou manuelle)
    """
    STATUT_CHOICES = [
        ('non_repondu', 'Non répondu'),
        ('repondu', 'Répondu'),
        ('corrige', 'Corrigé'),
    ]
    
    passage_evaluation = models.ForeignKey(
        PassageEvaluation,
        on_delete=models.CASCADE,
        related_name='reponses_questions'
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='reponses_apprenants'
    )
    
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='non_repondu'
    )
    
    # Pour les questions à choix (QCM)
    choix_selectionnes = models.ManyToManyField(
        Reponse,
        blank=True,
        related_name='selections_apprenants'
    )
    
    # Pour les questions textuelles
    reponse_texte = models.TextField(
        blank=True,
        help_text="Réponse textuelle de l'apprenant"
    )
    
    # Pour les questions nécessitant un fichier
    fichier_reponse = models.FileField(
        upload_to='questions/reponses/%Y/%m/',
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'docx', 'doc', 'txt', 'zip', 'jpg', 'jpeg', 'png']
        )],
        help_text="Fichier réponse de l'apprenant"
    )
    
    # Notation
    points_obtenus = models.FloatField(
        default=0.0,
        help_text="Points obtenus pour cette question"
    )
    commentaire_correcteur = models.TextField(
        blank=True,
        help_text="Commentaire du correcteur pour cette question"
    )
    
    date_reponse = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    date_correction = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('passage_evaluation', 'question')
        verbose_name = "Réponse à une question"
        verbose_name_plural = "Réponses aux questions"
        ordering = ['question__ordre']

    def clean(self):
        # Vérifier que la question appartient bien à l'évaluation
        if self.question.evaluation != self.passage_evaluation.evaluation:
            raise ValidationError(
                "La question ne fait pas partie de cette évaluation."
            )
        
        # Vérifier la cohérence des réponses selon le type
        if self.question.type_question in ['choix_unique', 'choix_multiple']:
            if self.reponse_texte or self.fichier_reponse:
                raise ValidationError(
                    "Les questions à choix ne peuvent pas avoir de réponse texte ou fichier."
                )
        
        if self.question.type_question in ['texte_court', 'texte_long']:
            if self.fichier_reponse or self.choix_selectionnes.exists():
                raise ValidationError(
                    "Les questions textuelles ne peuvent pas avoir de fichier ou de choix sélectionnés."
                )
        
        if self.question.type_question == 'fichier':
            if self.reponse_texte or self.choix_selectionnes.exists():
                raise ValidationError(
                    "Les questions fichier ne peuvent pas avoir de texte ou de choix sélectionnés."
                )
        
        # Vérifier les points
        if self.points_obtenus < 0:
            raise ValidationError("Les points ne peuvent pas être négatifs.")
        if self.points_obtenus > self.question.points:
            raise ValidationError(
                f"Les points obtenus ({self.points_obtenus}) ne peuvent pas dépasser "
                f"les points de la question ({self.question.points})."
            )

    def calculer_points_automatique(self):
        """Calcule automatiquement les points pour les QCM"""
        if self.question.mode_correction != 'automatique':
            return None
        
        choix_corrects = set(
            self.question.reponses_predefinies.filter(est_correcte=True).values_list('id', flat=True)
        )
        choix_selectionnes = set(self.choix_selectionnes.values_list('id', flat=True))
        
        if self.question.type_question == 'choix_unique':
            # Choix unique : tout ou rien
            if choix_selectionnes == choix_corrects:
                self.points_obtenus = self.question.points
            else:
                self.points_obtenus = 0.0
        
        elif self.question.type_question == 'choix_multiple':
            # Choix multiple : proportionnel
            if not choix_corrects:
                self.points_obtenus = 0.0
            else:
                bonnes_reponses = len(choix_selectionnes & choix_corrects)
                mauvaises_reponses = len(choix_selectionnes - choix_corrects)
                total_correct = len(choix_corrects)
                
                # Formule : (bonnes - mauvaises) / total_correct * points_max
                score = (bonnes_reponses - mauvaises_reponses) / total_correct
                self.points_obtenus = max(0, score * self.question.points)
        
        self.statut = 'corrige'
        self.date_correction = timezone.now()
        self.save()
        return self.points_obtenus

    def __str__(self):
        return f"{self.passage_evaluation.apprenant} - Q: {self.question.enonce_texte[:30]}..."

    @property
    def pourcentage_reussite(self):
        """Retourne le pourcentage de réussite pour cette question"""
        if self.question.points == 0:
            return 0
        return round((self.points_obtenus / self.question.points) * 100, 2)


# ============================================================================
# PASSAGES DE QUIZ
# ============================================================================

class PassageQuiz(models.Model):
    """Similaire à PassageEvaluation mais pour les quiz formatifs"""
    apprenant = models.ForeignKey(
        'users.Apprenant',
        on_delete=models.CASCADE,
        related_name='quiz_passes'
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='passages'
    )
    
    score = models.FloatField(default=0.0)
    date_passage = models.DateTimeField(auto_now_add=True)
    termine = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Passage de quiz"
        verbose_name_plural = "Passages de quiz"
        ordering = ['-date_passage']

    def __str__(self):
        return f"{self.apprenant} - {self.quiz.titre} - {self.score}pts"

    def calculer_score(self):
        """Calcule le score total du quiz"""
        total_points = 0
        for reponse in self.reponses_quiz.all():
            if reponse.question.mode_correction == 'automatique':
                reponse.calculer_points_automatique()
            total_points += reponse.points_obtenus
        
        self.score = total_points
        self.save()
        return self.score


class ReponseQuiz(models.Model):
    """Réponses aux questions de quiz"""
    passage_quiz = models.ForeignKey(
        PassageQuiz,
        on_delete=models.CASCADE,
        related_name='reponses_quiz'
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='reponses_quiz'
    )
    
    choix_selectionnes = models.ManyToManyField(
        Reponse,
        blank=True,
        related_name='selections_quiz'
    )
    
    points_obtenus = models.FloatField(default=0.0)
    date_reponse = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('passage_quiz', 'question')
        verbose_name = "Réponse de quiz"
        verbose_name_plural = "Réponses de quiz"

    def calculer_points_automatique(self):
        """Calcule automatiquement les points (identique à ReponseQuestion)"""
        if self.question.mode_correction != 'automatique':
            return None
        
        choix_corrects = set(
            self.question.reponses_predefinies.filter(est_correcte=True).values_list('id', flat=True)
        )
        choix_selectionnes = set(self.choix_selectionnes.values_list('id', flat=True))
        
        if self.question.type_question == 'choix_unique':
            if choix_selectionnes == choix_corrects:
                self.points_obtenus = self.question.points
            else:
                self.points_obtenus = 0.0
        
        elif self.question.type_question == 'choix_multiple':
            if not choix_corrects:
                self.points_obtenus = 0.0
            else:
                bonnes_reponses = len(choix_selectionnes & choix_corrects)
                mauvaises_reponses = len(choix_selectionnes - choix_corrects)
                total_correct = len(choix_corrects)
                
                score = (bonnes_reponses - mauvaises_reponses) / total_correct
                self.points_obtenus = max(0, score * self.question.points)
        
        self.save()
        return self.points_obtenus

    def __str__(self):
        return f"{self.passage_quiz.apprenant} - Quiz Q: {self.question.enonce_texte[:30]}..."