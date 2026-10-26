# courses/tests_stats.py
"""Tests du tableau de bord formateur (tuteur IA)."""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import AnneeScolaire, Classe, Groupe, Institution, Matiere
from courses.models import (
    BlocContenu, ConversationTuteur, Cours, EvenementTuteur, MessageTuteur,
    Module, QuizTuteur, Sequence,
)
from locations.models import Pays
from users.models import Apprenant, Formateur, UserRole

API = "/api/v1"


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class TuteurStatsTests(TestCase):
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
        self.matiere2 = Matiere.objects.create(institution=self.inst, nom="Réseaux")

        self.f1 = self._formateur("f1@stats.t")
        self.f2 = self._formateur("f2@stats.t")

        self.cours1 = self._cours("Cours A", self.f1, self.matiere)
        self.cours2 = self._cours("Cours B", self.f2, self.matiere2)
        self.bloc1 = self._bloc(self.cours1, "Piles")
        self.bloc2 = self._bloc(self.cours2, "Réseaux")

        self.appr = Apprenant.objects.create(
            email="appr@stats.t", nom="A", prenom="T", role=self.roles["Apprenant"],
            institution=self.inst, is_active=True, groupe=self.groupe)
        self.appr.set_password("Test@1234"); self.appr.save()

        self.conv1 = ConversationTuteur.objects.create(
            apprenant=self.appr, bloc=self.bloc1, cours=self.cours1,
            institution=self.inst, titre="Piles")
        self.conv2 = ConversationTuteur.objects.create(
            apprenant=self.appr, bloc=self.bloc2, cours=self.cours2,
            institution=self.inst, titre="Réseaux")

        for texte in ["Explique-moi les piles", "Les piles encore", "Comprendre les piles"]:
            MessageTuteur.objects.create(conversation=self.conv1, role="user",
                                         contenu=texte, statut="termine")
        MessageTuteur.objects.create(conversation=self.conv2, role="user",
                                     contenu="Explique-moi le routage", statut="termine")

        self.quiz1 = QuizTuteur.objects.create(
            conversation=self.conv1, apprenant=self.appr, bloc=self.bloc1,
            cours=self.cours1, titre="Piles", questions=[], reponses=[],
            score=40, statut="corrige")
        QuizTuteur.objects.create(
            conversation=self.conv1, apprenant=self.appr, bloc=self.bloc1,
            cours=self.cours1, titre="Piles 2", questions=[], reponses=[],
            score=60, statut="corrige")

        EvenementTuteur.objects.create(
            type="refus_evaluation", apprenant=self.appr, cours=self.cours1,
            bloc=self.bloc1, institution=self.inst)
        EvenementTuteur.objects.create(
            type="refus_evaluation", apprenant=self.appr, cours=self.cours2,
            bloc=self.bloc2, institution=self.inst)

        self._p_inst = patch("core.tenant.default_institution_id", return_value=self.inst.id)
        self._p_inst.start()
        self.addCleanup(self._p_inst.stop)

        self.client = APIClient()

    def _formateur(self, email):
        f = Formateur.objects.create(email=email, nom="F", prenom="T",
                                     role=self.roles["Formateur"], institution=self.inst,
                                     is_active=True)
        f.institutions.add(self.inst)
        f.set_password("Test@1234"); f.save()
        return f

    def _cours(self, titre, formateur, matiere):
        return Cours.objects.create(
            titre=titre, institution=self.inst, annee_scolaire=self.annee,
            matiere=matiere, groupe=self.groupe, enseignant=formateur)

    def _bloc(self, cours, titre):
        module = Module.objects.create(titre=f"M {titre}", cours=cours)
        sequence = Sequence.objects.create(titre=f"S {titre}", module=module)
        return BlocContenu.objects.create(
            sequence=sequence, titre=titre, type_bloc="texte",
            contenu_texte=f"Contenu du bloc {titre}.")

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def test_formateur_ne_voit_que_ses_cours(self):
        r = self.as_(self.f1).get(f"{API}/chat/tuteur/stats/")
        self.assertEqual(r.status_code, 200, r.data)
        data = r.data["data"]
        self.assertEqual(data["conversations"], 1)
        self.assertEqual(data["messages"], 3)
        self.assertEqual([c["id"] for c in data["cours_disponibles"]], [self.cours1.id])
        self.assertEqual(data["par_cours"][0]["cours_id"], self.cours1.id)

    def test_refus_evaluation_comptabilise(self):
        data = self.as_(self.f1).get(f"{API}/chat/tuteur/stats/").data["data"]
        self.assertEqual(data["refus_evaluation"], 1)

    def test_quiz_score_moyen(self):
        data = self.as_(self.f1).get(f"{API}/chat/tuteur/stats/").data["data"]
        self.assertEqual(data["quiz"]["total"], 2)
        self.assertEqual(data["quiz"]["score_moyen"], 50.0)

    def test_notions_agregees(self):
        data = self.as_(self.f1).get(f"{API}/chat/tuteur/stats/").data["data"]
        mots = {n["mot"] for n in data["notions"]}
        self.assertIn("piles", mots)
        self.assertNotIn("routage", mots)

    def test_apprenant_refuse(self):
        r = self.as_(self.appr).get(f"{API}/chat/tuteur/stats/")
        self.assertEqual(r.status_code, 403)

    def test_filtre_sur_un_cours_non_autorise(self):
        r = self.as_(self.f1).get(f"{API}/chat/tuteur/stats/?cours={self.cours2.id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["data"]["conversations"], 0)

    def test_periode_exclut_les_anciennes_conversations(self):
        ConversationTuteur.objects.filter(pk=self.conv1.pk).update(
            maj_le=timezone.now() - timedelta(days=90))
        data = self.as_(self.f1).get(f"{API}/chat/tuteur/stats/?jours=30").data["data"]
        self.assertEqual(data["conversations"], 0)
