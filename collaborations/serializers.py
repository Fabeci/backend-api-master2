from rest_framework import serializers
from .models import Conversation, Participant, Message, Forum, Commentaire
from users.models import User  # Assuming the User model is in the 'users' app
from courses.models import Cours, Sequence, Module  # Assuming the course models are in 'courses' app

class ConversationSerializer(serializers.ModelSerializer):
    participants = serializers.StringRelatedField(many=True)  # Nom des participants
    messages = serializers.StringRelatedField(many=True)  # Identifiant des messages

    class Meta:
        model = Conversation
        fields = ['id', 'sujet', 'date_creation', 'participants', 'messages']
        
        
class ParticipantSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField()  # Nom d'utilisateur du participant
    conversation = ConversationSerializer()  # Sérialiser la conversation associée

    class Meta:
        model = Participant
        fields = ['user', 'conversation', 'date_rejoint', 'dernier_message_lu']
        
        
class MessageSerializer(serializers.ModelSerializer):
    envoyeur = serializers.StringRelatedField()  # Nom de l'envoyeur du message
    conversation = ConversationSerializer()  # Sérialiser la conversation associée

    class Meta:
        model = Message
        fields = ['id', 'conversation', 'envoyeur', 'contenu', 'date_envoi']
        
        
class ForumSerializer(serializers.ModelSerializer):
    cours = serializers.StringRelatedField()  # Affiche le titre du cours
    sequence = serializers.StringRelatedField()  # Affiche le titre de la séquence
    module = serializers.StringRelatedField()  # Affiche le titre du module
    auteur = serializers.StringRelatedField()  # Affiche le nom de l'auteur du forum

    class Meta:
        model = Forum
        fields = ['id', 'titre', 'description', 'cours', 'sequence', 'module', 'auteur', 'date_creation']
        
        
class CommentaireSerializer(serializers.ModelSerializer):
    auteur = serializers.StringRelatedField()  # Nom de l'auteur du commentaire
    forum = ForumSerializer()  # Sérialiser le forum associé
    parent = serializers.StringRelatedField()  # ID du commentaire parent, s'il existe

    class Meta:
        model = Commentaire
        fields = ['id', 'forum', 'auteur', 'contenu', 'date_creation', 'parent']