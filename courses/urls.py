# courses/urls.py

from django.urls import path
from .views import (
    # Cours
    BlocProgressListAPIView,
    BlocProgressToggleAPIView,
    CoursListCreateAPIView,
    CoursDetailAPIView,
    CoursModulesAPIView,
    CoursProgressListAPIView,
    CoursProgressToggleAPIView,
    
    # Modules
    ModuleListCreateAPIView,
    ModuleDetailAPIView,
    ModuleProgressListAPIView,
    ModuleProgressToggleAPIView,
    ModuleSequencesAPIView,
    
    # Séquences
    SequenceDetailAPIView,
    SequenceBlocsAPIView,
    SequenceListCreateAPIView,
    SequenceProgressListAPIView,
    SequenceProgressToggleAPIView,
    SequenceRessourcesAPIView,
    
    # Blocs de contenu
    BlocContenuListCreateAPIView,
    BlocContenuDetailAPIView,
    
    # Ressources
    RessourceSequenceListCreateAPIView,
    RessourceSequenceDetailAPIView,
    RessourceTelechargementAPIView,
    
    # Inscriptions, Suivis, Sessions, Participations
    InscriptionCoursListCreateAPIView,
    InscriptionCoursDetailAPIView,
    SuiviListCreateAPIView,
    SuiviDetailAPIView,
    SessionListCreateAPIView,
    SessionDetailAPIView,
    SessionParticipantsAPIView,
    ParticipationListCreateAPIView,
    ParticipationDetailAPIView,
)

urlpatterns = [
    # Cours
    path('cours/', CoursListCreateAPIView.as_view(), name='cours-list-create'),
    path('cours/<int:pk>/', CoursDetailAPIView.as_view(), name='cours-detail'),
    path('cours/<int:cours_id>/modules/', CoursModulesAPIView.as_view(), name='cours-modules'),
    
    # Modules
    path('modules/', ModuleListCreateAPIView.as_view(), name='module-list-create'),
    path('modules/<int:pk>/', ModuleDetailAPIView.as_view(), name='module-detail'),
    path('modules/<int:module_id>/sequences/', ModuleSequencesAPIView.as_view(), name='module-sequences'),
    
    # Séquences
    path('sequences/', SequenceListCreateAPIView.as_view(), name='sequence-list-create'),
    path('sequences/<int:pk>/', SequenceDetailAPIView.as_view(), name='sequence-detail'),
    path('sequences/<int:sequence_id>/blocs/', SequenceBlocsAPIView.as_view(), name='sequence-blocs'),
    path('sequences/<int:sequence_id>/ressources/', SequenceRessourcesAPIView.as_view(), name='sequence-ressources'),
    
    # Blocs de contenu
    path('blocs-contenu/', BlocContenuListCreateAPIView.as_view(), name='bloc-contenu-list-create'),
    path('blocs-contenu/<int:pk>/', BlocContenuDetailAPIView.as_view(), name='bloc-contenu-detail'),
    
    # Ressources / Pièces jointes
    path('ressources/', RessourceSequenceListCreateAPIView.as_view(), name='ressource-list-create'),
    path('ressources/<int:pk>/', RessourceSequenceDetailAPIView.as_view(), name='ressource-detail'),
    path('ressources/<int:pk>/telecharger/', RessourceTelechargementAPIView.as_view(), name='ressource-telecharger'),
    
    # Inscriptions
    path('inscriptions/', InscriptionCoursListCreateAPIView.as_view(), name='inscription-list-create'),
    path('inscriptions/<int:pk>/', InscriptionCoursDetailAPIView.as_view(), name='inscription-detail'),
    
    # Suivis
    path('suivis/', SuiviListCreateAPIView.as_view(), name='suivi-list-create'),
    path('suivis/<int:pk>/', SuiviDetailAPIView.as_view(), name='suivi-detail'),
    
    # Sessions
    path('sessions/', SessionListCreateAPIView.as_view(), name='session-list-create'),
    path('sessions/<int:pk>/', SessionDetailAPIView.as_view(), name='session-detail'),
    path('sessions/<int:pk>/participants/', SessionParticipantsAPIView.as_view(), name='session-participants'),
    
    # Participations
    path('participations/', ParticipationListCreateAPIView.as_view(), name='participation-list-create'),
    path('participations/<int:pk>/', ParticipationDetailAPIView.as_view(), name='participation-detail'),


     # =========================================================================
    # PROGRESSION
    # =========================================================================
    path('progress/blocs/', BlocProgressListAPIView.as_view(), name='progress-blocs-list'),
    path('progress/blocs/<int:bloc_id>/', BlocProgressToggleAPIView.as_view(), name='progress-bloc-toggle'),

    path('progress/sequences/', SequenceProgressListAPIView.as_view(), name='progress-sequences-list'),
    path('progress/sequences/<int:sequence_id>/', SequenceProgressToggleAPIView.as_view(), name='progress-sequence-toggle'),

    path('progress/modules/', ModuleProgressListAPIView.as_view(), name='progress-modules-list'),
    path('progress/modules/<int:module_id>/', ModuleProgressToggleAPIView.as_view(), name='progress-module-toggle'),

    path('progress/cours/', CoursProgressListAPIView.as_view(), name='progress-cours-list'),
    path('progress/cours/<int:cours_id>/', CoursProgressToggleAPIView.as_view(), name='progress-cours-toggle'),
]