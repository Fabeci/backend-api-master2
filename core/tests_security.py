# core/tests_security.py
# ============================================================================
# Tests d'INTÉGRATION — périmètres, publication, corrigés, LMD.
# Lancer : python manage.py test core.tests_security -v2
# ============================================================================
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User, UserRole, Apprenant, Formateur
from locations.models import Pays
from academics.models import (
    Institution, AnneeScolaire, Classe, Groupe, Matiere, Semestre, UE,
)
from courses.models import Cours, Module, Sequence, BlocContenu, InscriptionCours, Session
from evaluations.models import Evaluation, PassageEvaluation


API = "/api/v1"


def _user(model, email, role, institution):
    u = model.objects.create(email=email, nom="Test", prenom="User",
                             role=role, institution=institution, is_active=True)
    u.set_password("Test@1234")
    u.save()
    return u


class PerimetresEtLMDTests(TestCase):
    def setUp(self):
        # ✅ Contexte MONO-ÉTABLISSEMENT : on aligne l'institution de référence
        #    sur celle du test (sinon le périmètre pointe vers l'institution 27).
        self.pays = Pays.objects.create(nom="Sénégal", code="SN")
        self.inst = Institution.objects.create(nom="Sup'Info", pays=self.pays)
        self.annee = AnneeScolaire.objects.create(
            institution=self.inst, annee_format_classique="2025-2026", est_active=True)
        self.roles = {n: UserRole.objects.get_or_create(name=n)[0]
                      for n in ["Admin", "Responsable", "Formateur", "Apprenant"]}

        self.classe = Classe.objects.create(nom="L3 Info", institution=self.inst, annee_scolaire=self.annee)
        self.groupe = Groupe.objects.create(nom="Groupe A", institution=self.inst,
                                            annee_scolaire=self.annee, classe=self.classe)
        self.matiere = Matiere.objects.create(institution=self.inst, nom="Développement Web")

        self.admin = _user(User, "admin@sec.t", self.roles["Admin"], self.inst)
        self.resp = _user(User, "resp@sec.t", self.roles["Responsable"], self.inst)
        self.f1 = _user(Formateur, "f1@sec.t", self.roles["Formateur"], self.inst)
        self.f2 = _user(Formateur, "f2@sec.t", self.roles["Formateur"], self.inst)
        self.appr = _user(Apprenant, "appr@sec.t", self.roles["Apprenant"], self.inst)
        self.appr.groupe = self.groupe
        self.appr.save()
        # ✅ Périmètre pédagogique : le formateur doit être rattaché à l'établissement
        self.f1.institutions.add(self.inst)
        self.f2.institutions.add(self.inst)

        self.cours1 = Cours.objects.create(
            groupe=self.groupe, enseignant=self.f1, matiere=self.matiere,
            annee_scolaire=self.annee, institution=self.inst, titre="Dev Web L3")
        self.cours2 = Cours.objects.create(
            groupe=self.groupe, enseignant=self.f2, matiere=self.matiere,
            annee_scolaire=self.annee, institution=self.inst, titre="Dev Web (autre)")

        self.module1 = Module.objects.create(cours=self.cours1, titre="Module 1", ordre=1)
        self.seq1 = Sequence.objects.create(module=self.module1, titre="Séquence 1", ordre=1)
        self.bloc1 = BlocContenu.objects.create(sequence=self.seq1, titre="Bloc 1", type_bloc="texte")

        self.eval1 = Evaluation.objects.create(
            cours=self.cours1, enseignant=self.f1, titre="Examen", type_evaluation="structuree",
            bareme=20, date_debut=timezone.now() - timedelta(days=2),
            date_fin=timezone.now() + timedelta(days=2), est_publiee=True,
            coefficient=1, categorie="examen")

        InscriptionCours.objects.create(apprenant=self.appr, cours=self.cours1, statut="inscrit",
                                        institution=self.inst, annee_scolaire=self.annee)

        # LMD : S5 → UE DEV → matière (EC)
        self.sem = Semestre.objects.create(classe=self.classe, annee_scolaire=self.annee,
                                           numero=5, institution=self.inst)
        self.ue = UE.objects.create(semestre=self.sem, code="DEV", libelle="Développement",
                                    credits=6, coefficient=1, institution=self.inst)
        self.matiere.ue = self.ue
        self.matiere.credits = 6
        self.matiere.coefficient = 1
        self.matiere.save()

        # Patch du contexte mono-établissement (importé au moment de l'appel).
        self._p_inst = patch("core.tenant.default_institution_id", return_value=self.inst.id)
        self._p_annee = patch("core.tenant.default_annee_scolaire", return_value=self.annee)
        self._p_inst.start(); self._p_annee.start()
        self.addCleanup(self._p_inst.stop)
        self.addCleanup(self._p_annee.stop)

        self.client = APIClient()

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    # ── Formateur ─────────────────────────────────────────────────────────
    def test_formateur_voit_ses_cours(self):
        r = self.as_(self.f1).get(f"{API}/cours/")
        self.assertEqual(r.status_code, 200)

    def test_formateur_ne_modifie_pas_un_cours_etranger(self):
        r = self.as_(self.f1).patch(f"{API}/cours/{self.cours2.id}/", {"titre": "PIRATE"}, format="json")
        self.assertIn(r.status_code, (403, 404))

    def test_formateur_modifie_son_module(self):
        r = self.as_(self.f1).patch(f"{API}/modules/{self.module1.id}/", {"description": "ok"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_formateur_ne_modifie_pas_le_module_etranger(self):
        r = self.as_(self.f2).patch(f"{API}/modules/{self.module1.id}/", {"description": "x"}, format="json")
        self.assertIn(r.status_code, (403, 404))

    def test_formateur_cree_une_seance_sur_son_cours(self):
        r = self.as_(self.f1).post(f"{API}/sessions/", {
            "formateur_id": self.f1.id, "cours_id": self.cours1.id, "titre": "Séance test",
            "date_debut": (timezone.now() + timedelta(days=1)).isoformat(),
            "date_fin": (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 201, r.content[:300])

    def test_formateur_ne_cree_pas_de_seance_hors_perimetre(self):
        r = self.as_(self.f2).post(f"{API}/sessions/", {
            "formateur_id": self.f2.id, "cours_id": self.cours1.id, "titre": "Pirate",
            "date_debut": (timezone.now() + timedelta(days=1)).isoformat(),
            "date_fin": (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
        }, format="json")
        self.assertIn(r.status_code, (403, 404))

    # ── Apprenant ─────────────────────────────────────────────────────────
    def test_apprenant_ne_cree_pas_de_contenu(self):
        r = self.as_(self.appr).post(f"{API}/modules/", {"cours": self.cours1.id, "titre": "X"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_apprenant_ne_voit_pas_un_cours_etranger(self):
        r = self.as_(self.appr).get(f"{API}/cours/{self.cours2.id}/")
        self.assertEqual(r.status_code, 404)

    def test_apprenant_ne_voit_pas_les_corriges(self):
        r = self.as_(self.appr).get(f"{API}/evaluations/{self.eval1.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("est_correcte", r.content.decode())

    # ── Responsable ───────────────────────────────────────────────────────
    def test_responsable_ne_cree_pas_de_seance(self):
        r = self.as_(self.resp).post(f"{API}/sessions/", {
            "formateur_id": self.f1.id, "cours_id": self.cours1.id, "titre": "Refus",
            "date_debut": (timezone.now() + timedelta(days=1)).isoformat(),
            "date_fin": (timezone.now() + timedelta(days=1, hours=2)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 403)

    def test_responsable_ne_cree_pas_d_evaluation(self):
        r = self.as_(self.resp).post(f"{API}/evaluations/", {
            "cours": self.cours1.id, "titre": "Refus", "type_evaluation": "devoir", "bareme": 20,
            "date_debut": timezone.now().isoformat(), "date_fin": (timezone.now() + timedelta(days=1)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 403)

    # ── Publication programmée ────────────────────────────────────────────
    def test_bloc_programme_invisible_avant_la_date(self):
        self.bloc1.etat_publication = "programme"
        self.bloc1.date_publication_programmee = timezone.now() + timedelta(days=5)
        self.bloc1.save()
        r = self.as_(self.appr).get(f"{API}/blocs-contenu/{self.bloc1.id}/")
        self.assertEqual(r.status_code, 404)

    # ── LMD : moyenne + rattrapage ────────────────────────────────────────
    def test_bulletin_moyenne_et_rattrapage(self):
        PassageEvaluation.objects.create(apprenant=self.appr, evaluation=self.eval1,
                                         numero_tentative=1, session="normale", statut="corrige", note=5)
        PassageEvaluation.objects.create(apprenant=self.appr, evaluation=self.eval1,
                                         numero_tentative=2, session="rattrapage", statut="corrige", note=13)
        r = self.as_(self.resp).get(f"{API}/bulletins/{self.appr.id}/{self.annee.id}/")
        self.assertEqual(r.status_code, 200)
        data = r.json().get("data") or {}
        self.assertEqual(data.get("moyenne_annee"), 13.0)
        self.assertTrue(data.get("valide_annee"))
        self.assertEqual(data.get("mention"), "Assez bien")
