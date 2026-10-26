# courses/tests_chat.py
"""Tests de l'assistant pédagogique IA (chat par bloc).

Lancer : python manage.py test courses.tests_chat -v2
"""
import io
import json
import os
import tempfile
from datetime import timedelta
from unittest.mock import Mock, patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import (
    AnneeScolaire, Classe, Groupe, Institution, Matiere,
)
from courses.models import (
    BlocContenu, ConversationTuteur, Cours, DocumentChunk, InscriptionCours,
    MessageTuteur, Module, QuizTuteur, Sequence,
)
from courses.services import difficulte, rag
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


MEDIA_TEST = tempfile.mkdtemp(prefix="somapro-chat-media-")

QUIZ_JSON = json.dumps({
    "questions": [
        {"question": "Une pile est de type… ?", "options": ["FIFO", "LIFO", "LILO", "RANDOM"],
         "bonne_reponse": 1, "explication": "LIFO = dernier entré, premier sorti."},
        {"question": "Quelle opération ajoute un élément ?", "options": ["pop", "push", "peek", "clear"],
         "bonne_reponse": 1, "explication": "push empile un élément."},
        {"question": "Que fait pop ?", "options": ["Ajoute", "Retire le dernier", "Vide tout", "Trie"],
         "bonne_reponse": 1, "explication": "pop retire l'élément au sommet."},
    ]
})


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    MEDIA_ROOT=MEDIA_TEST,
)
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


    def _passage_evaluation(self, statut="en_cours", apprenant=None):
        from evaluations.models import Evaluation, PassageEvaluation

        evaluation = Evaluation.objects.create(
            cours=self.cours,
            enseignant=self.formateur,
            titre="Examen final",
            type_evaluation="structuree",
            bareme=20,
            date_debut=timezone.now() - timedelta(hours=1),
            date_fin=timezone.now() + timedelta(hours=1),
            est_publiee=True,
            coefficient=1,
            categorie="examen",
        )
        PassageEvaluation.objects.create(
            apprenant=apprenant or self.appr,
            evaluation=evaluation,
            statut=statut,
            session="normale",
            numero_tentative=1,
        )
        return evaluation

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

    # ── Anti-triche : évaluation en cours ──────────────────────────────────
    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_evaluation_en_cours_bloque_l_assistant(self, mocked):
        self._passage_evaluation(statut="en_cours")

        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["data"]["evaluation"]["en_cours"])

        r2 = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi la notion."}, format="json")
        self.assertEqual(r2.status_code, 423)
        self.assertFalse(mocked.called)
        self.assertEqual(MessageTuteur.objects.count(), 0)

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_apres_remise_l_assistant_redevient_disponible(self, mocked):
        self._passage_evaluation(statut="soumis")
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi la notion."}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(mocked.called)
        self.assertFalse(r.data["data"]["evaluation"]["en_cours"])

    def test_evaluation_d_un_autre_apprenant_ne_bloque_pas(self):
        self._passage_evaluation(statut="en_cours", apprenant=self.autre)
        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["data"]["evaluation"]["en_cours"])

    # ── Streaming SSE ──────────────────────────────────────────────────────
    @patch("courses.services.chat_tuteur.stream_llm")
    def test_stream_envoie_les_deltas_et_persiste(self, mocked_stream):
        def faux_flux(*args, **kwargs):
            yield {"type": "delta", "text": "Bonjour "}
            yield {"type": "delta", "text": "le monde"}
            yield {"type": "done", "provider": "mock", "model": "test", "tokens": 3}

        mocked_stream.side_effect = faux_flux
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/stream/",
            {"contenu": "Explique-moi."}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r["Content-Type"])
        corps = b"".join(r.streaming_content).decode()
        self.assertIn("Bonjour ", corps)
        self.assertIn("le monde", corps)
        self.assertIn("event: done", corps)

        assistant = MessageTuteur.objects.filter(role="assistant").first()
        self.assertEqual(assistant.contenu, "Bonjour le monde")
        self.assertEqual(assistant.statut, "termine")
        self.assertTrue(assistant.sources)
        self.assertEqual(assistant.sources[0]["bloc_id"], self.bloc.id)
        self.assertEqual(MessageTuteur.objects.filter(role="user").count(), 1)

    def test_stream_salutation_repond_sans_modele(self):
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/stream/",
            {"contenu": "Bonjour"}, format="json")
        corps = b"".join(r.streaming_content).decode()
        self.assertIn("Je suis votre tuteur", corps)
        self.assertIn("event: done", corps)

    @patch("courses.services.chat_tuteur.stream_llm")
    def test_stream_erreur_ia_persiste_le_statut(self, mocked_stream):
        def flux_en_erreur(*args, **kwargs):
            yield {"type": "error", "message": "timeout"}

        mocked_stream.side_effect = flux_en_erreur
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/stream/",
            {"contenu": "Explique-moi."}, format="json")
        corps = b"".join(r.streaming_content).decode()
        self.assertIn("event: error", corps)
        assistant = MessageTuteur.objects.filter(role="assistant").first()
        self.assertEqual(assistant.statut, "erreur")

    def test_stream_bloque_pendant_evaluation(self):
        self._passage_evaluation(statut="en_cours")
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/stream/",
            {"contenu": "Explique-moi."}, format="json")
        self.assertEqual(r.status_code, 423)
        self.assertEqual(MessageTuteur.objects.count(), 0)

    def test_stream_acces_refuse_sans_inscription(self):
        r = self.as_(self.autre).post(
            f"{API}/blocs/{self.bloc.id}/chat/stream/",
            {"contenu": "Explique-moi."}, format="json")
        self.assertEqual(r.status_code, 403)

    # ── Citations / sources ────────────────────────────────────────────────
    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_sources_incluent_le_bloc_courant(self, _mocked):
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi cette notion."}, format="json")
        sources = r.data["data"]["message"]["sources"]
        self.assertTrue(sources)
        self.assertEqual(sources[0]["bloc_id"], self.bloc.id)
        self.assertEqual(sources[0]["bloc_titre"], self.bloc.titre)
        self.assertTrue(sources[0]["principal"])
        self.assertIn(self.sequence.titre, sources[0]["sequence_titre"])

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_sources_voisines_pertinentes(self, _mocked):
        voisin = BlocContenu.objects.create(
            sequence=self.sequence,
            titre="Les boucles for",
            type_bloc="texte",
            contenu_texte="Une boucle for répète un traitement.",
        )
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi les boucles for."}, format="json")
        ids = [s["bloc_id"] for s in r.data["data"]["message"]["sources"]]
        self.assertIn(self.bloc.id, ids)
        self.assertIn(voisin.id, ids)
        self.assertLessEqual(len(ids), 3)

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_historique_conserve_les_sources(self, _mocked):
        self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi cette notion."}, format="json")
        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        assistant = [m for m in r.data["data"]["messages"] if m["role"] == "assistant"][0]
        self.assertTrue(assistant["sources"])

    # ── RAG documentaire ───────────────────────────────────────────────────
    def _pdf(self, texte: str, nom: str = "algo.pdf"):
        from reportlab.pdfgen import canvas

        tampon = io.BytesIO()
        doc = canvas.Canvas(tampon)
        doc.drawString(80, 750, texte)
        doc.save()
        self.bloc.fichier.save(nom, ContentFile(tampon.getvalue()), save=True)
        self.bloc.refresh_from_db()
        return os.path.basename(self.bloc.fichier.name)

    def test_decoupage_produit_des_extraits_avec_chevauchement(self):
        texte = "A" * 3000
        morceaux = rag.decouper(texte, taille=1000, chevauchement=200)
        self.assertGreaterEqual(len(morceaux), 3)
        self.assertTrue(all(len(m) <= 1000 for m in morceaux))
        self.assertEqual(morceaux[0][-200:], morceaux[1][:200])

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_rag_indexe_le_pdf_et_le_cite(self, mocked):
        nom = self._pdf("Une pile est une structure LIFO : dernier entre, premier sorti.")
        r = self.as_(self.appr).post(
            f"{API}/blocs/{self.bloc.id}/chat/",
            {"contenu": "Explique-moi la structure LIFO du document."}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        # indexation créée
        self.assertGreater(DocumentChunk.objects.filter(bloc=self.bloc).count(), 0)

        # le prompt contient l'extrait du document
        prompt = mocked.call_args[0][1]
        self.assertIn("EXTRAITS DE DOCUMENTS", prompt)
        self.assertIn("LIFO", prompt)
        self.assertIn(nom, prompt)

        # la réponse cite le document
        sources = r.data["data"]["message"]["sources"]
        documents = [s for s in sources if s.get("kind") == "document"]
        self.assertTrue(documents)
        self.assertEqual(documents[0]["document_nom"], nom)
        self.assertEqual(documents[0]["page"], 1)

    def test_rag_ne_fuit_pas_vers_un_autre_cours(self):
        autre_matiere = Matiere.objects.create(institution=self.inst, nom="Autre matière")
        autre_cours = Cours.objects.create(
            titre="Autre cours", institution=self.inst,
            annee_scolaire=self.annee, matiere=autre_matiere,
            groupe=self.groupe, enseignant=self.formateur,
        )
        autre_module = Module.objects.create(titre="M2", cours=autre_cours)
        autre_sequence = Sequence.objects.create(titre="S2", module=autre_module)
        autre_bloc = BlocContenu.objects.create(
            sequence=autre_sequence, titre="Secret", type_bloc="texte",
            contenu_texte="CONFIDENTIEL-ZETA",
        )
        DocumentChunk.objects.create(
            cours=autre_cours, bloc=autre_bloc, institution=self.inst,
            source_nom="secret.pdf", source_type="pdf", page=1,
            texte="Ceci contient le mot CONFIDENTIEL-ZETA.",
        )
        resultats = rag.rechercher(self.cours, "CONFIDENTIEL-ZETA")
        self.assertEqual(resultats, [])

    @patch("courses.services.chat_tuteur.call_llm", side_effect=_fake_llm)
    def test_rag_recherche_retourne_le_passage_le_plus_pertinent(self, _mocked):
        nom = self._pdf("Les boucles for répètent un traitement un nombre connu de fois.")
        rag.indexer_bloc(self.bloc)
        resultats = rag.rechercher(self.cours, "boucles for")
        self.assertTrue(resultats)
        self.assertIn("boucles for", resultats[0]["texte"].lower())
        self.assertEqual(resultats[0]["source_nom"], nom)

    # ── Quiz « Interroge-moi » ─────────────────────────────────────────────
    @patch("courses.services.quiz_tuteur.call_llm")
    def test_quiz_genere_sans_exposer_les_reponses(self, mocked):
        mocked.return_value = {"content": QUIZ_JSON, "error": None, "provider": "mock", "model": "test"}
        r = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        self.assertEqual(r.status_code, 200, r.data)
        questions = r.data["data"]["questions"]
        self.assertEqual(len(questions), 3)
        self.assertNotIn("bonne_reponse", questions[0])
        self.assertNotIn("explication", questions[0])
        self.assertEqual(len(questions[0]["options"]), 4)
        self.assertEqual(r.data["data"]["source"], "ia")
        self.assertEqual(QuizTuteur.objects.count(), 1)

    @patch("courses.services.quiz_tuteur.call_llm")
    def test_quiz_correction_et_score(self, mocked):
        mocked.return_value = {"content": QUIZ_JSON, "error": None, "provider": "mock", "model": "test"}
        gen = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        quiz_id = gen.data["data"]["quiz_id"]

        r = self.as_(self.appr).post(
            f"{API}/chat/quiz/{quiz_id}/corriger/",
            {"reponses": [1, 1, 1]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["data"]["score"], 100.0)
        self.assertTrue(all(d["correct"] for d in r.data["data"]["details"]))
        self.assertTrue(all("explication" in q for q in r.data["data"]["questions"]))

        quiz = QuizTuteur.objects.get(pk=quiz_id)
        self.assertEqual(quiz.statut, "corrige")

    @patch("courses.services.quiz_tuteur.call_llm")
    def test_quiz_mauvaises_reponses_score_zero(self, mocked):
        mocked.return_value = {"content": QUIZ_JSON, "error": None, "provider": "mock", "model": "test"}
        gen = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        quiz_id = gen.data["data"]["quiz_id"]
        r = self.as_(self.appr).post(
            f"{API}/chat/quiz/{quiz_id}/corriger/",
            {"reponses": [0, 0, 0]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["data"]["score"], 0.0)

    @patch("courses.services.quiz_tuteur.call_llm")
    def test_quiz_d_un_autre_apprenant_inaccessible(self, mocked):
        mocked.return_value = {"content": QUIZ_JSON, "error": None, "provider": "mock", "model": "test"}
        gen = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        quiz_id = gen.data["data"]["quiz_id"]
        r = self.as_(self.autre).post(
            f"{API}/chat/quiz/{quiz_id}/corriger/",
            {"reponses": [1, 1, 1]}, format="json")
        self.assertEqual(r.status_code, 404)

    @patch("courses.services.quiz_tuteur.call_llm")
    def test_quiz_json_invalide_utilise_le_secours(self, mocked):
        mocked.return_value = {"content": "ceci n'est pas du json", "error": None, "provider": "mock", "model": "test"}
        r = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["data"]["source"], "contenu")
        self.assertGreaterEqual(len(r.data["data"]["questions"]), 1)
        self.assertEqual(QuizTuteur.objects.count(), 1)

    @override_settings(AI_PROVIDER="mock")
    def test_quiz_mock_utilise_le_secours_sans_ia(self):
        r = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["data"]["source"], "contenu")
        self.assertGreaterEqual(len(r.data["data"]["questions"]), 1)

    @patch("courses.services.quiz_tuteur.call_llm")
    def test_quiz_sans_contenu_ni_ia_renvoie_502(self, mocked):
        mixed = json.dumps({"questions": []})
        mocked.return_value = {"content": mixed, "error": None, "provider": "mock", "model": "test"}
        bloc_vide = BlocContenu.objects.create(
            sequence=self.sequence, titre="Vidéo sans texte", type_bloc="video")
        r = self.as_(self.appr).post(f"{API}/blocs/{bloc_vide.id}/chat/quiz/")
        self.assertEqual(r.status_code, 502)

    def test_quiz_bloque_pendant_evaluation(self):
        self._passage_evaluation(statut="en_cours")
        r = self.as_(self.appr).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        self.assertEqual(r.status_code, 423)

    def test_quiz_acces_refuse_sans_inscription(self):
        r = self.as_(self.autre).post(f"{API}/blocs/{self.bloc.id}/chat/quiz/")
        self.assertEqual(r.status_code, 403)

    # ── Détection de difficulté / remédiation ──────────────────────────────
    def _conv(self):
        return ConversationTuteur.objects.create(
            apprenant=self.appr, bloc=self.bloc, cours=self.cours,
            institution=self.inst, titre=self.bloc.titre)

    def _msg(self, conv, texte):
        return MessageTuteur.objects.create(
            conversation=conv, role="user", contenu=texte, statut="termine")

    def test_difficulte_questions_repetees(self):
        conv = self._conv()
        for texte in ["Explique-moi les piles", "Les piles encore", "Je veux comprendre les piles"]:
            self._msg(conv, texte)
        d = difficulte.analyser(conv)
        self.assertEqual(d["niveau"], "difficulte")
        self.assertTrue(d["notions"])
        types = {a["type"] for a in d["actions"]}
        self.assertIn("quiz", types)
        self.assertIn("revoir_bloc", types)

    def test_pas_de_difficulte_sur_questions_variees(self):
        conv = self._conv()
        for texte in ["Qu'est-ce qu'une variable ?", "Comment fonctionne une boucle ?",
                      "Parle-moi des fonctions."]:
            self._msg(conv, texte)
        d = difficulte.analyser(conv)
        self.assertEqual(d["niveau"], "ok")
        self.assertEqual(d["actions"], [])

    def test_phrase_explicite_difficulte(self):
        conv = self._conv()
        for texte in ["Explique-moi ce bloc.", "Donne un exemple.", "Je ne comprends pas."]:
            self._msg(conv, texte)
        d = difficulte.analyser(conv)
        self.assertEqual(d["niveau"], "difficulte")
        self.assertTrue(d["message"])

    def test_difficulte_ignoree_si_trop_peu_de_messages(self):
        conv = self._conv()
        self._msg(conv, "les piles")
        self._msg(conv, "les piles")
        self.assertEqual(difficulte.analyser(conv)["niveau"], "ok")

    def test_api_expose_la_difficulte(self):
        r = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        conv = ConversationTuteur.objects.get(pk=r.data["data"]["conversation"]["id"])
        for texte in ["les piles", "les piles encore", "les piles toujours"]:
            self._msg(conv, texte)
        r2 = self.as_(self.appr).get(f"{API}/blocs/{self.bloc.id}/chat/")
        self.assertIn("difficulte", r2.data["data"])
        self.assertEqual(r2.data["data"]["difficulte"]["niveau"], "difficulte")
