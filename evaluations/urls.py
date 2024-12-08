from django.urls import path
from .views import (
    QuizListCreateAPIView, QuestionListCreateAPIView,
    ReponseListCreateAPIView, EvaluationListCreateAPIView,
    ApprenantEvaluationListCreateAPIView, SolutionListCreateAPIView
)

urlpatterns = [
    path('quizz/', QuizListCreateAPIView.as_view(), name='quiz-list-create'),
    path('questions/', QuestionListCreateAPIView.as_view(), name='question-list-create'),
    path('reponses/', ReponseListCreateAPIView.as_view(), name='reponse-list-create'),
    path('evaluations/', EvaluationListCreateAPIView.as_view(), name='evaluation-list-create'),
    path('apprenant-evaluations/', ApprenantEvaluationListCreateAPIView.as_view(), name='apprenant-evaluation-list-create'),
    path('solutions/', SolutionListCreateAPIView.as_view(), name='solution-list-create'),
]
