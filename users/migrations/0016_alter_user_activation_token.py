# Generated by Django 5.1.6 on 2025-03-24 23:08

import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0015_user_activation_token'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='activation_token',
            field=models.UUIDField(blank=True, default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
