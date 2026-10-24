# analytics/urls.py
# ============================================================================
# ANALYTICS URLS — inclut aussi les endpoints IA
# ============================================================================

from django.urls import path
from .views import (
    AnalyticsDebugView,
    BlocAnalyticsOpenView,
    BlocAnalyticsCloseView,
    BulkAnalyticsSummaryView,
    AIGenerateContentView,
    AISuggestionsView,
    ContenuGenereDetailView,
    ContenuGenereConsulteView,
    ContenuGenereFeedbackView,
    QuizGenereClaudeDetailView,
    QuizGenereClaudeConsulteView,
    QuizGenereClaudeScoreView,
    RecommandationsListView,
    RecommandationVueView,
    RecommandationSuivieView,
    RecommandationIgnoreeView,
)
from .adaptive_views import (
    BulkLearningEventsView,
    MasteryView,
    MasteryRefreshView,
    KnowledgeGapListView,
    KnowledgeGapAckView,
    DropoutAlertListView,
    DropoutAlertAckView,
    LearnerProfileView,
    RiskScoreView,
    LearnerLearningStateView,
    LearnerProgressView,
    LearnerEngagementView,
    LearnerPerformanceView,
    LearnerCompetencesView,
    LearnerSignalsView,
    LearnerDiagnosticsView,
    LearnerInterventionsView,
    InterventionGenerateView,
    LearnerOutcomesView,
    CohortOverviewView,
    BlocAideView,
    BlocGenererView,
    BlocAideReponseView,
    RecommendationsView,
)
from .dashboard_api_views import (
    AdminDashboardAPIView,
    FormateurDashboardAPIView,
    ResponsableDashboardAPIView,
    ApprenantDashboardAPIView,
    ParentDashboardAPIView,
    UnifiedDashboardAPIView,
)

urlpatterns = [

    # ── Endpoint unifié — détection automatique du rôle ────────────────────
    path('dashboard/',                        UnifiedDashboardAPIView.as_view(),     name='dashboard-unified'),

    # ── Endpoints dédiés (backward compat) ────────────────────────────────
    path('dashboard/admin/',                  AdminDashboardAPIView.as_view(),       name='dashboard-admin'),
    path('dashboard/formateur/',              FormateurDashboardAPIView.as_view(),   name='dashboard-formateur'),
    path('dashboard/responsable-academique/', ResponsableDashboardAPIView.as_view(), name='dashboard-responsable'),
    path('dashboard/apprenant/',              ApprenantDashboardAPIView.as_view(),   name='dashboard-apprenant'),
    path('dashboard/parent/',                 ParentDashboardAPIView.as_view(),      name='dashboard-parent'),

    # ── Diagnostic ─────────────────────────────────────────────────────────
    path('analytics/debug/', AnalyticsDebugView.as_view(), name='analytics-debug'),

    # ── Tracking blocs ──────────────────────────────────────────────────
    # ⚠️ session/close AVANT bloc/open
    path(
        'analytics/bloc/session/<int:session_id>/close/',
        BlocAnalyticsCloseView.as_view(), name='analytics-bloc-close',
    ),
    path(
        'analytics/bloc/<int:bloc_id>/open/',
        BlocAnalyticsOpenView.as_view(), name='analytics-bloc-open',
    ),

    # ── Bulk résumés ────────────────────────────────────────────────────
    path(
        'analytics/bulk-summary/',
        BulkAnalyticsSummaryView.as_view(), name='analytics-bulk-summary',
    ),

    # ── IA Generation ──────────────────────────────────────────────────
    path(
        'analytics/ai/generate-content/',
        AIGenerateContentView.as_view(), name='ai-generate-content',
    ),
    path(
        'analytics/ai/suggestions/<int:apprenant_id>/',
        AISuggestionsView.as_view(), name='ai-suggestions',
    ),

    # ── Contenu généré ────────────────────────────────────────────────
    path(
        'analytics/contenu/<int:pk>/',
        ContenuGenereDetailView.as_view(), name='analytics-contenu-detail',
    ),
    path(
        'analytics/contenu/<int:pk>/consulte/',
        ContenuGenereConsulteView.as_view(), name='analytics-contenu-consulte',
    ),
    path(
        'analytics/contenu/<int:pk>/feedback/',
        ContenuGenereFeedbackView.as_view(), name='analytics-contenu-feedback',
    ),

    # ── Quiz généré ────────────────────────────────────────────────────
    path(
        'analytics/quiz-genere/<int:pk>/',
        QuizGenereClaudeDetailView.as_view(), name='quiz-genere-detail',
    ),
    path(
        'analytics/quiz-genere/<int:pk>/consulte/',
        QuizGenereClaudeConsulteView.as_view(), name='quiz-genere-consulte',
    ),
    path(
        'analytics/quiz-genere/<int:pk>/score/',
        QuizGenereClaudeScoreView.as_view(), name='quiz-genere-score',
    ),

    # ── Recommandations (stub) ────────────────────────────────────────
    path(
        'analytics/recommendations/<int:apprenant_id>/',
        RecommandationsListView.as_view(), name='analytics-reco-list',
    ),
    path(
        'analytics/recommendations/<int:pk>/vue/',
        RecommandationVueView.as_view(), name='analytics-reco-vue',
    ),
    path(
        'analytics/recommendations/<int:pk>/suivie/',
        RecommandationSuivieView.as_view(), name='analytics-reco-suivie',
    ),
    path(
        'analytics/recommendations/<int:pk>/ignoree/',
        RecommandationIgnoreeView.as_view(), name='analytics-reco-ignoree',
    ),

    # ── Events bulk ──────────────────────────────────────────────────────
    path(
        'analytics/events/bulk/',
        BulkLearningEventsView.as_view(), name='events-bulk',
    ),

    # ── Adaptive Learning ─────────────────────────────────────────────────

    # Mastery scores
    path(
        'analytics/mastery/<int:apprenant_id>/',
        MasteryView.as_view(), name='mastery-list',
    ),
    path(
        'analytics/mastery/<int:apprenant_id>/refresh/',
        MasteryRefreshView.as_view(), name='mastery-refresh',
    ),

    # Knowledge gaps
    path(
        'analytics/gaps/<int:apprenant_id>/',
        KnowledgeGapListView.as_view(), name='gaps-list',
    ),
    path(
        'analytics/gaps/<int:pk>/ack/',
        KnowledgeGapAckView.as_view(), name='gap-ack',
    ),

    # Dropout alerts
    path(
        'analytics/alerts/<int:apprenant_id>/',
        DropoutAlertListView.as_view(), name='alerts-list',
    ),
    path(
        'analytics/alerts/<int:pk>/ack/',
        DropoutAlertAckView.as_view(), name='alert-ack',
    ),

    # Learner profile
    path(
        'analytics/profil/<int:apprenant_id>/',
        LearnerProfileView.as_view(), name='learner-profile',
    ),

    # Risk score
    path(
        'analytics/risk/<int:apprenant_id>/',
        RiskScoreView.as_view(), name='risk-score',
    ),

    # Progressions multi-niveaux + état d'apprentissage (Phase 3)
    path(
        'analytics/learning-state/<int:apprenant_id>/',
        LearnerLearningStateView.as_view(), name='learning-state',
    ),
    path(
        'analytics/progress/<int:apprenant_id>/',
        LearnerProgressView.as_view(), name='learner-progress',
    ),
    path(
        'analytics/engagement/<int:apprenant_id>/',
        LearnerEngagementView.as_view(), name='learner-engagement',
    ),
    path(
        'analytics/performance/<int:apprenant_id>/',
        LearnerPerformanceView.as_view(), name='learner-performance',
    ),
    path(
        'analytics/competences/<int:apprenant_id>/',
        LearnerCompetencesView.as_view(), name='learner-competences',
    ),
    path(
        'analytics/signals/<int:apprenant_id>/',
        LearnerSignalsView.as_view(), name='learner-signals',
    ),
    path(
        'analytics/diagnostics/<int:apprenant_id>/',
        LearnerDiagnosticsView.as_view(), name='learner-diagnostics',
    ),
    path(
        'analytics/interventions/<int:apprenant_id>/',
        LearnerInterventionsView.as_view(), name='learner-interventions',
    ),
    path(
        'analytics/interventions/<int:pk>/generer/',
        InterventionGenerateView.as_view(), name='intervention-generate',
    ),
    path(
        'analytics/outcomes/<int:apprenant_id>/',
        LearnerOutcomesView.as_view(), name='learner-outcomes',
    ),
    path(
        'analytics/cohort/',
        CohortOverviewView.as_view(), name='cohort-overview',
    ),

    # Aide contextuelle par bloc (accessible à tout moment)
    path(
        'analytics/blocs/<int:bloc_id>/aide/',
        BlocAideView.as_view(), name='bloc-aide',
    ),
    path(
        'analytics/blocs/<int:bloc_id>/generer/',
        BlocGenererView.as_view(), name='bloc-generer',
    ),
    path(
        'analytics/blocs/<int:bloc_id>/reponse-aide/',
        BlocAideReponseView.as_view(), name='bloc-reponse-aide',
    ),

    # Recommendations
    path(
        'analytics/adaptive-recommendations/<int:apprenant_id>/',
        RecommendationsView.as_view(), name='adaptive-recommendations',
    ),
]