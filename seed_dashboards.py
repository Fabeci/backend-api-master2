#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed des donnees pour remplir les tableaux de bord.
Utilise les comptes crees par create_test_accounts.py.
"""
import os, sys, random, datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from django.utils import timezone
from django.db import transaction

from users.models import User, Admin, Parent, Apprenant, Formateur, ResponsableAcademique, SuperAdmin
from academics.models import Institution, AnneeScolaire, Classe, Groupe, Departement, Matiere, Specialite
from courses.models import (
    Cours, Module, Sequence, BlocContenu, InscriptionCours, Session, Participation, Suivi
)
from evaluations.models import (
    Evaluation, Quiz, Question, Reponse, PassageEvaluation, ReponseQuestion, PassageQuiz
)
from progress.models import (
    ProgressionApprenant, ProgressionModule, ProgressionSequence, HistoriqueActivite,
    PlanAction, ObjectifPlanAction
)
from collaborations.models import Conversation, Participant, Message, Forum, Commentaire
from feedback.models import Feedback
from notifications.models import Notification
from analytics.models import BlocAnalytics, BlocAnalyticsSummary

def out(msg):
    sys.stdout.buffer.write((msg + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

def ok(msg):  out(f"  [OK] {msg}")
def section(t): out(f"\n{'='*55}\n  {t}\n{'='*55}")

def rand_delta(days_back_max=30):
    return timezone.now() - datetime.timedelta(
        days=random.randint(0, days_back_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )

@transaction.atomic
def run():
    # ─── Verification des comptes de test ─────────────────────────────
    section("Verification des comptes de test")
    try:
        superadmin = User.objects.get(email="superadmin@testlms.com")
        admin_user  = User.objects.get(email="admin@testlms.com")
        resp_user   = User.objects.get(email="responsable@testlms.com")
        form_user   = User.objects.get(email="formateur@testlms.com")
        parent_user = User.objects.get(email="parent@testlms.com")
        appr_user   = User.objects.get(email="apprenant@testlms.com")
    except User.DoesNotExist as e:
        out(f"  [ERREUR] Compte manquant : {e}")
        out("  Lancez d'abord : python create_test_accounts.py")
        return

    admin_obj  = Admin.objects.get(pk=admin_user.pk)
    resp_obj   = ResponsableAcademique.objects.get(pk=resp_user.pk)
    form_obj   = Formateur.objects.get(pk=form_user.pk)
    parent_obj = Parent.objects.get(pk=parent_user.pk)
    appr_obj   = Apprenant.objects.get(pk=appr_user.pk)

    inst  = admin_user.institution
    annee = admin_user.annee_scolaire_active
    groupe = appr_obj.groupe
    dep   = resp_obj.departement
    ok(f"Institution : {inst}")
    ok(f"Annee       : {annee}")
    ok(f"Groupe      : {groupe}")
    ok(f"Departement : {dep}")

    # ─── Rendre les comptes accessibles au dashboard admin ─────────────
    section("Activation is_staff pour acces aux dashboards")
    for u, label in [
        (parent_user, "Parent"),
        (appr_user,   "Apprenant"),
        (form_user,   "Formateur"),
        (resp_user,   "Responsable"),
    ]:
        if not u.is_staff:
            User.objects.filter(pk=u.pk).update(is_staff=True)
            ok(f"is_staff=True pour {label}")
        else:
            ok(f"is_staff deja True pour {label}")

    # ─── Matieres (une par cours, contrainte unique groupe+matiere+enseignant+annee) ─
    section("Matieres")
    mat_python, _ = Matiere.objects.get_or_create(nom="Langage Python", institution=inst)
    mat_sql,    _ = Matiere.objects.get_or_create(nom="Bases de Donnees", institution=inst)
    mat_web,    _ = Matiere.objects.get_or_create(nom="Developpement Web", institution=inst)
    ok(f"3 matieres pret : {mat_python}, {mat_sql}, {mat_web}")

    # ─── Cours (3 cours pour le groupe de l'apprenant) ─────────────────
    section("Cours")
    cours_data = [
        ("Introduction au Python",   mat_python, 15, "2025-09-01", "2026-01-31"),
        ("Bases de Donnees SQL",     mat_sql,    20, "2025-09-01", "2026-02-28"),
        ("Developpement Web",        mat_web,    18, "2026-01-15", "2026-06-30"),
    ]
    cours_list = []
    for titre, mat, vh, dd, df in cours_data:
        # La contrainte unique est sur (groupe, matiere, enseignant, annee_scolaire)
        c, created = Cours.objects.get_or_create(
            groupe=groupe,
            matiere=mat,
            enseignant=form_obj,
            annee_scolaire=annee,
            defaults=dict(
                titre=titre,
                institution=inst,
                volume_horaire=vh * 60,
                departement=dep,
                date_debut=datetime.date.fromisoformat(dd),
                date_fin=datetime.date.fromisoformat(df),
            )
        )
        cours_list.append(c)
        ok(f"{'Cree' if created else 'Existant'} : {c.titre}")

    # Attacher le formateur a l'institution (pour ses dashboards)
    form_obj.institutions.add(inst)
    form_obj.groupes.add(groupe)

    # ─── Modules + Sequences + Blocs ───────────────────────────────────
    section("Modules / Sequences / Blocs")
    for cours in cours_list:
        for mi in range(1, 3):
            mod, _ = Module.objects.get_or_create(
                titre=f"Module {mi} - {cours.titre[:20]}",
                cours=cours,
                defaults=dict(institution=inst, annee_scolaire=annee)
            )
            for si in range(1, 3):
                seq, _ = Sequence.objects.get_or_create(
                    titre=f"Sequence {si} - {mod.titre[:20]}",
                    module=mod,
                    defaults=dict(institution=inst, annee_scolaire=annee)
                )
                for bi in range(1, 4):
                    BlocContenu.objects.get_or_create(
                        sequence=seq,
                        titre=f"Bloc {bi}",
                        defaults=dict(
                            type_bloc='texte',
                            ordre=bi,
                            contenu_texte=f"Contenu pedagogique du bloc {bi} de la sequence {seq.titre}.",
                            duree_estimee_minutes=15,
                            est_visible=True,
                        )
                    )
    total_blocs = BlocContenu.objects.filter(sequence__module__cours__in=cours_list).count()
    ok(f"{len(cours_list)} cours, {total_blocs} blocs")

    # ─── InscriptionCours (normalement cree par signal) ────────────────
    section("Inscriptions cours")
    for cours in cours_list:
        InscriptionCours.objects.get_or_create(
            apprenant=appr_obj,
            cours=cours,
            defaults=dict(
                institution=inst,
                annee_scolaire=annee,
                statut='actif',
            )
        )
    ok(f"{InscriptionCours.objects.filter(apprenant=appr_obj).count()} inscriptions cours")

    # ─── Sessions de cours ─────────────────────────────────────────────
    section("Sessions de cours")
    nb_sessions = 0
    for cours in cours_list:
        for si in range(3):
            date_s = timezone.now() - datetime.timedelta(days=si * 7 + random.randint(1, 5))
            sess, created = Session.objects.get_or_create(
                titre=f"Session {si+1} - {cours.titre[:25]}",
                cours=cours,
                defaults=dict(
                    formateur=form_obj,
                    date_debut=date_s,
                    date_fin=date_s + datetime.timedelta(hours=2),
                    participation_mode=random.choice(['presentiel', 'distanciel']),
                    institution=inst,
                    annee_scolaire=annee,
                )
            )
            if created:
                nb_sessions += 1
                Participation.objects.get_or_create(
                    session=sess, apprenant=appr_obj,
                    defaults=dict(statut='present', source='manuelle', institution=inst, annee_scolaire=annee)
                )
    ok(f"{nb_sessions} nouvelles sessions creees")

    # ─── Evaluations ───────────────────────────────────────────────────
    section("Evaluations + Questions + Reponses")
    evaluations_list = []
    for cours in cours_list:
        for ei in range(1, 3):
            ev, created = Evaluation.objects.get_or_create(
                titre=f"Evaluation {ei} - {cours.titre[:25]}",
                cours=cours,
                defaults=dict(
                    enseignant=form_obj,
                    type_evaluation='structuree',
                    bareme=20.0,
                    consigne_texte=f"Repondez aux questions suivantes sur {cours.titre}.",
                    est_publiee=True,
                    date_debut=timezone.now() - datetime.timedelta(days=30),
                    date_fin=timezone.now() + datetime.timedelta(days=30),
                )
            )
            evaluations_list.append(ev)
            if created:
                for qi in range(1, 6):
                    q = Question.objects.create(
                        evaluation=ev,
                        type_question='choix_unique',
                        enonce_texte=f"Question {qi} de l'evaluation {ei} du cours {cours.titre[:20]} ?",
                        mode_correction='automatique',
                        points=4,
                        ordre=qi,
                    )
                    for ri in range(4):
                        Reponse.objects.create(
                            question=q,
                            texte=f"Reponse {chr(65+ri)}",
                            est_correcte=(ri == 0),
                            ordre=ri,
                        )
    ok(f"{len(evaluations_list)} evaluations")

    # ─── Quiz ───────────────────────────────────────────────────────────
    section("Quiz")
    quiz_list = []
    for seq in Sequence.objects.filter(module__cours__in=cours_list):
        qz, created = Quiz.objects.get_or_create(
            titre=f"Quiz - {seq.titre[:30]}",
            sequence=seq,
            defaults=dict(description=f"Quiz de verification de la sequence {seq.titre}.")
        )
        quiz_list.append(qz)
        if created:
            for qi in range(1, 4):
                q = Question.objects.create(
                    quiz=qz,
                    type_question='choix_unique',
                    enonce_texte=f"Question {qi} du quiz sur {seq.titre[:25]} ?",
                    mode_correction='automatique',
                    points=2,
                    ordre=qi,
                )
                for ri in range(3):
                    Reponse.objects.create(
                        question=q, texte=f"Option {chr(65+ri)}",
                        est_correcte=(ri == 0), ordre=ri,
                    )
    ok(f"{len(quiz_list)} quiz")

    # ─── Progressions Apprenant ────────────────────────────────────────
    section("Progressions Apprenant")
    progressions = []
    completion_values = [85.0, 45.0, 10.0]
    note_values     = [16.5,  9.0, None]
    statut_values   = ['en_cours', 'en_cours', 'non_commence']
    for cours, pct, note, statut in zip(cours_list, completion_values, note_values, statut_values):
        prog, created = ProgressionApprenant.objects.get_or_create(
            apprenant=appr_obj,
            cours=cours,
            defaults=dict(
                pourcentage_completion=pct,
                temps_total_minutes=random.randint(60, 300),
                statut=statut,
                note_moyenne_evaluations=note,
                taux_reussite_quiz=random.uniform(50, 90),
            )
        )
        if not created:
            # Mettre a jour les valeurs si deja existe
            prog.pourcentage_completion = pct
            prog.note_moyenne_evaluations = note
            prog.statut = statut
            prog.save()
        progressions.append(prog)

        # ProgressionModule
        for mod in cours.modules.all():
            pm, _ = ProgressionModule.objects.get_or_create(
                progression_apprenant=prog,
                module=mod,
                defaults=dict(
                    est_termine=(pct >= 80),
                    pourcentage_completion=min(pct + random.uniform(-10, 10), 100),
                    temps_passe_minutes=random.randint(30, 120),
                )
            )
            # ProgressionSequence
            for seq in mod.sequences.all():
                ProgressionSequence.objects.get_or_create(
                    progression_module=pm,
                    sequence=seq,
                    defaults=dict(
                        est_terminee=(pct >= 80),
                        pourcentage_completion=min(pct + random.uniform(-15, 15), 100),
                        nombre_visites=random.randint(1, 5),
                        temps_passe_minutes=random.randint(10, 45),
                    )
                )
    ok(f"{len(progressions)} progressions creees/mises a jour")

    # ─── Passages Evaluations ──────────────────────────────────────────
    section("Passages Evaluations (avec notes)")
    nb_passages = 0
    for ev, note_val in zip(evaluations_list[:3], [16.0, 8.5, 14.0]):
        passage, created = PassageEvaluation.objects.get_or_create(
            apprenant=appr_obj,
            evaluation=ev,
            defaults=dict(
                statut='corrige',
                note=note_val,
                date_debut=timezone.now() - datetime.timedelta(days=random.randint(5, 20)),
                date_soumission=timezone.now() - datetime.timedelta(days=random.randint(1, 5)),
            )
        )
        if created:
            nb_passages += 1
    ok(f"{nb_passages} passages evaluations crees")

    # ─── Passages Quiz ─────────────────────────────────────────────────
    section("Passages Quiz")
    nb_quiz_passes = 0
    for qz, score in zip(quiz_list[:4], [5, 3, 6, 4]):
        pq, created = PassageQuiz.objects.get_or_create(
            apprenant=appr_obj,
            quiz=qz,
            defaults=dict(
                score=score,
                termine=True,
                date_passage=timezone.now() - datetime.timedelta(days=random.randint(2, 15)),
            )
        )
        if created:
            nb_quiz_passes += 1
    ok(f"{nb_quiz_passes} passages quiz crees")

    # ─── Analytics (BlocAnalytics) ─────────────────────────────────────
    section("BlocAnalytics (sessions ouverture/fermeture)")
    blocs = list(BlocContenu.objects.filter(sequence__module__cours__in=cours_list[:2]))
    nb_analytics = 0
    for i, bloc in enumerate(blocs[:12]):
        duree = random.randint(300, 1200)
        scroll = random.randint(40, 100)
        ba = BlocAnalytics.objects.create(
            apprenant=appr_obj,
            bloc=bloc,
            sequence=bloc.sequence,
            module=bloc.sequence.module,
            cours=bloc.sequence.module.cours,
            ouvert_le=timezone.now() - datetime.timedelta(days=random.randint(1, 20), seconds=duree + 60),
            ferme_le=timezone.now() - datetime.timedelta(days=random.randint(1, 20)),
            duree_secondes=duree,
            scroll_max_pct=scroll,
            complete_en_session=(scroll >= 80),
        )
        nb_analytics += 1
        # BlocAnalyticsSummary
        summary, created = BlocAnalyticsSummary.objects.get_or_create(
            apprenant=appr_obj,
            bloc=bloc,
            defaults=dict(
                sequence=bloc.sequence,
                module=bloc.sequence.module,
                cours=bloc.sequence.module.cours,
                nb_ouvertures=1,
                nb_completions=1 if scroll >= 80 else 0,
                duree_totale_sec=duree,
                duree_moy_sec=duree,
                scroll_max_pct=scroll,
                premiere_ouverture=ba.ouvert_le,
                derniere_ouverture=ba.ouvert_le,
            )
        )
        if not created:
            summary.nb_ouvertures += 1
            summary.duree_totale_sec += duree
            summary.duree_moy_sec = summary.duree_totale_sec // summary.nb_ouvertures
            summary.save()
    ok(f"{nb_analytics} sessions BlocAnalytics + {BlocAnalyticsSummary.objects.filter(apprenant=appr_obj).count()} summaries")

    # ─── Historique Activite ───────────────────────────────────────────
    section("Historique Activite")
    # On supprime les anciens pour l'apprenant de test et on recrée
    HistoriqueActivite.objects.filter(apprenant=appr_obj).delete()
    types_activites = [
        ('connexion',               'Connexion a la plateforme',     0),
        ('consultation_cours',      'Consultation du cours Python',  25),
        ('debut_quiz',              'Debut du quiz Python Seq1',     0),
        ('fin_quiz',                'Fin du quiz - score: 5/6',      15),
        ('consultation_sequence',   'Lecture sequence 2 module 1',   20),
        ('consultation_module',     'Acces module 2',                0),
        ('soumission_evaluation',   'Soumission evaluation 1',       45),
        ('telechargement_ressource','Telechargement cours PDF',      0),
        ('participation_session',   'Session presentielle SQL',      120),
        ('consultation_cours',      'Reprise cours Bases de Donnees',30),
        ('debut_evaluation',        'Demarrage evaluation 2',        0),
        ('connexion',               'Connexion matinale',            0),
    ]
    # Creer sur les 12 derniers jours (1 activite par jour)
    for i, (type_act, desc, duree) in enumerate(types_activites):
        HistoriqueActivite.objects.create(
            apprenant=appr_obj,
            type_activite=type_act,
            description=desc,
            duree_minutes=duree,
            date_activite=timezone.now() - datetime.timedelta(days=i, hours=random.randint(8, 20)),
        )
    ok(f"{len(types_activites)} activites creees (streak={len(types_activites)} jours)")

    # ─── Plans d'action ────────────────────────────────────────────────
    section("Plans d'action")
    plans_data = [
        ("Reviser les bases Python",          cours_list[0], 'haute',   'en_cours',  7),
        ("Completer module SQL avance",        cours_list[1], 'moyenne', 'a_faire',   14),
        ("Preparer evaluation Web finale",     cours_list[2], 'urgente', 'a_faire',  -2),  # en retard
        ("Revoir les exercices du module 1",   cours_list[0], 'basse',   'termine',   3),
    ]
    for titre, cours, prio, statut, delta in plans_data:
        echeance = timezone.now().date() + datetime.timedelta(days=delta)
        plan, created = PlanAction.objects.get_or_create(
            titre=titre,
            apprenant=appr_obj,
            defaults=dict(
                cours=cours,
                priorite=prio,
                statut=statut,
                date_echeance=echeance,
                description=f"Plan de travail : {titre}",
                cree_par=form_user,
            )
        )
        if created:
            # Objectifs du plan
            for oi in range(1, 3):
                ObjectifPlanAction.objects.create(
                    plan_action=plan,
                    titre=f"Objectif {oi} : {titre[:30]}",
                    est_complete=(statut == 'termine'),
                    ordre=oi,
                )
    ok(f"{PlanAction.objects.filter(apprenant=appr_obj).count()} plans d'action")

    # ─── Notifications ─────────────────────────────────────────────────
    section("Notifications")
    notifs_data = [
        (appr_user,  "Nouvelle evaluation disponible",  "L'evaluation 1 du cours Python est publiee.",   'haute'),
        (appr_user,  "Quiz disponible",                 "Un quiz est disponible pour la sequence 2.",    'moyenne'),
        (appr_user,  "Plan d'action en retard",         "Votre plan 'Evaluation Web' est en retard.",   'haute'),
        (parent_user,"Progression de votre enfant",     "Brahim a complete 85% du cours Python.",        'moyenne'),
        (parent_user,"Note disponible",                  "Note evaluation: 16.5/20 en Python.",           'basse'),
        (form_user,  "Evaluation soumise",              "Un apprenant a soumis l'evaluation 1.",         'basse'),
        (form_user,  "Nouveau message",                 "Vous avez un nouveau message.",                 'moyenne'),
        (resp_user,  "Rapport mensuel",                 "Le rapport de progression est disponible.",     'basse'),
    ]
    nb_notifs = 0
    for recipient, titre, msg, prio in notifs_data:
        n, created = Notification.objects.get_or_create(
            recipient=recipient,
            titre=titre,
            defaults=dict(
                message=msg,
                type='inscription_cours',
                priorite=prio,
                canal='in_app',
                institution=inst,
                is_read=False,
            )
        )
        if created:
            nb_notifs += 1
    ok(f"{nb_notifs} notifications creees")

    # ─── Feedbacks ─────────────────────────────────────────────────────
    section("Feedbacks")
    for cours, note_f, texte in [
        (cours_list[0], 4.5, "Excellent cours, bien structure et progressif."),
        (cours_list[1], 3.8, "Bon contenu mais manque d'exercices pratiques."),
        (cours_list[2], 4.2, "Tres bon cours, les projets sont tres formateurs."),
    ]:
        Feedback.objects.get_or_create(
            cours=cours,
            auteur=appr_user,
            defaults=dict(contenu=texte, note=note_f)
        )
    ok(f"{Feedback.objects.filter(auteur=appr_user).count()} feedbacks")

    # ─── Forums + Commentaires ─────────────────────────────────────────
    section("Forums + Commentaires")
    nb_forums = 0
    for cours in cours_list:
        forum, created = Forum.objects.get_or_create(
            titre=f"Discussion - {cours.titre[:30]}",
            cours=cours,
            defaults=dict(
                description=f"Espace de discussion pour le cours {cours.titre}.",
                auteur=form_user,
            )
        )
        if created:
            nb_forums += 1
            for texte in [
                "Est-ce que quelqu'un peut expliquer le concept du module 2 ?",
                "J'ai trouve une ressource supplementaire interessante.",
                "Merci pour ce cours, tres instructif !",
            ]:
                Commentaire.objects.create(
                    forum=forum,
                    auteur=random.choice([appr_user, form_user]),
                    contenu=texte,
                )
    ok(f"{nb_forums} forums crees")

    # ─── Conversations ─────────────────────────────────────────────────
    section("Conversations")
    conv, created = Conversation.objects.get_or_create(
        sujet="Question sur le cours Python"
    )
    if created:
        Participant.objects.get_or_create(user=appr_user, conversation=conv)
        Participant.objects.get_or_create(user=form_user, conversation=conv)
        for texte, auteur in [
            ("Bonjour, j'ai une question sur la sequence 2.", appr_user),
            ("Bonjour ! Bien sur, de quoi s'agit-il ?",       form_user),
            ("Je ne comprends pas la notion de boucles.",     appr_user),
            ("C'est normal au debut. Voici une explication.", form_user),
        ]:
            Message.objects.create(conversation=conv, envoyeur=auteur, contenu=texte)
    ok(f"{Conversation.objects.count()} conversations")

    # ─── Suivi ─────────────────────────────────────────────────────────
    section("Suivi cours (table Suivi)")
    for cours, pct in zip(cours_list, [85, 45, 10]):
        Suivi.objects.get_or_create(
            apprenant=appr_obj,
            cours=cours,
            defaults=dict(
                progression=pct,
                note=16.5 if pct >= 80 else (9.0 if pct >= 40 else None),
                institution=inst,
                annee_scolaire=annee,
            )
        )
    ok(f"{Suivi.objects.filter(apprenant=appr_obj).count()} suivis")

    # ─── Resume final ──────────────────────────────────────────────────
    out("")
    out("=" * 60)
    out("  SEED DASHBOARDS TERMINE")
    out("=" * 60)
    rows = [
        ("Cours",              Cours.objects.filter(institution=inst).count()),
        ("InscriptionCours",   InscriptionCours.objects.filter(apprenant=appr_obj).count()),
        ("Evaluations",        Evaluation.objects.filter(cours__institution=inst).count()),
        ("Quiz",               Quiz.objects.count()),
        ("PassageEvaluation",  PassageEvaluation.objects.filter(apprenant=appr_obj).count()),
        ("ProgressionApprenant", ProgressionApprenant.objects.filter(apprenant=appr_obj).count()),
        ("HistoriqueActivite", HistoriqueActivite.objects.filter(apprenant=appr_obj).count()),
        ("BlocAnalytics",      BlocAnalytics.objects.filter(apprenant=appr_obj).count()),
        ("PlanAction",         PlanAction.objects.filter(apprenant=appr_obj).count()),
        ("Notification",       Notification.objects.filter(institution=inst).count()),
        ("Feedback",           Feedback.objects.filter(auteur=appr_user).count()),
        ("Forum",              Forum.objects.filter(cours__institution=inst).count()),
        ("Conversation",       Conversation.objects.count()),
    ]
    for label, count in rows:
        out(f"  {label:<28} : {count}")
    out("=" * 60)

    out("\n  URLs des dashboards :")
    out("  http://127.0.0.1:8000/admin/dashboard/             (accueil)")
    out("  http://127.0.0.1:8000/admin/dashboard/superadmin/  (SuperAdmin)")
    out("  http://127.0.0.1:8000/admin/dashboard/admin/       (Admin)")
    out("  http://127.0.0.1:8000/admin/dashboard/formateur/   (Formateur)")
    out("  http://127.0.0.1:8000/admin/dashboard/responsable/ (Responsable)")
    out("  http://127.0.0.1:8000/admin/dashboard/parent/      (Parent)")
    out("  http://127.0.0.1:8000/admin/dashboard/apprenant/   (Apprenant)")
    out("")
    out("  Connectez-vous sur /admin/ avec le bon compte avant d'acceder au dashboard.")
    out("")

if __name__ == "__main__":
    run()
