from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0022_blocprogress_est_valide_blocprogress_etat_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='cours',
            name='image',
            field=models.URLField(
                blank=True,
                help_text="URL de l'image de couverture (téléversée depuis les ressources)",
                max_length=500,
                null=True,
                verbose_name="Image du cours",
            ),
        ),
    ]
