from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0023_cours_image"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="lien_visio",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Lien de visioconférence à rejoindre (Google Meet ou autre)",
            ),
        ),
        migrations.AddField(
            model_name="session",
            name="meet_space_name",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                help_text="Ressource Google Meet (ex. 'spaces/abc123') — vide si non généré",
            ),
        ),
        migrations.AddField(
            model_name="session",
            name="meet_derniere_sync",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Dernière synchronisation automatique des présences depuis Google Meet",
            ),
        ),
    ]
