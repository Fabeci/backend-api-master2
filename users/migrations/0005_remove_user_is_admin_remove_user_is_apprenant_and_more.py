# Generated by Django 5.1.2 on 2024-11-27 01:11

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_alter_user_pays_residence'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='is_admin',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_apprenant',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_formateur',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_parent',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_responsable_academique',
        ),
        migrations.RemoveField(
            model_name='user',
            name='is_super_admin',
        ),
    ]
