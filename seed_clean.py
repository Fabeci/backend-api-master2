#!/usr/bin/env python
"""
Seed script final - Genere toutes les donnees de test
"""

import os, sys, random, datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from django.utils import timezone
from django.db import transaction
from django.core.files.base import ContentFile

from academics.models import Institution, Pays, AnneeScolaire, Classe, Groupe, Departement, DomaineEtude, Filiere, Specialite, Matiere
from users.models import User, UserRole, Admin, Parent, Apprenant, Formateur, ResponsableAcademique, SuperAdmin
from courses.models import Cours, Module, Sequence, BlocContenu, RessourceSequence, Session, InscriptionCours, Participation
from evaluations.models import Quiz, Evaluation, Question, Reponse, PassageQuiz, PassageEvaluation, ReponseQuestion
from progress.models import ProgressionApprenant, ProgressionModule, ProgressionSequence, HistoriqueActivite, PlanAction, ObjectifPlanAction
from collaborations.models import Conversation, Participant, Message, Forum, Commentaire
from feedback.models import Feedback
from resources.models import Ressource
from notifications.models import Notification

# =============================
# CONFIG
# =============================
NB_INST = 2
NB_APPR = 20
NB_FORM = 6
NB_PARENTS = 10
NB_CLASSES = 2

# =============================
# UTILITAIRES
# =============================
def rp(prefix, cur, tot, suffix=''):
    filled = int(50*cur/tot)
    bar = '#'*filled + '-'*(50-filled)
    sys.stdout.write(f'\r{prefix} |{bar}| {100*cur/tot:.1f}% {suffix}')
    sys.stdout.flush()

def rand_phone(): return f"+2217{random.randint(1000000,9999999)}"

def fake_word():
    return random.choice(["cours","module","seq","bloc","doc","video","texte","html","python","web","api","data","code","algo","reseau","securite","design","mobile","server","client","dev","test","proj","equipe","collab","innov"])

def fake_sentence():
    return ' '.join([fake_word().capitalize() for _ in range(random.randint(4,8))]) + '.'

def fake_text(n):
    return ' '.join([fake_word() for _ in range(n//5+2)])[:n]

def create_child(child_model, email, role_name, **kw):
    """Creer un utilisateur de type enfant (Admin, Formateur, etc.) directement."""
    role_obj = UserRole.objects.get(name=role_name)
    child = child_model(
        email=email,
        role=role_obj,
        is_active=True,
        is_staff=True,  # Tous les profils peuvent accéder à l'interface admin
        is_superuser=(role_name=='SuperAdmin'),
        **kw
    )
    child.set_password("password123")
    child.save()
    return child

# =============================
# NETTOYAGE
# =============================
print("=== Nettoyage ===")
from django.apps import apps
from django.db import connection

# Ordre de suppression inverse des dependances (parents apres enfants)
clean_order = [
    'notifications.Notification',
    'collaborations.Commentaire',
    'collaborations.Message',
    'collaborations.Conversation',
    'collaborations.Participant',
    'collaborations.Forum',
    'feedback.Feedback',
    'resources.Ressource',
    'progress.PlanAction',
    'progress.ObjectifPlanAction',
    'progress.HistoriqueActivite',
    'progress.ProgressionApprenant',
    'progress.ProgressionQuiz',
    'progress.ProgressionSequence',
    'progress.ProgressionModule',
    'evaluations.ReponseQuestion',
    'evaluations.Question',
    'evaluations.PassageQuiz',
    'evaluations.PassageEvaluation',
    'evaluations.Quiz',
    'evaluations.Evaluation',
    'courses.RessourceSequence',
    'courses.BlocContenu',
    'courses.Sequence',
    'courses.Module',
    'courses.Cours',
    'courses.InscriptionCours',
    'courses.Participation',
    'academics.Matiere',
    'academics.Specialite',
    'academics.Filiere',
    'academics.DomaineEtude',
    'academics.Classe',
    'academics.Groupe',
    'academics.Departement',
    'academics.AnneeScolaire',
    'users.Admin',
    'users.Parent',
    'users.Apprenant',
    'users.Formateur',
    'users.ResponsableAcademique',
    'users.SuperAdmin',
    'users.User',
    'academics.Institution',
    'academics.Pays',
    'users.UserRole',
]

models = []
for model_label in clean_order:
    try:
        app_label, model_name = model_label.split('.')
        model = apps.get_model(app_label, model_name)
        models.append(model)
    except LookupError:
        pass

total = sum(m.objects.count() for m in models)
for i,m in enumerate(models):
    count = m.objects.count()
    if count > 0:
        m.objects.all().delete()
    rp('Clean', i+1, len(models), f'({total})')
print(f"\n[OK] {total} supprimes")

# =============================
# ROLES & PAYS
# =============================
print("\n=== Roles ===")
for r in ['Admin','Parent','Apprenant','Formateur','ResponsableAcademique','SuperAdmin']:
    UserRole.objects.get_or_create(name=r)
print("[OK] 6 roles")

print("\n=== Pays ===")
pays_list = []
pays_data = [("Senegal","SN"),("Maroc","MA"),("Algerie","DZ"),("Tunisie","TN"),("CoteIvoire","CI")]
for nom,code in pays_data[:NB_INST]:
    p,_ = Pays.objects.get_or_create(code=code, defaults={'nom':nom})
    pays_list.append(p)
print(f"[OK] {len(pays_list)} pays")

# =============================
# INSTITUTIONS & ANNEES
# =============================
print("\n=== Institutions ===")
insts = []
for i in range(NB_INST):
    inst = Institution.objects.create(
        nom=f"Inst {i+1}",
        pays=pays_list[i],
        email=f"inst{i+1}@test.sn",
        telephone_1=rand_phone(),
        nombre_etudiants=random.randint(100,500)
    )
    insts.append(inst)
print(f"[OK] {len(insts)} institutions")

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

# =============================
# RESPONSABLES (avant departements)
# =============================
print("\n=== Responsables ===")
responsables = []
for i in range(2):
    ra = create_child(ResponsableAcademique, f"resp{i+1}@sma.pro", "ResponsableAcademique", nom="Resp", prenom=f"Ac{i+1}", telephone=rand_phone(), institution=insts[i%len(insts)])
    responsables.append(ra)
print(f"[OK] {len(responsables)} responsables")

# =============================
# DEPARTEMENTS
# =============================
print("\n=== Departements ===")
deps = []
for inst in insts:
    # Find responsable for this institution
    resp_inst = next((r for r in responsables if r.institution == inst), None)
    for nom in ["Info","Math"]:
        d = Departement.objects.create(nom=nom, institution=inst, responsable_academique=resp_inst, est_actif=True)
        deps.append(d)
print(f"[OK] {len(deps)} departements")

# =============================
# REFERENTIELS
# =============================
print("\n=== Referentiels ===")
domaines = []
for dep in deps:
    dom = DomaineEtude.objects.create(nom=f"Dom_{dep.nom}", institution=dep.institution, departement=dep)
    domaines.append(dom)
filieres = []
for dom in domaines:
    f = Filiere.objects.create(nom=f"Fil_{dom.nom}", institution=dom.institution, domaine_etude=dom)
    filieres.append(f)
specs = []
for f in filieres:
    s = Specialite.objects.create(nom=f"Spec_{f.nom}", institution=f.institution)
    specs.append(s)
mats = []
for inst in insts:
    for nom in ["Math","Physique","Info"]:
        mats.append(Matiere.objects.create(nom=nom, institution=inst))
print(f"[OK] {len(domaines)}D, {len(filieres)}F, {len(specs)}S, {len(mats)}M")

# =============================
# UTILISATEURS
# =============================
print("\n=== SuperAdmins ===")
for i in range(1):
    sa = create_child(SuperAdmin, f"superadmin{i+1}@sma.pro", "SuperAdmin", nom="Sup", prenom=f"Adm{i+1}", telephone=rand_phone())
print(f"[OK] {SuperAdmin.objects.count()} SuperAdmin")

print("\n=== Admins ===")
for i,inst in enumerate(insts):
    admin = create_child(Admin, f"admin{i+1}@sma.pro", "Admin", nom="Admin", prenom=f"Inst{i+1}", telephone=rand_phone(), institution=inst)
print(f"[OK] {Admin.objects.count()} Admins")

print("\n=== Formateurs ===")
formateurs = []
role_form = UserRole.objects.get(name="Formateur")
for i in range(NB_FORM):
    f = create_child(Formateur, f"form{i+1}@sma.pro", "Formateur", nom=random.choice(["Ndiaye","Diallo","Gueye","Fall","Seck"]), prenom=random.choice(["Mamadou","Ibrahima","Aissatou","Fatou"]), telephone=rand_phone())
    if specs: f.specialites.set(random.sample(specs, min(2,len(specs))))
    formateurs.append(f)  # store Formateur child object
    rp('Formateurs', i+1, NB_FORM)
print(f"\n[OK] {len(formateurs)} formateurs")

print("\n=== Parents ===")
parents = []
role_parent = UserRole.objects.get(name="Parent")
for i in range(NB_PARENTS):
    p = create_child(Parent, f"parent{i+1}@sma.pro", "Parent", nom=random.choice(["Fall","Seck","Diop"]), prenom=random.choice(["Fatou","Mariama","Awa"]), telephone=rand_phone(), institution=random.choice(insts))
    parents.append(p)
    rp('Parents', i+1, NB_PARENTS)
print()

print("\n=== Apprenants ===")
apprenants = []
role_app = UserRole.objects.get(name="Apprenant")
for i in range(NB_APPR):
    a = create_child(Apprenant, f"app{i+1}@sma.pro", "Apprenant",
                     nom=random.choice(["Sow","Diop","Gueye"]),
                     prenom=random.choice(["Moussa","Awa","Ibrahima"]),
                     telephone=rand_phone(),
                     matricule=f"APP-{timezone.now().strftime('%y')}{random.randint(100,999)}",
                     date_naissance=timezone.now().date() - datetime.timedelta(days=365*18),
                     tuteur=random.choice(parents) if parents else None)
    apprenants.append(a)
    rp('Apprenants', i+1, NB_APPR)
print()

# =============================
# CLASSES & GROUPES
# =============================
print("\n=== Classes & Groupes ===")
classes = []
for annee in annees:
    inst = annee.institution
    for i in range(NB_CLASSES):
        c = Classe.objects.create(nom=f"Classe {i+1}", institution=inst, annee_scolaire=annee)
        classes.append(c)
groupes = []
for c in classes:
    for g in ['A','B']:
        grp = Groupe.objects.create(nom=f"Grp {g}", institution=c.institution, annee_scolaire=c.annee_scolaire, classe=c)
        groupes.append(grp)
print(f"[OK] {len(classes)} classes, {len(groupes)} groupes")

# Inscriptions will be created after courses

# =============================
# COURS & CONTENU
# =============================
print("\n=== Cours ===")
cours_list = []
for form in formateurs:
    nb_c = 1  # one course per formateur to avoid duplicates
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
        # Departement via filiere
        if grp.classe.filieres.exists():
            f = grp.classe.filieres.first()
            if f and f.domaine_etude and f.domaine_etude.departement:
                c.departement = f.domaine_etude.departement
                c.save()
        cours_list.append(c)
        
        # Modules
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
                RessourceSequence.objects.create(sequence=seq, titre="Res", description="doc", fichier=ContentFile(b"dummy", name="dummy.txt"))
    rp('Cours', formateurs.index(form)+1, len(formateurs))
print(f"\n[OK] {len(cours_list)} cours")

# =============================
# INSCRIPTIONS
# =============================
print("\n=== Inscriptions ===")
insc_count = 0
for app in apprenants:
    # Each apprenant enrolls in 1-2 random courses
    for c in random.sample(cours_list, min(2, len(cours_list))):
        InscriptionCours.objects.create(
            apprenant=app,
            cours=c,
            statut=random.choice(['inscrit', 'en_cours', 'termine'])
        )
        insc_count += 1
print(f"[OK] {insc_count} inscriptions")

# Evaluations & Quizzes
print("\n=== Evaluations ===")
ev_c = 0
for c in cours_list:
    for i in range(2):
        ev = Evaluation.objects.create(cours=c, enseignant=c.enseignant, titre=f"Eval {i+1}", type_evaluation='structuree', bareme=20.0, consigne_texte=fake_text(100), est_publiee=True)
        ev_c += 1
        for qi in range(3):
            q = Question.objects.create(evaluation=ev, type_question='choix_unique', enonce_texte=fake_text(80), mode_correction='automatique', points=2, ordre=qi)
            for rj in range(3):
                Reponse.objects.create(question=q, texte=fake_sentence(), est_correcte=(rj==0), ordre=rj)
print(f"[OK] {ev_c} evaluations")

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

# Progressions & Activites
print("\n=== Progressions & Activites ===")
prog_c = 0
# Create a progression for each enrollment
for insc in InscriptionCours.objects.select_related('apprenant', 'cours').all():
    app = insc.apprenant
    c = insc.cours
    prog = ProgressionApprenant.objects.create(
        apprenant=app,
        cours=c,
        pourcentage_completion=random.uniform(10,100),
        temps_total_minutes=random.randint(30,300),
        statut=random.choice(['en_cours','termine']),
        note_moyenne_evaluations=random.uniform(8,18) if random.random()>0.4 else None
    )
    prog_c += 1
    for mod in c.modules.all()[:2]:
        pm = ProgressionModule.objects.create(progression_apprenant=prog, module=mod, est_termine=random.random()>0.5, pourcentage_completion=random.uniform(0,100))
        for seq in mod.sequences.all()[:2]:
            ProgressionSequence.objects.create(progression_module=pm, sequence=seq, est_terminee=random.random()>0.4, pourcentage_completion=random.uniform(0,100))
    for k in range(5):
        HistoriqueActivite.objects.create(apprenant=app, type_activite='consultation_cours', duree_minutes=random.randint(5,30), description=fake_sentence())
    if random.random()>0.6:
        plan = PlanAction.objects.create(apprenant=app, cours=c, titre="Plan", description=fake_text(80), priorite='moyenne')
        for oi in range(2):
            ObjectifPlanAction.objects.create(plan_action=plan, titre=f"Obj {oi+1}", description=fake_text(50))
print(f"\n[OK] {prog_c} progressions")

# Feedbacks, Conversations, Forums, Notifications
print("\n=== Feedbacks ===")
fb_c = 0
for c in cours_list[:10]:
    for i in range(2):
        Feedback.objects.create(cours=c, auteur=random.choice(apprenants), contenu=fake_text(100), note=random.uniform(3,5))
        fb_c += 1
print(f"[OK] {fb_c} feedbacks")

print("\n=== Conversations ===")
for i in range(5):
    conv = Conversation.objects.create(sujet=fake_sentence())
    parts = random.sample(list(User.objects.all()), 3)
    for u in parts:
        Participant.objects.create(user=u, conversation=conv)
    for j in range(3):
        Message.objects.create(conversation=conv, envoyeur=random.choice(parts), contenu=fake_text(50))
print(f"[OK] {Conversation.objects.count()} conversations")

print("\n=== Forums ===")
for c in cours_list[:10]:
    f = Forum.objects.create(titre=f"Forum", description=fake_text(70), cours=c, auteur=random.choice(formateurs))
    for k in range(4):
        Commentaire.objects.create(forum=f, auteur=random.choice(apprenants), contenu=fake_text(80))
print(f"[OK] {Forum.objects.count()} forums")

print("\n=== Notifications ===")
notif_c = 0
for u in User.objects.all():
    for i in range(random.randint(0,3)):
        Notification.objects.create(recipient=u, type='inscription_cours', priorite='moyenne', canal='in_app', titre=fake_sentence(), message=fake_text(50), institution=u.institution)
        notif_c += 1
print(f"[OK] {notif_c} notifications")

# =============================
# RESUME
# =============================
print("\n========== TERMINE ==========")
from django.db import connection
with connection.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    print(f"Tables: {cur.fetchone()[0]}")
for m in apps.get_models():
    cnt = m.objects.count()
    if cnt>0:
        print(f"  {m._meta.verbose_name_plural.title()}: {cnt}")

print("\nComptes tests (mdp: password123):")
print("  superadmin1@sma.pro")
print("  admin1@sma.pro")
print("  resp1@sma.pro")
print("  form1-6@sma.pro")
print("  parent1-10@sma.pro")
print("  app1-20@sma.pro")
