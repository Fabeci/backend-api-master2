# courses/tests_chat.py
"""Tests de l'assistant pédagogique IA (chat par bloc).

Lancer : python manage.py test courses.tests_chat -v2
"""
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from academics.models import (
    AnneeScolaire, Classe, Groupe, Institution, Matiere,
)
from courses.models import (
    BlocContenu, ConversationTuteur, Cours, InscriptionCours, MessageTuteur,
    Module, Sequence,
)
from locations.models import Pays
from users.models import Apprenant, Formateur, User, UserRole

API = "/api/v1"


def _fake_llm(system_prompt="", user_prompt="", json_mode=True, max_tokens=None):
    return {
        "content": "Voici une explication **simple** du concept.",
        "error": None,
        "provider": "mock",
        "model": "mock-test",
        "degraded": False,
    }


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ChatTuteurTests(TestCase):
    def setUp(self):
        self.pays = Pays.objects.create(nom="Sénégal", code="SN")
        self.inst = Institution.objects.create(nom="Sup'Info", pays=self.pays)
        self.annee = AnneeScolaire.objects.create(
            institution=self.inst, annee_format_classique="2025-2026", est_active=True)
        self.roles = {n: UserRole.objects.get_or_create(name=n)[0]
                      for n in ["Admin", "Formateur", "Apprenant"]}

        self.classe = Classe.objects.create(nom="L3 Info", institution=self.inst, annee_scolaire=self.annee)
        self.groupe = Groupe.objects.create(nom="Groupe A", institution=self.inst,
                                            annee_scolaire=self.annee, classe=self.classe)
        self.matiere = Matiere.objects.create(institution=self.inst, nom="Algorithmique")

        self.formateur = Formateur.objects.create(
            email="form@chat.t", nom="Test", prenom="Formateur",
            role=self.roles["Formateur"], institution=self.inst, is_active=True)
        self.formateur.institutions.add(self.inst)
        self.cours = Cours.objects.create(
            titre="Algorithmique avancée", institution=self.inst,
            annee_scolaire=self.annee, matiere=self.matiere,
            groupe=self.groupe, enseignant=self.formateur)
        self.module = Module.objects.create(titre="Structures de données", cours=self.cours)
        self.sequence = Sequence.objects.create(titre="Les piles", module=self.module)
        self.bloc = BlocContenu.objects.create(
            sequence=self.sequence, titre="Définition d'une pile",
            type_bloc="texte",
            contenu_texte="Une pile est une structure LIFO : le dernier élément "
                          "entré est le premier sorti.",
        )

        self.appr = self._make_apprenant("appr@chat.t", inscrit=True)
        self.autre = self._make_apprenant("autre@chat.t", inscrit=False)

        self._p_inst = patch("core.tenant.default_institution_id", return_value=self.inst.id)
        self._p_annee = patch("core.tenant.default_annee_scolaire", return_value=self.annee)
        self._p_inst.start(); self._p_annee.start()
        self.addCleanup(self._p_inst.stop)
        self.addCleanup(self._p_annee.stop)

        self.client = APIClient()

    def _make_apprenant(self, email, inscrit=True):
        user = Apprenant.objects.create(
            email=email, nom="Test", prenom="Apprenant",
            role=self.roles["Apprenant"], institution=self.inst,
            is_active=True, groupe=self.groupe,
        )
        user.set_password("Test@1234")
        user.save()
        if inscrit:
            InscriptionCours.objects.create(
                apprenant=user, cours=self.cours, statut="inscrit",
                institution=self.inst, annee_scolaire=self.annee)
        return user

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    # ── Ouverture / contexte ───────────────────────────────────────────────
    def test_ouverture_cree_une_conversation_avec_suggestions(self):
        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertEqual(r.status_code, 200, r.data)
        data = r.data["data"]
        self.assertIsNotNone(data["conversation"]["id"])
        self.assertEqual(data["messages"], [])
        self.assertEqual(len(data["suggestions"]), 4)
        self.assertIn(self.bloc.titre, data["suggestions"][0])
        self.assertTrue(data["contexte"]["contenu_disponible"])
        self.assertEqual(ConversationTuteur.objects.count(), 1)

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_le_contenu_du_bloc_est_envoye_au_modele(self, mocked):
        self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi la notion."}, format="json")
        self.assertTrue(mocked.called)
        _, user_prompt = mocked.call_args[0][0], mocked.call_args[0][1]
        self.assertIn("LIFO", user_prompt)
        self.assertIn(self.bloc.titre, user_prompt)
        self.assertIn("Explique-moi la notion.", user_prompt)

    # ── Envoi / réponse ────────────────────────────────────────────────────
    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_envoi_question_recoit_une_reponse(self, _mocked):
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Peux-tu simplifier ?"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        message = r.data["data"]["message"]
        self.assertEqual(message["role"], "assistant")
        self.assertEqual(message["statut"], "termine")
        self.assertIn("explication", message["contenu"])
        self.assertEqual(MessageTuteur.objects.filter(conversation__bloc=self.bloc).count(), 2)

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_historique_conserve_apres_rechargement(self, _mocked):
        self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Première question"}, format="json")
        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertEqual(r.status_code, 200)
        roles = [m["role"] for m in r.data["data"]["messages"]]
        self.assertEqual(roles, ["user", "assistant"])

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_double_envoi_meme_client_id_est_idempotent(self, mocked):
        payload = {"contenu": "Question", "client_id": "abc-123"}
        r1 = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/", payload, format="json")
        r2 = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/", payload, format="json")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data["message"], "Message déjà traité.")
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(MessageTuteur.objects.filter(role="user").count(), 1)

    def test_message_trop_long_refuse(self):
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "x" * 3000}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_message_vide_refuse(self):
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/", {"contenu": "   "}, format="json")
        self.assertEqual(r.status_code, 400)

    @patch("courses.services.chat_tuteur.call_llm", side_effect=RuntimeError("timeout"))
    def test_erreur_ia_renvoie_502_et_message_erreur(self, _mocked):
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Question"}, format="json")
        self.assertEqual(r.status_code, 502)
        self.assertFalse(r.data["success"])
        assistant = MessageTuteur.objects.filter(role="assistant").first()
        self.assertEqual(assistant.statut, "erreur")
        self.assertTrue(assistant.erreur)

    # ── Nouvelle conversation / suppression ────────────────────────────────
    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_nouvelle_conversation_archive_l_ancienne(self, _mocked):
        self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/", {"contenu": "Q1"}, format="json")
        ancienne = ConversationTuteur.objects.get(statut="active")
        r = self.as_(self.appr).post(f"{API}/chat/conversations/{ancienne.id}/nouvelle/")
        self.assertEqual(r.status_code, 200, r.data)
        nouvelle = r.data["data"]["conversation"]
        self.assertNotEqual(nouvelle["id"], ancienne.id)
        self.assertEqual(ConversationTuteur.objects.filter(statut="active").count(), 1)
        self.assertEqual(ConversationTuteur.objects.get(pk=ancienne.id).statut, "archivee")
        self.assertEqual(r.data["data"]["messages"], [])

    def test_supprimer_sa_conversation(self):
        conv = ConversationTuteur.objects.create(
            apprenant=self.appr, bloc=self.bloc, cours=self.cours,
            institution=self.inst, titre=self.bloc.titre)
        r = self.as_(self.appr).delete(f"{API}/chat/conversations/{conv.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(ConversationTuteur.objects.filter(pk=conv.id).exists())

    # ── Sécurité ───────────────────────────────────────────────────────────
    def test_apprenant_non_inscrit_refuse(self):
        r = self.as_(self.autre).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertEqual(r.status_code, 403)

    def test_conversation_d_un_autre_apprenant_inaccessible(self):
        conv = ConversationTuteur.objects.create(
            apprenant=self.appr, bloc=self.bloc, cours=self.cours,
            institution=self.inst, titre=self.bloc.titre)
        r_get = self.as_(self.autre).get(f"{API}/chat/conversations/{conv.id}/")
        r_del = self.as_(self.autre).delete(f"{API}/chat/conversations/{conv.id}/")
        self.assertEqual(r_get.status_code, 404)
        self.assertEqual(r_del.status_code, 404)
        self.assertTrue(ConversationTuteur.objects.filter(pk=conv.id).exists())

    def test_authentification_requise(self):
        self.client.force_authenticate(user=None)
        r = self.client.get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertIn(r.status_code, (401, 403))

    def test_bloc_masque_refuse(self):
        self.bloc.est_visible = False
        self.bloc.save(update_fields=["est_visible"])
        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertEqual(r.status_code, 403)
