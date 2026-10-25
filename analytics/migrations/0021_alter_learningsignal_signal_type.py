# Phase 8+ : nouveaux types de signaux remontés depuis les lacunes / la maîtrise
# (lacune_critique, lacune_moderee, maitrise_fragile, remediation_insuffisante)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0020_interventionoutcome'),
    ]

    operations = [
        migrations.AlterField(
            model_name='learningsignal',
            name='signal_type',
            field=models.CharField(choices=[
                ('inactivite_prolongee', 'Inactivité prolongée'),
                ('baisse_engagement', 'Baisse d’engagement'),
                ('progression_stagnante', 'Progression stagnante'),
                ('progression_trop_lente', 'Progression trop lente'),
                ('erreurs_repetitives', 'Erreurs répétitives'),
                ('competence_fragile', 'Compétence fragile'),
                ('regression', 'Régression'),
                ('echec_repete', 'Échec répété'),
                ('difficulte_persistante', 'Difficulté persistante'),
                ('sequence_abandonnee', 'Séquence abandonnée'),
                ('faible_performance', 'Faible performance'),
                ('aucune_activite', 'Aucune activité'),
                ('lacune_critique', 'Lacune critique'),
                ('lacune_moderee', 'Lacune modérée'),
                ('maitrise_fragile', 'Maîtrise fragile'),
                ('remediation_insuffisante', 'Remédiation insuffisante'),
            ], max_length=32),
        ),
    ]
