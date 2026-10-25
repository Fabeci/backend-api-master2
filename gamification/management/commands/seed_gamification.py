"""
Management command: seed_gamification
Creates the reference Badge and Mission records needed for the gamification MVP.
Safe to run multiple times (uses get_or_create).
"""
from django.core.management.base import BaseCommand


BADGES = [
    {
        'code': 'premier_pas',
        'nom': 'Premiers Pas',
        'description': 'Bienvenue ! Vous avez rejoint la plateforme.',
        'categorie': 'decouverte',
        'rarete': 'commun',
        'icone': 'bi-door-open',
        'couleur': '#6c757d',
        'xp_bonus': 10,
    },
    {
        'code': 'premier_cours',
        'nom': 'Curieux',
        'description': "Vous avez ouvert votre premier contenu pédagogique.",
        'categorie': 'decouverte',
        'rarete': 'commun',
        'icone': 'bi-book',
        'couleur': '#0d6efd',
        'xp_bonus': 10,
    },
    {
        'code': 'premiere_sequence',
        'nom': 'Première Séquence',
        'description': 'Félicitations ! Vous avez terminé votre première séquence.',
        'categorie': 'progression',
        'rarete': 'commun',
        'icone': 'bi-check-circle',
        'couleur': '#198754',
        'xp_bonus': 25,
    },
    {
        'code': 'premier_quiz',
        'nom': 'Candidat',
        'description': 'Vous avez participé à votre premier quiz.',
        'categorie': 'evaluation',
        'rarete': 'commun',
        'icone': 'bi-question-circle',
        'couleur': '#fd7e14',
        'xp_bonus': 15,
    },
    {
        'code': 'quiz_parfait',
        'nom': 'Score Parfait',
        'description': 'Bravo ! 100% à un quiz !',
        'categorie': 'evaluation',
        'rarete': 'rare',
        'icone': 'bi-trophy',
        'couleur': '#ffc107',
        'xp_bonus': 50,
    },
    {
        'code': 'mention_tres_bien',
        'nom': 'Mention Très Bien',
        'description': 'Vous avez obtenu ≥ 90% à une évaluation.',
        'categorie': 'evaluation',
        'rarete': 'rare',
        'icone': 'bi-award',
        'couleur': '#6f42c1',
        'xp_bonus': 75,
    },
    {
        'code': 'lecteur_vorace',
        'nom': 'Lecteur Vorace',
        'description': 'Vous avez complété 10 blocs de contenu.',
        'categorie': 'progression',
        'rarete': 'peu_commun',
        'icone': 'bi-journal-bookmark',
        'couleur': '#20c997',
        'xp_bonus': 50,
    },
    {
        'code': 'streak_7j',
        'nom': 'Semaine de Feu',
        'description': '7 jours consécutifs de connexion.',
        'categorie': 'regularite',
        'rarete': 'peu_commun',
        'icone': 'bi-fire',
        'couleur': '#fd7e14',
        'xp_bonus': 70,
    },
    {
        'code': 'streak_30j',
        'nom': 'Mois Imparable',
        'description': '30 jours consécutifs de connexion.',
        'categorie': 'regularite',
        'rarete': 'rare',
        'icone': 'bi-lightning-charge',
        'couleur': '#dc3545',
        'xp_bonus': 300,
    },
    {
        'code': 'phoenix',
        'nom': 'Phénix',
        'description': 'Vous avez repris après une longue absence.',
        'categorie': 'regularite',
        'rarete': 'peu_commun',
        'icone': 'bi-arrow-repeat',
        'couleur': '#e91e63',
        'xp_bonus': 50,
    },
    {
        'code': 'niveau_5',
        'nom': 'Expert Confirmé',
        'description': "Vous avez atteint le niveau 5 : Stratège.",
        'categorie': 'progression',
        'rarete': 'rare',
        'icone': 'bi-stars',
        'couleur': '#ff9800',
        'xp_bonus': 200,
    },
]

MISSIONS = [
    # Quotidiennes — facile
    {
        'titre': 'Première connexion du jour',
        'description': 'Connectez-vous aujourd\'hui.',
        'type_mission': 'quotidienne',
        'difficulte': 'facile',
        'action': 'connexion',
        'quantite': 1,
        'xp_recompense': 20,
    },
    {
        'titre': 'Ouvrez 2 blocs',
        'description': 'Complétez 2 blocs de contenu aujourd\'hui.',
        'type_mission': 'quotidienne',
        'difficulte': 'facile',
        'action': 'bloc_complete',
        'quantite': 2,
        'xp_recompense': 30,
    },
    {
        'titre': 'Participez à un quiz',
        'description': 'Passez au moins un quiz aujourd\'hui.',
        'type_mission': 'quotidienne',
        'difficulte': 'facile',
        'action': 'quiz_participe',
        'quantite': 1,
        'xp_recompense': 25,
    },
    # Quotidiennes — normale
    {
        'titre': 'Complétez 5 blocs',
        'description': 'Complétez 5 blocs de contenu aujourd\'hui.',
        'type_mission': 'quotidienne',
        'difficulte': 'normale',
        'action': 'bloc_complete',
        'quantite': 5,
        'xp_recompense': 60,
    },
    {
        'titre': 'Terminez une séquence',
        'description': 'Complétez une séquence de formation.',
        'type_mission': 'quotidienne',
        'difficulte': 'normale',
        'action': 'sequence_done',
        'quantite': 1,
        'xp_recompense': 80,
    },
    {
        'titre': 'Réussissez un quiz',
        'description': 'Obtenez au moins 60% à un quiz.',
        'type_mission': 'quotidienne',
        'difficulte': 'normale',
        'action': 'quiz_reussi',
        'quantite': 1,
        'xp_recompense': 50,
    },
    # Quotidiennes — difficile
    {
        'titre': 'Sprint de contenu',
        'description': 'Complétez 10 blocs aujourd\'hui.',
        'type_mission': 'quotidienne',
        'difficulte': 'difficile',
        'action': 'bloc_complete',
        'quantite': 10,
        'xp_recompense': 120,
    },
    {
        'titre': 'Double séquence',
        'description': 'Terminez 2 séquences aujourd\'hui.',
        'type_mission': 'quotidienne',
        'difficulte': 'difficile',
        'action': 'sequence_done',
        'quantite': 2,
        'xp_recompense': 150,
    },
    {
        'titre': 'Excellez au quiz',
        'description': 'Obtenez un score parfait (100%) à un quiz.',
        'type_mission': 'quotidienne',
        'difficulte': 'defi',
        'action': 'quiz_parfait',
        'quantite': 1,
        'xp_recompense': 200,
    },
    # Hebdomadaires
    {
        'titre': 'Régularité de la semaine',
        'description': 'Connectez-vous 5 jours cette semaine.',
        'type_mission': 'hebdomadaire',
        'difficulte': 'normale',
        'action': 'connexion',
        'quantite': 5,
        'xp_recompense': 200,
    },
    {
        'titre': 'Formateur assidu',
        'description': 'Complétez 20 blocs cette semaine.',
        'type_mission': 'hebdomadaire',
        'difficulte': 'difficile',
        'action': 'bloc_complete',
        'quantite': 20,
        'xp_recompense': 300,
    },
]


class Command(BaseCommand):
    help = 'Seed gamification badges and missions with reference data'

    def handle(self, *args, **options):
        from gamification.models import Badge, Mission

        created_b = updated_b = 0
        for data in BADGES:
            obj, created = Badge.objects.update_or_create(
                code=data['code'],
                defaults={k: v for k, v in data.items() if k != 'code'},
            )
            if created:
                created_b += 1
            else:
                updated_b += 1

        self.stdout.write(f'Badges  : {created_b} créés, {updated_b} mis à jour')

        created_m = updated_m = 0
        for data in MISSIONS:
            obj, created = Mission.objects.update_or_create(
                titre=data['titre'],
                defaults={k: v for k, v in data.items() if k != 'titre'},
            )
            if created:
                created_m += 1
            else:
                updated_m += 1

        self.stdout.write(f'Missions: {created_m} créées, {updated_m} mises à jour')
        self.stdout.write(self.style.SUCCESS('Gamification seed terminé.'))
