from django.core.management.base import BaseCommand
from users.models import UserRole

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        roles = ["Super Admin", "Admin", "Formateur", "Apprenant", "Parent", "Responsable Académique"]
        for role in roles:
            UserRole.objects.get_or_create(name=role)
        self.stdout.write(self.style.SUCCESS("Les rôles ont été créés avec succès !"))
