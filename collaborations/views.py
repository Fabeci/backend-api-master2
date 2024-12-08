from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import get_object_or_404
from .models import Conversation, Participant, Message, Forum, Commentaire
from .serializers import ConversationSerializer, ParticipantSerializer, MessageSerializer, ForumSerializer, CommentaireSerializer

# Vues pour Conversation
class ConversationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        conversations = Conversation.objects.all()
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

    def get_object(self, pk):
        try:
            return Conversation.objects.get(pk=pk)
        except Conversation.DoesNotExist:
            return None

    def get(self, request, pk, format=None):
        conversation = self.get_object(pk)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ConversationSerializer(conversation)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        conversation = self.get_object(pk)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ConversationSerializer(conversation, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        conversation = self.get_object(pk)
        if conversation is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        conversation.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Vues pour Participant
class ParticipantListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        participants = Participant.objects.all()
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

    def get_object(self, pk):
        try:
            return Participant.objects.get(pk=pk)
        except Participant.DoesNotExist:
            return None

    def get(self, request, pk, format=None):
        participant = self.get_object(pk)
        if participant is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ParticipantSerializer(participant)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        participant = self.get_object(pk)
        if participant is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = ParticipantSerializer(participant, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        participant = self.get_object(pk)
        if participant is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        participant.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Vues pour Message
class MessageListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        messages = Message.objects.all()
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

    def get_object(self, pk):
        try:
            return Message.objects.get(pk=pk)
        except Message.DoesNotExist:
            return None

    def get(self, request, pk, format=None):
        message = self.get_object(pk)
        if message is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MessageSerializer(message)
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        message = self.get_object(pk)
        if message is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = MessageSerializer(message, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        message = self.get_object(pk)
        if message is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        message.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Vues pour Forum
class ForumListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        forums = Forum.objects.all()
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
        serializer = ForumSerializer(forum, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        forum = self.get_object(pk)
        if forum is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        forum.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Vues pour Commentaire
class CommentaireListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, format=None):
        commentaires = Commentaire.objects.all()
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
        serializer = CommentaireSerializer(commentaire, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        commentaire = self.get_object(pk)
        if commentaire is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        commentaire.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    
class MessageByConversationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id, format=None):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        messages = Message.objects.filter(conversation=conversation)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, conversation_id, format=None):
        conversation = get_object_or_404(Conversation, id=conversation_id)
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

