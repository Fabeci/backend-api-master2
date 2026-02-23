# courses/urls_ai.py

from django.urls import path
from .views_ai import (
    AIAnalyzeView,
    AISuggestionsView,
    BlocGenereConsulteView,
    BlocGenereFeedbackView,
    QuizGenereConsulteView,
    QuizGenereScoreView,
)

urlpatterns = [

    # Déclencher une analyse et lancer la génération GPT
    path(
        'ai/analyze/',
        AIAnalyzeView.as_view(),
        name='ai-analyze',
    ),

    # Récupérer les suggestions générées pour un apprenant
    path(
        'ai/suggestions/<int:apprenant_id>/',
        AISuggestionsView.as_view(),
        name='ai-suggestions',
    ),

    # Blocs générés
    path(
        'ai/bloc-genere/<int:pk>/consulte/',
        BlocGenereConsulteView.as_view(),
        name='ai-bloc-genere-consulte',
    ),
    path(
        'ai/bloc-genere/<int:pk>/feedback/',
        BlocGenereFeedbackView.as_view(),
        name='ai-bloc-genere-feedback',
    ),

    # Quiz générés
    path(
        'ai/quiz-genere/<int:pk>/consulte/',
        QuizGenereConsulteView.as_view(),
        name='ai-quiz-genere-consulte',
    ),
    path(
        'ai/quiz-genere/<int:pk>/score/',
        QuizGenereScoreView.as_view(),
        name='ai-quiz-genere-score',
    ),
]