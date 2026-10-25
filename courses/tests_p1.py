# courses/tests_p1.py
# ============================================================================
# Tests de non-régression des correctifs P1 :
#  - statuts d'inscription actifs
#  - score quiz en pourcentage
#  - verrouillage des questions déjà répondues
#  - soumission automatique / expiration d'examen
#  - conflits de séances
# ============================================================================
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from courses.tests_parcours import _Base
from courses.views import _cours_ids_inscrits
from courses.models import Session
from courses.serializers import SessionSerializer
from evaluations.models import (
    Evaluation, PassageEvaluation, PassageQuiz, Question, Reponse,
    ReponseQuestion, ReponseQuiz, Quiz,
)
from users.models import UserRole


def _role(name):
    return UserRole.objects.get_or_create(name=name)[0]


class ActiveEnrollmentTests(_Base):
    def test_en_cours_est_actif(self):
        a = self.learner()
        self.assertIn(self.cours.id, _cours_ids_inscrits(a))


class QuizScoreTests(_Base):
    def test_score_en_pourcentage(self):
        a = self.learner()
        quiz = Quiz.objects.create(sequence=self.s1, titre='Quiz test')
        question = Question.objects.create(
            quiz=quiz, enonce_texte='Q1', type_question='choix_unique', points=1,
        )
        bonne = Reponse.objects.create(question=question, texte='Bonne', est_correcte=True)
        passage = PassageQuiz.objects.create(apprenant=a, quiz=quiz)
        reponse = ReponseQuiz.objects.create(passage_quiz=passage, question=question)
        reponse.choix_selectionnes.add(bonne)

        self.assertEqual(passage.calculer_score(), 100.0)


class SessionConflictTests(_Base):
    def test_chevauchement_refuse(self):
        start = timezone.now() + timedelta(days=1)
        end = start + timedelta(hours=1)
        Session.objects.create(
            titre='S1', cours=self.cours, formateur=self.formateur,
            date_debut=start, date_fin=end,
        )

        serializer = SessionSerializer(data={
            'titre': 'S2',
            'cours_id': self.cours.id,
            'formateur_id': self.formateur.id,
            'date_debut': (start + timedelta(minutes=30)).isoformat(),
            'date_fin': (end + timedelta(minutes=30)).isoformat(),
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn('date_debut', serializer.errors)


class QuestionLockTests(_Base):
    def setUp(self):
        self.formateur.role = _role('Formateur')
        self.formateur.save(update_fields=['role'])
        self.apprenant = self.learner()
        self.apprenant.role = _role('Apprenant')
        self.apprenant.save(update_fields=['role'])

        self.evaluation = Evaluation.objects.create(
            cours=self.cours, enseignant=self.formateur,
            titre='E test', type_evaluation='structuree', bareme=10, est_publiee=True,
        )
        self.question = Question.objects.create(
            evaluation=self.evaluation, enonce_texte='Q', type_question='texte_long', points=1,
        )
        passage = PassageEvaluation.objects.create(
            apprenant=self.apprenant, evaluation=self.evaluation, numero_tentative=1,
        )
        ReponseQuestion.objects.create(passage_evaluation=passage, question=self.question)

    def test_suppression_question_repondue_refusee(self):
        client = APIClient()
        client.force_authenticate(user=self.formateur)
        response = client.delete(f'/api/v1/questions/{self.question.id}/')
        self.assertEqual(response.status_code, 400)

    def test_points_non_modifiables(self):
        client = APIClient()
        client.force_authenticate(user=self.formateur)
        response = client.patch(
            f'/api/v1/questions/{self.question.id}/', {'points': 5}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_enonce_modifiable(self):
        client = APIClient()
        client.force_authenticate(user=self.formateur)
        response = client.patch(
            f'/api/v1/questions/{self.question.id}/',
            {'enonce_texte': 'Q modifiée'}, format='json',
        )
        self.assertEqual(response.status_code, 200)


class ExamDurationTests(_Base):
    def setUp(self):
        self.apprenant = self.learner()
        self.apprenant.role = _role('Apprenant')
        self.apprenant.save(update_fields=['role'])
        self.evaluation = Evaluation.objects.create(
            cours=self.cours, enseignant=self.formateur,
            titre='E durée', type_evaluation='simple', bareme=10,
            est_publiee=True, duree_minutes=1,
        )

    def test_soumission_auto_acceptee(self):
        passage = PassageEvaluation.objects.create(
            apprenant=self.apprenant, evaluation=self.evaluation, numero_tentative=1,
        )
        client = APIClient()
        client.force_authenticate(user=self.apprenant)
        response = client.post(
            f'/api/v1/passages-evaluations/{passage.id}/soumettre/',
            {'auto': True}, format='json',
        )
        self.assertEqual(response.status_code, 200)

    def test_sauvegarde_apres_expiration_refusee(self):
        passage = PassageEvaluation.objects.create(
            apprenant=self.apprenant, evaluation=self.evaluation, numero_tentative=1,
        )
        PassageEvaluation.objects.filter(pk=passage.pk).update(
            date_debut=timezone.now() - timedelta(minutes=5),
        )
        client = APIClient()
        client.force_authenticate(user=self.apprenant)
        response = client.put(
            f'/api/v1/passages-evaluations/{passage.id}/sauvegarder/',
            {'reponse_texte': 'test'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
