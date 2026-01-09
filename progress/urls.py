# progress/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ProgressionApprenantViewSet,
    ProgressionModuleViewSet,
    ProgressionSequenceViewSet,
    ProgressionQuizViewSet,
    HistoriqueActiviteViewSet,
    PlanActionViewSet,
    ObjectifPlanActionViewSet,
)

app_name = 'progress'

router = DefaultRouter()
router.register(r'progressions-apprenants', ProgressionApprenantViewSet, basename='progression-apprenant')
router.register(r'progressions-modules', ProgressionModuleViewSet, basename='progression-module')
router.register(r'progressions-sequences', ProgressionSequenceViewSet, basename='progression-sequence')
router.register(r'progressions-quiz', ProgressionQuizViewSet, basename='progression-quiz')
router.register(r'historique-activites', HistoriqueActiviteViewSet, basename='historique-activite')
router.register(r'plans-action', PlanActionViewSet, basename='plan-action')
router.register(r'objectifs-plan-action', ObjectifPlanActionViewSet, basename='objectif-plan-action')

urlpatterns = [
    path('', include(router.urls)),
]