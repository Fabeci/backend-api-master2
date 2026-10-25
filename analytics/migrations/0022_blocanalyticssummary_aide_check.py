from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0021_alter_learningsignal_signal_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='blocanalyticssummary',
            name='aide_check_reponse',
            field=models.BooleanField(
                blank=True, null=True,
                help_text="Auto-évaluation : True=bloqué (aide), False=ça va, None=non posée",
            ),
        ),
        migrations.AddField(
            model_name='blocanalyticssummary',
            name='aide_check_le',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
