# Generated by Django 5.1.2 on 2024-11-17 17:00

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('courses', '0002_initial'),
        ('evaluations', '0001_initial'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='apprenantevaluation',
            name='apprenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='apprenant_evaluations', to='users.apprenant'),
        ),
        migrations.AddField(
            model_name='evaluation',
            name='cours',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluations', to='courses.cours'),
        ),
        migrations.AddField(
            model_name='apprenantevaluation',
            name='evaluation',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='apprenant_evaluations', to='evaluations.evaluation'),
        ),
        migrations.AddField(
            model_name='question',
            name='evaluation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='questions_evaluation', to='evaluations.evaluation'),
        ),
        migrations.AddField(
            model_name='quiz',
            name='sequence',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quizz', to='courses.sequence'),
        ),
        migrations.AddField(
            model_name='question',
            name='quiz',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='questions_quizz', to='evaluations.quiz'),
        ),
        migrations.AddField(
            model_name='reponse',
            name='question',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reponses', to='evaluations.question'),
        ),
        migrations.AddField(
            model_name='solution',
            name='question',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='questions', to='evaluations.question'),
        ),
        migrations.AlterUniqueTogether(
            name='apprenantevaluation',
            unique_together={('apprenant', 'evaluation')},
        ),
    ]
