# courses/urls_analytics.py
# ============================================================================
# URL PATTERNS ANALYTICS
#
# INTÉGRATION dans votre urls.py principal :
#
#   Option A — include (recommandé) :
#   ------------------------------------
#   from django.urls import path, include
#   urlpatterns = [
#       ...
#       path('', include('courses.urls_analytics')),
#       ...
#   ]
#
#   Option B — copier-coller directement dans urls.py :
#   ------------------------------------
#   from courses.views_analytics import (
#       AnalyticsDebugView,
#       BlocAnalyticsOpenView, BlocAnalyticsCloseView,
#       BulkAnalyticsSummaryView,
#       RecommandationsListView, RecommandationVueView, RecommandationSuivieView,
#       ContenuGenereDetailView, ContenuGenereConsulteView, ContenuGenereFeedbackView,
#   )
#   puis ajouter les path() ci-dessous dans votre urlpatterns.
#
# ⚠️  ORDRE CRITIQUE :
#   'bloc/session/<session_id>/close/' DOIT être déclaré AVANT
#   'bloc/<bloc_id>/open/' — sinon Django interprète 'session' comme
#   un bloc_id et retourne 404 ou 500.
# ============================================================================

from django.urls import path
from .views import (
    AnalyticsDebugView,
    BlocAnalyticsOpenView,
    BlocAnalyticsCloseView,
    BulkAnalyticsSummaryView,
    RecommandationsListView,
    RecommandationVueView,
    RecommandationSuivieView,
    ContenuGenereDetailView,
    ContenuGenereConsulteView,
    ContenuGenereFeedbackView,
)

urlpatterns = [

    # ── Diagnostic (désactiver en production) ──────────────────────────────
    path(
        'analytics/debug/',
        AnalyticsDebugView.as_view(),
        name='analytics-debug',
    ),

    # ── Tracking blocs ─────────────────────────────────────────────────────
    # ⚠️  session/close AVANT bloc/open (ordre Django)
    path(
        'analytics/bloc/session/<int:session_id>/close/',
        BlocAnalyticsCloseView.as_view(),
        name='analytics-bloc-close',
    ),
    path(
        'analytics/bloc/<int:bloc_id>/open/',
        BlocAnalyticsOpenView.as_view(),
        name='analytics-bloc-open',
    ),

    # ── Bulk résumés ───────────────────────────────────────────────────────
    path(
        'analytics/bulk-summary/',
        BulkAnalyticsSummaryView.as_view(),
        name='analytics-bulk-summary',
    ),

    # ── Recommandations ────────────────────────────────────────────────────
    path(
        'analytics/recommendations/<int:apprenant_id>/',
        RecommandationsListView.as_view(),
        name='analytics-recommendations-list',
    ),
    path(
        'analytics/recommendations/<int:pk>/vue/',
        RecommandationVueView.as_view(),
        name='analytics-reco-vue',
    ),
    path(
        'analytics/recommendations/<int:pk>/suivie/',
        RecommandationSuivieView.as_view(),
        name='analytics-reco-suivie',
    ),

    # ── Contenu généré ─────────────────────────────────────────────────────
    path(
        'analytics/contenu/<int:pk>/',
        ContenuGenereDetailView.as_view(),
        name='analytics-contenu-detail',
    ),
    path(
        'analytics/contenu/<int:pk>/consulte/',
        ContenuGenereConsulteView.as_view(),
        name='analytics-contenu-consulte',
    ),
    path(
        'analytics/contenu/<int:pk>/feedback/',
        ContenuGenereFeedbackView.as_view(),
        name='analytics-contenu-feedback',
    ),
]