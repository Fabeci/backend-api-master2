#!/usr/bin/env python
"""
Seed script - Generation donnees test SOMAPRO
"""

import os, sys, random, datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from django.utils import timezone
from django.db import transaction

# Models
from academics.models import Institution, Pays, AnneeScolaire, Classe, Groupe, Departement, DomaineEtude, Filiere, Specialite, Matiere
from users.models import User, UserRole, Admin, Parent, Apprenant, Formateur, ResponsableAcademique, SuperAdmin
from courses.models import Cours, Module, Sequence, BlocContenu, RessourceSequence, InscriptionCours
from evaluations.models import Quiz, Evaluation, Question, Reponse, PassageQuiz, PassageEvaluation, ReponseQuestion
from progress.models import ProgressionApprenant, ProgressionModule, ProgressionSequence, ProgressionQuiz, HistoriqueActivite, PlanAction, ObjectifPlanAction
from collaborations.models import Conversation, Participant, Message, Forum, Commentaire
from feedback.models import Feedback
from resources.models import Ressource
from notifications.models import Notification

# ============================
# UTILITAIRES
# ============================

def rp(prefix, cur, tot, suffix=''):
    filled = int(50 * cur / tot)
    bar = '#' * filled + '-' * (50 - filled)
    sys.stdout.write(f'\r{prefix} |{bar}| {100*cur/tot:.1f}% {suffix}')
    sys.stdout.flush()

def rand_phone():
    return f"+2217{random.randint(1000000,9999999)}"

def fake_word():
    mots = ["formation","cours","module","sequence","bloc","video","texte","html","python","java","web","api","data","code","algo","reseau","securite","design","mobile","server","client","frontend","backend","dev","test","agile","projet","equipe","innovation"]
    return random.choice(mots)

def fake_sentence():
    words = [fake_word().capitalize() for _ in range(random.randint(4,8))]
    return ' '.join(words) + '.'

def fake_text(n):
    return ' '.join([fake_word() for _ in range(n//5+2)])[:n]

def create_user(email, role, **kw):
    role_obj,_ = UserRole.objects.get_or_create(name=role)
    pwd = "password123"
    user = User.objects.create_user(email=email, password=pwd, role=role_obj, **kw)
    user.is_active = True
    user.save()
    return user

# ============================
# CONFIG
# ============================
NB_INST = 2
NB_APPR = 20
NB_FORM = 6
NB_PARENTS = 10
NB_CLASSES = 2

# ============================
# MAIN
# ============================

# Nettoyage
print("=== Nettoyage base ===")
from django.apps import apps
models = list(apps.get_models())
total_objs = sum(m.objects.count() for m in models)
for i,m in enumerate(models):
    m.objects.all().delete()
    rp('Clean', i+1, len(models), f'({total_objs} obj)')
print(f"\n[OK] {total_objs} objets supprimes")

# Roles
print("\n=== Roles ===")
for r in ['Admin','Parent','Apprenant','Formateur','ResponsableAcademique','SuperAdmin']:
    UserRole.objects.get_or_create(name=r)
print("[OK] 6 roles")

# Pays
print("\n=== Pays ===")
pays_list = []
pays_data = [("Senegal","SN"),("Maroc","MA"),("Algerie","DZ"),("Tunisie","TN"),("CoteIvoire","CI")]
for nom,code in pays_data[:NB_INST]:
    p,_ = Pays.objects.get_or_create(code=code, defaults={'nom':nom})
    pays_list.append(p)
print(f"[OK] {len(pays_list)} pays")

# Institutions
print("\n=== Institutions ===")
insts = []
for i in range(NB_INST):
    inst = Institution.objects.create(
        nom=f"Inst {i+1}",
        pays=pays_list[i % len(pays_list)],
        email=f"inst{i+1}@test.sn",
        telephone_1=rand_phone(),
        nombre_etudiants=random.randint(100,500)
    )
    insts.append(inst)
print(f"[OK] {len(insts)} institutions")

# Annees
print("\n=== Annees ===")
annees = []
current = timezone.now().year
for i in range(2):
    a = AnneeScolaire.objects.create(
        institution=insts[i%len(insts)],
        annee_format_classique=f"{current+i}-{current+i+1}",
        date_debut=datetime.date(current+i,9,1),
        date_fin=datetime.date(current+i+1,6,30),
        est_active=(i==1)
    )
    annees.append(a)
print(f"[OK] {len(annees)} annees")

# Departements
print("\n=== Departements ===")
deps = []
for inst in insts:
    for nom in ["Info","Math"]:
        d = Departement.objects.create(nom=nom, institution=inst, responsable_academique=None, est_actif=True)
        deps.append(d)
print(f"[OK] {len(deps)} departements")

# Referentiels
print("\n=== Referentiels ===")
domaines = []
for dep in deps:
    dom = DomaineEtude.objects.create(nom="Dom Test", institution=dep.institution, departement=dep)
    domaines.append(dom)
filieres = []
for dom in domaines:
    f = Filiere.objects.create(nom="Fil Test", institution=dom.institution, domaine_etude=dom)
    filieres.append(f)
specs = []
for f in filieres:
    s = Specialite.objects.create(nom="Spec Test", institution=f.institution)
    specs.append(s)
mats = []
for inst in insts:
    for nom in ["Math","Physique","Info"]:
        m = Matiere.objects.create(nom=nom, institution=inst)
        mats.append(m)
print(f"[OK] {len(domaines)}D, {len(filieres)}F, {len(specs)}S, {len(mats)}M")

# ============================
# UTILISATEURS
# ===========================

def rand_phone(): return f"+2217{random.randint(1000000,9999999)}"

print("\n=== SuperAdmins ===")
for i in range(1):
    u = create_user(f"superadmin{i+1}@sma.pro","SuperAdmin",nom="Sup",prenom=f"Adm{i+1}",telephone=rand_phone(),is_staff=True,is_superuser=True)
    SuperAdmin.objects.create(user_ptr=u)
print(f"[OK] {SuperAdmin.objects.count()} SuperAdmin")

print("\n=== Admins ===")
for i,inst in enumerate(insts):
    u = create_user(f"admin{i+1}@sma.pro","Admin",nom="Admin",prenom=f"Inst{i+1}",telephone=rand_phone(),institution=inst,is_staff=True)
    Admin.objects.create(user_ptr=u, institution=inst)
print(f"[OK] {Admin.objects.count()} Admins")

print("\n=== Responsables ===")
for i,dep in enumerate(deps[:2]):
    u = create_user(f"resp{i+1}@sma.pro","ResponsableAcademique",nom="Resp",prenom=f"Ac{i+1}",telephone=rand_phone(),institution=dep.institution,departement=dep)
    ra = ResponsableAcademique.objects.create(user_ptr=u, departement=dep)
    dep.responsable_academique = ra
    dep.save()
print(f"[OK] {ResponsableAcademique.objects.count()} Responsables")

print("\n=== Formateurs ===")
formateurs = []
for i in range(NB_FORM):
    u = create_user(f"form{i+1}@sma.pro","Formateur",nom=random.choice(["Ndiaye","Diallo","Gueye"]),prenom=random.choice(["Mamadou","Ibrahima","Aissatou"]),telephone=rand_phone())
    f = Formateur.objects.create(user_ptr=u)
    if specs: f.specialites.set(random.sample(specs, min(2,len(specs))))
    formateurs.append(u)
    rp('Formateurs', i+1, NB_FORM)
print(f"\n[OK] {len(formateurs)} formateurs")

print("\n=== Parents ===")
parents = []
for i in range(NB_PARENTS):
    u = create_user(f"parent{i+1}@sma.pro","Parent",nom=random.choice(["Fall","Seck"]),prenom=random.choice(["Fatou","Mariama"]),telephone=rand_phone())
    Parent.objects.create(user_ptr=u, institution=random.choice(insts))
    parents.append(u)
    rp('Parents', i+1, NB_PARENTS)
print()

print("\n=== Apprenants ===")
apprenants = []
for i in range(NB_APPR):
    u = create_user(f"app{i+1}@sma.pro","Apprenant",nom=random.choice(["Sow","Diop"]),prenom=random.choice(["Moussa","Awa"]),telephone=rand_phone())
    a = Apprenant.objects.create(
        user_ptr=u,
        matricule=f"APP-{timezone.now().strftime('%y')}{random.randint(100,999)}",
        date_naissance=timezone.now().date() - datetime.timedelta(days=365*18),
        tuteur=random.choice(parents) if parents else None
    )
    apprenants.append(u)
    rp('Apprenants', i+1, NB_APPR)
print()

# Classes et groupes
print("\n=== Classes & Groupes ===")
classes = []
for inst in insts:
    for annee in annees:
        for i in range(NB_CLASSES):
            c = Classe.objects.create(nom=f"Classe {i+1}", institution=inst, annee_scolaire=annee)
            classes.append(c)
groupes = []
for c in classes:
    for g in ['A','B']:
        grp = Groupe.objects.create(nom=f"Grp {g}", institution=c.institution, annee_scolaire=c.annee_scolaire, classe=c)
        groupes.append(grp)
print(f"[OK] {len(classes)} classes, {len(groupes)} groupes")

# Inscriptions
print("\n=== Inscriptions ===")
for app in apprenants:
    grp = random.choice(groupes)
    InscriptionCours.objects.create(
        apprenant=app,
        institution=grp.institution,
        annee_scolaire=grp.annee_scolaire,
        classe=grp.classe,
        statut='actif',
        statut_paiement='paye'
    )
print(f"[OK] {len(apprenants)} inscriptions")

# ============================
# COURS ET CONTENU
# ============================

print("\n=== Cours & Contenu ===")
cours_list = []
for form in formateurs:
    nb_c = random.randint(1,2)
    for i in range(nb_c):
        grp = random.choice(groupes)
        mat = random.choice(mats)
        c = Cours.objects.create(
            titre=f"Cours {i+1}",
            groupe=grp,
            enseignant=form,
            matiere=mat,
            volume_horaire=random.randint(20,40)*60,
            statut='en_cours',
            institution=grp.institution,
            annee_scolaire=grp.annee_scolaire
        )
        if grp.classe.filieres.exists():
            f = grp.classe.filieres.first()
            if f and f.domaine_etude and f.domaine_etude.departement:
                c.departement = f.domaine_etude.departement
                c.save()
        cours_list.append(c)
        
        # Modules, sequences, blocs
        for jm in range(2):
            mod = Module.objects.create(titre=f"Mod {jm+1}", cours=c, institution=c.institution, annee_scolaire=c.annee_scolaire)
            for ks in range(2):
                seq = Sequence.objects.create(titre=f"Seq {ks+1}", module=mod, institution=c.institution, annee_scolaire=c.annee_scolaire)
                for kb in range(3):
                    BlocContenu.objects.create(
                        sequence=seq,
                        titre=f"Bloc {kb+1}",
                        type_bloc=random.choice(['texte','html']),
                        ordre=kb,
                        contenu_texte=fake_text(100),
                        duree_estimee_minutes=10,
                        est_visible=True
                    )
                RessourceSequence.objects.create(sequence=seq, titre="Res", description="doc", fichier=None, type_ressource='pdf')
    rp('Cours', formateurs.index(form)+1, len(formateurs))
print(f"\n[OK] {len(cours_list)} cours")

# Evaluations
print("\n=== Evaluations ===")
ev_c = 0
for c in cours_list:
    for i in range(2):
        ev = Evaluation.objects.create(
            cours=c,
            enseignant=c.enseignant,
            titre=f"Eval {i+1}",
            type_evaluation='structuree',
            bareme=20.0,
            consigne_texte=fake_text(100),
            est_publiee=True
        )
        ev_c += 1
        for qi in range(3):
            q = Question.objects.create(
                evaluation=ev,
                type_question='choix_unique',
                enonce_texte=fake_text(80),
                mode_correction='automatique',
                points=2,
                ordre=qi
            )
            for rj in range(3):
                Reponse.objects.create(question=q, texte=fake_sentence(), est_correcte=(rj==0), ordre=rj)
print(f"[OK] {ev_c} evaluations")

# Quizzes
print("\n=== Quizzes ===")
qz_c = 0
for seq in Sequence.objects.all():
    if random.random()>0.5:
        qz = Quiz.objects.create(titre=f"Quiz", sequence=seq, description=fake_text(80))
        qz_c += 1
        for qi in range(5):
            q = Question.objects.create(quiz=qz, type_question='choix_unique', enonce_texte=fake_text(80), mode_correction='automatique', points=1, ordre=qi)
            for rj in range(3):
                Reponse.objects.create(question=q, texte=fake_sentence(), est_correcte=(rj==0), ordre=rj)
print(f"[OK] {qz_c} quizzes")

# Progressions
print("\n=== Progressions & Activites ===")
prog_c = 0
for app in apprenants:
    for c in random.sample(cours_list, min(2, len(cours_list))):
        prog = ProgressionApprenant.objects.create(
            apprenant=app,
            cours=c,
            pourcentage_completion=random.uniform(10,100),
            temps_total_minutes=random.randint(30,300),
            statut=random.choice(['en_cours','termine']),
            note_moyenne_evaluations=random.uniform(8,18) if random.random()>0.4 else None
        )
        prog_c += 1
        # Modules
        for mod in c.modules.all()[:2]:
            pm = ProgressionModule.objects.create(progression_apprenant=prog, module=mod, est_termine=random.random()>0.5, pourcentage_completion=random.uniform(0,100))
            for seq in mod.sequences.all()[:2]:
                ProgressionSequence.objects.create(progression_module=pm, sequence=seq, est_terminee=random.random()>0.4, pourcentage_completion=random.uniform(0,100))
        # Historique
        for k in range(5):
            HistoriqueActivite.objects.create(apprenant=app, type_activite='consultation_cours', duree_minutes=random.randint(5,30), description=fake_sentence())
        # Plans
        if random.random()>0.6:
            plan = PlanAction.objects.create(apprenant=app, cours=c, titre=f"Plan", description=fake_text(80), priorite='moyenne')
            for oi in range(2):
                ObjectifPlanAction.objects.create(plan_action=plan, titre=f"Obj {oi+1}", description=fake_text(50))
    rp('Prog', apprenants.index(app)+1, len(apprenants))
print(f"\n[OK] {prog_c} progressions")

# Feedbacks
print("\n=== Feedbacks ===")
fb_c = 0
for c in cours_list[:10]:
    for i in range(2):
        Feedback.objects.create(cours=c, auteur=random.choice(apprenants), contenu=fake_text(100), note=random.uniform(3,5))
        fb_c += 1
print(f"[OK] {fb_c} feedbacks")

# Conversations
print("\n=== Conversations ===")
for i in range(5):
    conv = Conversation.objects.create(sujet=fake_sentence())
    parts = random.sample(list(User.objects.all()), 3)
    for u in parts:
        Participant.objects.create(user=u, conversation=conv)
    for j in range(3):
        Message.objects.create(conversation=conv, envoyeur=random.choice(parts), contenu=fake_text(50))
print(f"[OK] {Conversation.objects.count()} conversations")

# Forums
print("\n=== Forums ===")
for c in cours_list[:10]:
    f = Forum.objects.create(titre=f"Forum", description=fake_text(70), cours=c, auteur=random.choice(formateurs))
    for k in range(4):
        Commentaire.objects.create(forum=f, auteur=random.choice(apprenants), contenu=fake_text(80))
print(f"[OK] {Forum.objects.count()} forums")

# Notifications
print("\n=== Notifications ===")
notif_c = 0
for u in User.objects.all():
    for i in range(random.randint(0,3)):
        Notification.objects.create(recipient=u, type='inscription_cours', priorite='moyenne', canal='in_app', titre=fake_sentence(), message=fake_text(50), institution=u.institution)
        notif_c += 1
print(f"[OK] {notif_c} notifications")

# ============================
# RESUME
# ============================
print("\n========== TERMINE ==========")
from django.db import connection
with connection.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    print(f"Tables: {cur.fetchone()[0]}")
for m in apps.get_models():
    cnt = m.objects.count()
    if cnt>0:
        print(f"  {m._meta.verbose_name_plural.title()}: {cnt}")

print("\nComptes (mdp: password123):")
print("  superadmin1@sma.pro")
print("  admin1@sma.pro   (2 admins)")
print("  resp1@sma.pro    (2 resp)")
print("  form1-6@sma.pro  (6 formateurs)")
print("  parent1-10@sma.pro (10 parents)")
print("  app1-20@sma.pro  (20 apprenants)")
