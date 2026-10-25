from django.db import migrations


def backfill(apps, schema_editor):
    """✅ Les cours existants impliquent une affectation : on la matérialise
    pour que la charge d'enseignement soit visible dès l'ouverture de l'écran."""
    Cours = apps.get_model("courses", "Cours")
    Affectation = apps.get_model("academics", "AffectationEnseignement")

    for c in Cours.objects.exclude(enseignant__isnull=True).iterator():
        if not (c.groupe_id and c.matiere_id and c.annee_scolaire_id):
            continue
        Affectation.objects.get_or_create(
            formateur_id=c.enseignant_id,
            groupe_id=c.groupe_id,
            matiere_id=c.matiere_id,
            annee_scolaire_id=c.annee_scolaire_id,
            defaults={"institution_id": c.institution_id, "est_actif": True},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0015_affectationenseignement"),
        ("courses", "0030_publication_progressive"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
