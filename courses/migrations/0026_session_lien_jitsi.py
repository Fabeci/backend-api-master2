from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0025_session_rappel_envoye"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="lien_jitsi",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Salle Jitsi embarquable dans l'app (réunion dans SOMAPRO)",
            ),
        ),
    ]
