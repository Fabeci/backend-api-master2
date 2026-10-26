# evaluations/tests_explication.py
"""Tests de « Explique mon erreur » (évaluation remise uniquement)."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import AnneeScolaire, Classe, Groupe, Institution, Matiere
from courses.models import BlocContenu, Cours, Module, Sequence
from evaluations.models import (
    Evaluation, PassageEvaluation, Question, Reponse, ReponseQuestion,
)
from locations.models import Pays
from users.models import Apprenant, Formateur, UserRole

API = "/api/v1"
EXPLICATION = "### Pourquoi c'est faux\n\nUne pile est **LIFO**…"


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ExplicationErreurTests(TestCase):
    def setUp(self):
        self.pays = Pays.objects.create(nom="Sénégal", code="SN")
        self.inst = Institution.objects.create(nom="Sup'Info", pays=self.pays)
        self.annee = AnneeScolaire.objects.create(
            institution=self.inst, annee_format_classique="2025-2026", est_active=True)
        self.roles = {n: UserRole.objects.get_or_create(name=n)[0]
                      for n in ["Formateur", "Apprenant"]}

        self.classe = Classe.objects.create(nom="L3", institution=self.inst, annee_scolaire=self.annee)
        self.groupe = Groupe.objects.create(nom="G1", institution=self.inst,
                                            annee_scolaire=self.annee, classe=self.classe)
        self.matiere = Matiere.objects.create(institution=self.inst, nom="Algorithmique")

        self.formateur = Formateur.objects.create(
            email="form@expl.t", nom="F", prenom="Test",
            role=self.roles["Formateur"], institution=self.inst, is_active=True)
        self.formateur.institutions.add(self.inst)

        self.cours = Cours.objects.create(
            titre="Algorithmique", institution=self.inst, annee_scolaire=self.annee,
            matiere=self.matiere, groupe=self.groupe, enseignant=self.formateur)
        self.module = Module.objects.create(titre="Structures", cours=self.cours)
        self.sequence = Sequence.objects.create(titre="Piles", module=self.module)
        self.bloc = BlocContenu.objects.create(
            sequence=self.sequence, titre="Les piles LIFO", type_bloc="texte",
            contenu_texte="Une pile est une structure LIFO : dernier entré, premier sorti.",
        )

        self.evaluation = Evaluation.objects.create(
            cours=self.cours, enseignant=self.formateur, titre="Contrôle piles",
            type_evaluation="structuree", bareme=20,
            date_debut=timezone.now() - timedelta(days=1),
            date_fin=timezone.now() + timedelta(days=1),
            est_publiee=True, coefficient=1, categorie="examen",
        )
        self.question = Question.objects.create(
            evaluation=self.evaluation,
            enonce_texte="Quel est le principe d'une pile LIFO ?",
            type_question="choix_unique", points=2,
        )
        self.bonne = Reponse.objects.create(
            question=self.question, texte="Dernier entré, premier sorti", est_correcte=True)
        self.fausse = Reponse.objects.create(
            question=self.question, texte="Premier entré, premier sorti", est_correcte=False)

        self.appr = self._apprenant("appr@expl.t")
        self.autre = self._apprenant("autre@expl.t")

        self.passage = PassageEvaluation.objects.create(
            apprenant=self.appr, evaluation=self.evaluation, statut="corrige", note=0,
        )
        self.reponse = ReponseQuestion.objects.create(
            passage_evaluation=self.passage, question=self.question, statut="repondu",
        )
        self.reponse.choix_selectionnes.add(self.fausse)

        self.client = APIClient()

    def _apprenant(self, email):
        u = Apprenant.objects.create(
            email=email, nom="A", prenom="Test", role=self.roles["Apprenant"],
            institution=self.inst, is_active=True, groupe=self.groupe)
        u.set_password("Test@1234"); u.save()
        return u

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def _appel(self, user=None, question_id=None):
        return self.as_(user or self.appr).post(
            f"{API}/passages-evaluations/{self.passage.id}/explication/",
            {"question_id": question_id or self.question.id}, format="json")

    @patch("evaluations.views_explication.call_llm")
    def test_explication_apres_remise(self, mocked):
        mocked.return_value = {"content": EXPLICATION, "error": None,
                               "provider": "mock", "model": "test"}
        r = self._appel()
        self.assertEqual(r.status_code, 200, r.data)
        data = r.data["data"]
        self.assertIn("Pourquoi c'est faux", data["explication"])
        self.assertEqual(data["reponse_apprenant"], "Premier entré, premier sorti")
        self.assertEqual(data["bonnes_reponses"], ["Dernier entré, premier sorti"])
        self.assertIsNotNone(data["source"])
        self.assertEqual(data["source"]["bloc_id"], self.bloc.id)

        prompt = mocked.call_args[0][1]
        self.assertIn("Quel est le principe d'une pile LIFO", prompt)
        self.assertIn("Premier entré, premier sorti", prompt)
        self.assertIn("Dernier entré, premier sorti", prompt)

    def test_refuse_avant_remise(self):
        self.passage.statut = "en_cours"
        self.passage.save(update_fields=["statut"])
        r = self._appel()
        self.assertEqual(r.status_code, 403)

    def test_refuse_a_un_autre_apprenant(self):
        r = self._appel(user=self.autre)
        self.assertEqual(r.status_code, 404)

    @patch("evaluations.views_explication.call_llm")
    def test_refuse_si_la_reponse_est_correcte(self, mocked):
        self.reponse.choix_selectionnes.clear()
        self.reponse.choix_selectionnes.add(self.bonne)
        r = self._appel()
        self.assertEqual(r.status_code, 400)
        self.assertFalse(mocked.called)

    @patch("evaluations.views_explication.call_llm")
    def test_erreur_ia_renvoie_502(self, mocked):
        mocked.return_value = {"content": "", "error": "timeout"}
        r = self._appel()
        self.assertEqual(r.status_code, 502)

    def test_question_invalide(self):
        r = self.as_(self.appr).post(
            f"{API}/passages-evaluations/{self.passage.id}/explication/",
            {"question_id": 999999}, format="json")
        self.assertEqual(r.status_code, 404)
