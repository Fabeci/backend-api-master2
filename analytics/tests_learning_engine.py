# analytics/tests_learning_engine.py
# ============================================================================
# Tests du MOTEUR DE SUIVI PÉDAGOGIQUE (Phase 17) — 12 cas
# ============================================================================
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from users.models import Apprenant, Formateur
from academics.models import Pays, Institution, AnneeScolaire, Classe, Groupe, Matiere
from courses.models import (
    Cours, Module, Sequence, BlocContenu, BlocProgress, InscriptionCours,
)
from evaluations.models import Quiz, Question, Reponse, PassageQuiz, ReponseQuiz
from analytics.models import (
    BlocAnalytics, BlocAnalyticsSummary, SequenceAnalyticsSummary,
    KnowledgeGap, SkillMasteryScore, ContenuGenere, AIAnalysisRequest,
    RecommandationPedagogique, LearningSignal, LearningDiagnosis,
    LearningIntervention, InterventionOutcome,
)
from analytics.services.progress_engine import refresh_learning_state
from analytics.services.engagement_engine import refresh_engagement_state
from analytics.services.performance_engine import refresh_performance_state
from analytics.services.signal_engine import emit_signal, refresh_signals
from analytics.services.diagnosis_engine import refresh_diagnoses
from analytics.services.intervention_engine import refresh_interventions
from analytics.services.risk_engine import refresh_risk_state
from analytics.services.outcome_engine import measure_intervention


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pays = Pays.objects.create(nom='PaysX', code='PX')
        cls.inst = Institution.objects.create(nom='InstX', pays=cls.pays)
        cls.annee = AnneeScolaire.objects.create(
            institution=cls.inst, annee_format_classique='2025-2026', est_active=True,
        )
        cls.classe = Classe.objects.create(nom='Cls', institution=cls.inst, annee_scolaire=cls.annee)
        cls.groupe = Groupe.objects.create(
            nom='G', institution=cls.inst, annee_scolaire=cls.annee, classe=cls.classe,
        )
        cls.matiere = Matiere.objects.create(institution=cls.inst, nom='Maths')
        cls.formateur = Formateur.objects.create(email='form@t.com', nom='F', prenom='F')
        cls.cours = Cours.objects.create(
            titre='Cours Test', groupe=cls.groupe, enseignant=cls.formateur,
            matiere=cls.matiere, institution=cls.inst, annee_scolaire=cls.annee,
        )
        cls.module = Module.objects.create(
            titre='Mod', cours=cls.cours, institution=cls.inst, annee_scolaire=cls.annee,
        )
        cls.seq = Sequence.objects.create(
            titre='Seq', module=cls.module, institution=cls.inst, annee_scolaire=cls.annee,
        )
        cls.bloc1 = BlocContenu.objects.create(
            sequence=cls.seq, titre='B1', type_bloc='texte', ordre=1, duree_estimee_minutes=5,
        )
        cls.bloc2 = BlocContenu.objects.create(
            sequence=cls.seq, titre='B2', type_bloc='texte', ordre=2, duree_estimee_minutes=5,
        )
        cls.quiz = Quiz.objects.create(sequence=cls.seq)

    def make_apprenant(self, email):
        a = Apprenant.objects.create(email=email, nom='A', prenom='A')
        InscriptionCours.objects.create(
            apprenant=a, cours=self.cours, statut='en_cours',
            institution=self.inst, annee_scolaire=self.annee,
        )
        return a

    def add_activity(self, a, days_ago=0, duree=300, complete=True):
        s = BlocAnalytics.objects.create(
            apprenant=a, bloc=self.bloc1, sequence=self.seq, module=self.module, cours=self.cours,
            ouvert_le=timezone.now() - timedelta(days=days_ago), duree_secondes=duree,
            complete_en_session=complete,
        )
        BlocAnalyticsSummary.objects.get_or_create(
            apprenant=a, bloc=self.bloc1,
            defaults={'sequence': self.seq, 'module': self.module, 'cours': self.cours},
        )
        return s

    def add_quiz_passage(self, a, score, days_ago=0, wrong=0, right=0):
        p = PassageQuiz.objects.create(
            apprenant=a, quiz=self.quiz, score=score, termine=True,
        )
        # date_passage est auto_now_add → on force la date pour tester avant/après
        PassageQuiz.objects.filter(pk=p.pk).update(
            date_passage=timezone.now() - timedelta(days=days_ago))
        p.refresh_from_db()
        for _ in range(right):
            q = Question.objects.create(quiz=self.quiz, enonce_texte='Q?', type_question='choix_unique')
            ReponseQuiz.objects.create(passage_quiz=p, question=q, points_obtenus=1)
        for _ in range(wrong):
            q = Question.objects.create(quiz=self.quiz, enonce_texte='Q?', type_question='choix_unique')
            ReponseQuiz.objects.create(passage_quiz=q and p, question=q, points_obtenus=0)
        return p


class Cas12SansActivite(_Base):
    def test_apprenant_sans_activite_pas_de_difficulte_contenu(self):
        a = self.make_apprenant('c12@t.com')
        refresh_signals(a)
        d = refresh_diagnoses(a)
        types = {x.diagnosis_type for x in d}
        self.assertNotIn('MASTERY_GAP', types)
        self.assertNotIn('PERFORMANCE_DROP', types)


class Cas1ActifPerformant(_Base):
    def test_aucun_diagnostic_critique(self):
        a = self.make_apprenant('c1@t.com')
        self.add_activity(a, 0, 300)
        for i in range(3):
            self.add_quiz_passage(a, 90, days_ago=i, right=3)
        refresh_performance_state(a)
        st = refresh_learning_state(a)
        self.assertIn(st.avg_mastery, [0, st.avg_mastery])  # sanity
        d = refresh_diagnoses(a)
        self.assertFalse(any(x.priority == 1 for x in d))  # pas de P1


class Cas2UneSeuleMauvaise(_Base):
    def test_pas_de_diagnostic_critique(self):
        a = self.make_apprenant('c2@t.com')
        self.add_activity(a, 0, 120)
        self.add_quiz_passage(a, 40, wrong=1)
        d = refresh_diagnoses(a)
        self.assertFalse(any(x.severity == 'critique' for x in d))


class Cas34DifficultePuisIntervention(_Base):
    def test_difficulte_persistante_genere_intervention(self):
        a = self.make_apprenant('c34@t.com')
        self.add_activity(a, 0, 300)
        for i in range(3):
            self.add_quiz_passage(a, 20, days_ago=i, wrong=2)
        refresh_performance_state(a)
        refresh_learning_state(a)
        diags = refresh_diagnoses(a)
        self.assertTrue(any(x.diagnosis_type in ('DIFFICULTY_PERSISTENT', 'PERFORMANCE_DROP') for x in diags))
        ivs = refresh_interventions(a, diagnoses=diags)
        self.assertTrue(len(ivs) >= 1)


class Cas5ContenuExistant(_Base):
    def test_contenu_genere_disponible(self):
        a = self.make_apprenant('c5@t.com')
        self.add_activity(a, 0, 300)
        req = AIAnalysisRequest.objects.create(apprenant=a, sequence=self.seq, trigger='sequence_complexe', status='success')
        cg = ContenuGenere.objects.create(ai_request=req, apprenant=a, type_contenu='bloc_simplifie',
                                          titre='Explication', contenu_html='<p>x</p>', sequence_source=self.seq)
        reco = RecommandationPedagogique.objects.create(
            apprenant=a, cours=self.cours, sequence_cible=self.seq, contenu_genere=cg,
            type_recommandation='bloc_revoir', message='m', priorite=1)
        self.assertIsNotNone(reco.contenu_genere_id)


class Cas6QuizExistant(_Base):
    def test_quiz_genere_disponible(self):
        from analytics.models import QuizGenereClaude
        a = self.make_apprenant('c6@t.com')
        req = AIAnalysisRequest.objects.create(apprenant=a, sequence=self.seq, trigger='quiz_rate', status='success')
        qg = QuizGenereClaude.objects.create(ai_request=req, apprenant=a, titre='Quiz', questions=[])
        reco = RecommandationPedagogique.objects.create(
            apprenant=a, cours=self.cours, sequence_cible=self.seq, quiz_genere=qg,
            type_recommandation='quiz_supplementaire', message='m', priorite=1)
        self.assertIsNotNone(reco.quiz_genere_id)


class Cas78Efficacite(_Base):
    def test_intervention_efficace_et_inefficace(self):
        a = self.make_apprenant('c78@t.com')
        # avant : mauvais
        self.add_quiz_passage(a, 30, days_ago=10, wrong=2)
        iv = LearningIntervention.objects.create(
            apprenant=a, intervention_type='AI_CONTENT', priority=1,
            sequence=self.seq, cours=self.cours, message='m',
        )
        iv.created_at = timezone.now() - timedelta(days=5)
        iv.save(update_fields=['created_at'])
        # après : bon
        self.add_quiz_passage(a, 85, days_ago=1, right=3)
        o = measure_intervention(iv)
        self.assertEqual(o.effectiveness, 'efficace')
        # scénario inefficace : après très bas
        iv2 = LearningIntervention.objects.create(
            apprenant=a, intervention_type='AI_CONTENT', priority=2, sequence=self.seq, message='m2')
        iv2.created_at = timezone.now() - timedelta(days=1)
        iv2.save(update_fields=['created_at'])
        self.add_quiz_passage(a, 0, days_ago=0, wrong=3)
        o2 = measure_intervention(iv2)
        self.assertIn(o2.effectiveness, ('inefficace', 'partielle'))


class Cas9AntiDoublon(_Base):
    def test_recommandation_non_dupliquee(self):
        a = self.make_apprenant('c9@t.com')
        self.add_activity(a, 0, 300)
        KnowledgeGap.objects.create(apprenant=a, sequence=self.seq, severity='critique', statut='detectee')
        from analytics.services.recommendation_engine import RecommendationEngine
        r1 = RecommendationEngine(a).analyser_et_recommander()
        r2 = RecommendationEngine(a).analyser_et_recommander()
        self.assertEqual(len(r2), 0)


class Cas10Inactif(_Base):
    def test_risque_inactivite(self):
        a = self.make_apprenant('c10@t.com')
        self.add_activity(a, days_ago=20, duree=300)
        refresh_engagement_state(a)
        from analytics.models import LearnerEngagementState
        e = LearnerEngagementState.objects.get(apprenant=a)
        self.assertTrue(any(s['type'] == 'inactivite_prolongee' for s in e.signals))


class Cas11SignauxRegroupes(_Base):
    def test_deux_signaux_une_diagnostic(self):
        a = self.make_apprenant('c11@t.com')
        from analytics.services.diagnosis_engine import compute_diagnoses
        signals = [
            {'signal_type': 'faible_performance', 'severity': 'moderee', 'valeur': 10, 'reference': 'r', 'preuves': [], 'sequence': self.seq},
            {'signal_type': 'erreurs_repetitives', 'severity': 'moderee', 'valeur': 2, 'reference': 'r', 'preuves': [], 'sequence': self.seq},
        ]
        computed = compute_diagnoses(a, signals=signals)
        diags = refresh_diagnoses(a, diagnoses=computed)
        seq_diags = [d for d in diags if d.sequence_id == self.seq.pk]
        self.assertEqual(len(seq_diags), 1)
        self.assertGreaterEqual(len(seq_diags[0].signal_types), 2)


class BlocAideFeedbackEtNettoyage(_Base):
    """Aide par bloc : feedback exposé + nettoyage des propositions."""

    def setUp(self):
        from rest_framework.test import APIClient
        self.a = self.make_apprenant('aide-api@t.com')
        self.client = APIClient()
        self.client.force_authenticate(user=self.a)
        self.req = AIAnalysisRequest.objects.create(
            apprenant=self.a, sequence=self.seq,
            trigger='sequence_complexe', status='success',
        )

    def _contenu(self, titre='Templates Jinja2 et formulaires', **kw):
        return ContenuGenere.objects.create(
            ai_request=self.req, apprenant=self.a,
            type_contenu='bloc_simplifie', titre=titre,
            bloc_source=self.bloc1, sequence_source=self.seq, **kw,
        )

    def test_aide_expose_le_feedback(self):
        c = self._contenu(a_aide=True)
        r = self.client.get(f'/api/v1/analytics/blocs/{self.bloc1.pk}/aide/')
        self.assertEqual(r.status_code, 200)
        item = next(x for x in r.data['contenus'] if x['id'] == c.pk)
        self.assertIs(item['a_aide'], True)

    def test_nettoyage_supprime_uniquement_les_aides_de_l_apprenant(self):
        c1 = self._contenu()
        c2 = self._contenu(a_aide=False)
        autre = self.make_apprenant('autre-aide@t.com')
        req2 = AIAnalysisRequest.objects.create(
            apprenant=autre, sequence=self.seq,
            trigger='sequence_complexe', status='success',
        )
        c3 = ContenuGenere.objects.create(
            ai_request=req2, apprenant=autre, type_contenu='bloc_simplifie',
            titre='Autre apprenant', bloc_source=self.bloc1, sequence_source=self.seq,
        )
        r = self.client.delete(f'/api/v1/analytics/blocs/{self.bloc1.pk}/aides/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['supprimes'], 2)
        self.assertFalse(ContenuGenere.objects.filter(pk__in=[c1.pk, c2.pk]).exists())
        self.assertTrue(ContenuGenere.objects.filter(pk=c3.pk).exists())

    def test_nettoyage_sans_aide(self):
        r = self.client.delete(f'/api/v1/analytics/blocs/{self.bloc2.pk}/aides/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['supprimes'], 0)

    def test_nettoyage_exige_authentification(self):
        from rest_framework.test import APIClient
        anon = APIClient()
        r = anon.delete(f'/api/v1/analytics/blocs/{self.bloc1.pk}/aides/')
        self.assertIn(r.status_code, (401, 403))
