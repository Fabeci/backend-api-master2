#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Creation des comptes de test - un compte par profil utilisateur.
Mot de passe pour tous les comptes : Test@1234
"""
import os, sys, datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'master_backend_api.settings')

import django
django.setup()

from django.db import transaction
from locations.models import Pays
from academics.models import Institution, AnneeScolaire, Departement, Classe, Groupe
from users.models import User, UserRole, Admin, Parent, Apprenant, Formateur, ResponsableAcademique, SuperAdmin

PASSWORD = "Test@1234"

EMAILS = [
    "superadmin@testlms.com",
    "admin@testlms.com",
    "responsable@testlms.com",
    "formateur@testlms.com",
    "apprenant@testlms.com",
    "parent@testlms.com",
]

def out(msg):
    sys.stdout.buffer.write((msg + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()

def ok(msg):   out(f"  [OK] {msg}")
def line():    out("-" * 55)
def title(t):  line(); out(f"  {t}"); line()


@transaction.atomic
def run():
    title("1. Suppression des anciens comptes de test")
    deleted = 0
    for email in EMAILS:
        n, _ = User.objects.filter(email=email).delete()
        deleted += n
    ok(f"{deleted} ancien(s) compte(s) supprime(s)")

    # --- Roles ---
    title("2. Creation des roles")
    roles = {}
    for nom in ["SuperAdmin", "Admin", "ResponsableAcademique", "Formateur", "Apprenant", "Parent"]:
        r, created = UserRole.objects.get_or_create(name=nom)
        roles[nom] = r
        ok(f"Role {'cree' if created else 'existant'} : {nom}")

    # --- Donnees de base ---
    title("3. Donnees academiques")
    pays, _ = Pays.objects.get_or_create(code="TD", defaults={"nom": "Tchad"})
    ok(f"Pays : {pays.nom}")

    inst, created = Institution.objects.get_or_create(
        email="test@lms-demo.com",
        defaults={
            "nom": "LMS Demo Institution",
            "pays": pays,
            "telephone_1": "+23500000000",
            "nombre_etudiants": 200,
        }
    )
    ok(f"Institution : {inst.nom} ({'creee' if created else 'existante'})")

    annee, _ = AnneeScolaire.objects.get_or_create(
        institution=inst,
        annee_format_classique="2025-2026",
        defaults={
            "date_debut": datetime.date(2025, 9, 1),
            "date_fin": datetime.date(2026, 6, 30),
            "est_active": True,
        }
    )
    ok(f"Annee scolaire : {annee.annee_format_classique} (active={annee.est_active})")

    classe, _ = Classe.objects.get_or_create(
        nom="Licence 3", institution=inst, annee_scolaire=annee,
    )
    ok(f"Classe : {classe.nom}")

    groupe, _ = Groupe.objects.get_or_create(
        nom="Groupe A", institution=inst, annee_scolaire=annee, classe=classe,
    )
    ok(f"Groupe : {groupe.nom}")

    # Helper : champs communs User
    def base_fields(role_name, nom, prenom, telephone, **extra):
        return dict(
            role=roles[role_name],
            nom=nom, prenom=prenom,
            telephone=telephone,
            institution=inst,
            annee_scolaire_active=annee,
            is_active=True,
            **extra
        )

    def save_user(obj, password):
        obj.set_password(password)
        # bypass full_clean pour eviter les signaux de validation complexes
        obj.save()
        return obj

    title("4. Creation des comptes utilisateurs")

    # 1. SuperAdmin
    sa = SuperAdmin(email="superadmin@testlms.com",
                    **base_fields("SuperAdmin", "Kamara", "Ibrahim", "+23500000001",
                                  is_staff=True, is_superuser=True))
    save_user(sa, PASSWORD)
    ok("SuperAdmin            : superadmin@testlms.com")

    # 2. Admin
    ad = Admin(email="admin@testlms.com",
               **base_fields("Admin", "Mahamat", "Ali", "+23500000002", is_staff=True))
    save_user(ad, PASSWORD)
    ok("Admin                 : admin@testlms.com")

    # 3. Responsable Academique (sans departement pour l'instant)
    ra_user = User(email="responsable@testlms.com",
                   **base_fields("ResponsableAcademique", "Ousman", "Halime", "+23500000003"))
    save_user(ra_user, PASSWORD)
    ra = ResponsableAcademique(user_ptr_id=ra_user.pk, departement=None)
    ra.__dict__.update(ra_user.__dict__)
    ResponsableAcademique.objects.filter(pk=ra_user.pk).delete()
    ra = ResponsableAcademique(email="responsable@testlms.com",
                               **base_fields("ResponsableAcademique", "Ousman", "Halime", "+23500000003"),
                               departement=None)
    ra.pk = ra_user.pk  # ne pas creer un nouveau User
    User.objects.filter(pk=ra_user.pk).delete()  # supprimer le User intermediaire
    save_user(ra, PASSWORD)
    ok("ResponsableAcademique : responsable@testlms.com")

    # Departement (necessite le RA)
    dep, dep_created = Departement.objects.get_or_create(
        nom="Departement Informatique",
        institution=inst,
        defaults={"responsable_academique": ra, "est_actif": True}
    )
    if not dep_created:
        Departement.objects.filter(pk=dep.pk).update(responsable_academique=ra)
        dep.refresh_from_db()
    # Synchronise RA.departement
    ResponsableAcademique.objects.filter(pk=ra.pk).update(departement=dep)
    ok(f"Departement           : {dep.nom}")

    # 4. Formateur
    fo = Formateur(email="formateur@testlms.com",
                   **base_fields("Formateur", "Abderamane", "Fatima", "+23500000004"))
    save_user(fo, PASSWORD)
    fo.institutions.add(inst)
    fo.groupes.add(groupe)
    ok("Formateur             : formateur@testlms.com")

    # 5. Parent (avant Apprenant car tuteur)
    pa = Parent(email="parent@testlms.com",
                **base_fields("Parent", "Hassane", "Mariam", "+23500000005"))
    save_user(pa, PASSWORD)
    ok("Parent                : parent@testlms.com")

    # 6. Apprenant
    ap = Apprenant(
        email="apprenant@testlms.com",
        **base_fields("Apprenant", "Brahim", "Aicha", "+23500000006"),
        matricule="APP-2025-001",
        date_naissance=datetime.date(2002, 3, 15),
        groupe=groupe,
        tuteur=pa,
    )
    save_user(ap, PASSWORD)
    ok("Apprenant             : apprenant@testlms.com  (tuteur -> parent@testlms.com)")

    # --- Tableau final ---
    out("")
    out("=" * 70)
    out("  COMPTES DE TEST CREES")
    out("  Mot de passe universel : Test@1234")
    out("=" * 70)
    out(f"  {'Role':<26} {'Email':<32} Acces")
    out(f"  {'-'*24} {'-'*30} {'-'*18}")
    rows = [
        ("SuperAdmin",             "superadmin@testlms.com",     "Total - toutes institutions"),
        ("Admin",                  "admin@testlms.com",          "Gestion institution entiere"),
        ("ResponsableAcademique",  "responsable@testlms.com",    "Departement Informatique"),
        ("Formateur",              "formateur@testlms.com",      "Cours, Modules, Evaluations"),
        ("Apprenant",              "apprenant@testlms.com",      "Cours inscrits uniquement"),
        ("Parent",                 "parent@testlms.com",         "Suivi de son enfant"),
    ]
    for role, email, acces in rows:
        out(f"  {role:<26} {email:<32} {acces}")
    out("=" * 70)
    out(f"\n  Institution   : {inst.nom}")
    out(f"  Annee active  : {annee.annee_format_classique}")
    out(f"  Classe/Groupe : {classe.nom} / {groupe.nom}")
    out(f"  Departement   : {dep.nom}")
    out(f"\n  Lien famille  : Brahim Aicha (apprenant) -> Hassane Mariam (parent)")
    out("")

if __name__ == "__main__":
    run()
