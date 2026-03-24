# courses/management/commands/sync_cours_statut.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from courses.models import Cours

class Command(BaseCommand):
    help = "Synchronise le statut de tous les cours selon leurs dates"

    def handle(self, *args, **options):
        cours_list = Cours.objects.exclude(
            date_debut=None, date_fin=None
        ).select_related()
        
        updated = 0
        today = timezone.localdate()

        for cours in cours_list:
            nouveau_statut = cours.statut_calcule
            if cours.statut != nouveau_statut:
                cours.statut = nouveau_statut
                cours.save(update_fields=["statut"])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{updated} cours mis à jour sur {cours_list.count()} traités."
            )
        )