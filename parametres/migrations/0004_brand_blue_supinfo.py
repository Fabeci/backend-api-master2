from django.db import migrations, models


def brand_blue_forward(apps, schema_editor):
    """Remplace l'ancienne couleur par défaut (#6366f1) par le bleu Sup'Info Dakar."""
    ParametresInstitution = apps.get_model('parametres', 'ParametresInstitution')
    ParametresInstitution.objects.filter(couleur_principale='#6366f1').update(
        couleur_principale='#0E71B4'
    )


def brand_blue_backward(apps, schema_editor):
    ParametresInstitution = apps.get_model('parametres', 'ParametresInstitution')
    ParametresInstitution.objects.filter(couleur_principale='#0E71B4').update(
        couleur_principale='#6366f1'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('parametres', '0003_preferencesutilisateur_theme'),
    ]

    operations = [
        migrations.AlterField(
            model_name='parametresinstitution',
            name='couleur_principale',
            field=models.CharField(default='#0E71B4', max_length=20),
        ),
        migrations.RunPython(brand_blue_forward, brand_blue_backward),
    ]
