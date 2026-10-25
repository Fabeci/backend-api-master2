from django.db import migrations


def link_structure(apps, schema_editor):
    """✅ Répare le chaînage académique nécessaire au périmètre « département » :

    - domaine sans département → rattaché à l'unique département de l'établissement ;
    - classe sans filière → rattachée aux filières de ce département.

    Ne s'applique QUE si l'établissement a exactement un département (aucune
    invention de données dans les établissements multi-départements).
    """
    Departement = apps.get_model("academics", "Departement")
    DomaineEtude = apps.get_model("academics", "DomaineEtude")
    Filiere = apps.get_model("academics", "Filiere")
    Classe = apps.get_model("academics", "Classe")

    inst_ids = (Departement.objects.values_list("institution_id", flat=True)
                .distinct())
    for inst_id in inst_ids:
        depts = Departement.objects.filter(institution_id=inst_id)
        if depts.count() != 1:
            continue
        dept = depts.first()

        DomaineEtude.objects.filter(
            institution_id=inst_id, departement__isnull=True
        ).update(departement=dept)

        filiere_ids = list(
            Filiere.objects.filter(domaine_etude__departement_id=dept.id)
            .values_list("id", flat=True)
        )
        if not filiere_ids:
            continue
        for classe in Classe.objects.filter(institution_id=inst_id, filieres__isnull=True):
            classe.filieres.set(filiere_ids)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0016_backfill_affectations"),
    ]

    operations = [
        migrations.RunPython(link_structure, migrations.RunPython.noop),
    ]
