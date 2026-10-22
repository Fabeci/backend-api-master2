from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0024_session_meet"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="rappel_envoye",
            field=models.BooleanField(
                default=False,
                help_text="Un rappel « séance à venir » a déjà été envoyé aux participants",
            ),
        ),
    ]
