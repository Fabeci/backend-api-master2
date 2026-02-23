# courses/models_ai.py
# ============================================================================
# MODÈLES IA — Blocs et quiz générés par ChatGPT à partir des analytics
#
# Flux :
#   1. analytics détectent un trigger (temps_long ou quiz_raté)
#   2. AIAnalysisRequest créée → envoyée à ChatGPT
#   3. ChatGPT retourne JSON → BlocGenere ou QuizGenere créé
#   4. Frontend affiche le contenu généré dans le panneau AITutor
# ============================================================================
from django.db import models
from django.utils import timezone


class AIAnalysisRequest(models.Model):
    """
    Historique de toutes les requêtes envoyées à ChatGPT.
    Sert à éviter les doublons, auditer les coûts et déboguer.
    """

    TRIGGER_CHOICES = [
        ('temps_long',   'Temps passé trop long sur un bloc'),
        ('quiz_rate',    'Quiz raté ou score faible'),
        ('scroll_faible','Scroll insuffisant (bloc peu lu)'),
        ('multi_reouverture', 'Bloc réouvert plusieurs fois'),
    ]

    STATUS_CHOICES = [
        ('pending',  'En attente'),
        ('success',  'Succès'),
        ('error',    'Erreur'),
        ('skipped',  'Ignoré (doublon récent)'),
    ]

    apprenant   = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='ai_requests')
    bloc        = models.ForeignKey('courses.BlocContenu', on_delete=models.SET_NULL, null=True, blank=True)
    sequence    = models.ForeignKey('courses.Sequence',    on_delete=models.SET_NULL, null=True, blank=True)
    cours       = models.ForeignKey('courses.Cours',       on_delete=models.SET_NULL, null=True, blank=True)
    quiz        = models.ForeignKey('evaluations.Quiz',        on_delete=models.SET_NULL, null=True, blank=True,
                                    help_text='Renseigné uniquement pour le trigger quiz_rate')

    trigger         = models.CharField(max_length=30, choices=TRIGGER_CHOICES)
    status          = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Contexte envoyé à GPT (pour audit/debug)
    prompt_context  = models.JSONField(default=dict, blank=True)
    # Réponse brute de GPT
    gpt_response    = models.TextField(blank=True)
    # Erreur éventuelle
    error_message   = models.TextField(blank=True)

    tokens_used     = models.PositiveIntegerField(default=0)
    created_at      = models.DateTimeField(default=timezone.now)
    completed_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Requête IA'
        verbose_name_plural = 'Requêtes IA'
        ordering            = ['-created_at']
        indexes             = [
            models.Index(fields=['apprenant', 'bloc', 'trigger']),
            models.Index(fields=['apprenant', 'quiz', 'trigger']),
        ]

    def __str__(self):
        return f'[{self.trigger}] {self.apprenant} — {self.status}'


class BlocGenere(models.Model):
    """
    Bloc de contenu simplifié généré par ChatGPT pour aider un apprenant
    qui a mis trop de temps sur un bloc (trigger = temps_long).

    Ce bloc est affiché dans le panneau AITutor du course-player.
    Il n'est PAS inséré dans le cours — il reste une aide contextuelle.
    """

    TYPE_CHOICES = [
        ('explication_simple', 'Explication simplifiée'),
        ('analogie',           'Analogie / métaphore'),
        ('exemples',           'Exemples concrets'),
        ('resume',             'Résumé en points clés'),
        ('faq',                'FAQ — questions fréquentes'),
    ]

    ai_request  = models.OneToOneField(AIAnalysisRequest, on_delete=models.CASCADE, related_name='bloc_genere')
    apprenant   = models.ForeignKey('users.Apprenant',    on_delete=models.CASCADE, related_name='blocs_generes')
    bloc_source = models.ForeignKey('courses.BlocContenu', on_delete=models.SET_NULL, null=True, related_name='blocs_generes')

    type_generation = models.CharField(max_length=30, choices=TYPE_CHOICES, default='explication_simple')

    titre       = models.CharField(max_length=300)
    contenu_html= models.TextField()

    # Concepts ciblés identifiés par GPT
    concepts_cibles = models.JSONField(default=list, blank=True)

    # Feedback de l'apprenant
    a_aide          = models.BooleanField(null=True, blank=True)  # None = pas encore évalué
    feedback_le     = models.DateTimeField(null=True, blank=True)

    a_ete_consulte  = models.BooleanField(default=False)
    consulte_le     = models.DateTimeField(null=True, blank=True)

    created_at  = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name        = 'Bloc généré'
        verbose_name_plural = 'Blocs générés'
        ordering            = ['-created_at']

    def __str__(self):
        return f'Bloc généré — {self.apprenant} → {self.bloc_source}'

    def marquer_consulte(self):
        if not self.a_ete_consulte:
            self.a_ete_consulte = True
            self.consulte_le    = timezone.now()
            self.save(update_fields=['a_ete_consulte', 'consulte_le'])

    def soumettre_feedback(self, a_aide: bool):
        self.a_aide     = a_aide
        self.feedback_le= timezone.now()
        self.save(update_fields=['a_aide', 'feedback_le'])


class QuizGenere(models.Model):
    """
    Quiz de remédiation généré par ChatGPT à partir des questions ratées
    d'un passage de quiz (trigger = quiz_rate).

    Structure JSON stockée dans `questions` :
    [
      {
        "question": "Quelle est la différence entre X et Y ?",
        "type": "qcm",          # qcm | vrai_faux | texte_libre
        "options": ["A", "B", "C", "D"],
        "bonne_reponse": "B",
        "explication": "Parce que..."
      },
      ...
    ]
    """

    ai_request      = models.OneToOneField(AIAnalysisRequest, on_delete=models.CASCADE, related_name='quiz_genere')
    apprenant       = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='quiz_generes')
    quiz_source     = models.ForeignKey('evaluations.Quiz',    on_delete=models.SET_NULL, null=True, related_name='quiz_generes',
                                         help_text='Quiz original dont les questions ont été ratées')

    titre           = models.CharField(max_length=300)
    consigne        = models.TextField(blank=True)

    # Questions générées — liste de dict (voir format ci-dessus)
    questions       = models.JSONField(default=list)

    # Concepts sur lesquels l'apprenant a échoué
    concepts_rates  = models.JSONField(default=list, blank=True)

    # Résultat si l'apprenant a passé ce quiz de remédiation
    score_remediation   = models.SmallIntegerField(null=True, blank=True)  # 0-100
    passe_le            = models.DateTimeField(null=True, blank=True)
    remediation_reussie = models.BooleanField(null=True, blank=True)

    a_ete_consulte  = models.BooleanField(default=False)
    consulte_le     = models.DateTimeField(null=True, blank=True)

    created_at      = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name        = 'Quiz généré'
        verbose_name_plural = 'Quiz générés'
        ordering            = ['-created_at']

    def __str__(self):
        return f'Quiz généré — {self.apprenant} → {self.quiz_source}'

    def marquer_consulte(self):
        if not self.a_ete_consulte:
            self.a_ete_consulte = True
            self.consulte_le    = timezone.now()
            self.save(update_fields=['a_ete_consulte', 'consulte_le'])

    def soumettre_score(self, score: int):
        self.score_remediation    = score
        self.passe_le             = timezone.now()
        self.remediation_reussie  = score >= 60
        self.save(update_fields=['score_remediation', 'passe_le', 'remediation_reussie'])