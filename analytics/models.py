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

    # ── Auto-évaluation avant toute proposition d'aide (temps long) ──────────
    # None = la question n'a jamais été posée ; True = l'apprenant a dit « oui,
    # je suis bloqué » ; False = « non ». On ne propose un contenu QUE sur True.
    aide_check_reponse  = models.BooleanField(null=True, blank=True)
    aide_check_le       = models.DateTimeField(null=True, blank=True)

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
    # Trace : requête déclenchée par une intervention (Phase 11)
    intervention = models.ForeignKey('analytics.LearningIntervention', on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_requests')

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


# ============================================================================
# PARTIE 4 : ADAPTIVE LEARNING — Profil, Maîtrise, Lacunes, Alertes
# ============================================================================

class LearningEventType(models.TextChoices):
    """Taxonomie des événements pédagogiques (Phase 2 — journal d'activité)."""
    COURSE_OPENED        = 'COURSE_OPENED', 'Cours ouvert'
    MODULE_OPENED        = 'MODULE_OPENED', 'Module ouvert'
    SESSION_STARTED      = 'SESSION_STARTED', 'Session démarrée'
    SESSION_PAUSED       = 'SESSION_PAUSED', 'Session en pause'
    SESSION_RESUMED      = 'SESSION_RESUMED', 'Session reprise'
    SEQUENCE_STARTED     = 'SEQUENCE_STARTED', 'Séquence démarrée'
    SEQUENCE_COMPLETED   = 'SEQUENCE_COMPLETED', 'Séquence terminée'
    BLOCK_STARTED        = 'BLOCK_STARTED', 'Bloc démarré'
    BLOCK_PAUSED         = 'BLOCK_PAUSED', 'Bloc en pause'
    BLOCK_RESUMED        = 'BLOCK_RESUMED', 'Bloc repris'
    BLOCK_COMPLETED      = 'BLOCK_COMPLETED', 'Bloc terminé'
    RESOURCE_OPENED      = 'RESOURCE_OPENED', 'Ressource ouverte'
    RESOURCE_VIEWED      = 'RESOURCE_VIEWED', 'Ressource consultée'
    RESOURCE_COMPLETED   = 'RESOURCE_COMPLETED', 'Ressource terminée'
    QUIZ_STARTED         = 'QUIZ_STARTED', 'Quiz démarré'
    QUESTION_ANSWERED    = 'QUESTION_ANSWERED', 'Question répondue'
    QUESTION_CHANGED     = 'QUESTION_CHANGED', 'Question changée'
    QUIZ_SUBMITTED       = 'QUIZ_SUBMITTED', 'Quiz soumis'
    QUIZ_RETAKEN         = 'QUIZ_RETAKEN', 'Quiz refait'
    EVALUATION_STARTED   = 'EVALUATION_STARTED', 'Évaluation démarrée'
    EVALUATION_PAUSED    = 'EVALUATION_PAUSED', 'Évaluation en pause'
    EVALUATION_RESUMED   = 'EVALUATION_RESUMED', 'Évaluation reprise'
    EVALUATION_SUBMITTED = 'EVALUATION_SUBMITTED', 'Évaluation soumise'
    RECOMMENDATION_VIEWED   = 'RECOMMENDATION_VIEWED', 'Recommandation vue'
    RECOMMENDATION_ACCEPTED = 'RECOMMENDATION_ACCEPTED', 'Recommandation acceptée'
    RECOMMENDATION_IGNORED  = 'RECOMMENDATION_IGNORED', 'Recommandation ignorée'
    INTERVENTION_STARTED = 'INTERVENTION_STARTED', 'Intervention démarrée'
    INTERVENTION_COMPLETED = 'INTERVENTION_COMPLETED', 'Intervention terminée'
    AI_CONTENT_VIEWED    = 'AI_CONTENT_VIEWED', 'Contenu IA consulté'
    AI_QUIZ_COMPLETED    = 'AI_QUIZ_COMPLETED', 'Quiz IA terminé'
    # Génériques (compat des anciens trackers)
    OTHER                = 'OTHER', 'Autre'


class LearningEvent(models.Model):
    """
    Événement pédagogique xAPI-like, enrichi (Phase 2) avec la hiérarchie
    pédagogique indexable + durée + source, pour reconstruire le parcours
    d'apprentissage et alimenter les moteurs de suivi.

    Reçoit les traquages du frontend sous forme de lots via
    POST /api/analytics/events/bulk/.
    """
    apprenant  = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='learning_events', null=True, blank=True)

    # ── Hiérarchie pédagogique (nullable, indexée) ──────────────────────────
    cours      = models.ForeignKey('courses.Cours', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_events')
    module     = models.ForeignKey('courses.Module', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_events')
    sequence   = models.ForeignKey('courses.Sequence', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_events')
    bloc       = models.ForeignKey('courses.BlocContenu', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_events')
    ressource  = models.ForeignKey('courses.RessourceSequence', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_events')
    session    = models.ForeignKey('courses.Session', on_delete=models.SET_NULL, null=True, blank=True, related_name='learning_events')

    # ── Identification technique de session (ex-`session_id`) ───────────────
    trace_id   = models.CharField(max_length=64, blank=True)

    event_type = models.CharField(max_length=64, choices=LearningEventType.choices, db_index=True)
    ts         = models.DateTimeField(db_index=True)
    duree_ms   = models.PositiveIntegerField(default=0, help_text='Durée de l’événement (ms) si pertinente')
    source     = models.CharField(max_length=32, blank=True, help_text='web | beacon | system | signal')
    payload    = models.JSONField(default=dict, blank=True, help_text='Métadonnées libres')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Événement pédagogique'
        verbose_name_plural = 'Événements pédagogiques'
        ordering            = ['-ts']
        indexes             = [
            models.Index(fields=['apprenant', 'event_type', 'ts']),
            models.Index(fields=['apprenant', 'cours', 'ts']),
            models.Index(fields=['apprenant', 'sequence', 'ts']),
            models.Index(fields=['apprenant', 'bloc', 'ts']),
            models.Index(fields=['trace_id']),
        ]

    def __str__(self):
        return f'{self.event_type} — {self.apprenant} @ {self.ts}'


class LearnerProfile(models.Model):
    PROFIL_CHOICES = [
        ('rapide',      'Apprenant rapide'),
        ('perseverant', 'Apprenant persévérant'),
        ('difficulte',  'Apprenant en difficulté'),
        ('irregulier',  'Apprenant irrégulier'),
        ('risque',      'Apprenant à risque de décrochage'),
        ('autonome',    'Apprenant autonome'),
        ('standard',    'Apprenant standard'),
    ]
    apprenant               = models.OneToOneField('users.Apprenant', on_delete=models.CASCADE, related_name='profil_adaptatif')
    score_engagement        = models.FloatField(default=0)
    score_regularite        = models.FloatField(default=0)
    score_risque_decrochage = models.FloatField(default=0)
    profil_type             = models.CharField(max_length=32, choices=PROFIL_CHOICES, default='standard')
    type_contenu_prefere    = models.CharField(max_length=16, blank=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Profil apprenant (adaptatif)'
        verbose_name_plural = 'Profils apprenants (adaptatifs)'

    def __str__(self):
        return f'{self.apprenant} — {self.profil_type}'

    def recalculer(self):
        """Recalcule tous les scores à partir des analytics existants."""
        from django.db.models import Count
        from datetime import timedelta
        from django.utils import timezone

        since_30 = timezone.now() - timedelta(days=30)

        # Régularité : jours distincts actifs sur 30j (20j = 100 pts)
        jours_actifs = (
            BlocAnalyticsSummary.objects.filter(
                apprenant=self.apprenant,
                derniere_ouverture__gte=since_30,
            )
            .dates('derniere_ouverture', 'day')
            .count()
        )
        self.score_regularite = round(min(100.0, jours_actifs * (100.0 / 20)), 2)

        # Engagement : % blocs complétés / consultés (tous temps)
        totals = BlocAnalyticsSummary.objects.filter(apprenant=self.apprenant).aggregate(
            ouv=Count('id'),
            comp=Count('date_completion', filter=models.Q(date_completion__isnull=False)),
        )
        ouv  = totals['ouv']  or 1
        comp = totals['comp'] or 0
        self.score_engagement = round((comp / ouv) * 100, 2)

        # Risque décrochage — délégué au dropout_engine
        try:
            from .dropout_engine import compute_dropout_risk
            self.score_risque_decrochage = compute_dropout_risk(self.apprenant)
        except Exception:
            pass

        # Type de contenu préféré (type_bloc le plus consulté)
        try:
            top = (
                BlocAnalytics.objects.filter(apprenant=self.apprenant)
                .values('bloc__type_bloc')
                .annotate(nb=Count('id'))
                .order_by('-nb')
                .first()
            )
            self.type_contenu_prefere = top['bloc__type_bloc'] if top else ''
        except Exception:
            pass

        # Profil dominant
        r   = self.score_risque_decrochage
        e   = self.score_engagement
        reg = self.score_regularite

        if r >= 60:
            self.profil_type = 'risque'
        elif reg < 30:
            self.profil_type = 'irregulier'
        elif e < 40:
            self.profil_type = 'difficulte'
        elif e >= 80 and reg >= 70:
            self.profil_type = 'autonome'
        elif e >= 70 and reg >= 60:
            self.profil_type = 'perseverant'
        else:
            self.profil_type = 'standard'

        self.save()


class SkillMasteryScore(models.Model):
    NIVEAU_CHOICES = [
        ('non_acquis', 'Non acquis'),
        ('fragile',    'Fragile'),
        ('maitrise',   'Maîtrisé'),
        ('expert',     'Expert'),
    ]
    apprenant        = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='mastery_scores')
    cours            = models.ForeignKey('courses.Cours',    null=True, blank=True, on_delete=models.CASCADE, related_name='mastery_scores')
    module           = models.ForeignKey('courses.Module',   null=True, blank=True, on_delete=models.CASCADE, related_name='mastery_scores')
    sequence         = models.ForeignKey('courses.Sequence', null=True, blank=True, on_delete=models.CASCADE, related_name='mastery_scores')
    score            = models.FloatField(default=0)
    niveau           = models.CharField(max_length=16, choices=NIVEAU_CHOICES, default='non_acquis')
    score_quiz       = models.FloatField(default=0)
    score_completion = models.FloatField(default=0)
    score_temps      = models.FloatField(default=0)
    tendance         = models.CharField(
        max_length=16,
        choices=[('hausse','En hausse'),('stable','Stable'),('baisse','En baisse')],
        default='stable',
    )
    score_precedent  = models.FloatField(null=True, blank=True)
    # Confiance (0-1) : quantité et cohérence des preuves disponibles (Phase 6)
    confidence       = models.FloatField(default=0)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Score de maîtrise'
        verbose_name_plural = 'Scores de maîtrise'
        indexes = [
            models.Index(fields=['apprenant', 'sequence']),
            models.Index(fields=['apprenant', 'module']),
            models.Index(fields=['apprenant', 'cours']),
        ]

    def __str__(self):
        target = self.sequence or self.module or self.cours
        return f'{self.apprenant} — {target} — {self.niveau} ({self.score:.0f}%)'


class KnowledgeGap(models.Model):
    SEVERITY_CHOICES = [
        ('faible',   'Faible'),
        ('moderee',  'Modérée'),
        ('critique', 'Critique'),
    ]
    STATUT_CHOICES = [
        ('detectee', 'Détectée'),
        ('en_cours', 'Remédiation en cours'),
        ('resolue',  'Résolue'),
    ]
    apprenant   = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='knowledge_gaps')
    sequence    = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, related_name='knowledge_gaps')
    severity    = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default='faible')
    statut      = models.CharField(max_length=16, choices=STATUT_CHOICES, default='detectee')
    description = models.TextField(blank=True)
    evidence    = models.JSONField(default=list)
    ai_request  = models.ForeignKey(AIAnalysisRequest, null=True, blank=True, on_delete=models.SET_NULL, related_name='knowledge_gaps')
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Lacune identifiée'
        verbose_name_plural = 'Lacunes identifiées'
        ordering            = ['-detected_at']

    def __str__(self):
        return f'{self.apprenant} — {self.sequence} — {self.severity}'


class DropoutAlert(models.Model):
    ALERT_TYPES = [
        ('inactivite',        'Inactivité prolongée'),
        ('engagement_faible', 'Faible engagement'),
        ('echec_repete',      'Échec répété'),
        ('risque_eleve',      'Score de risque élevé'),
    ]
    STATUT_CHOICES = [
        ('active',  'Active'),
        ('vue',     'Vue'),
        ('resolue', 'Résolue'),
    ]
    apprenant    = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='dropout_alerts')
    cours        = models.ForeignKey('courses.Cours', null=True, blank=True, on_delete=models.SET_NULL, related_name='dropout_alerts')
    alert_type   = models.CharField(max_length=32, choices=ALERT_TYPES)
    score_risque = models.FloatField()
    message      = models.TextField()
    statut       = models.CharField(max_length=16, choices=STATUT_CHOICES, default='active')
    created_at   = models.DateTimeField(auto_now_add=True)
    resolved_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Alerte décrochage'
        verbose_name_plural = 'Alertes décrochage'
        ordering            = ['-created_at']
        indexes             = [models.Index(fields=['apprenant', 'statut'])]

    def __str__(self):
        return f'[{self.alert_type}] {self.apprenant} — risque={self.score_risque:.0f}%'


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


# ============================================================================
# PARTIE 5 : RECOMMANDATIONS PÉDAGOGIQUES
# ============================================================================

class RecommandationPedagogique(models.Model):
    """
    Recommandation personnalisée affichée à l'apprenant.

    Générée par analytics.services.recommendation_engine.RecommendationEngine
    (à partir des lacunes / fragilités / séquences non évaluées) ou par les
    tâches de génération de contenu. Peut pointer vers un ContenuGenere
    (bloc simplifié, approche alternative, module de révision…).

    Le suivi utilisateur (est_vue / est_suivie) est piloté par les endpoints
    /api/v1/analytics/recommendations/<pk>/vue/ et .../suivie/.
    """
    TYPE_CHOICES = [
        ('bloc_revoir',          'Bloc à revoir'),
        ('changement_approche',  "Changer d'approche"),
        ('contenu_alternatif',   'Contenu alternatif disponible'),
        ('quiz_supplementaire',  'Quiz supplémentaire'),
        ('module_revision',      'Module de révision'),
        ('pause',                'Prendre une pause'),
    ]

    apprenant  = models.ForeignKey(
        'users.Apprenant', on_delete=models.CASCADE,
        related_name='recommandations',
    )
    cours      = models.ForeignKey(
        'courses.Cours', on_delete=models.CASCADE,
        null=True, blank=True, related_name='recommandations',
    )
    bloc_cible = models.ForeignKey(
        'courses.BlocContenu', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recommandations',
    )
    sequence_cible = models.ForeignKey(
        'courses.Sequence', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recommandations',
    )
    contenu_genere = models.ForeignKey(
        ContenuGenere, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recommandations',
    )
    quiz_genere = models.ForeignKey(
        QuizGenereClaude, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recommandations',
    )
    # Projection d'une intervention pédagogique (Phase 10)
    intervention = models.ForeignKey(
        'analytics.LearningIntervention', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recommandations',
    )

    type_recommandation = models.CharField(max_length=32, choices=TYPE_CHOICES)
    message             = models.TextField()
    priorite            = models.PositiveSmallIntegerField(default=3)  # 1 = plus urgent

    est_vue        = models.BooleanField(default=False)
    date_vue       = models.DateTimeField(null=True, blank=True)
    est_suivie     = models.BooleanField(default=False)
    date_suivie    = models.DateTimeField(null=True, blank=True)
    # Rejetée explicitement par l'apprenant → ne doit plus réapparaître.
    est_ignoree    = models.BooleanField(default=False)
    date_ignoree   = models.DateTimeField(null=True, blank=True)

    date_expiration = models.DateTimeField(null=True, blank=True)
    date_creation   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Recommandation pédagogique'
        verbose_name_plural = 'Recommandations pédagogiques'
        ordering            = ['-priorite', '-date_creation']
        indexes = [
            models.Index(fields=['apprenant', 'est_suivie'], name='reco_appr_suivie_idx'),
            models.Index(fields=['apprenant', 'est_vue'],    name='reco_appr_vue_idx'),
        ]

    def __str__(self):
        return f'[{self.type_recommandation}] {self.apprenant} (p{self.priorite})'

    def marquer_vue(self):
        if not self.est_vue:
            self.est_vue = True
            self.date_vue = timezone.now()
            self.save(update_fields=['est_vue', 'date_vue'])

    def marquer_suivie(self):
        if not self.est_suivie:
            self.est_suivie = True
            self.date_suivie = timezone.now()
            if not self.est_vue:
                self.est_vue = True
                self.date_vue = self.date_suivie
            self.save(update_fields=['est_suivie', 'date_suivie', 'est_vue', 'date_vue'])

    def marquer_ignoree(self):
        """Rejette définitivement la recommandation (ne réapparaîtra plus)."""
        if not self.est_ignoree:
            self.est_ignoree = True
            self.date_ignoree = timezone.now()
            if not self.est_vue:
                self.est_vue = True
                self.date_vue = self.date_ignoree
            self.save(update_fields=['est_ignoree', 'date_ignoree', 'est_vue', 'date_vue'])


# ============================================================================
# PARTIE 6 : ÉTAT D'APPRENTISSAGE (Phase 3 — progression multi-niveaux)
# ============================================================================

class LearnerLearningState(models.Model):
    """
    État d'apprentissage agrégé d'un apprenant (snapshot recalculable).

    La progression est calculée à plusieurs niveaux (cours → module → séquence
    → bloc) par `analytics.services.progress_engine`, chacun avec des dimensions
    DISTINCTES : complétion, temps réalisé, évaluation (quiz), maîtrise.

    Les champs `engagement_level`, `risk_level`, `mastery_level` sont renseignés
    par les phases ultérieures (4, 6, 9). `details` contient le détail par cours.
    """
    TREND_CHOICES = [('hausse', 'En hausse'), ('stable', 'Stable'), ('baisse', 'En baisse')]
    LEVEL_CHOICES = [('faible', 'Faible'), ('moyen', 'Moyen'), ('eleve', 'Élevé')]

    apprenant = models.OneToOneField(
        'users.Apprenant', on_delete=models.CASCADE, related_name='learning_state',
    )

    # Progression globale
    global_progress_pct = models.FloatField(default=0)   # blocs terminés / total
    total_time_sec      = models.PositiveIntegerField(default=0)
    last_activity       = models.DateTimeField(null=True, blank=True)
    activity_days_30    = models.PositiveSmallIntegerField(default=0)
    cours_count         = models.PositiveIntegerField(default=0)

    modules_done        = models.PositiveIntegerField(default=0)
    modules_in_progress = models.PositiveIntegerField(default=0)
    sequences_done      = models.PositiveIntegerField(default=0)
    sequences_blocked   = models.PositiveIntegerField(default=0)

    # Dimensions distinctes (ne pas confondre progression et maîtrise)
    avg_quiz_score      = models.FloatField(default=0)
    avg_mastery         = models.FloatField(default=0)

    trend               = models.CharField(max_length=16, choices=TREND_CHOICES, default='stable')

    # Renseignés par les phases ultérieures
    engagement_level    = models.CharField(max_length=16, choices=LEVEL_CHOICES, blank=True)
    risk_level          = models.CharField(max_length=16, choices=LEVEL_CHOICES, blank=True)
    mastery_level       = models.CharField(max_length=16, choices=LEVEL_CHOICES, blank=True)

    details             = models.JSONField(default=dict, blank=True, help_text='Détail par cours/module')
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "État d'apprentissage"
        verbose_name_plural = "États d'apprentissage"

    def __str__(self):
        return f'{self.apprenant} — {self.global_progress_pct:.0f}% ({self.trend})'


class LearnerEngagementState(models.Model):
    """
    État d'engagement d'un apprenant (Phase 4).

    L'engagement mesure la FRÉQUENCE et la RÉGULARITÉ des interactions
    (à ne pas confondre avec la progression ou la maîtrise) :
    sessions, durée moyenne, temps hebdo, jours actifs, interruptions,
    reprises, tendance.
    """
    LEVEL_CHOICES = [('faible', 'Faible'), ('moyen', 'Moyen'), ('eleve', 'Élevé')]
    TREND_CHOICES = [('hausse', 'En hausse'), ('stable', 'Stable'), ('baisse', 'En baisse')]

    apprenant = models.OneToOneField(
        'users.Apprenant', on_delete=models.CASCADE, related_name='engagement_state',
    )

    score            = models.FloatField(default=0)          # 0-100
    niveau           = models.CharField(max_length=16, choices=LEVEL_CHOICES, default='moyen')
    tendance         = models.CharField(max_length=16, choices=TREND_CHOICES, default='stable')

    sessions_30d     = models.PositiveIntegerField(default=0)
    avg_session_sec  = models.PositiveIntegerField(default=0)
    weekly_time_sec  = models.PositiveIntegerField(default=0)
    prev_weekly_sec  = models.PositiveIntegerField(default=0)
    active_days_30   = models.PositiveSmallIntegerField(default=0)
    regularity_pct   = models.FloatField(default=0)
    last_activity    = models.DateTimeField(null=True, blank=True)
    interruptions    = models.PositiveIntegerField(default=0)   # sessions non terminées (30j)
    resumes          = models.PositiveIntegerField(default=0)   # blocs repris (>1 ouverture)

    signals          = models.JSONField(default=list, blank=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "État d'engagement"
        verbose_name_plural = "États d'engagement"

    def __str__(self):
        return f'{self.apprenant} — engagement {self.niveau} ({self.score:.0f})'


class LearnerPerformanceState(models.Model):
    """
    État de performance d'un apprenant (Phase 5).

    Agrège les résultats pédagogiques (quiz + évaluations) pour détecter :
    échec ponctuel, difficulté répétée, amélioration, stagnation, régression.
    Ne considère pas seulement la note finale (erreurs répétées, évolution).
    """
    STATUS_CHOICES = [
        ('none',              '—'),
        ('echec_ponctuel',    'Échec ponctuel'),
        ('difficulte_repetee','Difficulté répétée'),
        ('amelioration',      'Amélioration'),
        ('stagnation',        'Stagnation'),
        ('regression',        'Régression'),
    ]
    TREND_CHOICES = [('hausse', 'En hausse'), ('stable', 'Stable'), ('baisse', 'En baisse')]

    apprenant = models.OneToOneField(
        'users.Apprenant', on_delete=models.CASCADE, related_name='performance_state',
    )

    avg_score       = models.FloatField(default=0)     # 0-100
    last_score      = models.FloatField(null=True, blank=True)
    best_score      = models.FloatField(null=True, blank=True)
    worst_score     = models.FloatField(null=True, blank=True)
    recent_avg      = models.FloatField(null=True, blank=True)
    previous_avg    = models.FloatField(null=True, blank=True)

    attempts_total  = models.PositiveIntegerField(default=0)
    attempts_30d    = models.PositiveIntegerField(default=0)
    quiz_count      = models.PositiveIntegerField(default=0)
    evaluation_count = models.PositiveIntegerField(default=0)

    error_rate      = models.FloatField(default=0)     # % réponses fausses
    repeated_errors = models.PositiveIntegerField(default=0)  # questions ratées ≥ 2 fois

    trend           = models.CharField(max_length=16, choices=TREND_CHOICES, default='stable')
    status          = models.CharField(max_length=24, choices=STATUS_CHOICES, default='none')

    details         = models.JSONField(default=dict, blank=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "État de performance"
        verbose_name_plural = "États de performance"

    def __str__(self):
        return f'{self.apprenant} — perf {self.avg_score:.0f} ({self.status})'


# ============================================================================
# PARTIE 7 : COMPÉTENCES & MAÎTRISE (Phase 6)
# ============================================================================

class Competence(models.Model):
    """Référentiel de compétences (n'existait pas auparavant)."""
    code        = models.CharField(max_length=64)
    libelle     = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    institution = models.ForeignKey(
        'academics.Institution', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='competences',
    )
    est_active  = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = 'Compétence'
        verbose_name_plural = 'Compétences'
        ordering            = ['libelle']
        constraints = [
            models.UniqueConstraint(fields=['institution', 'code'], name='uniq_competence_inst_code'),
        ]

    def __str__(self):
        return f'{self.libelle} ({self.code})'


class CompetenceCible(models.Model):
    """Lien d'une compétence vers une cible pédagogique (cours/module/séquence/bloc/question/évaluation)."""
    competence = models.ForeignKey(Competence, on_delete=models.CASCADE, related_name='cibles')
    cours      = models.ForeignKey('courses.Cours', on_delete=models.CASCADE, null=True, blank=True, related_name='competences')
    module     = models.ForeignKey('courses.Module', on_delete=models.CASCADE, null=True, blank=True, related_name='competences')
    sequence   = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, null=True, blank=True, related_name='competences')
    bloc       = models.ForeignKey('courses.BlocContenu', on_delete=models.CASCADE, null=True, blank=True, related_name='competences')
    question   = models.ForeignKey('evaluations.Question', on_delete=models.CASCADE, null=True, blank=True, related_name='competences')
    evaluation = models.ForeignKey('evaluations.Evaluation', on_delete=models.CASCADE, null=True, blank=True, related_name='competences')

    class Meta:
        verbose_name        = 'Cible de compétence'
        verbose_name_plural = 'Cibles de compétences'

    def __str__(self):
        return f'{self.competence.code} → {self.label()}'

    def label(self) -> str:
        for kind, obj in (
            ('séquence', self.sequence), ('module', self.module), ('cours', self.cours),
            ('bloc', self.bloc), ('question', self.question), ('évaluation', self.evaluation),
        ):
            if obj is not None:
                return f'{kind} {getattr(obj, "titre", None) or getattr(obj, "enonce_texte", "") or obj.pk}'
        return '—'


class CompetenceMastery(models.Model):
    """Maîtrise d'une compétence par un apprenant, avec confiance (quantité/cohérence des preuves)."""
    NIVEAU_CHOICES = [
        ('non_acquis', 'Non acquis'), ('fragile', 'Fragile'),
        ('maitrise', 'Maîtrisé'), ('expert', 'Expert'),
    ]
    TREND_CHOICES = [('hausse', 'En hausse'), ('stable', 'Stable'), ('baisse', 'En baisse')]

    apprenant     = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='competence_masteries')
    competence    = models.ForeignKey(Competence, on_delete=models.CASCADE, related_name='masteries')
    score         = models.FloatField(default=0)        # 0-100
    confidence    = models.FloatField(default=0)         # 0-1
    niveau        = models.CharField(max_length=16, choices=NIVEAU_CHOICES, default='non_acquis')
    tendance      = models.CharField(max_length=16, choices=TREND_CHOICES, default='stable')
    score_precedent = models.FloatField(null=True, blank=True)
    evidence_count = models.PositiveSmallIntegerField(default=0)
    evidence      = models.JSONField(default=list, blank=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Maîtrise de compétence'
        verbose_name_plural = 'Maîtrises de compétences'
        unique_together     = ('apprenant', 'competence')
        indexes             = [models.Index(fields=['apprenant', 'niveau'])]

    def __str__(self):
        return f'{self.apprenant} — {self.competence.code} — {self.score:.0f}% (conf {self.confidence:.2f})'


# ============================================================================
# PARTIE 8 : SIGNAUX PÉDAGOGIQUES (Phase 7)
# ============================================================================

class LearningSignal(models.Model):
    """
    Signal pédagogique détecté, agrégeable en diagnostic (Phase 8).

    Chaque signal porte : type, cible, sévérité, valeur, seuil/référence,
    preuves, horodatage. Les signaux ACTIFS sont recalculés et les obsolètes
    automatiquement résolus (protection contre le bruit).
    """
    TYPE_CHOICES = [
        ('inactivite_prolongee', 'Inactivité prolongée'),
        ('baisse_engagement',    'Baisse d’engagement'),
        ('progression_stagnante','Progression stagnante'),
        ('progression_trop_lente','Progression trop lente'),
        ('erreurs_repetitives',  'Erreurs répétitives'),
        ('competence_fragile',   'Compétence fragile'),
        ('regression',           'Régression'),
        ('echec_repete',         'Échec répété'),
        ('difficulte_persistante','Difficulté persistante'),
        ('sequence_abandonnee',  'Séquence abandonnée'),
        ('faible_performance',   'Faible performance'),
        ('aucune_activite',      'Aucune activité'),
        # Remontés depuis les lacunes / la maîtrise (Phase 8+ : la reco = diagnostic)
        ('lacune_critique',      'Lacune critique'),
        ('lacune_moderee',       'Lacune modérée'),
        ('maitrise_fragile',     'Maîtrise fragile'),
        ('remediation_insuffisante', 'Remédiation insuffisante'),
    ]
    SEVERITY_CHOICES = [('faible', 'Faible'), ('moderee', 'Modérée'), ('critique', 'Critique')]
    STATUT_CHOICES   = [('actif', 'Actif'), ('resolu', 'Résolu')]

    apprenant   = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='learning_signals')

    signal_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    severity    = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default='faible')
    valeur      = models.FloatField(default=0)
    reference   = models.CharField(max_length=120, blank=True, help_text='Seuil ou référence utilisée')
    preuves     = models.JSONField(default=list, blank=True)

    # Cible (au plus une renseignée)
    cours       = models.ForeignKey('courses.Cours', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_signals')
    module      = models.ForeignKey('courses.Module', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_signals')
    sequence    = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_signals')
    bloc        = models.ForeignKey('courses.BlocContenu', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_signals')
    competence  = models.ForeignKey('analytics.Competence', on_delete=models.CASCADE, null=True, blank=True, related_name='signals')

    statut      = models.CharField(max_length=16, choices=STATUT_CHOICES, default='actif')
    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Signal pédagogique'
        verbose_name_plural = 'Signaux pédagogiques'
        ordering            = ['-updated_at']
        indexes = [
            models.Index(fields=['apprenant', 'statut']),
            models.Index(fields=['apprenant', 'signal_type']),
        ]

    def __str__(self):
        return f'{self.signal_type} ({self.severity}) — {self.apprenant}'


# ============================================================================
# PARTIE 9 : DIAGNOSTICS PÉDAGOGIQUES (Phase 8)
# ============================================================================

class LearningDiagnosis(models.Model):
    """
    Diagnostic pédagogique agrégé (Signaux → Agrégation → Diagnostic).

    Un seul diagnostic par CIBLE (anti-bruit) : plusieurs signaux sur la même
    cible produisent un diagnostic unique, explicable (raison + preuves).
    """
    TYPE_CHOICES = [
        ('MASTERY_GAP',          'Lacune de maîtrise'),
        ('DIFFICULTY_PERSISTENT','Difficulté persistante'),
        ('PERFORMANCE_DROP',     'Baisse de performance'),
        ('DISENGAGEMENT',        'Désengagement'),
        ('STAGNATION',           'Stagnation'),
        ('ABANDONMENT',          'Abandon'),
    ]
    SEVERITY_CHOICES = [('faible', 'Faible'), ('moderee', 'Modérée'), ('critique', 'Critique')]
    STATUT_CHOICES   = [('actif', 'Actif'), ('resolu', 'Résolu')]

    apprenant      = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='learning_diagnoses')

    diagnosis_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    severity       = models.CharField(max_length=16, choices=SEVERITY_CHOICES, default='faible')
    priority       = models.PositiveSmallIntegerField(default=3)  # 1=P1 … 4=P4
    confidence     = models.FloatField(default=0)                 # 0-1

    cours          = models.ForeignKey('courses.Cours', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_diagnoses')
    module         = models.ForeignKey('courses.Module', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_diagnoses')
    sequence       = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_diagnoses')
    bloc           = models.ForeignKey('courses.BlocContenu', on_delete=models.CASCADE, null=True, blank=True, related_name='learning_diagnoses')
    competence     = models.ForeignKey('analytics.Competence', on_delete=models.CASCADE, null=True, blank=True, related_name='diagnoses')

    signal_types   = models.JSONField(default=list, blank=True)
    evidence       = models.JSONField(default=list, blank=True)
    reason         = models.TextField(blank=True)

    statut         = models.CharField(max_length=16, choices=STATUT_CHOICES, default='actif')
    detected_at    = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    resolved_at    = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Diagnostic pédagogique'
        verbose_name_plural = 'Diagnostics pédagogiques'
        ordering            = ['priority', '-updated_at']
        indexes = [
            models.Index(fields=['apprenant', 'statut']),
            models.Index(fields=['apprenant', 'priority']),
        ]

    def __str__(self):
        return f'{self.diagnosis_type} P{self.priority} — {self.apprenant}'


# ============================================================================
# PARTIE 10 : RISQUE DE DÉCROCHAGE (Phase 9)
# ============================================================================

class LearnerRiskState(models.Model):
    """
    Indicateur de risque de décrochage (snapshot explicable).

    Ce n'est PAS une vérité absolue : c'est un indicateur pédagogique
    combinant activité, engagement, performance, diagnostics et interventions
    ignorées. Complète (sans remplacer) `dropout_engine` / `DropoutAlert`.
    """
    LEVEL_CHOICES = [('faible', 'Faible'), ('moyen', 'Moyen'), ('eleve', 'Élevé')]
    TREND_CHOICES = [('hausse', 'En hausse'), ('stable', 'Stable'), ('baisse', 'En baisse')]

    apprenant   = models.OneToOneField('users.Apprenant', on_delete=models.CASCADE, related_name='risk_state')
    risk_score  = models.FloatField(default=0)        # 0-100
    risk_level  = models.CharField(max_length=16, choices=LEVEL_CHOICES, default='faible')
    reasons     = models.JSONField(default=list, blank=True)
    breakdown   = models.JSONField(default=dict, blank=True)
    trend       = models.CharField(max_length=16, choices=TREND_CHOICES, default='stable')
    detected_at = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = 'Risque de décrochage'
        verbose_name_plural = 'Risques de décrochage'

    def __str__(self):
        return f'{self.apprenant} — risque {self.risk_level} ({self.risk_score:.0f})'


# ============================================================================
# PARTIE 11 : INTERVENTIONS PÉDAGOGIQUES (Phase 10)
# ============================================================================

class LearningIntervention(models.Model):
    """
    Intervention pédagogique issue d'un diagnostic.

    Le moteur choisit le TYPE d'intervention selon la nature/gravité du
    diagnostic. Les interventions destinées à l'apprenant sont « projetées »
    en `RecommandationPedagogique` (compatibilité frontend).
    """
    TYPE_CHOICES = [
        ('AI_CONTENT',            'Contenu IA'),
        ('AI_QUIZ',               'Quiz IA'),
        ('REVIEW_SEQUENCE',       'Revoir la séquence'),
        ('REVIEW_BLOCK',          'Revoir le bloc'),
        ('RESOURCE_RECOMMENDATION','Ressource recommandée'),
        ('RETAKE_QUIZ',           'Refaire le quiz'),
        ('PRACTICE',              'Exercice de pratique'),
        ('TRAINER_ALERT',         'Alerte formateur'),
    ]
    STATUS_CHOICES = [
        ('proposee', 'Proposée'), ('acceptee', 'Acceptée'), ('en_cours', 'En cours'),
        ('terminee', 'Terminée'), ('ignoree', 'Ignorée'), ('expiree', 'Expirée'),
    ]

    apprenant      = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='interventions')
    diagnosis      = models.ForeignKey(LearningDiagnosis, on_delete=models.SET_NULL, null=True, blank=True, related_name='interventions')
    intervention_type = models.CharField(max_length=32, choices=TYPE_CHOICES)
    priority       = models.PositiveSmallIntegerField(default=3)
    status         = models.CharField(max_length=16, choices=STATUS_CHOICES, default='proposee')
    message        = models.TextField(blank=True)
    reason         = models.TextField(blank=True)

    cours          = models.ForeignKey('courses.Cours', on_delete=models.CASCADE, null=True, blank=True, related_name='interventions')
    module         = models.ForeignKey('courses.Module', on_delete=models.CASCADE, null=True, blank=True, related_name='interventions')
    sequence       = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, null=True, blank=True, related_name='interventions')
    bloc           = models.ForeignKey('courses.BlocContenu', on_delete=models.CASCADE, null=True, blank=True, related_name='interventions')
    competence     = models.ForeignKey('analytics.Competence', on_delete=models.CASCADE, null=True, blank=True, related_name='interventions')

    contenu_genere = models.ForeignKey(ContenuGenere, on_delete=models.SET_NULL, null=True, blank=True, related_name='interventions')
    quiz_genere    = models.ForeignKey(QuizGenereClaude, on_delete=models.SET_NULL, null=True, blank=True, related_name='interventions')

    expires_at     = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    completed_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name        = 'Intervention pédagogique'
        verbose_name_plural = 'Interventions pédagogiques'
        ordering            = ['priority', '-created_at']
        indexes = [
            models.Index(fields=['apprenant', 'status']),
            models.Index(fields=['apprenant', 'priority']),
        ]

    def __str__(self):
        return f'{self.intervention_type} P{self.priority} [{self.status}] — {self.apprenant}'


# ============================================================================
# PARTIE 12 : MESURE D'EFFICACITÉ (Phase 12)
# ============================================================================

class InterventionOutcome(models.Model):
    """
    Mesure de l'effet d'une intervention : avant/après + effectivité.

    Répond à « l'intervention a-t-elle fonctionné ? » — et si non, permet au
    moteur d'augmenter la priorité ou de changer de stratégie.
    """
    STATUS_CHOICES = [
        ('non_mesuree', 'Non mesurée'),
        ('efficace',    'Efficace'),
        ('partielle',   'Partielle'),
        ('inefficace',  'Inefficace'),
    ]

    intervention = models.OneToOneField(
        LearningIntervention, on_delete=models.CASCADE, related_name='outcome',
    )
    apprenant    = models.ForeignKey('users.Apprenant', on_delete=models.CASCADE, related_name='intervention_outcomes')

    score_before   = models.FloatField(null=True, blank=True)
    score_after    = models.FloatField(null=True, blank=True)
    mastery_before = models.FloatField(null=True, blank=True)
    mastery_after  = models.FloatField(null=True, blank=True)
    completion     = models.FloatField(default=0)   # 0-100
    improvement    = models.FloatField(null=True, blank=True)
    effectiveness  = models.CharField(max_length=16, choices=STATUS_CHOICES, default='non_mesuree')
    details        = models.JSONField(default=dict, blank=True)
    measured_at    = models.DateTimeField(null=True, blank=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Efficacité d'intervention"
        verbose_name_plural = "Efficacités d'intervention"

    def __str__(self):
        return f'{self.intervention_id} — {self.effectiveness} ({self.improvement})'