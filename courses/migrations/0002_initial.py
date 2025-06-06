# Generated by Django 5.1.2 on 2024-11-17 17:00

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('academics', '0002_initial'),
        ('courses', '0001_initial'),
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cours',
            name='enseignant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='users.formateur'),
        ),
        migrations.AddField(
            model_name='cours',
            name='groupe',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.groupe'),
        ),
        migrations.AddField(
            model_name='cours',
            name='matiere',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='academics.matiere'),
        ),
        migrations.AddField(
            model_name='inscriptioncours',
            name='apprenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscriptions', to='users.apprenant'),
        ),
        migrations.AddField(
            model_name='inscriptioncours',
            name='cours',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='inscriptions', to='courses.cours'),
        ),
        migrations.AddField(
            model_name='module',
            name='cours',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='modules', to='courses.cours'),
        ),
        migrations.AddField(
            model_name='participation',
            name='apprenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participations', to='users.apprenant'),
        ),
        migrations.AddField(
            model_name='sequence',
            name='module',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sequences', to='courses.module'),
        ),
        migrations.AddField(
            model_name='session',
            name='cours',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='courses.cours'),
        ),
        migrations.AddField(
            model_name='session',
            name='formateur',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='users.formateur'),
        ),
        migrations.AddField(
            model_name='participation',
            name='session',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='participations', to='courses.session'),
        ),
        migrations.AddField(
            model_name='suivi',
            name='apprenant',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suivis', to='users.apprenant'),
        ),
        migrations.AddField(
            model_name='suivi',
            name='cours',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='suivis', to='courses.cours'),
        ),
        migrations.AlterUniqueTogether(
            name='participation',
            unique_together={('session', 'apprenant')},
        ),
    ]
