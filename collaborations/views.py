from django.db.models import Q
from core.tenant import default_institution_id
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import get_object_or_404
from .models import Conversation, Participant, Message, Forum, Commentaire
from .serializers import ConversationSerializer, ParticipantSerializer, MessageSerializer, ForumSerializer, CommentaireSerializer


# ============================================================================
# ✅ SÉCURITÉ — helpers d'accès (les vues étaient ouvertes à tous les
# utilisateurs authentifiés : lecture et suppression de données d'autrui).
# ============================================================================

def _is_privileged(user) -> bool:
    from users.access_control import role_key
    return bool(getattr(user, 'is_superuser', False)) or role_key(user) in (
        'superadmin', 'admin', 'responsable', 'responsableacademique'
    )


def _conversations_for(user):
    """Conversations dont l'utilisateur est participant."""
    return Conversation.objects.filter(participants__user=user).distinct()


def _messages_for(user):
    """Messages des conversations dont l'utilisateur est participant."""
    return Message.objects.filter(conversation__participants__user=user).distinct()


def _is_author(user, obj) -> bool:
    for attr in ('envoyeur', 'auteur', 'user'):
        owner = getattr(obj, attr, None)
        if owner is not None:
            return owner.pk == user.pk
    return False


# ============================================================================
# Conversation
# ============================================================================
class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        conversations = _conversations_for(request.user).prefetch_related('participants', 'messages')
        serializer = ConversationSerializer(conversations, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = ConversationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        # ✅ SÉCURITÉ : uniquement les conversations de l'utilisateur.
        return _conversations_for(user).filter(pk=pk).first()

    def get(self, request, pk, format=None):
        conversation = self.get_object(pk, request.user)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ConversationSerializer(conversation)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        conversation = self.get_object(pk, request.user)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ConversationSerializer(conversation, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        conversation = self.get_object(pk, request.user)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Participant
# ============================================================================
class ParticipantListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        # ✅ SÉCURITÉ : participants des conversations de l'utilisateur.
        participants = Participant.objects.filter(
            conversation__participants__user=request.user
        ).distinct()
        serializer = ParticipantSerializer(participants, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = ParticipantSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ParticipantDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        return Participant.objects.filter(
            conversation__participants__user=user, pk=pk
        ).distinct().first()

    def get(self, request, pk, format=None):
        participant = self.get_object(pk, request.user)
        if participant is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ParticipantSerializer(participant)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        participant = self.get_object(pk, request.user)
        if participant is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ParticipantSerializer(participant, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        participant = self.get_object(pk, request.user)
        if participant is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : sa propre participation, ou rôle privilégié.
        if participant.user_id != request.user.pk and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        participant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Message
# ============================================================================
class MessageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        # ✅ SÉCURITÉ : messages des conversations de l'utilisateur.
        messages = _messages_for(request.user)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = MessageSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MessageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk, user):
        return _messages_for(user).filter(pk=pk).first()

    def get(self, request, pk, format=None):
        message = self.get_object(pk, request.user)
        if message is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MessageSerializer(message)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        message = self.get_object(pk, request.user)
        if message is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : seul l'auteur (ou un rôle privilégié) peut modifier.
        if not _is_author(request.user, message) and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = MessageSerializer(message, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        message = self.get_object(pk, request.user)
        if message is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : seul l'auteur (ou un rôle privilégié) peut supprimer.
        if not _is_author(request.user, message) and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Forum
# ============================================================================
class ForumListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        iid = default_institution_id()
        forums = Forum.objects.filter(
            Q(cours__institution_id=iid) | Q(cours__isnull=True)
        )
        serializer = ForumSerializer(forums, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = ForumSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ForumDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Forum.objects.get(pk=pk)
        except Forum.DoesNotExist:
            return None

    def get(self, request, pk, format=None):
        forum = self.get_object(pk)
        if forum is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ForumSerializer(forum)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        forum = self.get_object(pk)
        if forum is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : seul l'auteur (ou un rôle privilégié) peut modifier.
        if not _is_author(request.user, forum) and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = ForumSerializer(forum, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        forum = self.get_object(pk)
        if forum is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : seul l'auteur (ou un rôle privilégié) peut supprimer.
        if not _is_author(request.user, forum) and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        forum.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# Commentaire
# ============================================================================
class CommentaireListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        iid = default_institution_id()
        commentaires = Commentaire.objects.filter(
            Q(forum__cours__institution_id=iid) | Q(forum__cours__isnull=True)
        )
        serializer = CommentaireSerializer(commentaires, many=True)
        return Response(serializer.data)

    def post(self, request, format=None):
        serializer = CommentaireSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentaireDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return Commentaire.objects.get(pk=pk)
        except Commentaire.DoesNotExist:
            return None

    def get(self, request, pk, format=None):
        commentaire = self.get_object(pk)
        if commentaire is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = CommentaireSerializer(commentaire)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        commentaire = self.get_object(pk)
        if commentaire is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : seul l'auteur (ou un rôle privilégié) peut modifier.
        if not _is_author(request.user, commentaire) and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        serializer = CommentaireSerializer(commentaire, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        commentaire = self.get_object(pk)
        if commentaire is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        # ✅ SÉCURITÉ : seul l'auteur (ou un rôle privilégié) peut supprimer.
        if not _is_author(request.user, commentaire) and not _is_privileged(request.user):
            return Response({'detail': 'Accès refusé.'}, status=status.HTTP_403_FORBIDDEN)
        commentaire.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageByConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_conversation(self, conversation_id, user):
        # ✅ SÉCURITÉ : accès réservé aux participants de la conversation.
        return _conversations_for(user).filter(id=conversation_id).first()

    def get(self, request, conversation_id, format=None):
        conversation = self._get_conversation(conversation_id, request.user)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        messages = Message.objects.filter(conversation=conversation)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, conversation_id, format=None):
        conversation = self._get_conversation(conversation_id, request.user)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        data = request.data
        data['conversation'] = conversation.id  # Associer le message à cette conversation
        serializer = MessageSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CommentaireByForumView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, forum_id, format=None):
        forum = get_object_or_404(Forum, id=forum_id)
        commentaires = Commentaire.objects.filter(forum=forum)
        serializer = CommentaireSerializer(commentaires, many=True)
        return Response(serializer.data)

    def post(self, request, forum_id, format=None):
        forum = get_object_or_404(Forum, id=forum_id)
        data = request.data
        data['forum'] = forum.id  # Associer le commentaire à ce forum
        serializer = CommentaireSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
