from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BlocAnalyticsViewSet, RecommandationViewSet, ContenuGenereViewSet

router = DefaultRouter()
router.register(r'bloc-analytics', BlocAnalyticsViewSet, basename='bloc-analytics')
router.register(r'recommandations', RecommandationViewSet, basename='recommandations')
router.register(r'contenus-generes', ContenuGenereViewSet, basename='contenus-generes')

urlpatterns = [
    path('', include(router.urls)),
]