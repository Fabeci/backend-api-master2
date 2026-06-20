# analytics/models.py
# ============================================================================
# ANALYTICS — Capture des interactions + Contenus générés par IA
# ============================================================================
from django.db import models
from django.utils import timezone


# ============================================================================
# PARTIE 1 : ANALYTICS (interactions apprenant)
# ============================================================================

class BlocAnalytics(models.Model):
    """
    Une entrée = une session d'ouverture d'un bloc par un apprenant.
    Créée au moment où l'apprenant ouvre le bloc, complétée à la fermeture.
    """
    apprenant   = models.ForeignKey('users.Apprenant',    on_delete=models.CASCADE, related_name='bloc_analytics')
    bloc        = models.ForeignKey('courses.BlocContenu', on_delete=models.CASCADE, related_name='analytics_sessions')
    sequence    = models.ForeignKey('courses.Sequence',    on_delete=models.SET_NULL, null=True, blank=True)
    module      = models.ForeignKey('courses.Module',      on_delete=models.SET_NULL, null=True, blank=True)
    cours       = models.ForeignKey('courses.Cours',       on_delete=models.SET_NULL, null=True, blank=True)

    ouvert_le           = models.DateTimeField(default=timezone.now)
    ferme_le            = models.DateTimeField(null=True, blank=True)
    duree_secondes      = models.PositiveIntegerField(default=0)
    scroll_max_pct      = models.PositiveSmallIntegerField(default=0)   # 0-100
    complete_en_session = models.BooleanField(default=False)

    class Meta:
        verbose_name        = 'Session de bloc'
        verbose_name_plural = 'Sessions de blocs'
        ordering            = ['-ouvert_le']
        indexes             = [
            models.Index(fields=['apprenant', 'bloc']),
            models.Index(fields=['apprenant', 'cours']),
        ]

    def __str__(self):
        return f'{self.apprenant} → {self.bloc.titre} ({self.duree_secondes}s)'

    def clore(self, duree_sec: int = 0, scroll_pct: int = 0, complete: bool = False):
        self.ferme_le            = timezone.now()
        self.duree_secondes      = duree_sec or max(0, int((self.ferme_le - self.ouvert_le).total_seconds()))
        self.scroll_max_pct      = scroll_pct
        self.complete_en_session = complete
        self.save(update_fields=['ferme_le', 'duree_secondes', 'scroll_max_pct', 'complete_en_session'])


# ── Résumé (apprenant × bloc) ─────────────────────────────────────────────

class BlocAnalyticsSummary(models.Model):
    """
    Résumé agrégé par (apprenant, bloc). Mis à jour après chaque session.
    Source de vérité pour les indicateurs affichés dans les composants.
    """
    apprenant           = models.ForeignKey('users.Apprenant',    on_delete=models.CASCADE, related_name='bloc_summaries')
    bloc                = models.ForeignKey('courses.BlocContenu', on_delete=models.CASCADE, related_name='analytics_summary')
    sequence            = models.ForeignKey('courses.Sequence',    on_delete=models.SET_NULL, null=True, blank=True)
    module              = models.ForeignKey('courses.Module',      on_delete=models.SET_NULL, null=True, blank=True)
    cours               = models.ForeignKey('courses.Cours',       on_delete=models.SET_NULL, null=True, blank=True)

    nb_ouvertures       = models.PositiveIntegerField(default=0)
    nb_completions      = models.PositiveIntegerField(default=0)

    duree_totale_sec    = models.PositiveIntegerField(default=0)   # Σ toutes sessions
    duree_moy_sec       = models.PositiveIntegerField(default=0)   # Moyenne par session

    # Ratio = temps passé / temps estimé du bloc (en %)
    # < 50 % → rapide, 50-130 % → normal, > 130 % → long
    ratio_temps_pct     = models.SmallIntegerField(default=0)

    scroll_max_pct      = models.PositiveSmallIntegerField(default=0)

    premiere_ouverture  = models.DateTimeField(null=True, blank=True)
    derniere_ouverture  = models.DateTimeField(null=True, blank=True)
    date_completion     = models.DateTimeField(null=True, blank=True)

    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Résumé bloc'
        verbose_name_plural = 'Résumés blocs'
        unique_together     = ('apprenant', 'bloc')

    def recalculer(self):
        sessions = BlocAnalytics.objects.filter(apprenant=self.apprenant, bloc=self.bloc, ferme_le__isnull=False)
        n          = sessions.count()
        total_sec  = sum(s.duree_secondes for s in sessions)
        nb_comp    = sessions.filter(complete_en_session=True).count()
        scroll_max = max((s.scroll_max_pct for s in sessions), default=0)

        self.nb_ouvertures     = n
        self.nb_completions    = nb_comp
        self.duree_totale_sec  = total_sec
        self.duree_moy_sec     = round(total_sec / n) if n else 0
        self.scroll_max_pct    = scroll_max

        est_sec = (getattr(self.bloc, 'duree_estimee_minutes', 0) or 0) * 60
        self.ratio_temps_pct   = round((total_sec / est_sec) * 100) if est_sec else 0

        premier = sessions.order_by('ouvert_le').first()
        dernier = sessions.order_by('-ouvert_le').first()
        if premier: self.premiere_ouverture = premier.ouvert_le
        if dernier: self.derniere_ouverture = dernier.ouvert_le

        if nb_comp and not self.date_completion:
            comp = sessions.filter(complete_en_session=True).order_by('ferme_le').first()
            if comp: self.date_completion = comp.ferme_le

        self.save()


# ── Résumé (apprenant × séquence) ────────────────────────────────────────

class SequenceAnalyticsSummary(models.Model):
    apprenant               = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='sequence_summaries')
    sequence                = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, related_name='analytics_summary')
    module                  = models.ForeignKey('courses.Module',   on_delete=models.SET_NULL, null=True, blank=True)
    cours                   = models.ForeignKey('courses.Cours',    on_delete=models.SET_NULL, null=True, blank=True)

    nb_blocs_consultes      = models.PositiveSmallIntegerField(default=0)
    nb_blocs_total          = models.PositiveSmallIntegerField(default=0)
    nb_blocs_completes      = models.PositiveSmallIntegerField(default=0)

    duree_totale_sec        = models.PositiveIntegerField(default=0)
    duree_estimee_sec       = models.PositiveIntegerField(default=0)
    ratio_temps_pct         = models.SmallIntegerField(default=0)

    nb_quiz_passes          = models.PositiveSmallIntegerField(default=0)
    score_moyen_quiz        = models.SmallIntegerField(default=0)   # 0-100

    premiere_activite       = models.DateTimeField(null=True, blank=True)
    derniere_activite       = models.DateTimeField(null=True, blank=True)
    completee_le            = models.DateTimeField(null=True, blank=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('apprenant', 'sequence')


# ── Résumé (apprenant × module) ──────────────────────────────────────────

class ModuleAnalyticsSummary(models.Model):
    apprenant                   = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='module_summaries')
    module                      = models.ForeignKey('courses.Module',   on_delete=models.CASCADE, related_name='analytics_summary')
    cours                       = models.ForeignKey('courses.Cours',    on_delete=models.SET_NULL, null=True, blank=True)

    nb_sequences_consultees     = models.PositiveSmallIntegerField(default=0)
    nb_sequences_total          = models.PositiveSmallIntegerField(default=0)
    nb_sequences_completes      = models.PositiveSmallIntegerField(default=0)

    nb_blocs_total              = models.PositiveSmallIntegerField(default=0)
    nb_blocs_completes          = models.PositiveSmallIntegerField(default=0)

    duree_totale_sec            = models.PositiveIntegerField(default=0)
    duree_estimee_sec           = models.PositiveIntegerField(default=0)
    ratio_temps_pct             = models.SmallIntegerField(default=0)

    score_moyen_quiz            = models.SmallIntegerField(default=0)
    premiere_activite           = models.DateTimeField(null=True, blank=True)
    derniere_activite           = models.DateTimeField(null=True, blank=True)
    complete_le                 = models.DateTimeField(null=True, blank=True)
    updated_at                  = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('apprenant', 'module')


# ============================================================================
# PARTIE 2 : REQUÊTES IA
# ============================================================================

class AIAnalysisRequest(models.Model):
    """
    Historique de toutes les requêtes envoyées à Claude.
    Sert à éviter les doublons, auditer les coûts et déboguer.
    """
    TRIGGER_CHOICES = [
        ('temps_long',           'Temps passé trop long sur un bloc'),
        ('multi_reouverture',    'Bloc rouvert plusieurs fois'),
        ('quiz_rate',           'Quiz raté ou score faible'),
        ('sequence_complexe',    'Séquence trop complexe'),
        ('module_difficile',   'Module difficile (score bas)'),
        ('cours_abandonne',      'Cours abandonné (ratio < 30%)'),
    ]

    STATUS_CHOICES = [
        ('pending',  'En attente'),
        ('success', 'Succès'),
        ('error',   'Erreur'),
        ('skipped', 'Ignoré (doublon récent)'),
    ]

    apprenant = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='ai_requests')
    bloc     = models.ForeignKey('courses.BlocContenu', on_delete=models.SET_NULL, null=True, blank=True)
    sequence = models.ForeignKey('courses.Sequence', on_delete=models.SET_NULL, null=True, blank=True)
    module   = models.ForeignKey('courses.Module', on_delete=models.SET_NULL, null=True, blank=True)
    cours    = models.ForeignKey('courses.Cours', on_delete=models.SET_NULL, null=True, blank=True)
    quiz     = models.ForeignKey('evaluations.Quiz', on_delete=models.SET_NULL, null=True, blank=True)

    trigger = models.CharField(max_length=30, choices=TRIGGER_CHOICES)
    status  = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    prompt_context = models.JSONField(default=dict, blank=True)
    gpt_response  = models.TextField(blank=True)
    error_message = models.TextField(blank=True)

    tokens_used   = models.PositiveIntegerField(default=0)
    created_at   = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Requête IA'
        verbose_name_plural = 'Requêtes IA'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['apprenant', 'bloc', 'trigger']),
            models.Index(fields=['apprenant', 'quiz', 'trigger']),
        ]

    def __str__(self):
        return f'[{self.trigger}] {self.apprenant} — {self.status}'


# ============================================================================
# PARTIE 3 : CONTENUS GÉNÉRÉS PAR IA
# ============================================================================

class ContenuGenere(models.Model):
    """
    Contenu adaptatif généré par Claude.
    Peut être : bloc simplifié, séquence adaptative, module de révision.
    """
    TYPE_CHOICES = [
        ('bloc_simplifie',       'Bloc simplifié'),
        ('bloc_alternatif',       'Approche alternative'),
        ('sequence_adaptative',  'Séquence adaptative'),
        ('module_revision',      'Module de révision'),
        ('quiz_remediation',    'Quiz de remédiation'),
    ]

    ai_request = models.ForeignKey(AIAnalysisRequest, on_delete=models.CASCADE, related_name='contenu_genere')
    apprenant  = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='contenus_genere')

    type_contenu   = models.CharField(max_length=30, choices=TYPE_CHOICES)
    titre         = models.CharField(max_length=300)
    description   = models.TextField(blank=True)

    contenu_html   = models.TextField(blank=True, help_text='HTML pour affichage direct')
    contenu_json  = models.JSONField(default=dict, blank=True, help_text='Données structurées')

    bloc_source    = models.ForeignKey(
        'courses.BlocContenu', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contenus_generes'
    )
    sequence_source = models.ForeignKey(
        'courses.Sequence', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contenus_generes'
    )
    module_source = models.ForeignKey(
        'courses.Module', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contenus_generes'
    )
    quiz_source   = models.ForeignKey(
        'evaluations.Quiz', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='contenus_generes'
    )

    concepts_cibles = models.JSONField(default=list, blank=True)
    niveau_difficulte = models.CharField(
        max_length=20,
        choices=[
            ('debutant', 'Débutant'),
            ('intermediaire', 'Intermédiaire'),
            ('avance', 'Avancé'),
        ],
        blank=True, null=True
    )

    a_ete_consulte = models.BooleanField(default=False)
    consulte_le     = models.DateTimeField(null=True, blank=True)
    a_aide         = models.BooleanField(null=True, blank=True)
    feedback_le    = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Contenu généré'
        verbose_name_plural = 'Contenus générés'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_type_contenu_display()} — {self.apprenant}'

    def marquer_consulte(self):
        if not self.a_ete_consulte:
            self.a_ete_consulte = True
            self.consulte_le = timezone.now()
            self.save(update_fields=['a_ete_consulte', 'consulte_le'])

    def soumettre_feedback(self, a_aide: bool):
        self.a_aide = a_aide
        self.feedback_le = timezone.now()
        self.save(update_fields=['a_aide', 'feedback_le'])


class QuizGenereClaude(models.Model):
    """
    Quiz de remédiation généré par Claude.
    """
    ai_request = models.OneToOneField(
        AIAnalysisRequest, on_delete=models.CASCADE,
        related_name='quiz_genere'
    )
    apprenant  = models.ForeignKey(
        'users.Apprenant', on_delete=models.CASCADE,
        related_name='quiz_generes_claude'
    )
    quiz_source = models.ForeignKey(
        'evaluations.Quiz', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='quiz_generes_claude'
    )

    titre        = models.CharField(max_length=300)
    consigne     = models.TextField(blank=True)
    questions   = models.JSONField(default=list)

    concepts_rates = models.JSONField(default=list, blank=True)

    score_remediation    = models.SmallIntegerField(null=True, blank=True)
    passe_le           = models.DateTimeField(null=True, blank=True)
    remediation_reussie = models.BooleanField(null=True, blank=True)

    a_ete_consulte = models.BooleanField(default=False)
    consulte_le   = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Quiz généré (Claude)'
        verbose_name_plural = 'Quiz générés (Claude)'
        ordering = ['-created_at']

    def __str__(self):
        return f'Quiz — {self.apprenant} → {self.quiz_source}'

    def marquer_consulte(self):
        if not self.a_ete_consulte:
            self.a_ete_consulte = True
            self.consulte_le = timezone.now()
            self.save(update_fields=['a_ete_consulte', 'consulte_le'])

    def soumettre_score(self, score: int):
        self.score_remediation = score
        self.passe_le = timezone.now()
        self.remediation_reussie = score >= 60
        self.save(update_fields=['score_remediation', 'passe_le', 'remediation_reussie'])