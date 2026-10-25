# Ajout du rejet explicite (est_ignoree) des recommandations pédagogiques

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0007_recommandationpedagogique'),
    ]

    operations = [
        migrations.AddField(
            model_name='recommandationpedagogique',
            name='est_ignoree',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='recommandationpedagogique',
            name='date_ignoree',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
