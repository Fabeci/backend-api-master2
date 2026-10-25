from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0017_link_departement_structure"),
    ]

    operations = [
        migrations.CreateModel(
            name="Semestre",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.PositiveSmallIntegerField(choices=[(1, "S1"), (2, "S2"), (3, "S3"), (4, "S4"), (5, "S5"), (6, "S6")])),
                ("libelle", models.CharField(blank=True, max_length=100)),
                ("date_debut", models.DateField(blank=True, null=True)),
                ("date_fin", models.DateField(blank=True, null=True)),
                ("est_actif", models.BooleanField(default=True)),
                ("annee_scolaire", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="semestres", to="academics.anneescolaire")),
                ("classe", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="semestres", to="academics.classe")),
                ("institution", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="semestres", to="academics.institution")),
            ],
            options={"verbose_name": "Semestre", "verbose_name_plural": "Semestres", "ordering": ["numero"],
                     "unique_together": {("classe", "annee_scolaire", "numero")}},
        ),
        migrations.CreateModel(
            name="UE",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=50)),
                ("libelle", models.CharField(max_length=255)),
                ("credits", models.PositiveSmallIntegerField(default=0, verbose_name="Crédits (UE)")),
                ("coefficient", models.FloatField(default=1.0, verbose_name="Coefficient (UE)")),
                ("seuil_validation", models.FloatField(default=10.0, verbose_name="Seuil de validation (/20)")),
                ("est_active", models.BooleanField(default=True)),
                ("institution", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="ues", to="academics.institution")),
                ("semestre", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="ues", to="academics.semestre")),
            ],
            options={"verbose_name": "Unité d'enseignement", "verbose_name_plural": "Unités d'enseignement",
                     "ordering": ["code"], "unique_together": {("semestre", "code")}},
        ),
        migrations.AddField(
            model_name="matiere", name="ue",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="matieres", to="academics.ue"),
        ),
        migrations.AddField(
            model_name="matiere", name="credits",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Crédits (EC)"),
        ),
        migrations.AddField(
            model_name="matiere", name="coefficient",
            field=models.FloatField(default=1.0, verbose_name="Coefficient (EC)"),
        ),
    ]
