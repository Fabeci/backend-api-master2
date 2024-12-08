from django.urls import path
from .views import (
    FeedbackListCreateAPIView, ProgressionListCreateAPIView,
    HistoriqueProgressionListCreateAPIView, PlanActionListCreateAPIView
)

urlpatterns = [
    path('feedbacks/', FeedbackListCreateAPIView.as_view(), name='feedback-list-create'),
    path('progressions/', ProgressionListCreateAPIView.as_view(), name='progression-list-create'),
    path('historique-progressions/', HistoriqueProgressionListCreateAPIView.as_view(), name='historique-progression-list-create'),
    path('plans-actions/', PlanActionListCreateAPIView.as_view(), name='plan-action-list-create'),
]
