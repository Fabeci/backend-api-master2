# academics/management/commands/recalculer_progressions.py
from django.core.management.base import BaseCommand

from courses.models import InscriptionCours, Sequence
from courses.services.progression import recompute_sequence, recompute_module, recompute_cours


class Command(BaseCommand):
    help = ("Recalcule la progression CONTENU (blocs → séquences → modules → cours) "
            "pour les inscriptions. Idempotent.")

    def add_arguments(self, parser):
        parser.add_argument("--apprenant", type=int, help="Limiter à un apprenant")
        parser.add_argument("--cours", type=int, help="Limiter à un cours")

    def handle(self, *args, **options):
        qs = InscriptionCours.objects.select_related("apprenant", "cours")
        if options.get("apprenant"):
            qs = qs.filter(apprenant_id=options["apprenant"])
        if options.get("cours"):
            qs = qs.filter(cours_id=options["cours"])

        total = 0
        for ins in qs.iterator():
            for seq in Sequence.objects.filter(module__cours=ins.cours):
                recompute_sequence(ins.apprenant, seq)
            for module in ins.cours.modules.all():
                recompute_module(ins.apprenant, module)
            recompute_cours(ins.apprenant, ins.cours)
            total += 1

        self.stdout.write(self.style.SUCCESS(
            f"{total} inscription(s) recalculée(s)."
        ))
