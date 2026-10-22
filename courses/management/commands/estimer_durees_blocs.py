# courses/management/commands/estimer_durees_blocs.py
# Recalcule la durée estimée des blocs de contenu.
from django.core.management.base import BaseCommand

from courses.models import BlocContenu
from courses.estimation import estimer_duree_minutes


class Command(BaseCommand):
    help = (
        "Recalcule la durée estimée des blocs de contenu. "
        "Par défaut : uniquement les blocs à 0. Utiliser --all pour tout recalculer."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--all', action='store_true',
            help="Recalculer TOUS les blocs (écrase les durées saisies).",
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Afficher ce qui serait fait sans enregistrer.",
        )

    def handle(self, *args, **options):
        qs = BlocContenu.objects.all()
        if not options['all']:
            qs = qs.filter(duree_estimee_minutes=0)

        ids = list(qs.values_list('id', flat=True))
        total = len(ids)
        updated = 0

        for bloc in BlocContenu.objects.filter(id__in=ids).select_related('sequence'):
            nouvelle = estimer_duree_minutes(bloc)
            if bloc.duree_estimee_minutes == nouvelle:
                continue
            if not options['dry_run']:
                bloc.duree_estimee_minutes = nouvelle
                bloc.save(update_fields=['duree_estimee_minutes'])
            updated += 1

        prefix = 'DRY-RUN ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}{updated}/{total} bloc(s) mis à jour."
        ))
