# Generated for RecommandationPedagogique (recommandations personnalisées)

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0006_mastery_tendance'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecommandationPedagogique',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_recommandation', models.CharField(choices=[('bloc_revoir', 'Bloc à revoir'), ('changement_approche', "Changer d'approche"), ('contenu_alternatif', 'Contenu alternatif disponible'), ('quiz_supplementaire', 'Quiz supplémentaire'), ('module_revision', 'Module de révision'), ('pause', 'Prendre une pause')], max_length=32)),
                ('message', models.TextField()),
                ('priorite', models.PositiveSmallIntegerField(default=3)),
                ('est_vue', models.BooleanField(default=False)),
                ('date_vue', models.DateTimeField(blank=True, null=True)),
                ('est_suivie', models.BooleanField(default=False)),
                ('date_suivie', models.DateTimeField(blank=True, null=True)),
                ('date_expiration', models.DateTimeField(blank=True, null=True)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('apprenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recommandations', to='users.apprenant')),
                ('bloc_cible', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recommandations', to='courses.bloccontenu')),
                ('contenu_genere', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recommandations', to='analytics.contenugenere')),
                ('cours', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='recommandations', to='courses.cours')),
                ('sequence_cible', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='recommandations', to='courses.sequence')),
            ],
            options={
                'verbose_name': 'Recommandation pédagogique',
                'verbose_name_plural': 'Recommandations pédagogiques',
                'ordering': ['-priorite', '-date_creation'],
            },
        ),
        migrations.AddIndex(
            model_name='recommandationpedagogique',
            index=models.Index(fields=['apprenant', 'est_suivie'], name='reco_appr_suivie_idx'),
        ),
        migrations.AddIndex(
            model_name='recommandationpedagogique',
            index=models.Index(fields=['apprenant', 'est_vue'], name='reco_appr_vue_idx'),
        ),
    ]
