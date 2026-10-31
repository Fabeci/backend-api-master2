import json
import pathlib

from django.core.management.base import BaseCommand

from locations.models import Pays


class Command(BaseCommand):
    help = "Importe tous les pays (noms français, ISO2/ISO3) dans la table Pays."

    def handle(self, *args, **options):
        data_file = pathlib.Path(__file__).resolve().parents[2] / "data" / "countries_fr.json"
        rows = json.loads(data_file.read_text(encoding="utf-8"))
        created = updated = 0
        for row in rows:
            code = (row.get("code") or row.get("iso2") or "").upper()[:3]
            if not code:
                continue
            iso2 = (row.get("iso2") or "").upper()[:2]
            existing = None
            if iso2:
                existing = Pays.objects.filter(iso2__iexact=iso2).first()
            if existing is None:
                existing = Pays.objects.filter(code=code).first()
            if existing is None:
                existing = Pays.objects.filter(nom__iexact=row.get("nom") or "").first()
            if existing is None:
                Pays.objects.create(code=code, nom=row.get("nom") or code, iso2=iso2)
                created += 1
            else:
                existing.nom = row.get("nom") or existing.nom
                existing.iso2 = iso2 or existing.iso2
                existing.save(update_fields=["nom", "iso2"])
                updated += 1
            created += int(is_new)
            updated += int(not is_new)
        self.stdout.write(self.style.SUCCESS(
            f"Pays importés : {created} créés, {updated} mis à jour (total {Pays.objects.count()})."
        ))
