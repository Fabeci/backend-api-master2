from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0014_domaineetude_departement"),
        ("users", "0029_rolepermissionoverride"),
    ]

    operations = [
        migrations.CreateModel(
            name="AffectationEnseignement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("est_actif", models.BooleanField(default=True)),
                ("date_creation", models.DateTimeField(auto_now_add=True)),
                ("annee_scolaire", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="affectations_enseignement", to="academics.anneescolaire")),
                ("formateur", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="affectations_enseignement", to="users.formateur")),
                ("groupe", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="affectations_enseignement", to="academics.groupe")),
                ("institution", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                    related_name="affectations_enseignement", to="academics.institution")),
                ("matiere", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name="affectations_enseignement", to="academics.matiere")),
            ],
            options={
                "verbose_name": "Affectation d'enseignement",
                "verbose_name_plural": "Affectations d'enseignement",
                "ordering": ["-date_creation"],
            },
        ),
        migrations.AddConstraint(
            model_name="affectationenseignement",
            constraint=models.UniqueConstraint(
                fields=("formateur", "groupe", "matiere", "annee_scolaire"),
                name="unique_affectation_formateur_groupe_matiere_annee",
            ),
        ),
    ]
