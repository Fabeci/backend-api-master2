from django.urls import path
from .views import (
    # Quiz
    QuizListCreateAPIView,
    QuizDetailAPIView,
    PassageQuizListCreateAPIView,
    PassageQuizDetailAPIView,
    PassageQuizTerminerAPIView,
    ReponseQuizSubmitAPIView,
    
    # Questions et Réponses
    QuestionListCreateAPIView,
    QuestionDetailAPIView,
    ReponseListCreateAPIView,
    ReponseDetailAPIView,
    
    # Évaluations
    EvaluationListCreateAPIView,
    EvaluationDetailAPIView,
    EvaluationPublierAPIView,
    
    # Passages d'évaluations
    PassageEvaluationListCreateAPIView,
    PassageEvaluationDetailAPIView,
    PassageEvaluationSoumettreAPIView,
    
    # Réponses aux questions
    ReponseQuestionSubmitAPIView,
    ReponseQuestionDetailAPIView,
    
    # Correction
    CorrectionReponseAPIView,
    CorrectionEvaluationAPIView,
    EvaluationsACorrigerAPIView,
    
    # Statistiques
    StatistiquesApprenantAPIView,
    StatistiquesEvaluationAPIView,
)

app_name = 'evaluations'

urlpatterns = [
    # ============================================================================
    # QUIZ
    # ============================================================================
    
    # CRUD Quiz
    path('quiz/', 
         QuizListCreateAPIView.as_view(), 
         name='quiz-list-create'),
    path('quiz/<int:pk>/', 
         QuizDetailAPIView.as_view(), 
         name='quiz-detail'),
    
    # Passages de quiz
    path('passages-quiz/', 
         PassageQuizListCreateAPIView.as_view(), 
         name='passage-quiz-list-create'),
    path('passages-quiz/<int:pk>/', 
         PassageQuizDetailAPIView.as_view(), 
         name='passage-quiz-detail'),
    path('passages-quiz/<int:pk>/terminer/', 
         PassageQuizTerminerAPIView.as_view(), 
         name='passage-quiz-terminer'),
    
    # Réponses aux questions de quiz
    path('reponses-quiz/submit/', 
         ReponseQuizSubmitAPIView.as_view(), 
         name='reponse-quiz-submit'),
    
    
    # ============================================================================
    # QUESTIONS ET RÉPONSES PRÉDÉFINIES
    # ============================================================================
    
    # CRUD Questions
    path('questions/', 
         QuestionListCreateAPIView.as_view(), 
         name='question-list-create'),
    path('questions/<int:pk>/', 
         QuestionDetailAPIView.as_view(), 
         name='question-detail'),
    
    # CRUD Réponses prédéfinies (choix de QCM)
    path('reponses/', 
         ReponseListCreateAPIView.as_view(), 
         name='reponse-list-create'),
    path('reponses/<int:pk>/', 
         ReponseDetailAPIView.as_view(), 
         name='reponse-detail'),
    
    
    # ============================================================================
    # ÉVALUATIONS
    # ============================================================================
    
    # CRUD Évaluations
    path('evaluations/', 
         EvaluationListCreateAPIView.as_view(), 
         name='evaluation-list-create'),
    path('evaluations/<int:pk>/', 
         EvaluationDetailAPIView.as_view(), 
         name='evaluation-detail'),
    path('evaluations/<int:pk>/publier/', 
         EvaluationPublierAPIView.as_view(), 
         name='evaluation-publier'),
    
    # Passages d'évaluations (par les apprenants)
    path('passages-evaluations/', 
         PassageEvaluationListCreateAPIView.as_view(), 
         name='passage-evaluation-list-create'),
    path('passages-evaluations/<int:pk>/', 
         PassageEvaluationDetailAPIView.as_view(), 
         name='passage-evaluation-detail'),
    path('passages-evaluations/<int:pk>/soumettre/', 
         PassageEvaluationSoumettreAPIView.as_view(), 
         name='passage-evaluation-soumettre'),
    
    # Réponses aux questions d'évaluation
    path('reponses-questions/submit/', 
         ReponseQuestionSubmitAPIView.as_view(), 
         name='reponse-question-submit'),
     path(
        'reponses-questions/<int:pk>/',
        ReponseQuestionSubmitAPIView.as_view(),
        name='reponse-question-update'
    ),
    path('reponses-questions/<int:pk>/', 
         ReponseQuestionDetailAPIView.as_view(), 
         name='reponse-question-detail'),
    
    
    # ============================================================================
    # CORRECTION (ENSEIGNANTS)
    # ============================================================================
    
    # Corriger une réponse individuelle
    path('corrections/reponse/<int:pk>/', 
         CorrectionReponseAPIView.as_view(), 
         name='correction-reponse'),
    
    # Corriger une évaluation complète
    path('corrections/evaluation/<int:pk>/', 
         CorrectionEvaluationAPIView.as_view(), 
         name='correction-evaluation'),
    
    # Liste des évaluations à corriger
    path('corrections/a-corriger/', 
         EvaluationsACorrigerAPIView.as_view(), 
         name='evaluations-a-corriger'),
    
    
    # ============================================================================
    # STATISTIQUES
    # ============================================================================
    
    # Statistiques d'un apprenant
    path('statistiques/apprenant/<int:apprenant_id>/', 
         StatistiquesApprenantAPIView.as_view(), 
         name='stats-apprenant'),
    
    # Statistiques d'une évaluation
    path('statistiques/evaluation/<int:evaluation_id>/', 
         StatistiquesEvaluationAPIView.as_view(), 
         name='stats-evaluation'),
]