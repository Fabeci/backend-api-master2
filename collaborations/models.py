from django.db import models

# Create your models here.
class Conversation(models.Model):
    sujet = models.CharField(max_length=255, blank=True, null=True)  # Facultatif, sujet de la conversation
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Conversation {self.id} - Sujet: {self.sujet or 'Sans sujet'}"


class Participant(models.Model):
    user = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name="conversations")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    date_rejoint = models.DateTimeField(auto_now_add=True)
    dernier_message_lu = models.DateTimeField(blank=True, null=True)  # Pour le suivi des messages non lus

    class Meta:
        unique_together = (
        'user', 'conversation')  # Un utilisateur ne peut participer qu'une fois par conversation

    def __str__(self):
        return f"{self.user.username} - {self.conversation}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    envoyeur = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name="messages_envoyes")
    contenu = models.TextField()  # Contenu du message
    date_envoi = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Message de {self.envoyeur.username} - Conversation {self.conversation.id}"


class Forum(models.Model):
    titre = models.CharField(max_length=255)
    description = models.TextField()
    cours = models.ForeignKey('courses.Cours', on_delete=models.CASCADE, related_name='forums', null=True, blank=True)
    sequence = models.ForeignKey('courses.Sequence', on_delete=models.CASCADE, related_name='forums', null=True, blank=True)
    module = models.ForeignKey('courses.Module', on_delete=models.CASCADE, related_name='forums', null=True, blank=True)
    auteur = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='forums')
    date_creation = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.titre


class Commentaire(models.Model):
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='commentaires')
    auteur = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='commentaires')
    contenu = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, related_name='reponses', null=True, blank=True)

    def __str__(self):
        return f"Commentaire de {self.auteur.username} sur {self.forum.titre}"
