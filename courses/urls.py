# courses/urls.py

from django.urls import path
from courses.meet_views import (
    GoogleMeetStatusAPIView,
    SessionJitsiCreateAPIView,
    SessionMeetCreateAPIView,
    SessionMeetSyncAPIView,
)
from courses.teams_views import (
    SessionTeamsCreateAPIView,
    SessionTeamsSyncAPIView,
    TeamsStatusAPIView,
)
from courses.invite_views import (
    SessionInviteDetailAPIView,
    SessionInviteListCreateAPIView,
)
from courses.import_views import (
    BlocsImportExtractAPIView,
    SequenceBlocsImportCreateAPIView,
)
from courses.import_course_views import (
    CoursImportAnalyseAPIView,
    CoursImportCreateAPIView,
)
from courses.import_inscription_views import (
    InscriptionImportAnalyseAPIView,
    InscriptionImportCreateAPIView,
)
from .views import (
    # Cours
    BlocContenuUploadView,
    BlocProgressListAPIView,
    BlocProgressToggleAPIView,
    CoursIndicateursAPIView,
    CoursListCreateAPIView,
    CoursDetailAPIView,
    CoursModulesAPIView,
    CoursProgressListAPIView,
    CoursProgressToggleAPIView,
    
    # Modules
    ModuleListCreateAPIView,
    ModuleCopyAPIView,
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
    BlocContenuEstimerAPIView,
    
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
    SessionCalendrierAPIView,
    SessionDetailAPIView,
    SessionParticipantsAPIView,
    ParticipationListCreateAPIView,
    ParticipationDetailAPIView,
    # Parcours (déblocage progressif + reprise + validation)
    ParcoursAPIView,
    ResumeAPIView,
    BlocValiderAPIView,
)

from courses.views_chat import (  # noqa: E402
    BlocChatAPIView,
    BlocChatStreamAPIView,
    BlocQuizAPIView,
    ConversationChatDetailAPIView,
    ConversationChatNouvelleAPIView,
    QuizCorrectionAPIView,
)

urlpatterns = [
    # Cours
    path('cours/', CoursListCreateAPIView.as_view(), name='cours-list-create'),
    # Import d'un cours complet (Word / PDF → modules, séquences, blocs, quiz)
    path('cours/importer/analyser/', CoursImportAnalyseAPIView.as_view(), name='cours-import-analyser'),
    path('cours/importer/', CoursImportCreateAPIView.as_view(), name='cours-import-create'),
    path('cours/<int:pk>/', CoursDetailAPIView.as_view(), name='cours-detail'),
    path('cours/<int:cours_id>/modules/', CoursModulesAPIView.as_view(), name='cours-modules'),
    path('cours/<int:pk>/indicateurs/',  CoursIndicateursAPIView.as_view()),
    
    # Modules
    path('modules/', ModuleListCreateAPIView.as_view(), name='module-list-create'),
    path('modules/copier/', ModuleCopyAPIView.as_view(), name='module-copier'),
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
    path('blocs-contenu/<int:pk>/estimer/', BlocContenuEstimerAPIView.as_view(), name='bloc-contenu-estimer'),
    path('blocs-contenu/upload/', BlocContenuUploadView.as_view(), name='bloc-contenu-upload'),
    
    # Ressources / Pièces jointes
    path('ressources/', RessourceSequenceListCreateAPIView.as_view(), name='ressource-list-create'),
    path('ressources/<int:pk>/', RessourceSequenceDetailAPIView.as_view(), name='ressource-detail'),
    path('ressources/<int:pk>/telecharger/', RessourceTelechargementAPIView.as_view(), name='ressource-telecharger'),
    
    # Inscriptions
    path('inscriptions/', InscriptionCoursListCreateAPIView.as_view(), name='inscription-list-create'),
    # Import d'inscriptions depuis un document (CSV / Excel / Word / PDF / TXT)
    path('inscriptions/importer/analyser/', InscriptionImportAnalyseAPIView.as_view(), name='inscriptions-import-analyser'),
    path('inscriptions/importer/', InscriptionImportCreateAPIView.as_view(), name='inscriptions-import-create'),
    path('inscriptions/<int:pk>/', InscriptionCoursDetailAPIView.as_view(), name='inscription-detail'),
    
    # Suivis
    path('suivis/', SuiviListCreateAPIView.as_view(), name='suivi-list-create'),
    path('suivis/<int:pk>/', SuiviDetailAPIView.as_view(), name='suivi-detail'),
    
    # Sessions
    path('sessions/', SessionListCreateAPIView.as_view(), name='session-list-create'),
    path('sessions/calendrier/', SessionCalendrierAPIView.as_view(), name='session-calendrier'),
    path('sessions/<int:pk>/', SessionDetailAPIView.as_view(), name='session-detail'),
    path('sessions/<int:pk>/participants/', SessionParticipantsAPIView.as_view(), name='session-participants'),
    # Google Meet (réunions en direct)
    path('sessions/<int:pk>/meet/creer/', SessionMeetCreateAPIView.as_view(), name='session-meet-create'),
    path('sessions/<int:pk>/meet/synchroniser/', SessionMeetSyncAPIView.as_view(), name='session-meet-sync'),
    path('sessions/<int:pk>/jitsi/creer/', SessionJitsiCreateAPIView.as_view(), name='session-jitsi-create'),
    path('sessions/<int:pk>/teams/creer/', SessionTeamsCreateAPIView.as_view(), name='session-teams-create'),
    path('sessions/<int:pk>/teams/synchroniser/', SessionTeamsSyncAPIView.as_view(), name='session-teams-sync'),
    path('sessions/<int:pk>/invites/', SessionInviteListCreateAPIView.as_view(), name='session-invites'),
    path('sessions/<int:pk>/invites/<int:invite_id>/', SessionInviteDetailAPIView.as_view(), name='session-invite-detail'),
    # Import de blocs (fichier → brouillon → création en lot)
    path('blocs-contenu/importer/', BlocsImportExtractAPIView.as_view(), name='blocs-import-extract'),
    path('sequences/<int:pk>/blocs/importer/', SequenceBlocsImportCreateAPIView.as_view(), name='sequence-blocs-import'),
    path('meet/statut/', GoogleMeetStatusAPIView.as_view(), name='google-meet-status'),
    path('teams/statut/', TeamsStatusAPIView.as_view(), name='teams-status'),
    
    # Participations
    path('participations/', ParticipationListCreateAPIView.as_view(), name='participation-list-create'),
    path('participations/<int:pk>/', ParticipationDetailAPIView.as_view(), name='participation-detail'),


     # =========================================================================
    # PROGRESSION
    # =========================================================================
    path('progress/blocs/', BlocProgressListAPIView.as_view(), name='progress-blocs-list'),
    path('progress/blocs/<int:bloc_id>/valider/', BlocValiderAPIView.as_view(), name='progress-bloc-valider'),
    path('progress/blocs/<int:bloc_id>/', BlocProgressToggleAPIView.as_view(), name='progress-bloc-toggle'),

    # Parcours + reprise
    path('cours/<int:cours_id>/parcours/', ParcoursAPIView.as_view(), name='cours-parcours'),
    path('cours/<int:cours_id>/resume/', ResumeAPIView.as_view(), name='cours-resume'),

    path('progress/sequences/', SequenceProgressListAPIView.as_view(), name='progress-sequences-list'),
    path('progress/sequences/<int:sequence_id>/', SequenceProgressToggleAPIView.as_view(), name='progress-sequence-toggle'),

    path('progress/modules/', ModuleProgressListAPIView.as_view(), name='progress-modules-list'),
    path('progress/modules/<int:module_id>/', ModuleProgressToggleAPIView.as_view(), name='progress-module-toggle'),

    path('progress/cours/', CoursProgressListAPIView.as_view(), name='progress-cours-list'),
    path('progress/cours/<int:cours_id>/', CoursProgressToggleAPIView.as_view(), name='progress-cours-toggle'),

    # =========================================================================
    # ASSISTANT PÉDAGOGIQUE IA (chat par bloc)
    # =========================================================================
    path('blocs/<int:bloc_id>/chat/', BlocChatAPIView.as_view(), name='bloc-chat'),
    path('blocs/<int:bloc_id>/chat/stream/', BlocChatStreamAPIView.as_view(), name='bloc-chat-stream'),
    path('blocs/<int:bloc_id>/chat/quiz/', BlocQuizAPIView.as_view(), name='bloc-chat-quiz'),
    path('chat/quiz/<int:pk>/corriger/', QuizCorrectionAPIView.as_view(), name='chat-quiz-corriger'),
    path('chat/conversations/<int:pk>/', ConversationChatDetailAPIView.as_view(), name='chat-conversation-detail'),
    path('chat/conversations/<int:pk>/nouvelle/', ConversationChatNouvelleAPIView.as_view(), name='chat-conversation-nouvelle'),
]
