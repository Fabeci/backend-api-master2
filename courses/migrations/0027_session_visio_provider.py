from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0026_session_lien_jitsi"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="visio_provider",
            field=models.CharField(
                choices=[
                    ("aucune", "Aucune"),
                    ("google_meet", "Google Meet"),
                    ("jitsi", "Jitsi (dans SOMAPRO)"),
                    ("autre", "Autre (lien manuel)"),
                ],
                default="aucune",
                help_text="Plateforme de visioconférence de la séance",
                max_length=20,
            ),
        ),
    ]
