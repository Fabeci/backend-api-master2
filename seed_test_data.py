#!/usr/bin/env python
"""
Script de génération de données de test pour le projet SOMAPRO
Usage: python seed_test_data.py
"""

import os
import sys
import random
import datetime
from collections import defaultdict

# Setup Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from django.utils import timezone
from django.contrib.auth import get_user_model
from academics.models import (
    Institution, Pays, AnneeScolaire, Classe, Groupe,
    Departement, DomaineEtude, Filiere, Specialite, Matiere
)
from users.models import (
    User, UserRole, Admin, Parent, Apprenant, Formateur, ResponsableAcademique, SuperAdmin
)
from courses.models import Cours, Module, Sequence, BlocContenu, RessourceSequence, InscriptionCours
from evaluations.models import Quiz, Evaluation, Question, Reponse, PassageQuiz, PassageEvaluation, ReponseQuestion
from progress.models import (
    ProgressionApprenant, ProgressionModule, ProgressionSequence, ProgressionQuiz,
    HistoriqueActivite, PlanAction, ObjectifPlanAction
)
from collaborations.models import Conversation, Participant, Message, Forum, Commentaire
from feedback.models import Feedback
from resources.models import Ressource, RessourceSupplementaire
from notifications.models import Notification

from faker import Faker
import factory

fake = Faker('fr_FR')

# ============================================================================
# CONFIGURATION
# ============================================================================
NB_INSTITUTIONS = 3
NB_PAYS = 5
NB_ADMINS = 3
NB_PARENTS = 20
NB_APPRENANTS = 50
NB_FORMATEURS = 15
NB_RESPONSABLES = 5
NB_ANNEES_SCOLAIRES = 2
NB_CLASSES_PAR_INSTITUTION = 4
NB_GROUPES_PAR_CLASSE = 2
NB_COURS_PAR_FORMATEUR = 3
NB_MODULES_PAR_COURS = 4
NB_SEQUENCES_PAR_MODULE = 3
NB_BLOCS_PAR_SEQUENCE = 5
NB_QUESTIONS_PAR_QUIZ = 10
NB_REPONSES_PAR_QUESTION = 4
NB_EVALUATIONS_PAR_COURS = 2

# ============================================================================
# FACTORIES
# ============================================================================

class PaysFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Pays
    nom = factory.Faker('country')
    code = factory.LazyAttribute(lambda x: fake.country_code())

class InstitutionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Institution
    nom = factory.LazyAttribute(lambda x: f"{fake.company()} - {fake.word()}")
    pays = factory.Iterator(Pays.objects.all())
    adresse = factory.Faker('address')
    telephone_1 = factory.Faker('phone_number')
    email = factory.Faker('company_email')
    description = factory.Faker('text', max_nb_chars=200)
    type_institution = factory.Faker('random_element', elements=['Université', 'École', 'Centre de formation', 'Lycée'])
    nombre_etudiants = factory.Faker('random_int', min=100, max=5000)

class UserRoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserRole
    name = factory.Faker('random_element', elements=['Admin', 'Parent', 'Apprenant', 'Formateur', 'ResponsableAcademique', 'SuperAdmin'])

# ============================================================================
# UTILITAIRES
# ============================================================================

def random_date(start_date, end_date):
    """Génère une date aléatoire entre deux dates"""
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return start_date + datetime.timedelta(days=random_days)

def create_user(email, role_name, **kwargs):
    """Crée un utilisateur avec le rôle spécifié"""
    role, _ = UserRole.objects.get_or_create(name=role_name)
    user = User.objects.create_user(
        email=email,
        role=role,
        **kwargs
    )
    user.is_active = True
    user.save()
    return user

def progress_bar(current, total, prefix='', suffix='', length=50):
    """Affichage d'une barre de progression"""
    percent = f"{100 * (current / float(total)):.1f}"
    filled_length = int(length * current // total)
    bar = '█' * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()

# ============================================================================
# CRÉATEURS D'ENTITÉS
# ============================================================================

def create_pays(n=10):
    print(f"\n🌍 Création de {n} pays...")
    pays_list = []
    for i in range(n):
        p = PaysFactory()
        pays_list.append(p)
        progress_bar(i+1, n, prefix='Pays', suffix=f'({i+1}/{n})')
    print()
    return pays_list

def create_institutions(n=5):
    print(f"\n🏫 Création de {n} institutions...")
    insts = []
    for i in range(n):
        inst = InstitutionFactory()
        insts.append(inst)
        progress_bar(i+1, n, prefix='Institutions', suffix=f'({i+1}/{n})')
    print()
    return insts

def create_roles():
    print("\n🔐 Création des rôles utilisateur...")
    roles = [
        'Admin', 'Parent', 'Apprenant', 'Formateur',
        'ResponsableAcademique', 'SuperAdmin'
    ]
    for role_name in roles:
        UserRole.objects.get_or_create(name=role_name)
        print(f"  ✓ Rôle '{role_name}' créé")

def create_users():
    print("\n👥 Création des utilisateurs par profil...")
    
    # 1. SuperAdmins
    print("  🦸 SuperAdmins...")
    for i in range(2):
        create_user(
            email=f"superadmin{i+1}@sma.pro",
            role_name="SuperAdmin",
            nom=f"Super",
            prenom=f"Admin{i+1}",
            telephone=f"+221772{i:06d}",
            is_staff=True,
            is_superuser=True
        )
    print(f"    ✓ {2} SuperAdmin créés")

    # 2. Admins (un par institution)
    print("  👔 Admins...")
    insts = list(Institution.objects.all())
    for i, inst in enumerate(insts):
        create_user(
            email=f"admin{i+1}@sma.pro",
            role_name="Admin",
            nom=f"Admin",
            prenom=f"{inst.nom[:10]}",
            telephone=f"+221773{i:06d}",
            institution=inst,
            is_staff=True
        )
    print(f"    ✓ {len(insts)} Admins créés")

    # 3. Responsables Académiques
    print("  🎓 Responsables Académiques...")
    deps = Departement.objects.all()[:NB_RESPONSABLES]
    for i, dep in enumerate(deps):
        create_user(
            email=f"resp{i+1}@sma.pro",
            role_name="ResponsableAcademique",
            nom=f"Responsable",
            prenom=f"{dep.nom[:10]}{i+1}",
            telephone=f"+221774{i:06d}",
            institution=dep.institution,
            departement=dep
        )
    print(f"    ✓ {deps.count()} Responsables créés")

    # 4. Formateurs
    print("  👨‍🏫 Formateurs...")
    specialites = list(Specialite.objects.all())
    for i in range(NB_FORMATEURS):
        formateur = create_user(
            email=f"formateur{i+1}@sma.pro",
            role_name="Formateur",
            nom=fake.last_name(),
            prenom=fake.first_name(),
            telephone=f"+221775{i:06d}",
            is_staff=random.random() > 0.8
        )
        # Ajouter des spécialités
        if specialites:
            formateur.specialites.set(random.sample(specialites, min(3, len(specialites))))
        progress_bar(i+1, NB_FORMATEURS, prefix='Formateurs', suffix=f'({i+1}/{NB_FORMATEURS})')
    print()

    # 5. Parents
    print("  👨‍👩‍👧 Parents...")
    for i in range(NB_PARENTS):
        create_user(
            email=f"parent{i+1}@sma.pro",
            role_name="Parent",
            nom=fake.last_name(),
            prenom=fake.first_name(),
            telephone=f"+221776{i:06d}"
        )
    progress_bar(NB_PARENTS, NB_PARENTS, prefix='Parents')
    print()

    # 6. Apprenants
    print("  🎒 Apprenants...")
    parents = list(Parent.objects.all())
    classes = list(Classe.objects.all())
    for i in range(NB_APPRENANTS):
        parent = random.choice(parents) if parents else None
        classe = random.choice(classes) if classes else None
        apprenant = create_user(
            email=f"apprenant{i+1}@sma.pro",
            role_name="Apprenant",
            nom=fake.last_name(),
            prenom=fake.first_name(),
            telephone=f"+221777{i:06d}"
        )
        app = Apprenant.objects.get(pk=apprenant.pk)
        app.matricule = f"APP-{timezone.now().strftime('%y')}{random.randint(1000, 9999)}"
        app.date_naissance = random_date(
            timezone.now().date() - datetime.timedelta(days=365*25),
            timezone.now().date() - datetime.timedelta(days=365*15)
        )
        app.tuteur = parent
        app.save()
        
        # Inscription automatique
        if classe:
            annee_scolaire = AnneeScolaire.objects.filter(est_active=True).first()
            if annee_scolaire:
                InscriptionCours.objects.create(
                    apprenant=app,
                    institution=classe.institution,
                    annee_scolaire=annee_scolaire,
                    classe=classe,
                    statut='actif',
                    statut_paiement='en_attente'
                )
        progress_bar(i+1, NB_APPRENANTS, prefix='Apprenants', suffix=f'({i+1}/{NB_APPRENANTS})')
    print()

def create_academics():
    print("\n📚 Création de la structure académique...")
    
    # Départements
    print("  🏢 Départements...")
    insts = Institution.objects.all()
    noms_departements = ['Informatique', 'Mathématiques', 'Physique', 'Chimie', 'Biologie', 'Langues', 'Économie']
    for inst in insts:
        for j, nom in enumerate(noms_departements[:random.randint(3, 5)]):
            resp = random.choice(ResponsableAcademique.objects.filter(institution=inst)[:1])
            if resp:
                Departement.objects.create(
                    nom=nom,
                    institution=inst,
                    responsable_academique=resp
                )
    print(f"    ✓ {Departement.objects.count()} départements créés")

    # Domaines d'étude
    print("  🌍 Domaines d'étude...")
    for dep in Departement.objects.all():
        for k in range(random.randint(2, 4)):
            DomaineEtude.objects.create(
                nom=f"{fake.word().capitalize()} {fake.word().capitalize()}",
                institution=dep.institution,
                departement=dep
            )
    print(f"    ✓ {DomaineEtude.objects.count()} domaines créés")

    # Filieres
    print("  🎯 Filieres...")
    for domaine in DomaineEtude.objects.all():
        for k in range(random.randint(1, 3)):
            Filiere.objects.create(
                nom=f"{fake.word().capitalize()} {random.choice(['Licence', 'Master', 'Doctorat'])}",
                institution=domaine.institution,
                domaine_etude=domaine
            )
    print(f"    ✓ {Filiere.objects.count()} filières créées")

    # Specialités
    print("  🔬 Spécialités...")
    for filiere in Filiere.objects.all():
        for k in range(random.randint(1, 2)):
            Specialite.objects.create(
                nom=f"{fake.word().capitalize()} {fake.word().capitalize()}",
                institution=filiere.institution
            )
    print(f"    ✓ {Specialite.objects.count()} spécialités créées")

    # Matières
    print("  📖 Matières...")
    for dep in Departement.objects.all():
        for k in range(random.randint(5, 10)):
            Matiere.objects.create(
                nom=fake.catch_phrase(),
                institution=dep.institution
            )
    print(f"    ✓ {Matiere.objects.count()} matières créées")

def create_academics_structure():
    print("\n🏫 Création des classes et groupes...")
    
    annees = list(AnneeScolaire.objects.all())
    for inst in Institution.objects.all():
        for annee in annees:
            for i in range(NB_CLASSES_PAR_INSTITUTION):
                classe = Classe.objects.create(
                    nom=f"{random.choice(['L1', 'L2', 'L3', 'M1', 'M2'])} {fake.word().capitalize()}",
                    institution=inst,
                    annee_scolaire=annee,
                    description=fake.text(max_nb_chars=100)
                )
                # Ajouter des filières
                if Filiere.objects.filter(institution=inst).exists():
                    classe.filieres.set(random.sample(
                        list(Filiere.objects.filter(institution=inst)),
                        min(2, Filiere.objects.filter(institution=inst).count())
                    ))
                # Groupes
                for j in range(NB_GROUPES_PAR_CLASSE):
                    groupe = Groupe.objects.create(
                        nom=f"Groupe {chr(65+j)}",
                        institution=inst,
                        annee_scolaire=annee,
                        classe=classe,
                        description=fake.text(max_nb_chars=50)
                    )
    print(f"  ✓ {Classe.objects.count()} classes, {Groupe.objects.count()} groupes créés")

def create_courses():
    print("\n📝 Création des cours...")
    
    formateurs = list(Formateur.objects.all())
    groupes = list(Groupe.objects.all())
    matieres = list(Matiere.objects.all())
    annees = list(AnneeScolaire.objects.all())
    
    for formateur in formateurs:
        nb_cours = random.randint(1, NB_COURS_PAR_FORMATEUR)
        for i in range(nb_cours):
            groupe = random.choice(groupes)
            matiere = random.choice(matieres)
            annee = random.choice(annees)
            
            cours = Cours.objects.create(
                titre=f"{fake.word().capitalize()} - {matiere.nom[:30]}",
                groupe=groupe,
                enseignant=formateur,
                matiere=matiere,
                volume_horaire=random.randint(20, 60) * 60,  # en minutes
                date_debut=random_date(
                    timezone.now().date() - datetime.timedelta(days=180),
                    timezone.now().date() - datetime.timedelta(days=30)
                ),
                date_fin=random_date(
                    timezone.now().date() + datetime.timedelta(days=30),
                    timezone.now().date() + datetime.timedelta(days=180)
                ),
                statut=random.choice(['en_cours', 'planifie', 'termine']),
                institution=groupe.institution,
                annee_scolaire=annee,
                departement=groupe.classe.filieres.first().domaine_etude.departement if groupe.classe.filieres.exists() else None
            )
            
            # Créer modules, séquences, blocs
            create_course_content(cours)
            progress_bar(len(Cours.objects.all()), len(formateurs) * NB_COURS_PAR_FORMATEUR, 
                        prefix='Cours', suffix=f'({Cours.objects.count()})')
    print()

def create_course_content(cours):
    """Crée la structure complète d'un cours (modules, séquences, blocs)"""
    
    # Modules
    modules = []
    for i in range(NB_MODULES_PAR_COURS):
        module = Module.objects.create(
            titre=f"Module {i+1}: {fake.word().capitalize()}",
            cours=cours,
            description=fake.text(max_nb_chars=150),
            institution=cours.institution,
            annee_scolaire=cours.annee_scolaire
        )
        modules.append(module)
        
        # Séquences par module
        for j in range(NB_SEQUENCES_PAR_MODULE):
            sequence = Sequence.objects.create(
                titre=f"Séquence {j+1}: {fake.word().capitalize()}",
                module=module,
                institution=cours.institution,
                annee_scolaire=cours.annee_scolaire
            )
            
            # Blocs de contenu par séquence
            for k in range(NB_BLOCS_PAR_SEQUENCE):
                type_bloc = random.choice(['texte', 'html', 'markdown', 'video'])
                bloc = BlocContenu.objects.create(
                    sequence=sequence,
                    titre=f"Contenu {k+1}",
                    type_bloc=type_bloc,
                    ordre=k,
                    contenu_texte=fake.text(max_nb_chars=500) if type_bloc in ['texte', 'html'] else '',
                    contenu_html=f"<p>{fake.paragraph()}</p>" if type_bloc == 'html' else '',
                    contenu_markdown=fake.text(max_nb_chars=300) if type_bloc == 'markdown' else '',
                    video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ' if type_bloc == 'video' else '',
                    duree_estimee_minutes=random.randint(5, 30),
                    est_obligatoire=random.choice([True, False]),
                    est_visible=True
                )
                
                # Ressources associées
                if random.random() > 0.5:
                    RessourceSequence.objects.create(
                        sequence=sequence,
                        titre=f"Ressource {k+1}",
                        description=fake.text(max_nb_chars=100),
                        fichier=None,  # À remplir si nécessaire
                        type_ressource=random.choice(['document', 'pdf', 'presentation'])
                    )

def create_quizzes_and_evaluations():
    print("\n📊 Création des quizzes et évaluations...")
    
    sequences = list(Sequence.objects.all())
    formateurs = list(Formateur.objects.all())
    
    # Quizzes (un par séquence)
    print("  ❓ Quizzes...")
    for seq in sequences:
        if random.random() > 0.3:  # 70% des séquences ont un quiz
            quiz = Quiz.objects.create(
                titre=f"Quiz - {seq.titre[:30]}",
                sequence=seq,
                description=fake.text(max_nb_chars=200)
            )
            
            # Questions
            types_question = ['choix_unique', 'choix_multiple']
            for i in range(random.randint(5, 15)):
                question = Question.objects.create(
                    quiz=quiz,
                    type_question=random.choice(types_question),
                    enonce_texte=fake.paragraph(),
                    mode_correction='automatique',
                    points=random.choice([1, 2, 3, 5]),
                    ordre=i
                )
                
                # Réponses prédéfinies
                nb_correctes = 1 if question.type_question == 'choix_unique' else random.randint(1, 2)
                for j in range(random.randint(3, NB_REPONSES_PAR_QUESTION)):
                    Reponse.objects.create(
                        question=question,
                        texte=fake.sentence(),
                        est_correcte=(j < nb_correctes),
                        ordre=j
                    )
    
    print(f"    ✓ {Quiz.objects.count()} quizzes, {Question.objects.count()} questions créés")

    # Évaluations (par cours)
    print("  📝 Évaluations...")
    for cours in Cours.objects.all():
        formateur = cours.enseignant
        nb_evals = random.randint(1, NB_EVALUATIONS_PAR_COURS)
        for i in range(nb_evals):
            evaluation = Evaluation.objects.create(
                cours=cours,
                enseignant=formateur,
                titre=f"Évaluation {i+1} - {cours.titre[:30]}",
                type_evaluation=random.choice(['simple', 'structuree', 'mixte']),
                bareme=random.choice([10.0, 20.0, 50.0]),
                duree_minutes=random.choice([30, 45, 60, 90]),
                consigne_texte=fake.text(max_nb_chars=300),
                date_debut=random_date(timezone.now(), timezone.now() + datetime.timedelta(days=30)),
                date_fin=random_date(timezone.now() + datetime.timedelta(days=31), timezone.now() + datetime.timedelta(days=60)),
                est_publiee=True
            )
            
            if evaluation.type_evaluation in ['structuree', 'mixte']:
                # Ajouter questions
                types_q = ['choix_unique', 'choix_multiple', 'texte_court']
                for j in range(random.randint(3, 8)):
                    question = Question.objects.create(
                        evaluation=evaluation,
                        type_question=random.choice(types_q),
                        enonce_texte=fake.paragraph(),
                        mode_correction='automatique' if random.random() > 0.5 else 'manuelle',
                        points=random.choice([2, 5, 10]),
                        ordre=j
                    )
                    
                    if question.type_question in ['choix_unique', 'choix_multiple']:
                        for k in range(random.randint(3, 5)):
                            Reponse.objects.create(
                                question=question,
                                texte=fake.sentence(),
                                est_correcte=(k == 0),
                                ordre=k
                            )
    
    print(f"    ✓ {Evaluation.objects.count()} évaluations créées")

def create_progress_and_history():
    print("\n📈 Création des progressions et historique...")
    
    apprenants = list(Apprenant.objects.all())
    cours_list = list(Cours.objects.all())
    
    for apprenant in apprenants:
        # Inscriptions aux cours
        cours_pour_app = random.sample(cours_list, random.randint(2, 5))
        
        for cours in cours_pour_app:
            # Créer progression principale
            progression = ProgressionApprenant.objects.create(
                apprenant=apprenant,
                cours=cours,
                pourcentage_completion=random.uniform(0, 100),
                temps_total_minutes=random.randint(60, 600),
                statut=random.choice(['non_commence', 'en_cours', 'termine']),
                note_moyenne_evaluations=random.uniform(8, 18) if random.random() > 0.3 else None,
                taux_reussite_quiz=random.uniform(40, 95)
            )
            
            # Modules progressions
            for module in cours.modules.all()[:random.randint(1, 3)]:
                prog_module = ProgressionModule.objects.create(
                    progression_apprenant=progression,
                    module=module,
                    est_termine=random.random() > 0.5,
                    pourcentage_completion=random.uniform(0, 100),
                    temps_passe_minutes=random.randint(30, 180)
                )
                
                # Séquences progressions
                for sequence in module.sequences.all()[:random.randint(1, 2)]:
                    prog_seq = ProgressionSequence.objects.create(
                        progression_module=prog_module,
                        sequence=sequence,
                        est_terminee=random.random() > 0.4,
                        pourcentage_completion=random.uniform(0, 100),
                        temps_passe_minutes=random.randint(10, 60),
                        nombre_visites=random.randint(1, 10)
                    )
            
            # Quiz passés
            quizzes = Quiz.objects.filter(sequence__module__cours=cours)
            for quiz in quizzes[:random.randint(0, 2)]:
                passage = PassageQuiz.objects.create(
                    apprenant=apprenant,
                    quiz=quiz,
                    score=random.uniform(0, quiz.questions.count() * 5),
                    date_passage=random_date(
                        timezone.now() - datetime.timedelta(days=60),
                        timezone.now()
                    ),
                    termine=True
                )
                ProgressionQuiz.objects.create(
                    progression_apprenant=progression,
                    passage_quiz=passage,
                    score=passage.score,
                    pourcentage_reussite=random.uniform(50, 100)
                )
            
            # Évaluations passées
            evals = Evaluation.objects.filter(cours=cours)
            for evaluation in evals[:random.randint(0, 1)]:
                passage_eval = PassageEvaluation.objects.create(
                    apprenant=apprenant,
                    evaluation=evaluation,
                    statut=random.choice(['en_cours', 'soumis', 'corrige']),
                    date_debut=random_date(timezone.now() - datetime.timedelta(days=30), timezone.now() - datetime.timedelta(days=1)),
                    note=random.uniform(8, 19) if random.random() > 0.3 else None
                )
                
                # Réponses aux questions
                for question in evaluation.questions.all():
                    if random.random() > 0.2:
                        reponse = ReponseQuestion.objects.create(
                            passage_evaluation=passage_eval,
                            question=question,
                            statut=random.choice(['non_repondu', 'repondu', 'corrige']),
                            points_obtenus=question.points * random.uniform(0, 1) if question.points else 0
                        )
                        if question.type_question in ['choix_unique', 'choix_multiple']:
                            reponses_correctes = question.reponses_predefinies.filter(est_correcte=True)
                            if reponses_correctes.exists():
                                reponse.choix_selectionnes.set(random.sample(
                                    list(question.reponses_predefinies.all()),
                                    min(2, question.reponses_predefinies.count())
                                ))
            
            # Historique activité
            for k in range(random.randint(5, 20)):
                type_activite = random.choice([
                    'connexion', 'deconnexion', 'consultation_cours',
                    'consultation_sequence', 'debut_quiz', 'fin_quiz',
                    'debut_evaluation', 'soumission_evaluation'
                ])
                HistoriqueActivite.objects.create(
                    apprenant=apprenant,
                    type_activite=type_activite,
                    objet_type=random.choice(['cours', 'sequence', 'quiz', 'evaluation']),
                    objet_id=random.randint(1, 100),
                    date_activite=random_date(
                        timezone.now() - datetime.timedelta(days=90),
                        timezone.now()
                    ),
                    duree_minutes=random.randint(5, 120),
                    description=fake.sentence()
                )
            
            # Plans d'action
            for k in range(random.randint(0, 2)):
                plan = PlanAction.objects.create(
                    apprenant=apprenant,
                    cours=cours,
                    titre=fake.sentence(),
                    description=fake.text(max_nb_chars=200),
                    date_echeance=timezone.now().date() + datetime.timedelta(days=random.randint(7, 60)),
                    statut=random.choice(['a_faire', 'en_cours', 'termine']),
                    priorite=random.choice(['basse', 'moyenne', 'haute']),
                    cree_par=random.choice(list(User.objects.all()))
                )
                # Objectifs
                for l in range(random.randint(2, 5)):
                    ObjectifPlanAction.objects.create(
                        plan_action=plan,
                        titre=fake.sentence(),
                        description=fake.text(max_nb_chars=100),
                        ordre=l
                    )
    
    print(f"    ✓ {ProgressionApprenant.objects.count()} progressions, {HistoriqueActivite.objects.count()} historiques, {PlanAction.objects.count()} plans créés")

def create_feedback_and_collaborations():
    print("\n💬 Création de feedbacks et collaborations...")
    
    # Feedbacks
    print("  📝 Feedbacks...")
    apprenants = list(Apprenant.objects.all())
    for cours in Cours.objects.all():
        for i in range(random.randint(0, 3)):
            Feedback.objects.create(
                cours=cours,
                auteur=random.choice(apprenants),
                contenu=fake.paragraph(),
                note=random.uniform(3, 5)
            )
    print(f"    ✓ {Feedback.objects.count()} feedbacks créés")
    
    # Conversations
    print("  💭 Conversations...")
    for i in range(20):
        conv = Conversation.objects.create(sujet=fake.sentence())
        participants = random.sample(list(User.objects.all()), random.randint(2, 5))
        for user in participants:
            Participant.objects.create(user=user, conversation=conv)
        
        # Messages
        for j in range(random.randint(3, 10)):
            Message.objects.create(
                conversation=conv,
                envoyeur=random.choice(participants),
                contenu=fake.paragraph()
            )
    print(f"    ✓ {Conversation.objects.count()} conversations, {Message.objects.count()} messages créés")
    
    # Forums
    print("  🗨️ Forums...")
    for cours in Cours.objects.all()[:30]:
        forum = Forum.objects.create(
            titre=f"Forum - {cours.titre[:30]}",
            description=fake.text(max_nb_chars=200),
            cours=cours,
            auteur=random.choice(list(User.objects.all()))
        )
        # Commentaires
        for k in range(random.randint(5, 15)):
            Commentaire.objects.create(
                forum=forum,
                auteur=random.choice(list(User.objects.all())),
                contenu=fake.paragraph(),
                parent=random.choice(list(Commentaire.objects.filter(forum=forum))) if Commentaire.objects.filter(forum=forum).exists() else None
            )
    print(f"    ✓ {Forum.objects.count()} forums, {Commentaire.objects.count()} commentaires créés")

def create_notifications():
    print("\n🔔 Création des notifications...")
    
    types_notif = [
        'inscription_cours', 'evaluation_soumise', 'evaluation_corrigee',
        'cours_cree', 'module_ajoute', 'progression_faible',
        'session_a_venir', 'absence_enregistree', 'encouragement'
    ]
    
    for user in User.objects.all():
        nb_notif = random.randint(0, 10)
        for i in range(nb_notif):
            Notification.objects.create(
                recipient=user,
                sender=random.choice(list(User.objects.exclude(pk=user.pk))[:1]),
                type=random.choice(types_notif),
                priorite=random.choice(['basse', 'moyenne', 'haute', 'critique']),
                canal='in_app',
                titre=fake.sentence(),
                message=fake.paragraph(),
                is_read=random.random() > 0.5,
                institution=user.institution,
                annee_scolaire=AnneeScolaire.objects.filter(est_active=True).first()
            )
    print(f"    ✓ {Notification.objects.count()} notifications créées")

def create_resources():
    print("\n📁 Création de ressources...")
    
    sequences = list(Sequence.objects.all())
    apprenants = list(Apprenant.objects.all())
    
    for seq in sequences:
        for i in range(random.randint(1, 5)):
            Ressource.objects.create(
                sequence=seq,
                titre=f"Ressource {i+1}",
                description=fake.text(max_nb_chars=100),
                est_supplementaire=random.choice([True, False]),
                apprenant=random.choice(apprenants) if random.random() > 0.7 else None
            )
    print(f"    ✓ {Ressource.objects.count()} ressources créées")

# ============================================================================
# MAIN
# ============================================================================

def clean_database():
    """Supprime toutes les données existantes"""
    print("\n🧹 Nettoyage de la base de données...")
    
    # Ordre de suppression (respect contraintes FK)
    models_to_delete = [
        Notification, PreferenceNotification, DigestNotification,
        HistoriqueActivite, PlanAction, ObjectifPlanAction,
        ReponseQuestion, Reponse, Question, PassageEvaluation, PassageQuiz,
        ProgressionQuiz, ProgressionSequence, ProgressionModule, ProgressionApprenant,
        Suivi, BlocProgress, SequenceProgress, ModuleProgress, CoursProgress,
        RessourceSupplementaire, PieceJointe, RessourceSequence, Ressource,
        Commentaire, Forum, Message, Participant, Conversation,
        InscriptionCours, Feedback,
        Session, Participation, BlocContenu, SequenceContent, Sequence, Module, Cours,
        Inscription, Groupe, Classe, AnneeScolaire,
        Departement, Filiere, Specialite, Matiere, DomaineEtude,
        Apprenant, Formateur, Parent, Admin, ResponsableAcademique, SuperAdmin,
        User, UserRole, Institution, Pays
    ]
    
    total = sum([model.objects.count() for model in models_to_delete])
    for i, model in enumerate(models_to_delete):
        count = model.objects.count()
        if count > 0:
            model.objects.all().delete()
            progress_bar(i+1, len(models_to_delete), prefix='Nettoyage', suffix=f'({total} objets)')
        else:
            progress_bar(i+1, len(models_to_delete), prefix='Nettoyage', suffix='(0)')
    print(f"\n  ✓ Toutes les données supprimées ({total} objets)")

def main():
    print("="*70)
    print("🚀 GÉNÉRATION DE DONNÉES DE TEST - SOMAPRO")
    print("="*70)
    
    response = input("\n⚠️  Cette opération va EFFACER toutes les données existantes. Continuer ? (oui/non) : ")
    if response.lower() != 'oui':
        print("❌ Opération annulée.")
        return
    
    try:
        # 1. Nettoyage
        clean_database()
        
        # 2. Rôles
        create_roles()
        
        # 3. Pays
        create_pays(NB_PAYS)
        
        # 4. Institutions
        create_institutions(NB_INSTITUTIONS)
        
        # 5. Structure académique
        create_academics()
        create_academics_structure()
        
        # 6. Utilisateurs
        create_users()
        
        # 7. Cours + contenu
        create_courses()
        
        # 8. Quizzes & évaluations
        create_quizzes_and_evaluations()
        
        # 9. Progressions & historique
        create_progress_and_history()
        
        # 10. Feedbacks & collaborations
        create_feedback_and_collaborations()
        
        # 11. Notifications
        create_notifications()
        
        # 12. Ressources
        create_resources()
        
        print("\n" + "="*70)
        print("✅ GÉNÉRATION TERMINÉE !")
        print("="*70)
        print("\n📊 RÉSUMÉ:")
        print(f"  • Utilisateurs: {User.objects.count()}")
        print(f"  • Apprenants: {Apprenant.objects.count()}")
        print(f"  • Formateurs: {Formateur.objects.count()}")
        print(f"  • Cours: {Cours.objects.count()}")
        print(f"  • Modules: {Module.objects.count()}")
        print(f"  • Séquences: {Sequence.objects.count()}")
        print(f"  • Blocs: {BlocContenu.objects.count()}")
        print(f"  • Évaluations: {Evaluation.objects.count()}")
        print(f"  • Quiz: {Quiz.objects.count()}")
        print(f"  • Progressions: {ProgressionApprenant.objects.count()}")
        print(f"  • Notifications: {Notification.objects.count()}")
        print("\n🔗 Comptes de test:")
        print("  SuperAdmin: superadmin1@sma.pro / password123")
        print("  Admin: admin1@sma.pro / password123")
        print("  Formateur: formateur1@sma.pro / password123")
        print("  Apprenant: apprenant1@sma.pro / password123")
        print("  Parent: parent1@sma.pro / password123")
        
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
