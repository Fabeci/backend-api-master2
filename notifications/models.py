from django.db import models
from django.utils import timezone


# Create your models here.


class Notification(models.Model):
    TYPE_CHOICES = [
        ('INFO', 'Information'),
        ('SUCCESS', 'Succès'),
        ('WARNING', 'Avertissement'),
        ('ERROR', 'Erreur'),
    ]

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    message = models.TextField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='INFO')
    created_at = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)

    def mark_as_read(self):
        """Marque la notification comme lue"""
        self.is_read = True
        self.save()

    def __str__(self):
        return f"{self.get_type_display()} - {self.message[:20]}..."