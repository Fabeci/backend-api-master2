"""Réaligne les accès aux cours sur les groupes (le groupe est la référence).

Usage :
  python manage.py resync_inscriptions            # aperçu (rien n'est modifié)
  python manage.py resync_inscriptions --apply    # applique le réalignement
"""
from collections import defaultdict
from django.core.management.base import BaseCommand

from courses.models import Cours, InscriptionCours
from users.models import Apprenant
from courses.signals import sync_cours, sync_apprenant

ACTIFS = ("inscrit", "en_cours", "en cours", "encours")


class Command(BaseCommand):
    help = "Réaligne les inscriptions-cours sur les groupes (aperçu par défaut)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Applique réellement les changements.")

    def handle(self, *args, **options):
        apply = options["apply"]
        actifs = InscriptionCours.objects.filter(statut__in=ACTIFS).select_related("apprenant", "cours")
        total = actifs.count()
        keep, lose = 0, 0
        by_app = defaultdict(int)
        for r in actifs:
            ag, cg = r.apprenant.groupe_id, r.cours.groupe_id
            if ag is not None and ag == cg:
                keep += 1
                by_app[r.apprenant_id] += 1
            else:
                lose += 1

        self.stdout.write(f"Accès actifs : {total}")
        self.stdout.write(f"  conservés (élève.groupe == cours.groupe) : {keep}")
        self.stdout.write(f"  à retirer : {lose}")
        self.stdout.write(f"  élèves gardant ≥1 cours : {len(by_app)}/{Apprenant.objects.count()}")

        if not apply:
            self.stdout.write(self.style.WARNING("Aperçu uniquement — relancer avec --apply pour appliquer."))
            return

        for c in Cours.objects.exclude(groupe__isnull=True):
            sync_cours(c)
        for a in Apprenant.objects.exclude(groupe__isnull=True):
            sync_apprenant(a)
        self.stdout.write(self.style.SUCCESS("Réalignement appliqué."))
