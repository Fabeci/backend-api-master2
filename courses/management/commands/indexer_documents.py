# courses/management/commands/indexer_documents.py
"""Indexe les documents du cours (PDF/DOCX/TXT/MD) pour le tuteur IA."""
from django.core.management.base import BaseCommand

from courses.models import Cours
from courses.services import rag


class Command(BaseCommand):
    help = "Extrait et indexe les documents des cours (RAG du tuteur IA)."

    def add_arguments(self, parser):
        parser.add_argument("--cours", type=int, help="ID d'un cours précis")
        parser.add_argument("--all", action="store_true", help="Tous les cours")

    def handle(self, *args, **options):
        cours_qs = Cours.objects.all().order_by("id")
        if options.get("cours"):
            cours_qs = cours_qs.filter(pk=options["cours"])

        total = 0
        for cours in cours_qs:
            nombre = rag.indexer_cours(cours)
            total += nombre
            if nombre:
                self.stdout.write(f"  {cours.titre} : {nombre} extrait(s)")

        self.stdout.write(self.style.SUCCESS(f"Terminé — {total} extrait(s) indexé(s)."))
