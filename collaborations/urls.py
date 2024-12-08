from django.urls import path
from .views import (
    ConversationListView, ConversationDetailView,
    ParticipantListView, ParticipantDetailView,
    MessageListView, MessageDetailView,
    ForumListView, ForumDetailView,
    CommentaireListView, CommentaireDetailView,
    MessageByConversationView, CommentaireByForumView
)

urlpatterns = [
    # Conversations
    path('conversations/', ConversationListView.as_view(), name='conversation-list'),
    path('conversations/<int:pk>/', ConversationDetailView.as_view(), name='conversation-detail'),
    
    # Participants
    path('participants/', ParticipantListView.as_view(), name='participant-list'),
    path('participants/<int:pk>/', ParticipantDetailView.as_view(), name='participant-detail'),

    # Messages globaux
    path('messages/', MessageListView.as_view(), name='message-list'),
    path('messages/<int:pk>/', MessageDetailView.as_view(), name='message-detail'),

    # Messages par conversation
    path('conversations/<int:conversation_id>/messages/', MessageByConversationView.as_view(), name='messages-by-conversation'),

    # Forums
    path('forums/', ForumListView.as_view(), name='forum-list'),
    path('forums/<int:pk>/', ForumDetailView.as_view(), name='forum-detail'),

    # Commentaires globaux
    path('commentaires/', CommentaireListView.as_view(), name='commentaire-list'),
    path('commentaires/<int:pk>/', CommentaireDetailView.as_view(), name='commentaire-detail'),

    # Commentaires par forum
    path('forums/<int:forum_id>/commentaires/', CommentaireByForumView.as_view(), name='commentaires-by-forum'),
]
