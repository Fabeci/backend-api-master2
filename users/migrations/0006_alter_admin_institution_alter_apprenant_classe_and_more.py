# Generated by Django 5.1.2 on 2024-11-27 01:32

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0003_anneescolaire_description_classe_date_creation_and_more'),
        ('users', '0005_remove_user_is_admin_remove_user_is_apprenant_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='admin',
            name='institution',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='administrateurs', to='academics.institution'),
        ),
        migrations.AlterField(
            model_name='apprenant',
            name='classe',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='classe_apprenant', to='academics.classe'),
        ),
        migrations.AlterField(
            model_name='apprenant',
            name='groupe',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='groupe_apprenant', to='academics.groupe'),
        ),
        migrations.AlterField(
            model_name='apprenant',
            name='tuteur',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='users.parent'),
        ),
        migrations.AlterField(
            model_name='formateur',
            name='groupes',
            field=models.ManyToManyField(null=True, related_name='formateurs', to='academics.groupe'),
        ),
        migrations.AlterField(
            model_name='formateur',
            name='institutions',
            field=models.ManyToManyField(null=True, related_name='formateurs_users', to='academics.institution'),
        ),
        migrations.AlterField(
            model_name='formateur',
            name='specialites',
            field=models.ManyToManyField(null=True, related_name='formateurs', to='academics.specialite'),
        ),
        migrations.AlterField(
            model_name='responsableacademique',
            name='institution',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='responsables_academiques', to='academics.institution'),
        ),
    ]
