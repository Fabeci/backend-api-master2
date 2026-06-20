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
    QuizGenereClaudeConsulteView,
    QuizGenereClaudeScoreView,
    RecommandationsListView,
    RecommandationVueView,
    RecommandationSuivieView,
)
from .dashboard_api_views import (
    SuperAdminDashboardAPIView,
    AdminDashboardAPIView,
    FormateurDashboardAPIView,
    ResponsableDashboardAPIView,
    ApprenantDashboardAPIView,
    ParentDashboardAPIView,
)

urlpatterns = [

    # ── REST Dashboard (consommé par le frontend Angular) ───────────────────
    path('dashboard/super-admin/',          SuperAdminDashboardAPIView.as_view(), name='dashboard-super-admin'),
    path('dashboard/admin/',                AdminDashboardAPIView.as_view(),       name='dashboard-admin'),
    path('dashboard/formateur/',            FormateurDashboardAPIView.as_view(),   name='dashboard-formateur'),
    path('dashboard/responsable-academique/', ResponsableDashboardAPIView.as_view(), name='dashboard-responsable'),
    path('dashboard/apprenant/',            ApprenantDashboardAPIView.as_view(),   name='dashboard-apprenant'),
    path('dashboard/parent/',               ParentDashboardAPIView.as_view(),      name='dashboard-parent'),

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
]