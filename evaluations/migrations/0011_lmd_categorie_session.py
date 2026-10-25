from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluations", "0010_alter_passageevaluation_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluation", name="categorie",
            field=models.CharField(choices=[("cc", "Contrôle continu"), ("tp", "Travaux pratiques"),
                                            ("examen", "Examen"), ("autre", "Autre")],
                                   default="examen", max_length=20),
        ),
        migrations.AddField(
            model_name="evaluation", name="coefficient",
            field=models.FloatField(default=1.0, verbose_name="Coefficient"),
        ),
        migrations.AddField(
            model_name="passageevaluation", name="session",
            field=models.CharField(choices=[("normale", "Session normale"), ("rattrapage", "Session de rattrapage")],
                                   default="normale", max_length=20),
        ),
    ]
