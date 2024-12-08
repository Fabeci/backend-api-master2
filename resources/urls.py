from django.urls import path
from .views import (
    RessourceListCreateAPIView, RessourceSupplementaireListCreateAPIView,
    PieceJointeListCreateAPIView, RessourcePieceJointeListCreateAPIView,
    RessourceSuppPieceJointeListCreateAPIView
)

urlpatterns = [
    path('ressources/', RessourceListCreateAPIView.as_view(), name='ressource-list-create'),
    path('ressources-supplementaires/', RessourceSupplementaireListCreateAPIView.as_view(), name='ressource-supplementaire-list-create'),
    path('pieces-jointes/', PieceJointeListCreateAPIView.as_view(), name='piece-jointe-list-create'),
    path('ressource-piece-jointe/', RessourcePieceJointeListCreateAPIView.as_view(), name='ressource-piece-jointe-list-create'),
    path('ressource-supp-piece-jointe/', RessourceSuppPieceJointeListCreateAPIView.as_view(), name='ressource-supp-piece-jointe-list-create'),
]
