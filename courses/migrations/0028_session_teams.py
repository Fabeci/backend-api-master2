from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0027_session_visio_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="teams_join_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Lien de réunion Microsoft Teams à rejoindre",
            ),
        ),
        migrations.AddField(
            model_name="session",
            name="teams_meeting_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                help_text="Identifiant de la réunion en ligne Teams (rapport de présence)",
            ),
        ),
        migrations.AlterField(
            model_name="session",
            name="visio_provider",
            field=models.CharField(
                choices=[
                    ("aucune", "Aucune"),
                    ("google_meet", "Google Meet"),
                    ("teams", "Microsoft Teams"),
                    ("jitsi", "Jitsi (dans SOMAPRO)"),
                    ("autre", "Autre (lien manuel)"),
                ],
                default="aucune",
                help_text="Plateforme de visioconférence de la séance",
                max_length=20,
            ),
        ),
    ]
