"""
Seeder SOMAPRO — génère une base de données réaliste simulant plusieurs années d'activité.

Usage:
    python manage.py seed_data
    python manage.py seed_data --seed-size=large
    python manage.py seed_data --seed-size=xlarge --flush
"""
import random
from datetime import date, timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# ─────────────────────────────────────────────────────────────────────────────
# DONNÉES AFRICAINES
# ─────────────────────────────────────────────────────────────────────────────

PRENOMS_H = [
    'Oumar', 'Mamadou', 'Ibrahima', 'Cheikh', 'Abdoulaye', 'Moussa', 'Modou',
    'Assane', 'Pape', 'Lamine', 'Alioune', 'Seydou', 'Pathé', 'Thierno',
    'Boubacar', 'Souleymane', 'Malick', 'Babacar', 'Samba', 'Mouhamed',
    'Daouda', 'Khadim', 'Demba', 'Fallou', 'Idrissa', 'Birame', 'Alassane',
    'Youssou', 'Ousseynou', 'Landing', 'Abdou', 'Bocar', 'Djiby', 'Ousmane',
    'Ngor', 'Makhtar', 'Tidiane', 'Amadou', 'Sekou', 'Dieudonné', 'Hervé',
    'Patrick', 'Emmanuel', 'François', 'Éric', 'Christophe', 'Olivier',
    'Antoine', 'Sylvain', 'Koffi', 'Kwame', 'Kwesi', 'Kofi', 'Yao',
    'Brice', 'Serge', 'Didier', 'Rodrigue', 'Bertrand', 'Cédric',
]

PRENOMS_F = [
    'Fatou', 'Aissatou', 'Mariama', 'Rokhaya', 'Coumba', 'Aminata', 'Khady',
    'Sokhna', 'Maguette', 'Seynabou', 'Ramatoulaye', 'Adja', 'Fatoumata',
    'Astou', 'Dieynaba', 'Bineta', 'Safietou', 'Awa', 'Binta', 'Kadiatou',
    'Dienaba', 'Maïmouna', 'Nabou', 'Ngoné', 'Oumou', 'Penda', 'Yacine',
    'Ndéye', 'Diarra', 'Hawa', 'Marième', 'Aicha', 'Mame', 'Bintou',
    'Josephine', 'Marie', 'Clarisse', 'Suzanne', 'Céline', 'Angèle',
    'Véronique', 'Monique', 'Rose', 'Pauline', 'Delphine', 'Adjoua',
    'Akissi', 'Amoin', 'Aya', 'Amenan', 'Béatrice', 'Christine',
]

NOMS = [
    'Diallo', 'Sy', 'Kouyaté', 'Camara', 'Traoré', 'Koné', 'Coulibaly',
    'Touré', 'Ndiaye', 'Diop', 'Fall', 'Mbaye', 'Sow', 'Badji', 'Kane',
    'Thiam', 'Guèye', 'Sarr', 'Ba', 'Cissé', 'Dembélé', 'Sanogo', 'Bah',
    'Baldé', 'Barry', 'Dramé', 'Fofana', 'Haidara', 'Keita', 'Konaté',
    'Maïga', 'Sacko', 'Sissoko', 'Soumah', 'Soumaré', 'Tall', 'Oulare',
    'Doucouré', 'Diabaté', 'Doumbia', 'Kourouma', 'Diakhaby', 'Bangoura',
    'Bamba', 'Konté', 'Djiba', 'Bayo', 'Dakouo', 'Ouédraogo', 'Compaoré',
    'Kaboré', 'Sawadogo', 'Yago', 'Tapsoba', 'Nikiema', 'Napon', 'Zongo',
    'Belem', 'Soulama', 'Birba', 'Boni', 'Coulibaly', 'Yoboué', 'Fofana',
    'Kouassi', 'Konan', 'Koffi', 'Kra', 'Gbagbo', 'Assoumou', 'Aké',
]

PAYS_DATA = [
    {'nom': 'Sénégal',       'code': 'SEN', 'villes': ['Dakar', 'Thiès', 'Saint-Louis', 'Ziguinchor', 'Kaolack']},
    {"nom": "Côte d'Ivoire", 'code': 'CIV', 'villes': ['Abidjan', 'Bouaké', 'Yamoussoukro', 'San-Pédro', 'Daloa']},
    {'nom': 'Cameroun',      'code': 'CMR', 'villes': ['Douala', 'Yaoundé', 'Bafoussam', 'Garoua', 'Maroua']},
    {'nom': 'Mali',          'code': 'MLI', 'villes': ['Bamako', 'Sikasso', 'Mopti', 'Gao', 'Tombouctou']},
    {'nom': 'Burkina Faso',  'code': 'BFA', 'villes': ['Ouagadougou', 'Bobo-Dioulasso', 'Koudougou', 'Banfora', 'Ouahigouya']},
    {'nom': 'Guinée',        'code': 'GIN', 'villes': ['Conakry', 'Kankan', 'Labé', 'Nzérékoré', 'Kindia']},
    {'nom': 'Togo',          'code': 'TGO', 'villes': ['Lomé', 'Sokodé', 'Kara', 'Atakpamé', 'Kpalimé']},
    {'nom': 'Bénin',         'code': 'BEN', 'villes': ['Cotonou', 'Porto-Novo', 'Parakou', 'Abomey', 'Natitingou']},
]

INSTITUTIONS_DATA = [
    {
        'nom': "École Supérieure d'Informatique de Dakar",
        'pays': 'SEN', 'ville_idx': 0, 'type': 'École supérieure',
        'adresse': '45 Avenue Cheikh Anta Diop, Dakar',
        'email': 'contact@esid.sn', 'telephone_1': '+221 33 864 52 00',
        'description': "Formation d'excellence en informatique et technologies numériques.",
        'accreditations': 'CAMES, ISO 9001:2015',
    },
    {
        'nom': "Institut Polytechnique d'Abidjan",
        'pays': 'CIV', 'ville_idx': 0, 'type': 'Institut polytechnique',
        'adresse': '18 Boulevard de la Paix, Plateau, Abidjan',
        'email': 'info@ipa.ci', 'telephone_1': '+225 27 22 41 55 00',
        'description': "Établissement de référence pour les sciences, technologies et ingénierie.",
        'accreditations': "Ministère de l'ESRS, CAMES",
    },
    {
        'nom': "Université Numérique de Douala",
        'pays': 'CMR', 'ville_idx': 0, 'type': 'Université',
        'adresse': '72 Rue Joffre, Bonanjo, Douala',
        'email': 'contact@und.cm', 'telephone_1': '+237 233 42 65 00',
        'description': "Pionnière de l'enseignement numérique en Afrique centrale.",
        'accreditations': 'MINESUP Cameroun',
    },
    {
        'nom': "Grande École de Management de Bamako",
        'pays': 'MLI', 'ville_idx': 0, 'type': 'Grande école',
        'adresse': '23 Rue Baba Diarra, Hamdallaye, Bamako',
        'email': 'admin@gemb.ml', 'telephone_1': '+223 20 22 33 44',
        'description': "Formation en management, finance et entrepreneuriat.",
        'accreditations': 'DGESRS Mali, AACSB Candidat',
    },
    {
        'nom': "Institut Supérieur du Sahel",
        'pays': 'BFA', 'ville_idx': 0, 'type': 'Institut supérieur',
        'adresse': '8 Avenue de la Nation, Koulouba, Ouagadougou',
        'email': 'contact@iss.bf', 'telephone_1': '+226 25 30 68 00',
        'description': "Excellence académique au cœur du Sahel.",
        'accreditations': 'MESRS Burkina Faso, CAMES',
    },
]

DEPTS_TEMPLATES = [
    {
        'nom': "Informatique et Systèmes d'Information",
        'description': "Département dédié aux sciences informatiques et aux systèmes d'information.",
        'domaines': [
            {'nom': 'Génie Logiciel', 'filieres': ['Développement Web & Mobile', 'DevOps et Cloud']},
            {'nom': 'Réseaux et Sécurité', 'filieres': ['Cybersécurité', 'Administration Réseau']},
        ],
        'matieres': [
            'Algorithmique', 'Programmation Python', 'Bases de Données',
            'Architecture Logicielle', 'Cybersécurité', 'Développement Web',
            'Intelligence Artificielle', 'Réseaux Informatiques', 'Systèmes d\'exploitation',
        ],
        'specialites': ['Intelligence Artificielle', 'Cloud Computing', 'Data Science'],
        'niveaux': ['L1 Info', 'L2 Info', 'L3 Info', 'M1 Info', 'M2 Info'],
    },
    {
        'nom': "Sciences Économiques et Gestion",
        'description': "Département des sciences économiques, gestion et finance.",
        'domaines': [
            {'nom': 'Finance et Comptabilité', 'filieres': ["Finance d'Entreprise", 'Comptabilité-Contrôle']},
            {'nom': 'Management', 'filieres': ['Management Stratégique', 'Entrepreneuriat']},
        ],
        'matieres': [
            'Microéconomie', 'Macroéconomie', 'Comptabilité générale',
            "Finance d'entreprise", 'Marketing Stratégique', 'Droit des affaires',
            'Statistiques', 'Gestion de Projet', 'Économie africaine',
        ],
        'specialites': ['Finance Quantitative', 'Audit et Contrôle', 'Entrepreneuriat Social'],
        'niveaux': ['L1 Éco', 'L2 Éco', 'L3 Éco', 'M1 Gestion', 'M2 Finance'],
    },
    {
        'nom': "Sciences et Technologies",
        'description': "Département des sciences fondamentales et technologies appliquées.",
        'domaines': [
            {'nom': 'Mathématiques et Physique', 'filieres': ['Mathématiques Appliquées', 'Physique Industrielle']},
            {'nom': 'Génie Civil', 'filieres': ['BTP et Construction', 'Développement Durable']},
        ],
        'matieres': [
            'Mathématiques 1', 'Mathématiques 2', 'Physique',
            'Chimie', 'Mécanique des Fluides', 'Thermodynamique',
            'Résistance des Matériaux', 'Géotechnique',
        ],
        'specialites': ['Énergies Renouvelables', 'Ingénierie Civile', 'Génie Environnemental'],
        'niveaux': ['L1 ST', 'L2 ST', 'L3 ST', 'M1 ST', 'M2 ST'],
    },
    {
        'nom': "Lettres, Sciences Humaines et Communication",
        'description': "Département des lettres, sciences humaines et communication.",
        'domaines': [
            {'nom': 'Communication', 'filieres': ['Journalisme Numérique', 'Communication Digitale']},
            {'nom': 'Sciences Sociales', 'filieres': ['Sociologie', 'Psychologie du Travail']},
        ],
        'matieres': [
            'Français professionnel', 'Anglais des affaires', 'Histoire contemporaine',
            'Géopolitique africaine', 'Philosophie et Éthique', 'Techniques de communication',
        ],
        'specialites': ['Diplomatie', 'Traduction-Interprétation', 'Droit International'],
        'niveaux': ['L1 LSH', 'L2 LSH', 'L3 LSH', 'M1 Comm', 'M2 Comm'],
    },
]

ACADEMIC_YEARS = [
    {'label': '2021-2022', 'start': date(2021, 10, 1), 'end': date(2022, 7, 31)},
    {'label': '2022-2023', 'start': date(2022, 10, 1), 'end': date(2023, 7, 31)},
    {'label': '2023-2024', 'start': date(2023, 10, 1), 'end': date(2024, 7, 31)},
    {'label': '2024-2025', 'start': date(2024, 10, 1), 'end': date(2025, 7, 31)},
    {'label': '2025-2026', 'start': date(2025, 10, 1), 'end': date(2026, 7, 31)},
]

MODULE_TITRES = [
    "Introduction et Fondamentaux", "Concepts Avancés", "Pratique et Applications",
    "Études de Cas Africains", "Projets et Travaux Pratiques", "Synthèse et Révisions",
    "Approfondissement Théorique", "Mise en Pratique Professionnelle",
]

SEQUENCE_TITRES = [
    "Présentation des concepts de base", "Approfondissement théorique",
    "Exercices dirigés", "Travaux pratiques", "Étude de cas",
    "Quiz de validation", "Synthèse et points clés",
]

BLOCS_TEXTES = [
    "Ce cours présente les concepts fondamentaux de la discipline. L'étudiant sera capable de comprendre et d'appliquer les principes de base dans un contexte professionnel africain.",
    "Les objectifs pédagogiques de cette séquence sont : (1) maîtriser les concepts clés, (2) développer une approche analytique, (3) appliquer les méthodes dans des cas réels issus du contexte ouest-africain.",
    "La compétence numérique est devenue indispensable dans le contexte économique africain. Ce module aborde les outils et méthodes les plus utilisés dans le milieu professionnel.",
    "Étude de cas : Une entreprise africaine fait face à un défi de transformation. Comment aborder ce problème de façon méthodique ? Analysez la situation et proposez des solutions concrètes.",
    "Les fondements théoriques présentés dans cette section sont issus des meilleures pratiques internationales, adaptées au contexte spécifique de l'Afrique subsaharienne.",
    "Activité pratique : Réalisez une analyse comparative des systèmes utilisés dans votre région. Documentez vos observations et présentez vos conclusions lors de la prochaine session.",
    "Ce contenu s'inscrit dans le référentiel LMD (Licence-Master-Doctorat) adopté par les institutions africaines membres du CAMES.",
    "Points clés : l'approche par compétences, la pensée systémique, et l'adaptation au contexte local sont les trois piliers de cette formation.",
    "Dans ce module, nous explorons les applications concrètes à travers des exemples tirés des économies émergentes d'Afrique de l'Ouest et du Centre.",
    "Cette séquence vous permettra de consolider vos acquis et de préparer sereinement l'évaluation finale du module.",
]

SIZE_CONFIGS = {
    'small': {
        'nb_institutions': 1, 'nb_annees': 2,
        'nb_etudiants_par_inst': 60, 'nb_formateurs_par_inst': 8,
        'nb_responsables_par_inst': 2, 'nb_parents_ratio': 0.5,
        'nb_depts_par_inst': 2, 'nb_cours_par_groupe': 3,
        'nb_modules_par_cours': 2, 'nb_sequences_par_module': 3,
        'nb_blocs_par_sequence': 2, 'nb_sessions_par_cours': 5,
        'nb_evaluations_par_cours': 1, 'nb_questions_par_eval': 5,
        'participation_rate': 0.85,
    },
    'medium': {
        'nb_institutions': 2, 'nb_annees': 3,
        'nb_etudiants_par_inst': 180, 'nb_formateurs_par_inst': 20,
        'nb_responsables_par_inst': 3, 'nb_parents_ratio': 0.6,
        'nb_depts_par_inst': 3, 'nb_cours_par_groupe': 4,
        'nb_modules_par_cours': 3, 'nb_sequences_par_module': 3,
        'nb_blocs_par_sequence': 3, 'nb_sessions_par_cours': 8,
        'nb_evaluations_par_cours': 2, 'nb_questions_par_eval': 8,
        'participation_rate': 0.80,
    },
    'large': {
        'nb_institutions': 3, 'nb_annees': 4,
        'nb_etudiants_par_inst': 450, 'nb_formateurs_par_inst': 40,
        'nb_responsables_par_inst': 4, 'nb_parents_ratio': 0.5,
        'nb_depts_par_inst': 3, 'nb_cours_par_groupe': 5,
        'nb_modules_par_cours': 3, 'nb_sequences_par_module': 4,
        'nb_blocs_par_sequence': 3, 'nb_sessions_par_cours': 10,
        'nb_evaluations_par_cours': 2, 'nb_questions_par_eval': 10,
        'participation_rate': 0.78,
    },
    'xlarge': {
        'nb_institutions': 5, 'nb_annees': 4,
        'nb_etudiants_par_inst': 1200, 'nb_formateurs_par_inst': 80,
        'nb_responsables_par_inst': 4, 'nb_parents_ratio': 0.5,
        'nb_depts_par_inst': 4, 'nb_cours_par_groupe': 5,
        'nb_modules_par_cours': 4, 'nb_sequences_par_module': 4,
        'nb_blocs_par_sequence': 4, 'nb_sessions_par_cours': 12,
        'nb_evaluations_par_cours': 3, 'nb_questions_par_eval': 12,
        'participation_rate': 0.75,
    },
}

STUDENT_PROFILES = [
    # (weight, engagement, regularite, risque, profil_type)
    (30, 0.85, 0.80, 0.10, 'perseverant'),
    (20, 0.95, 0.90, 0.05, 'rapide'),
    (25, 0.55, 0.50, 0.40, 'irregulier'),
    (15, 0.30, 0.25, 0.75, 'difficulte'),
    (10, 0.20, 0.15, 0.85, 'risque'),
]

BADGE_DEFINITIONS = [
    {'code': 'premier_pas', 'nom': 'Premier Pas', 'categorie': 'engagement', 'rarete': 'commun', 'icone': '🚀', 'xp_bonus': 50, 'description': "Compléter son premier bloc de contenu"},
    {'code': 'assidu_7j', 'nom': 'Assidu 7 jours', 'categorie': 'regularite', 'rarete': 'commun', 'icone': '📅', 'xp_bonus': 100, 'description': "Se connecter 7 jours de suite"},
    {'code': 'marathon_30j', 'nom': 'Marathon 30 jours', 'categorie': 'regularite', 'rarete': 'peu_commun', 'icone': '🏃', 'xp_bonus': 500, 'description': "Se connecter 30 jours de suite"},
    {'code': 'quiz_master', 'nom': 'Quiz Master', 'categorie': 'performance', 'rarete': 'rare', 'icone': '🎯', 'xp_bonus': 200, 'description': "Obtenir 100% à 5 quiz de suite"},
    {'code': 'premier_module', 'nom': 'Premier Module', 'categorie': 'engagement', 'rarete': 'commun', 'icone': '📚', 'xp_bonus': 100, 'description': "Terminer son premier module"},
    {'code': 'premier_cours', 'nom': 'Diplômé de cours', 'categorie': 'perseverance', 'rarete': 'peu_commun', 'icone': '🎓', 'xp_bonus': 500, 'description': "Terminer un cours complet"},
    {'code': 'evaluateur', 'nom': 'Évaluateur', 'categorie': 'performance', 'rarete': 'commun', 'icone': '✍️', 'xp_bonus': 50, 'description': "Soumettre sa première évaluation"},
    {'code': 'mention_bien', 'nom': 'Mention Bien', 'categorie': 'performance', 'rarete': 'peu_commun', 'icone': '⭐', 'xp_bonus': 150, 'description': "Obtenir mention Bien à une évaluation"},
    {'code': 'explorateur', 'nom': 'Explorateur', 'categorie': 'engagement', 'rarete': 'commun', 'icone': '🔍', 'xp_bonus': 75, 'description': "Accéder à 10 séquences différentes"},
    {'code': 'legion_honneur', 'nom': 'Légion d\'Honneur', 'categorie': 'special', 'rarete': 'legendaire', 'icone': '🏆', 'xp_bonus': 2000, 'description': "Être dans le top 1% de la plateforme"},
    {'code': 'champion_90j', 'nom': 'Champion 90 jours', 'categorie': 'regularite', 'rarete': 'tres_rare', 'icone': '💎', 'xp_bonus': 2000, 'description': "Se connecter 90 jours de suite"},
    {'code': 'aide_pair', 'nom': 'Tuteur', 'categorie': 'collaboration', 'rarete': 'peu_commun', 'icone': '🤝', 'xp_bonus': 150, 'description': "Aider 5 pairs dans le forum"},
]

MISSION_DEFINITIONS = [
    {'titre': 'Connexion du jour', 'type': 'quotidienne', 'action': 'connexion', 'quantite': 1, 'xp': 10, 'difficulte': 'facile'},
    {'titre': 'Lire 3 blocs', 'type': 'quotidienne', 'action': 'bloc_complete', 'quantite': 3, 'xp': 30, 'difficulte': 'facile'},
    {'titre': 'Compléter une séquence', 'type': 'quotidienne', 'action': 'sequence_done', 'quantite': 1, 'xp': 50, 'difficulte': 'normale'},
    {'titre': 'Semaine productive', 'type': 'hebdomadaire', 'action': 'sequence_done', 'quantite': 5, 'xp': 250, 'difficulte': 'normale'},
    {'titre': 'Quiz du mois', 'type': 'mensuelle', 'action': 'quiz_participe', 'quantite': 10, 'xp': 300, 'difficulte': 'normale'},
    {'titre': 'Module complet', 'type': 'hebdomadaire', 'action': 'module_done', 'quantite': 1, 'xp': 150, 'difficulte': 'difficile'},
    {'titre': 'Évaluation soumise', 'type': 'quotidienne', 'action': 'eval_soumise', 'quantite': 1, 'xp': 30, 'difficulte': 'facile'},
    {'titre': 'Mois académique', 'type': 'mensuelle', 'action': 'cours_done', 'quantite': 1, 'xp': 1000, 'difficulte': 'defi'},
]


# ─────────────────────────────────────────────────────────────────────────────
# COMMANDE
# ─────────────────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    help = 'Seed the database with realistic multi-year SOMAPRO data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--seed-size', choices=['small', 'medium', 'large', 'xlarge'],
            default='medium', help='Volume de données (défaut: medium)',
        )
        parser.add_argument(
            '--flush', action='store_true',
            help='Supprimer les données existantes avant de générer',
        )

    def handle(self, *args, **options):
        self.size = options['seed_size']
        self.cfg = SIZE_CONFIGS[self.size]
        self._email_ctr = 1
        self._matricule_ctr = 10000
        self._pw = make_password('Somapro2024!')

        self.stdout.write(self.style.SUCCESS(f'\nSOMAP RO Seeder - taille: {self.size.upper()}'))
        self.stdout.write('-' * 60)

        with transaction.atomic():
            if options['flush']:
                self._flush()

            pays_map, villes_map = self._seed_locations()
            self._seed_parametres()
            institutions = self._seed_institutions(pays_map, villes_map)
            annees_map = self._seed_annees_scolaires(institutions)
            roles = self._seed_roles()
            refs = self._seed_referentiels(institutions)
            users = self._seed_users(institutions, annees_map, pays_map, villes_map, roles, refs)
            cg = self._seed_classes_groupes(institutions, annees_map, refs, users)
            self._seed_inscriptions_scolaires(cg, annees_map, users)
            cours_data = self._seed_cours(cg, refs, users, annees_map)
            content = self._seed_content(cours_data)
            self._seed_inscriptions_cours(cours_data, users)
            self._seed_sessions(cours_data, users)
            self._seed_evaluations(cours_data, content, users)
            self._seed_progression(cours_data, content, users)
            self._seed_analytics(cours_data, content, users)
            self._seed_gamification(users)
            self._seed_notifications(institutions, annees_map, cours_data, users)

        self.stdout.write(self.style.SUCCESS('\nSeeding termine avec succes !'))

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def _log(self, msg):
        self.stdout.write(f'  {msg}')

    def _email(self, prenom, nom, domain='somapro.edu'):
        slug = f"{prenom.lower().replace(' ', '').replace('-', '')}.{nom.lower()}"
        email = f"{slug}{self._email_ctr}@{domain}"
        self._email_ctr += 1
        return email

    def _matricule(self, inst_code='SP'):
        m = f"{inst_code}{self._matricule_ctr:05d}"
        self._matricule_ctr += 1
        return m

    def _rand_prenom(self, genre=None):
        if genre == 'F':
            return random.choice(PRENOMS_F)
        if genre == 'H':
            return random.choice(PRENOMS_H)
        return random.choice(PRENOMS_H + PRENOMS_F)

    def _rand_nom(self):
        return random.choice(NOMS)

    def _rand_date_naissance(self, min_age=17, max_age=30):
        today = date.today()
        days = random.randint(min_age * 365, max_age * 365)
        return today - timedelta(days=days)

    def _rand_date_in_year(self, annee_data, offset_days=0):
        start = annee_data['start'] + timedelta(days=offset_days)
        end = annee_data['end']
        if start >= end:
            return start
        delta = (end - start).days
        return start + timedelta(days=random.randint(0, delta))

    def _profile_weights(self):
        weights = [p[0] for p in STUDENT_PROFILES]
        return random.choices(STUDENT_PROFILES, weights=weights, k=1)[0]

    # ─── FLUSH ───────────────────────────────────────────────────────────────

    def _flush(self):
        self._log('Suppression des données existantes...')
        from gamification.models import UserBadge, UserMission, UserLevel, Streak, XPTransaction, Badge, Mission
        from analytics.models import (
            BlocAnalytics, BlocAnalyticsSummary, SequenceAnalyticsSummary,
            ModuleAnalyticsSummary, LearningEvent, LearnerProfile,
            SkillMasteryScore, KnowledgeGap, DropoutAlert,
        )
        from progress.models import ProgressionApprenant, ProgressionModule, ProgressionSequence, HistoriqueActivite
        from evaluations.models import ReponseQuestion, PassageEvaluation, ReponseQuiz, PassageQuiz, Reponse, Question, Evaluation, Quiz
        from courses.models import (
            BlocProgress, SequenceProgress, ModuleProgress, CoursProgress,
            Participation, Session, InscriptionCours, Suivi,
            BlocContenu, Sequence, Module, Cours,
        )
        from notifications.models import Notification, PreferenceNotification
        from academics.models import Inscription, Groupe, Classe, Departement, DomaineEtude, Filiere, Matiere, Specialite, AnneeScolaire
        from users.models import Apprenant, Formateur, ResponsableAcademique, Admin, Parent, SuperAdmin
        from parametres.models import ParametresInstitution, ParametresPlateforme, PreferencesUtilisateur
        from academics.models import Institution

        for model in [
            UserBadge, UserMission, XPTransaction, UserLevel, Streak, Badge, Mission,
            BlocAnalytics, BlocAnalyticsSummary, SequenceAnalyticsSummary,
            ModuleAnalyticsSummary, LearningEvent, LearnerProfile,
            SkillMasteryScore, KnowledgeGap, DropoutAlert,
            ProgressionApprenant, HistoriqueActivite,
            ReponseQuestion, PassageEvaluation, ReponseQuiz, PassageQuiz,
            Reponse, Question, Evaluation, Quiz,
            BlocProgress, SequenceProgress, ModuleProgress, CoursProgress,
            Participation, Session, InscriptionCours, Suivi,
            BlocContenu, Sequence, Module, Cours,
            Notification, PreferenceNotification,
            Inscription, Groupe, Classe,
            Filiere, DomaineEtude, Departement, Matiere, Specialite,
            AnneeScolaire,
            Apprenant, Formateur, ResponsableAcademique, Admin, Parent, SuperAdmin,
            PreferencesUtilisateur, ParametresInstitution,
            Institution,
        ]:
            try:
                count = model.objects.all().delete()[0]
                if count:
                    self._log(f'  Supprimé {count} {model.__name__}')
            except Exception:
                pass

    # ─── LOCATIONS ───────────────────────────────────────────────────────────

    def _seed_locations(self):
        from locations.models import Pays, Ville
        self._log('Pays et villes...')
        pays_map = {}
        villes_map = {}
        for pd in PAYS_DATA:
            pays, _ = Pays.objects.get_or_create(code=pd['code'], defaults={'nom': pd['nom']})
            pays_map[pd['code']] = pays
            villes_map[pd['code']] = []
            for vnom in pd['villes']:
                ville, _ = Ville.objects.get_or_create(nom=vnom, pays=pays)
                villes_map[pd['code']].append(ville)
        self._log(f'  {len(pays_map)} pays, {sum(len(v) for v in villes_map.values())} villes')
        return pays_map, villes_map

    # ─── PARAMETRES ──────────────────────────────────────────────────────────

    def _seed_parametres(self):
        from parametres.models import ParametresPlateforme
        ParametresPlateforme.get_instance()
        self._log('Paramètres plateforme initialisés')

    # ─── INSTITUTIONS ────────────────────────────────────────────────────────

    def _seed_institutions(self, pays_map, villes_map):
        from academics.models import Institution
        from parametres.models import ParametresInstitution
        n = self.cfg['nb_institutions']
        self._log(f'Institutions ({n})...')
        institutions = []
        for data in INSTITUTIONS_DATA[:n]:
            pays = pays_map[data['pays']]
            inst, created = Institution.objects.get_or_create(
                nom=data['nom'],
                defaults={
                    'pays': pays,
                    'adresse': data['adresse'],
                    'email': data['email'],
                    'telephone_1': data['telephone_1'],
                    'description': data['description'],
                    'accreditations': data['accreditations'],
                    'type_institution': data['type'],
                    'statut': 'active',
                    'nombre_etudiants': self.cfg['nb_etudiants_par_inst'],
                },
            )
            if created:
                ParametresInstitution.objects.get_or_create(institution=inst)
            institutions.append(inst)
        return institutions

    # ─── ANNÉES SCOLAIRES ────────────────────────────────────────────────────

    def _seed_annees_scolaires(self, institutions):
        from academics.models import AnneeScolaire
        n = self.cfg['nb_annees']
        years_to_use = ACADEMIC_YEARS[-n:]
        self._log(f'Années scolaires ({n} par institution)...')
        annees_map = {}  # inst.id -> list[AnneeScolaire]
        for inst in institutions:
            annees_map[inst.id] = []
            for i, yr in enumerate(years_to_use):
                is_last = (i == len(years_to_use) - 1)
                annee, _ = AnneeScolaire.objects.get_or_create(
                    institution=inst,
                    annee_format_classique=yr['label'],
                    defaults={
                        'date_debut': yr['start'],
                        'date_fin': yr['end'],
                        'est_active': is_last,
                        'description': f"Année académique {yr['label']}",
                    },
                )
                # If already exists, ensure only the last year is active
                if is_last and not annee.est_active:
                    annee.est_active = True
                    annee.save()
                annees_map[inst.id].append(annee)
        return annees_map

    # ─── ROLES ───────────────────────────────────────────────────────────────

    def _seed_roles(self):
        from users.models import UserRole
        roles = {}
        for name in ['Admin', 'Formateur', 'Apprenant', 'Parent', 'ResponsableAcademique', 'SuperAdmin']:
            role, _ = UserRole.objects.get_or_create(name=name)
            roles[name] = role
        self._log('Rôles utilisateurs créés')
        return roles

    # ─── RÉFÉRENTIELS ────────────────────────────────────────────────────────

    def _seed_referentiels(self, institutions):
        from academics.models import Departement, DomaineEtude, Filiere, Matiere, Specialite
        from users.models import ResponsableAcademique, UserRole
        n_depts = self.cfg['nb_depts_par_inst']
        self._log(f'Référentiels académiques ({n_depts} depts/inst)...')

        refs = {}
        role_ra = UserRole.objects.get(name='ResponsableAcademique')

        for inst in institutions:
            refs[inst.id] = {
                'depts': [], 'domaines': [], 'filieres': [],
                'matieres': [], 'specialites': [],
                'ra_users': [],
            }
            active_annee = self._get_active_annee(inst)
            n_ra = self.cfg['nb_responsables_par_inst']

            # Créer les ResponsableAcademiques d'abord (sans dept)
            ras = []
            for i in range(n_ra):
                genre = random.choice(['H', 'F'])
                prenom = self._rand_prenom(genre)
                nom = self._rand_nom()
                email = self._email(prenom, nom, domain='ra.somapro.edu')
                try:
                    ra = ResponsableAcademique.objects.create(
                        email=email, nom=nom, prenom=prenom,
                        password=self._pw, is_active=True,
                        role=role_ra, institution=inst,
                        annee_scolaire_active=active_annee,
                        telephone=f'+221 7{random.randint(0,9)} {random.randint(100,999)} {random.randint(10,99)} {random.randint(10,99)}',
                    )
                    ras.append(ra)
                except Exception:
                    pass
            refs[inst.id]['ra_users'] = ras

            # Créer les départements
            dept_templates = DEPTS_TEMPLATES[:n_depts]
            for j, tmpl in enumerate(dept_templates):
                ra = ras[j % len(ras)] if ras else None
                if not ra:
                    continue
                dept_nom = f"{tmpl['nom']}"
                try:
                    dept = Departement.objects.create(
                        nom=dept_nom,
                        description=tmpl['description'],
                        institution=inst,
                        responsable_academique=ra,
                        est_actif=True,
                    )
                    refs[inst.id]['depts'].append(dept)
                except Exception:
                    # Already exists
                    try:
                        dept = Departement.objects.get(nom=dept_nom, institution=inst)
                        refs[inst.id]['depts'].append(dept)
                    except Exception:
                        continue

                # Domaines et filières
                for dom_data in tmpl['domaines'][:2]:
                    dom_nom = dom_data['nom']
                    try:
                        dom = DomaineEtude.objects.get_or_create(
                            nom=dom_nom, institution=inst,
                            defaults={'departement': dept, 'est_actif': True},
                        )[0]
                        refs[inst.id]['domaines'].append(dom)
                    except Exception:
                        continue

                    for fil_nom in dom_data['filieres'][:2]:
                        try:
                            fil = Filiere.objects.get_or_create(
                                nom=fil_nom, institution=inst,
                                defaults={
                                    'domaine_etude': dom,
                                    'statut': 'actif', 'est_actif': True,
                                },
                            )[0]
                            refs[inst.id]['filieres'].append(fil)
                        except Exception:
                            pass

                # Matières
                for mat_nom in tmpl['matieres']:
                    try:
                        mat = Matiere.objects.get_or_create(
                            nom=mat_nom, institution=inst,
                            defaults={'est_actif': True},
                        )[0]
                        refs[inst.id]['matieres'].append(mat)
                    except Exception:
                        pass

                # Spécialités
                for spec_nom in tmpl['specialites']:
                    try:
                        spec = Specialite.objects.get_or_create(
                            nom=spec_nom, institution=inst,
                            defaults={'est_actif': True},
                        )[0]
                        refs[inst.id]['specialites'].append(spec)
                    except Exception:
                        pass

        total_mats = sum(len(r['matieres']) for r in refs.values())
        total_fils = sum(len(r['filieres']) for r in refs.values())
        self._log(f'  {total_mats} matières, {total_fils} filières créées')
        return refs

    def _get_active_annee(self, inst):
        from academics.models import AnneeScolaire
        return AnneeScolaire.objects.filter(institution=inst, est_active=True).first()

    # ─── UTILISATEURS ────────────────────────────────────────────────────────

    def _seed_users(self, institutions, annees_map, pays_map, villes_map, roles, refs):
        from users.models import SuperAdmin, Admin, Formateur, Parent, Apprenant
        from parametres.models import PreferencesUtilisateur
        self._log('Utilisateurs...')
        users = {
            'superadmins': [], 'admins': [], 'formateurs': [],
            'parents': [], 'apprenants': [],
            'apprenants_by_inst': {},
            'formateurs_by_inst': {},
        }

        # SuperAdmin global
        try:
            sa = SuperAdmin.objects.create(
                email='superadmin@somapro.edu',
                nom='Somapro', prenom='Admin',
                password=self._pw, is_active=True, is_staff=True, is_superuser=True,
                role=roles['SuperAdmin'],
            )
            users['superadmins'].append(sa)
        except Exception:
            pass

        all_pays = list(pays_map.values())

        for inst in institutions:
            inst_code = ''.join(w[0] for w in inst.nom.split()[:3]).upper()
            active_annee = self._get_active_annee(inst)
            users['apprenants_by_inst'][inst.id] = []
            users['formateurs_by_inst'][inst.id] = []
            pays_inst = inst.pays

            # Admin de l'institution
            prenom_a, nom_a = 'Directeur', self._rand_nom()
            try:
                admin = Admin.objects.create(
                    email=self._email(prenom_a, nom_a, domain=f'{inst_code.lower()}.edu'),
                    nom=nom_a, prenom=prenom_a, password=self._pw,
                    is_active=True, role=roles['Admin'],
                    institution=inst, annee_scolaire_active=active_annee,
                )
                users['admins'].append(admin)
                PreferencesUtilisateur.objects.get_or_create(user=admin)
            except Exception:
                pass

            # Formateurs
            n_form = self.cfg['nb_formateurs_par_inst']
            for _ in range(n_form):
                genre = random.choice(['H', 'F'])
                prenom = self._rand_prenom(genre)
                nom = self._rand_nom()
                pays_res = random.choice(all_pays)
                try:
                    form = Formateur.objects.create(
                        email=self._email(prenom, nom, domain='formateurs.edu'),
                        nom=nom, prenom=prenom, password=self._pw,
                        is_active=True, role=roles['Formateur'],
                        institution=inst, annee_scolaire_active=active_annee,
                        pays_residence=pays_res,
                        telephone=f'+22{random.randint(1,9)} {random.randint(10,99)} {random.randint(100,999)} {random.randint(10,99)} {random.randint(10,99)}',
                    )
                    form.institutions.add(inst)
                    # Ajouter quelques spécialités
                    specs = refs[inst.id]['specialites']
                    if specs:
                        for spec in random.sample(specs, min(2, len(specs))):
                            form.specialites.add(spec)
                    users['formateurs'].append(form)
                    users['formateurs_by_inst'][inst.id].append(form)
                    PreferencesUtilisateur.objects.get_or_create(user=form)
                except Exception:
                    pass

            # Parents
            n_parents = int(self.cfg['nb_etudiants_par_inst'] * self.cfg['nb_parents_ratio'])
            inst_parents = []
            for _ in range(n_parents):
                genre = random.choice(['H', 'F'])
                prenom = self._rand_prenom(genre)
                nom = self._rand_nom()
                pays_res = random.choice(all_pays)
                try:
                    parent = Parent.objects.create(
                        email=self._email(prenom, nom, domain='parents.edu'),
                        nom=nom, prenom=prenom, password=self._pw,
                        is_active=True, role=roles['Parent'],
                        pays_residence=pays_res,
                        telephone=f'+22{random.randint(1,9)} {random.randint(10,99)} {random.randint(100,999)} {random.randint(10,99)} {random.randint(10,99)}',
                    )
                    inst_parents.append(parent)
                    users['parents'].append(parent)
                except Exception:
                    pass

            # Apprenants
            n_app = self.cfg['nb_etudiants_par_inst']
            for i in range(n_app):
                genre = random.choice(['H', 'F'])
                prenom = self._rand_prenom(genre)
                nom = self._rand_nom()
                pays_res = random.choice(all_pays)
                tuteur = inst_parents[i % len(inst_parents)] if inst_parents else None
                try:
                    app = Apprenant.objects.create(
                        email=self._email(prenom, nom),
                        nom=nom, prenom=prenom, password=self._pw,
                        is_active=True, role=roles['Apprenant'],
                        institution=inst, annee_scolaire_active=active_annee,
                        pays_residence=pays_res,
                        matricule=self._matricule(inst_code),
                        date_naissance=self._rand_date_naissance(),
                        tuteur=tuteur,
                        telephone=f'+22{random.randint(1,9)} {random.randint(70,79)} {random.randint(100,999)} {random.randint(10,99)} {random.randint(10,99)}',
                    )
                    users['apprenants'].append(app)
                    users['apprenants_by_inst'][inst.id].append(app)
                    PreferencesUtilisateur.objects.get_or_create(user=app)
                except Exception:
                    pass

        n_app = len(users['apprenants'])
        n_form = len(users['formateurs'])
        self._log(f'  {n_app} apprenants, {n_form} formateurs, {len(users["parents"])} parents créés')
        return users

    # ─── CLASSES & GROUPES ───────────────────────────────────────────────────

    def _seed_classes_groupes(self, institutions, annees_map, refs, users):
        from academics.models import Classe, Groupe
        self._log('Classes et groupes...')
        cg = {}  # inst.id -> {annee.id -> [{classe, groupes, niveau}]}

        for inst in institutions:
            cg[inst.id] = {}
            depts = refs[inst.id]['depts']
            filieres = refs[inst.id]['filieres']
            formateurs = users['formateurs_by_inst'][inst.id]

            for annee in annees_map[inst.id]:
                cg[inst.id][annee.id] = []

                # Créer des classes par niveau (L1, L2, L3) pour chaque filière principale
                niveaux = ['L1', 'L2', 'L3']
                filieres_echantillon = filieres[:min(3, len(filieres))]

                for fil in filieres_echantillon:
                    for niveau in niveaux:
                        classe_nom = f"{niveau} — {fil.nom[:30]} {annee.annee_format_classique}"
                        try:
                            classe = Classe(
                                nom=classe_nom, institution=inst,
                                annee_scolaire=annee,
                                description=f"Classe {niveau} en {fil.nom}",
                            )
                            classe.save()
                            if filieres:
                                classe.filieres.add(fil)
                        except Exception:
                            try:
                                classe = Classe.objects.get(
                                    nom=classe_nom, institution=inst, annee_scolaire=annee,
                                )
                            except Exception:
                                continue

                        # 2 groupes par classe
                        classe_groupes = []
                        for lettre in ['A', 'B']:
                            groupe_nom = f"Groupe {lettre} — {niveau}"
                            try:
                                groupe = Groupe(
                                    nom=groupe_nom, institution=inst,
                                    annee_scolaire=annee, classe=classe,
                                    description=f"Groupe {lettre} de la classe {niveau}",
                                )
                                groupe.save()
                                # Assigner des enseignants
                                if formateurs:
                                    for form in random.sample(formateurs, min(3, len(formateurs))):
                                        groupe.enseignants.add(form)
                            except Exception:
                                try:
                                    groupe = Groupe.objects.get(
                                        nom=groupe_nom, institution=inst,
                                        annee_scolaire=annee, classe=classe,
                                    )
                                except Exception:
                                    continue
                            classe_groupes.append(groupe)

                        cg[inst.id][annee.id].append({
                            'classe': classe, 'groupes': classe_groupes,
                            'niveau': niveau, 'filiere': fil,
                        })

        total_groupes = sum(
            sum(len(cl['groupes']) for cl in cls)
            for inst_data in cg.values()
            for cls in inst_data.values()
        )
        self._log(f'  {total_groupes} groupes créés')
        return cg

    # ─── INSCRIPTIONS SCOLAIRES ──────────────────────────────────────────────

    def _seed_inscriptions_scolaires(self, cg, annees_map, users):
        from academics.models import Inscription
        self._log('Inscriptions scolaires...')
        count = 0

        for inst_id, annees in cg.items():
            apprenants = users['apprenants_by_inst'][inst_id]
            if not apprenants:
                continue

            for annee_id, classes_data in annees.items():
                # Récupérer l'objet annee
                from academics.models import AnneeScolaire, Institution
                try:
                    annee = AnneeScolaire.objects.get(pk=annee_id)
                    inst = Institution.objects.get(pk=inst_id)
                except Exception:
                    continue

                # Répartir les apprenants dans les classes/groupes
                all_groupes = [g for cd in classes_data for g in cd['groupes']]
                if not all_groupes:
                    continue

                # Pour l'année active, inscrire tous les apprenants
                # Pour les années passées, inscrire une partie
                from academics.models import AnneeScolaire as AS
                is_active = AS.objects.filter(pk=annee_id, est_active=True).exists()
                app_sample = apprenants if is_active else random.sample(
                    apprenants, int(len(apprenants) * 0.8)
                )

                for i, app in enumerate(app_sample):
                    groupe = all_groupes[i % len(all_groupes)]
                    classe = groupe.classe

                    # Assigner le groupe à l'apprenant (groupe actuel)
                    if is_active:
                        try:
                            app.groupe = groupe
                            app.save(update_fields=['groupe'])
                        except Exception:
                            pass

                    statut = 'actif' if is_active else random.choice(['actif', 'diplome', 'diplome', 'actif'])
                    statut_paiement = random.choice(['paye', 'paye', 'paye', 'en_attente'])

                    try:
                        Inscription.objects.get_or_create(
                            apprenant=app, institution=inst, annee_scolaire=annee,
                            defaults={
                                'classe': classe,
                                'statut': statut,
                                'statut_paiement': statut_paiement,
                            },
                        )
                        count += 1
                    except Exception:
                        pass

        self._log(f'  {count} inscriptions scolaires')

    # ─── COURS ───────────────────────────────────────────────────────────────

    def _seed_cours(self, cg, refs, users, annees_map):
        from courses.models import Cours
        self._log('Cours...')
        cours_data = []
        used_combos = set()
        n_cours = self.cfg['nb_cours_par_groupe']

        for inst_id, annees in cg.items():
            matieres = refs[inst_id]['matieres']
            formateurs = users['formateurs_by_inst'][inst_id]
            depts = refs[inst_id]['depts']

            if not matieres or not formateurs:
                continue

            for annee_id, classes_data in annees.items():
                from academics.models import AnneeScolaire, Institution
                try:
                    annee = AnneeScolaire.objects.get(pk=annee_id)
                    inst = Institution.objects.get(pk=inst_id)
                except Exception:
                    continue

                is_active_year = annee.est_active
                annee_data_raw = next(
                    (y for y in ACADEMIC_YEARS if y['label'] == annee.annee_format_classique),
                    ACADEMIC_YEARS[-1],
                )

                for class_data in classes_data:
                    for groupe in class_data['groupes']:
                        matieres_disponibles = list(matieres)
                        random.shuffle(matieres_disponibles)

                        for matiere in matieres_disponibles[:n_cours]:
                            formateur = random.choice(formateurs)
                            combo = (groupe.pk, matiere.pk, formateur.pk, annee.pk)
                            if combo in used_combos:
                                # Try different formateur
                                for alt_form in formateurs:
                                    c2 = (groupe.pk, matiere.pk, alt_form.pk, annee.pk)
                                    if c2 not in used_combos:
                                        formateur = alt_form
                                        combo = c2
                                        break
                                else:
                                    continue

                            used_combos.add(combo)
                            dept = depts[0] if depts else None

                            if is_active_year:
                                statut = random.choice(['en_cours', 'en_cours', 'planifie'])
                                date_d = annee_data_raw['start'] + timedelta(days=random.randint(0, 30))
                                date_f = annee_data_raw['end']
                            else:
                                statut = 'termine'
                                date_d = annee_data_raw['start']
                                date_f = annee_data_raw['end']

                            titre = f"{matiere.nom} — {class_data['niveau']}"
                            try:
                                cours = Cours.objects.create(
                                    titre=titre,
                                    groupe=groupe,
                                    enseignant=formateur,
                                    matiere=matiere,
                                    volume_horaire=random.randint(20, 60),
                                    date_debut=date_d,
                                    date_fin=date_f,
                                    statut=statut,
                                    institution=inst,
                                    annee_scolaire=annee,
                                    departement=dept,
                                )
                                cours_data.append({
                                    'cours': cours, 'inst': inst, 'annee': annee,
                                    'annee_data': annee_data_raw, 'groupe': groupe,
                                    'is_active': is_active_year,
                                })
                            except Exception:
                                pass

        self._log(f'  {len(cours_data)} cours créés')
        return cours_data

    # ─── CONTENU PÉDAGOGIQUE ─────────────────────────────────────────────────

    def _seed_content(self, cours_data):
        from courses.models import Module, Sequence, BlocContenu
        self._log('Modules, séquences et blocs...')
        content = []  # [{cours, modules: [{module, sequences: [{sequence, blocs}]}]}]
        n_mod = self.cfg['nb_modules_par_cours']
        n_seq = self.cfg['nb_sequences_par_module']
        n_bloc = self.cfg['nb_blocs_par_sequence']

        modules_bulk = []
        seqs_bulk = []
        blocs_bulk = []

        for cd in cours_data:
            cours = cd['cours']
            cours_content = {'cours': cours, 'modules': []}

            for m_idx in range(n_mod):
                mod_titre = MODULE_TITRES[m_idx % len(MODULE_TITRES)]
                module = Module(
                    titre=mod_titre, cours=cours, ordre=m_idx + 1,
                    duree_estimee=random.randint(3, 8),
                    institution=cours.institution,
                    annee_scolaire=cours.annee_scolaire,
                )
                module.save()
                mod_content = {'module': module, 'sequences': []}

                for s_idx in range(n_seq):
                    seq_titre = SEQUENCE_TITRES[s_idx % len(SEQUENCE_TITRES)]
                    seq = Sequence(
                        titre=seq_titre, module=module, ordre=s_idx + 1,
                        description=f"Séquence {s_idx + 1} du module {m_idx + 1}",
                        institution=cours.institution,
                        annee_scolaire=cours.annee_scolaire,
                    )
                    seq.save()
                    seq_blocs = []

                    for b_idx in range(n_bloc):
                        type_bloc = random.choice(['texte', 'texte', 'texte', 'markdown', 'video', 'lien'])
                        texte = random.choice(BLOCS_TEXTES) if type_bloc in ('texte', 'markdown') else None
                        bloc = BlocContenu(
                            sequence=seq,
                            titre=f"Contenu {b_idx + 1} — {seq_titre[:30]}",
                            type_bloc=type_bloc,
                            ordre=b_idx + 1,
                            contenu_texte=texte if type_bloc == 'texte' else None,
                            contenu_markdown=texte if type_bloc == 'markdown' else None,
                            video_url='https://example.com/video.mp4' if type_bloc == 'video' else None,
                            lien_externe='https://example.com/ressource' if type_bloc == 'lien' else None,
                            duree_estimee_minutes=random.randint(5, 25),
                            est_obligatoire=random.random() > 0.15,
                            est_visible=True,
                        )
                        seq_blocs.append(bloc)

                    BlocContenu.objects.bulk_create(seq_blocs, ignore_conflicts=True)
                    seq_blocs_saved = list(BlocContenu.objects.filter(sequence=seq).order_by('ordre'))
                    mod_content['sequences'].append({'sequence': seq, 'blocs': seq_blocs_saved})

                cours_content['modules'].append(mod_content)
            content.append(cours_content)

        total_blocs = sum(
            len(sc['blocs'])
            for cc in content
            for mc in cc['modules']
            for sc in mc['sequences']
        )
        self._log(f'  {len(content)} cours avec contenu, {total_blocs} blocs créés')
        return content

    # ─── INSCRIPTIONS COURS ──────────────────────────────────────────────────

    def _seed_inscriptions_cours(self, cours_data, users):
        from courses.models import InscriptionCours, Suivi
        self._log('Inscriptions aux cours...')
        inscriptions = []
        suivis = []
        seen = set()

        for cd in cours_data:
            cours = cd['cours']
            inst_id = cd['inst'].id
            apprenants = users['apprenants_by_inst'].get(inst_id, [])
            groupe = cd['groupe']

            # Apprenants du groupe
            groupe_apps = [a for a in apprenants if a.groupe_id == groupe.pk]
            if not groupe_apps:
                # Prendre un échantillon de l'institution
                groupe_apps = random.sample(apprenants, min(25, len(apprenants)))

            for app in groupe_apps:
                key = (app.pk, cours.pk)
                if key in seen:
                    continue
                seen.add(key)

                if cd['is_active']:
                    statut = random.choices(
                        ['inscrit', 'en_cours', 'en_cours', 'termine'],
                        weights=[10, 40, 40, 10]
                    )[0]
                else:
                    statut = random.choices(
                        ['termine', 'termine', 'abandonne', 'inscrit'],
                        weights=[60, 20, 15, 5]
                    )[0]

                inscriptions.append(InscriptionCours(
                    apprenant=app, cours=cours,
                    statut=statut,
                    institution=cours.institution,
                    annee_scolaire=cours.annee_scolaire,
                ))
                progression = random.randint(0, 100) if statut in ('en_cours', 'termine') else 0
                if statut == 'termine':
                    progression = 100
                suivis.append(Suivi(
                    apprenant=app, cours=cours,
                    progression=progression,
                    institution=cours.institution,
                    annee_scolaire=cours.annee_scolaire,
                ))

        InscriptionCours.objects.bulk_create(inscriptions, ignore_conflicts=True)
        Suivi.objects.bulk_create(suivis, ignore_conflicts=True)
        self._log(f'  {len(inscriptions)} inscriptions cours')

    # ─── SESSIONS ────────────────────────────────────────────────────────────

    def _seed_sessions(self, cours_data, users):
        from courses.models import Session, Participation
        self._log('Sessions et participations...')
        n_sess = self.cfg['nb_sessions_par_cours']
        part_rate = self.cfg['participation_rate']
        sessions_created = 0
        parts_bulk = []

        for cd in cours_data:
            cours = cd['cours']
            formateur = cours.enseignant
            annee_data = cd['annee_data']
            inst_id = cd['inst'].id
            apprenants = users['apprenants_by_inst'].get(inst_id, [])
            groupe_apps = [a for a in apprenants if a.groupe_id == cours.groupe_id]
            if not groupe_apps:
                groupe_apps = random.sample(apprenants, min(20, len(apprenants)))

            for s_idx in range(n_sess):
                # Répartir les sessions sur la durée du cours
                fraction = (s_idx + 1) / (n_sess + 1)
                delta_days = int((annee_data['end'] - annee_data['start']).days * fraction)
                sess_date = annee_data['start'] + timedelta(days=delta_days)
                sess_dt_start = timezone.make_aware(
                    __import__('datetime').datetime.combine(sess_date, __import__('datetime').time(8, 0))
                )
                sess_dt_end = sess_dt_start + timedelta(hours=2)

                if cd['is_active'] and sess_date > date.today():
                    statut = 'planifiee'
                else:
                    statut = random.choice(['realisee', 'realisee', 'realisee', 'annulee'])

                try:
                    sess = Session.objects.create(
                        titre=f"Séance {s_idx + 1} — {cours.titre[:40]}",
                        date_debut=sess_dt_start, date_fin=sess_dt_end,
                        formateur=formateur, cours=cours,
                        statut=statut,
                        participation_mode=random.choice(['presentiel', 'distanciel', 'hybride']),
                        institution=cours.institution,
                        annee_scolaire=cours.annee_scolaire,
                    )
                    sessions_created += 1

                    if statut == 'realisee':
                        presents = 0
                        for app in groupe_apps:
                            statut_p = 'present' if random.random() < part_rate else random.choice(['absent', 'retard', 'excuse'])
                            if statut_p == 'present':
                                presents += 1
                            parts_bulk.append(Participation(
                                session=sess, apprenant=app, statut=statut_p,
                                institution=cours.institution,
                                annee_scolaire=cours.annee_scolaire,
                            ))
                        sess.nb_presents = presents
                        sess.save(update_fields=['nb_presents'])
                except Exception:
                    pass

        Participation.objects.bulk_create(parts_bulk, ignore_conflicts=True)
        self._log(f'  {sessions_created} sessions, {len(parts_bulk)} participations')

    # ─── ÉVALUATIONS ─────────────────────────────────────────────────────────

    def _seed_evaluations(self, cours_data, content, users):
        from evaluations.models import Quiz, Question, Reponse, Evaluation, PassageEvaluation, ReponseQuestion, PassageQuiz
        self._log('Évaluations et quiz...')
        n_eval = self.cfg['nb_evaluations_par_cours']
        n_q = self.cfg['nb_questions_par_eval']
        passages_bulk = []
        quiz_count = 0

        # Index content by cours pk
        content_by_cours = {cc['cours'].pk: cc for cc in content}

        for cd in cours_data:
            cours = cd['cours']
            inst_id = cd['inst'].id
            apprenants = users['apprenants_by_inst'].get(inst_id, [])
            groupe_apps = [a for a in apprenants if a.groupe_id == cours.groupe_id]
            if not groupe_apps:
                groupe_apps = random.sample(apprenants, min(20, len(apprenants)))

            cc = content_by_cours.get(cours.pk)
            if not cc:
                continue

            annee_data = cd['annee_data']

            # ── Quiz sur les séquences ────────────────────────────────────────
            for mc in cc['modules'][:2]:
                for sc in mc['sequences'][:2]:
                    seq = sc['sequence']
                    try:
                        quiz = Quiz.objects.create(
                            titre=f"Quiz — {seq.titre[:50]}",
                            sequence=seq,
                            description="Validez votre compréhension de cette séquence.",
                        )
                        quiz_count += 1
                        questions_quiz = []
                        for q_idx in range(min(4, n_q)):
                            q = Question(
                                quiz=quiz,
                                enonce_texte=f"Question {q_idx + 1} : Quel est le concept principal abordé dans cette séquence ?",
                                type_question='choix_unique',
                                mode_correction='automatique',
                                points=1.0, ordre=q_idx + 1,
                            )
                            q.save()
                            # Réponses
                            reponses = [
                                Reponse(question=q, texte='Réponse A correcte', est_correcte=True, ordre=1),
                                Reponse(question=q, texte='Réponse B incorrecte', est_correcte=False, ordre=2),
                                Reponse(question=q, texte='Réponse C incorrecte', est_correcte=False, ordre=3),
                                Reponse(question=q, texte='Réponse D incorrecte', est_correcte=False, ordre=4),
                            ]
                            Reponse.objects.bulk_create(reponses)
                            questions_quiz.append((q, reponses))

                        # Passages quiz pour apprenants
                        for app in random.sample(groupe_apps, min(len(groupe_apps), 15)):
                            score = random.uniform(40, 100) if cd['is_active'] else random.uniform(30, 100)
                            try:
                                pq = PassageQuiz.objects.create(
                                    apprenant=app, quiz=quiz,
                                    score=round(score, 1), termine=True,
                                )
                            except Exception:
                                pass
                    except Exception:
                        pass

            # ── Évaluations formelles ─────────────────────────────────────────
            for e_idx in range(n_eval):
                fraction = (e_idx + 1) / (n_eval + 1)
                eval_date = annee_data['start'] + timedelta(
                    days=int((annee_data['end'] - annee_data['start']).days * fraction)
                )
                is_past = eval_date < date.today()

                try:
                    eval_obj = Evaluation.objects.create(
                        cours=cours,
                        enseignant=cours.enseignant,
                        titre=f"{'Examen' if e_idx == n_eval - 1 else 'Devoir'} {e_idx + 1} — {cours.matiere.nom[:30]}",
                        type_evaluation='structuree',
                        bareme=20.0,
                        duree_minutes=random.choice([60, 90, 120]),
                        date_debut=timezone.make_aware(__import__('datetime').datetime.combine(eval_date, __import__('datetime').time(8, 0))),
                        date_fin=timezone.make_aware(__import__('datetime').datetime.combine(eval_date + timedelta(days=14), __import__('datetime').time(23, 59))),
                        est_publiee=is_past or random.random() > 0.3,
                    )

                    eval_questions = []
                    for q_idx in range(n_q):
                        if q_idx < n_q // 2:
                            q_type = 'choix_unique'
                            mode = 'automatique'
                        else:
                            q_type = 'texte_court'
                            mode = 'manuelle'
                        q = Question(
                            evaluation=eval_obj,
                            enonce_texte=f"Question {q_idx + 1} : Expliquez le concept n°{q_idx + 1} du cours.",
                            type_question=q_type, mode_correction=mode,
                            points=20.0 / n_q, ordre=q_idx + 1,
                        )
                        q.save()

                        if q_type == 'choix_unique':
                            reponses = [
                                Reponse(question=q, texte='Réponse A — correcte', est_correcte=True, ordre=1),
                                Reponse(question=q, texte='Réponse B', est_correcte=False, ordre=2),
                                Reponse(question=q, texte='Réponse C', est_correcte=False, ordre=3),
                            ]
                            Reponse.objects.bulk_create(reponses)
                            eval_questions.append((q, reponses))
                        else:
                            eval_questions.append((q, []))

                    # Passages pour les apprenants
                    if is_past:
                        for app in groupe_apps:
                            note = random.gauss(12, 4)
                            note = max(0, min(20, round(note, 2)))
                            try:
                                passage = PassageEvaluation.objects.create(
                                    apprenant=app, evaluation=eval_obj,
                                    statut='corrige', note=note,
                                    date_soumission=timezone.make_aware(
                                        __import__('datetime').datetime.combine(eval_date + timedelta(days=random.randint(1, 10)), __import__('datetime').time(14, 0))
                                    ),
                                )
                            except Exception:
                                pass
                except Exception:
                    pass

        self._log(f'  {quiz_count} quiz créés')

    # ─── PROGRESSION ─────────────────────────────────────────────────────────

    def _seed_progression(self, cours_data, content, users):
        from courses.models import BlocProgress, SequenceProgress, ModuleProgress, CoursProgress
        from progress.models import ProgressionApprenant, ProgressionModule, ProgressionSequence, HistoriqueActivite
        self._log('Progression des apprenants...')

        content_by_cours = {cc['cours'].pk: cc for cc in content}
        bloc_progress_bulk = []
        seq_progress_bulk = []
        mod_progress_bulk = []
        cours_progress_bulk = []
        seen_bp = set()
        seen_sp = set()
        seen_mp = set()
        seen_cp = set()

        for cd in cours_data:
            cours = cd['cours']
            inst_id = cd['inst'].id
            apprenants = users['apprenants_by_inst'].get(inst_id, [])
            groupe_apps = [a for a in apprenants if a.groupe_id == cours.groupe_id]
            if not groupe_apps:
                groupe_apps = random.sample(apprenants, min(15, len(apprenants)))

            cc = content_by_cours.get(cours.pk)
            if not cc:
                continue

            all_blocs = [b for mc in cc['modules'] for sc in mc['sequences'] for b in sc['blocs']]
            all_seqs = [sc['sequence'] for mc in cc['modules'] for sc in mc['sequences']]
            all_mods = [mc['module'] for mc in cc['modules']]

            for app in groupe_apps:
                # Profil de l'étudiant : completeness entre 0.0 et 1.0
                if cd['is_active']:
                    completion = random.uniform(0.1, 0.9)
                else:
                    completion = random.uniform(0.5, 1.0)

                n_blocs_done = int(len(all_blocs) * completion)
                blocs_done = random.sample(all_blocs, n_blocs_done)

                for bloc in blocs_done:
                    key = (app.pk, bloc.pk)
                    if key not in seen_bp:
                        seen_bp.add(key)
                        bloc_progress_bulk.append(BlocProgress(
                            apprenant=app, bloc=bloc, est_termine=True,
                        ))

                n_seqs_done = int(len(all_seqs) * completion)
                for seq in all_seqs[:n_seqs_done]:
                    key = (app.pk, seq.pk)
                    if key not in seen_sp:
                        seen_sp.add(key)
                        seq_progress_bulk.append(SequenceProgress(
                            apprenant=app, sequence=seq, est_termine=True,
                        ))

                n_mods_done = int(len(all_mods) * completion)
                for mod in all_mods[:n_mods_done]:
                    key = (app.pk, mod.pk)
                    if key not in seen_mp:
                        seen_mp.add(key)
                        mod_progress_bulk.append(ModuleProgress(
                            apprenant=app, module=mod, est_termine=True,
                        ))

                cours_done = completion >= 0.95
                key = (app.pk, cours.pk)
                if key not in seen_cp:
                    seen_cp.add(key)
                    cours_progress_bulk.append(CoursProgress(
                        apprenant=app, cours=cours, est_termine=cours_done,
                    ))

                # ProgressionApprenant
                try:
                    ProgressionApprenant.objects.get_or_create(
                        apprenant=app, cours=cours,
                        defaults={
                            'pourcentage_completion': round(completion * 100, 1),
                            'statut': 'termine' if cours_done else ('en_cours' if completion > 0 else 'non_commence'),
                            'temps_total_minutes': int(completion * 300),
                        },
                    )
                except Exception:
                    pass

        BlocProgress.objects.bulk_create(bloc_progress_bulk, ignore_conflicts=True)
        SequenceProgress.objects.bulk_create(seq_progress_bulk, ignore_conflicts=True)
        ModuleProgress.objects.bulk_create(mod_progress_bulk, ignore_conflicts=True)
        CoursProgress.objects.bulk_create(cours_progress_bulk, ignore_conflicts=True)
        self._log(f'  {len(bloc_progress_bulk)} BlocProgress, {len(seq_progress_bulk)} SequenceProgress')

    # ─── ANALYTICS ───────────────────────────────────────────────────────────

    def _seed_analytics(self, cours_data, content, users):
        from analytics.models import (
            BlocAnalytics, BlocAnalyticsSummary, LearningEvent,
            LearnerProfile, SkillMasteryScore, KnowledgeGap, DropoutAlert,
        )
        self._log('Analytics et profils apprenants...')
        import datetime as dt

        content_by_cours = {cc['cours'].pk: cc for cc in content}
        events_bulk = []
        summaries_bulk = []
        profiles_bulk = []
        skills_bulk = []
        gaps_bulk = []
        alerts_bulk = []

        all_apprenants = users['apprenants']
        existing_profiles = set(LearnerProfile.objects.values_list('apprenant_id', flat=True))

        # LearnerProfile pour tous les apprenants
        for app in all_apprenants:
            if app.pk in existing_profiles:
                continue
            profile_data = self._profile_weights()
            profiles_bulk.append(LearnerProfile(
                apprenant=app,
                score_engagement=round(profile_data[1] + random.uniform(-0.1, 0.1), 2),
                score_regularite=round(profile_data[2] + random.uniform(-0.1, 0.1), 2),
                score_risque_decrochage=round(profile_data[3] + random.uniform(-0.1, 0.1), 2),
                profil_type=profile_data[4],
            ))

        LearnerProfile.objects.bulk_create(profiles_bulk, ignore_conflicts=True)

        # Analytics par cours
        for cd in cours_data[:min(len(cours_data), 30)]:  # Limiter pour perfs
            cours = cd['cours']
            inst_id = cd['inst'].id
            apprenants = users['apprenants_by_inst'].get(inst_id, [])
            groupe_apps = [a for a in apprenants if a.groupe_id == cours.groupe_id]
            if not groupe_apps:
                groupe_apps = random.sample(apprenants, min(10, len(apprenants)))

            cc = content_by_cours.get(cours.pk)
            if not cc:
                continue

            all_blocs = [b for mc in cc['modules'] for sc in mc['sequences'] for b in sc['blocs']]
            all_seqs = [sc['sequence'] for mc in cc['modules'] for sc in mc['sequences']]

            annee_data = cd['annee_data']
            year_start = dt.datetime.combine(annee_data['start'], dt.time(8, 0))
            year_end = dt.datetime.combine(
                min(annee_data['end'], date.today()),
                dt.time(22, 0),
            )
            if year_start >= year_end:
                continue

            for app in groupe_apps[:10]:  # 10 apprenants max par cours pour perf
                profile = next((p for p in profiles_bulk if p.apprenant_id == app.pk), None)
                engagement = getattr(profile, 'score_engagement', 0.6) if profile else 0.6

                # LearningEvents
                n_events = int(engagement * 30) + random.randint(0, 10)
                span = (year_end - year_start).total_seconds()
                for _ in range(n_events):
                    ts = timezone.make_aware(
                        year_start + dt.timedelta(seconds=random.uniform(0, span))
                    )
                    evt_type = random.choices(
                        ['bloc_opened', 'bloc_completed', 'sequence_completed', 'quiz_submitted', 'login'],
                        weights=[30, 25, 20, 15, 10]
                    )[0]
                    events_bulk.append(LearningEvent(
                        apprenant=app,
                        session_id=f"sess_{app.pk}_{random.randint(1000, 9999)}",
                        event_type=evt_type,
                        ts=ts,
                        payload={'cours_id': cours.pk, 'institution_id': inst_id},
                    ))

                # BlocAnalyticsSummary
                for bloc in random.sample(all_blocs, min(5, len(all_blocs))):
                    nb_ouv = random.randint(1, 5)
                    nb_comp = random.randint(0, nb_ouv)
                    summaries_bulk.append(BlocAnalyticsSummary(
                        apprenant=app, bloc=bloc,
                        sequence=bloc.sequence,
                        module=bloc.sequence.module,
                        cours=cours,
                        nb_ouvertures=nb_ouv,
                        nb_completions=nb_comp,
                        duree_totale_sec=random.randint(nb_ouv * 60, nb_ouv * 900),
                        scroll_max_pct=random.randint(20, 100),
                    ))

                # SkillMasteryScore
                for seq in random.sample(all_seqs, min(3, len(all_seqs))):
                    score = random.uniform(0.3, 1.0) * engagement
                    niveau = 'non_acquis' if score < 0.4 else ('fragile' if score < 0.6 else ('maitrise' if score < 0.85 else 'expert'))
                    skills_bulk.append(SkillMasteryScore(
                        apprenant=app, sequence=seq, cours=cours,
                        score=round(score, 2), niveau=niveau,
                        tendance=random.choice(['hausse', 'stable', 'stable', 'baisse']),
                    ))

                # KnowledgeGap pour les apprenants en difficulté
                if engagement < 0.4 and all_seqs:
                    gap_seq = random.choice(all_seqs)
                    severity = random.choice(['moderee', 'critique'])
                    gaps_bulk.append(KnowledgeGap(
                        apprenant=app, sequence=gap_seq,
                        severity=severity, statut='detectee',
                        description=f"Lacune détectée en {gap_seq.titre[:50]}",
                    ))

                # DropoutAlert
                if engagement < 0.25:
                    alerts_bulk.append(DropoutAlert(
                        apprenant=app, cours=cours,
                        alert_type='inactivite',
                        score_risque=round(1.0 - engagement, 2),
                        message=f"Apprenant inactif depuis plus de 14 jours dans {cours.titre[:40]}",
                        statut='active',
                    ))

        LearningEvent.objects.bulk_create(events_bulk, ignore_conflicts=True)
        BlocAnalyticsSummary.objects.bulk_create(summaries_bulk, ignore_conflicts=True)
        SkillMasteryScore.objects.bulk_create(skills_bulk, ignore_conflicts=True)
        KnowledgeGap.objects.bulk_create(gaps_bulk, ignore_conflicts=True)
        DropoutAlert.objects.bulk_create(alerts_bulk, ignore_conflicts=True)
        self._log(f'  {len(events_bulk)} events, {len(summaries_bulk)} summaries, {len(gaps_bulk)} gaps, {len(alerts_bulk)} alertes')

    # ─── GAMIFICATION ────────────────────────────────────────────────────────

    def _seed_gamification(self, users):
        from gamification.models import (
            Badge, UserBadge, UserLevel, Streak, XPTransaction, Mission, UserMission,
            LEVEL_THRESHOLDS, LEVEL_TITLES, XP_TABLE,
        )
        import datetime as dt
        self._log('Gamification (badges, XP, streaks)...')

        # Badges
        badges = {}
        for bd in BADGE_DEFINITIONS:
            badge, _ = Badge.objects.get_or_create(
                code=bd['code'],
                defaults={
                    'nom': bd['nom'], 'description': bd['description'],
                    'categorie': bd['categorie'], 'rarete': bd['rarete'],
                    'icone': bd['icone'], 'xp_bonus': bd['xp_bonus'],
                    'est_actif': True, 'conditions': {},
                },
            )
            badges[bd['code']] = badge

        # Missions
        missions = []
        for md in MISSION_DEFINITIONS:
            import datetime as dt2
            expire = timezone.now() + dt.timedelta(days=7 if md['type'] == 'hebdomadaire' else (30 if md['type'] == 'mensuelle' else 1))
            mission, _ = Mission.objects.get_or_create(
                titre=md['titre'],
                defaults={
                    'description': f"Mission : {md['titre']}",
                    'type_mission': md['type'],
                    'difficulte': md['difficulte'],
                    'action': md['action'],
                    'quantite': md['quantite'],
                    'xp_recompense': md['xp'],
                    'est_active': True,
                },
            )
            missions.append(mission)

        xp_transactions_bulk = []
        user_badges_bulk = []
        levels_bulk = []
        streaks_bulk = []
        user_missions_bulk = []

        existing_levels = set(UserLevel.objects.values_list('apprenant_id', flat=True))
        existing_streaks = set(Streak.objects.values_list('apprenant_id', flat=True))

        for app in users['apprenants']:
            # XP total simulé selon profil
            base_xp = random.choices(
                [random.randint(50, 300), random.randint(300, 2000), random.randint(2000, 10000), random.randint(10000, 50000)],
                weights=[20, 35, 30, 15]
            )[0]

            # Niveau
            niveau = 1
            for lvl in sorted(LEVEL_THRESHOLDS.keys()):
                if base_xp >= LEVEL_THRESHOLDS[lvl]:
                    niveau = lvl

            if app.pk not in existing_levels:
                levels_bulk.append(UserLevel(
                    apprenant=app, xp_total=base_xp,
                    xp_semaine=random.randint(0, min(base_xp, 500)),
                    niveau=niveau, titre=LEVEL_TITLES[niveau],
                ))

            # XP Transactions (quelques-unes)
            n_tx = random.randint(3, 12)
            sources = list(XP_TABLE.keys())
            for _ in range(n_tx):
                src = random.choice(sources)
                xp_val = XP_TABLE[src]
                xp_transactions_bulk.append(XPTransaction(
                    apprenant=app, source=src,
                    xp=xp_val, multiplicateur=1.0,
                    description=f"XP gagné pour {src}",
                ))

            # Streak
            if app.pk not in existing_streaks:
                streak_actuel = random.randint(0, 45)
                streaks_bulk.append(Streak(
                    apprenant=app,
                    streak_actuel=streak_actuel,
                    streak_max=max(streak_actuel, random.randint(0, 90)),
                    derniere_activite=date.today() - timedelta(days=random.randint(0, 3)),
                    protections_dispo=random.randint(0, 2),
                ))

            # Badges
            n_badges_earned = random.randint(0, 5)
            badge_list = list(badges.values())
            for badge in random.sample(badge_list, min(n_badges_earned, len(badge_list))):
                user_badges_bulk.append(UserBadge(
                    apprenant=app, badge=badge, est_affiche=True,
                ))

            # UserMissions
            if missions:
                for mission in random.sample(missions, min(2, len(missions))):
                    cible = mission.quantite
                    progression = random.randint(0, cible)
                    statut = 'completee' if progression >= cible else random.choice(['active', 'active', 'expiree'])
                    expire_le = timezone.now() + timedelta(days=random.randint(1, 7))
                    user_missions_bulk.append(UserMission(
                        apprenant=app, mission=mission,
                        statut=statut, progression=progression,
                        cible=cible, expire_le=expire_le,
                    ))

        UserLevel.objects.bulk_create(levels_bulk, ignore_conflicts=True)
        Streak.objects.bulk_create(streaks_bulk, ignore_conflicts=True)
        XPTransaction.objects.bulk_create(xp_transactions_bulk, ignore_conflicts=True)
        UserBadge.objects.bulk_create(user_badges_bulk, ignore_conflicts=True)
        UserMission.objects.bulk_create(user_missions_bulk, ignore_conflicts=True)

        self._log(f'  {len(levels_bulk)} niveaux, {len(xp_transactions_bulk)} XP transactions, {len(user_badges_bulk)} badges attribués')

    # ─── NOTIFICATIONS ───────────────────────────────────────────────────────

    def _seed_notifications(self, institutions, annees_map, cours_data, users):
        from notifications.models import Notification
        self._log('Notifications...')
        notifs_bulk = []

        notif_templates = [
            ('inscription_cours', 'moyenne', 'Inscription confirmée', 'Votre inscription au cours a été validée.'),
            ('evaluation_publiee', 'haute', 'Nouvelle évaluation disponible', 'Une évaluation vient d\'être publiée dans votre cours.'),
            ('session_a_venir', 'moyenne', 'Session à venir', 'Rappel : une session est prévue demain à 8h00.'),
            ('encouragement', 'basse', 'Bravo !', 'Vous avez complété une séquence. Continuez comme ça !'),
            ('cours_termine', 'haute', 'Cours terminé', 'Félicitations ! Vous avez terminé ce cours avec succès.'),
            ('absence_enregistree', 'haute', 'Absence enregistrée', 'Une absence a été enregistrée pour la dernière session.'),
        ]

        for app in random.sample(users['apprenants'], min(50, len(users['apprenants']))):
            n = random.randint(1, 8)
            for _ in range(n):
                t = random.choice(notif_templates)
                notifs_bulk.append(Notification(
                    recipient=app, type=t[0], priorite=t[1],
                    titre=t[2], message=t[3],
                    is_read=random.random() > 0.4,
                    statut_envoi='sent',
                ))

        Notification.objects.bulk_create(notifs_bulk, ignore_conflicts=True)
        self._log(f'  {len(notifs_bulk)} notifications créées')
