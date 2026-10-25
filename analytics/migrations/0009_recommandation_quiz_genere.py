# Ajout du lien RecommandationPedagogique → QuizGenereClaude (quiz IA de remédiation)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0008_recommandation_ignoree'),
    ]

    operations = [
        migrations.AddField(
            model_name='recommandationpedagogique',
            name='quiz_genere',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='recommandations',
                to='analytics.quizgenereclaude',
            ),
        ),
    ]
