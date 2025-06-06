# Generated by Django 5.1.2 on 2024-11-17 17:00

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Pays',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('code', models.CharField(max_length=3, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Ville',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('pays', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='villes', to='locations.pays')),
            ],
        ),
        migrations.CreateModel(
            name='Quartier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('ville', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='quartiers', to='locations.ville')),
            ],
        ),
    ]
