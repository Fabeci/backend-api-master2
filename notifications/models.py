# notifications/models.py
from django.db import models
from django.utils import timezone


class Notification(models.Model):

    TYPE_CHOICES = [
        ('INFO',    'Information'),
        ('SUCCESS', 'Succès'),
        ('WARNING', 'Avertissement'),
        ('ERROR',   'Erreur'),
    ]

    user = models.ForeignKey(
        'users.User',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Destinataire"
    )
    message = models.TextField(verbose_name="Message")
    type    = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default='INFO',
        verbose_name="Type"
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        verbose_name="Créée le"
    )
    is_read = models.BooleanField(default=False, verbose_name="Lue")

    # ── Optionnel : lier à un objet métier (institution, cours, etc.) ────────
    # Permet de savoir d'où vient la notification sans chercher dans le message
    institution = models.ForeignKey(
        'academics.Institution',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='notifications',
        verbose_name="Institution concernée"
    )

    class Meta:
        verbose_name          = "Notification"
        verbose_name_plural   = "Notifications"
        ordering              = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['user', 'created_at']),
        ]

    def mark_as_read(self):
        """Marque la notification comme lue."""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=['is_read'])

    def __str__(self):
        preview = self.message[:40] + ('…' if len(self.message) > 40 else '')
        return f"[{self.get_type_display()}] {self.user.email} — {preview}"


# ── Helper global pour créer des notifications facilement ────────────────────

def notify(user, message: str, type: str = 'INFO', institution=None) -> Notification:
    """
    Crée et retourne une notification pour un utilisateur.

    Usage :
        from notifications.models import notify
        notify(request.user, "Votre cours a été publié.", type='SUCCESS')
        notify(user, "Erreur lors de l'import.", type='ERROR', institution=inst)
    """
    return Notification.objects.create(
        user=user,
        message=message,
        type=type,
        institution=institution,
    )


def notify_many(users, message: str, type: str = 'INFO', institution=None):
    """
    Crée des notifications en bulk pour une liste d'utilisateurs.

    Usage :
        from notifications.models import notify_many
        notify_many(groupe.apprenants.all(), "Nouveau cours disponible.", type='INFO')
    """
    Notification.objects.bulk_create([
        Notification(user=u, message=message, type=type, institution=institution)
        for u in users
    ])