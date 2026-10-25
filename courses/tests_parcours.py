# courses/tests_parcours.py
# ============================================================================
# Tests du moteur de parcours (déblocage progressif, validation, reprise)
# ============================================================================
from django.test import TestCase
from django.utils import timezone

from users.models import Apprenant, Formateur
from academics.models import Pays, Institution, AnneeScolaire, Classe, Groupe, Matiere
from courses.models import (
    Cours, Module, Sequence, BlocContenu, BlocProgress, InscriptionCours,
)
from analytics.models import BlocAnalyticsSummary
from courses.parcours_engine import (
    build_parcours, resume_position, is_bloc_unlocked_for, validate_block, bloc_est_valide,
)


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pays = Pays.objects.create(nom='PX', code='PX')
        cls.inst = Institution.objects.create(nom='IX', pays=cls.pays)
        cls.annee = AnneeScolaire.objects.create(institution=cls.inst, annee_format_classique='2025-2026', est_active=True)
        cls.classe = Classe.objects.create(nom='C', institution=cls.inst, annee_scolaire=cls.annee)
        cls.groupe = Groupe.objects.create(nom='G', institution=cls.inst, annee_scolaire=cls.annee, classe=cls.classe)
        cls.matiere = Matiere.objects.create(institution=cls.inst, nom='M')
        cls.formateur = Formateur.objects.create(email='f@t.com', nom='F', prenom='F')
        cls.cours = Cours.objects.create(
            titre='Cours', groupe=cls.groupe, enseignant=cls.formateur,
            matiere=cls.matiere, institution=cls.inst, annee_scolaire=cls.annee,
        )
        cls.m1 = Module.objects.create(titre='M1', cours=cls.cours, ordre=1, institution=cls.inst, annee_scolaire=cls.annee)
        cls.m2 = Module.objects.create(titre='M2', cours=cls.cours, ordre=2, institution=cls.inst, annee_scolaire=cls.annee)
        cls.s1 = Sequence.objects.create(titre='S1', module=cls.m1, ordre=1, institution=cls.inst, annee_scolaire=cls.annee)
        cls.s2 = Sequence.objects.create(titre='S2', module=cls.m1, ordre=2, institution=cls.inst, annee_scolaire=cls.annee)
        cls.s3 = Sequence.objects.create(titre='S3', module=cls.m2, ordre=1, institution=cls.inst, annee_scolaire=cls.annee)
        cls.b1 = BlocContenu.objects.create(sequence=cls.s1, titre='B1', type_bloc='texte', ordre=1, duree_estimee_minutes=10)
        cls.b2 = BlocContenu.objects.create(sequence=cls.s1, titre='B2', type_bloc='texte', ordre=2, duree_estimee_minutes=10)
        cls.b3 = BlocContenu.objects.create(sequence=cls.s2, titre='B3', type_bloc='texte', ordre=1, duree_estimee_minutes=10)
        cls.b4 = BlocContenu.objects.create(sequence=cls.s3, titre='B4', type_bloc='texte', ordre=1, duree_estimee_minutes=10)

    def learner(self, email='l@t.com'):
        a = Apprenant.objects.create(email=email, nom='L', prenom='L')
        InscriptionCours.objects.create(apprenant=a, cours=self.cours, statut='en_cours',
                                        institution=self.inst, annee_scolaire=self.annee)
        return a

    def consult(self, a, bloc):
        """Simule une consultation suffisante → validation possible."""
        BlocAnalyticsSummary.objects.update_or_create(
            apprenant=a, bloc=bloc,
            defaults={'sequence': bloc.sequence, 'module': bloc.sequence.module,
                      'cours': self.cours, 'duree_totale_sec': (bloc.duree_estimee_minutes or 0) * 60,
                      'scroll_max_pct': 90, 'derniere_ouverture': timezone.now()},
        )


class FirstLock(_Base):
    def test_premier_bloc_debloque_suivant_verrouille(self):
        a = self.learner()
        parc = build_parcours(a, self.cours)
        blocs = parc['modules'][0]['sequences'][0]['blocs']
        self.assertFalse(blocs[0]['verrouille'])
        self.assertTrue(blocs[1]['verrouille'])


class ValidateUnlocksNext(_Base):
    def test_valider_debloque_le_suivant(self):
        a = self.learner()
        self.consult(a, self.b1)
        validate_block(a, self.b1)
        ok, _ = is_bloc_unlocked_for(a, self.b2)
        self.assertTrue(ok)
        # idempotence
        r1 = validate_block(a, self.b1)
        r2 = validate_block(a, self.b1)
        self.assertTrue(r1['ok'] and r2['ok'])
        self.assertEqual(BlocProgress.objects.filter(apprenant=a, bloc=self.b1).count(), 1)


class OptionalDoesNotBlock(_Base):
    def test_bloc_facultatif_ne_bloque_pas(self):
        a = self.learner()
        self.b2.est_obligatoire = False
        self.b2.save()
        self.consult(a, self.b1)
        validate_block(a, self.b1)
        # b2 facultatif non validé ne doit PAS bloquer b3 (séquence 2)
        ok, _ = is_bloc_unlocked_for(a, self.b3)
        self.assertTrue(ok)


class SequenceThenModule(_Base):
    def test_sequence_et_module(self):
        a = self.learner()
        for b in (self.b1, self.b2):
            self.consult(a, b); validate_block(a, b)
        # séquence 2 doit être débloquée
        parc = build_parcours(a, self.cours)
        seqs = parc['modules'][0]['sequences']
        self.assertFalse(seqs[1]['verrouille'])
        # valider s2 → module 2 débloqué
        self.consult(a, self.b3); validate_block(a, self.b3)
        parc = build_parcours(a, self.cours)
        self.assertFalse(parc['modules'][1]['verrouille'])


class LockedAccess(_Base):
    def test_acces_bloc_verrouille_interdit(self):
        a = self.learner()
        ok, raison = is_bloc_unlocked_for(a, self.b2)
        self.assertFalse(ok)
        self.assertIsNotNone(raison)


class Resume(_Base):
    def test_reprise_premier_non_valide(self):
        a = self.learner()
        pos = resume_position(a, self.cours)
        self.assertEqual(pos['bloc_id'], self.b1.pk)
        self.consult(a, self.b1); validate_block(a, self.b1)
        pos = resume_position(a, self.cours)
        self.assertEqual(pos['bloc_id'], self.b2.pk)
