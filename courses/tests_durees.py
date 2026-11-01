"""Durées calculées : module et séquence = somme des durées des blocs."""
from django.test import TestCase

from academics.models import (
    AnneeScolaire, Classe, Groupe, Institution, Matiere, Pays,
)
from courses.models import BlocContenu, Cours, Module, Sequence
from courses.serializers import ModuleSerializer, SequenceSerializer
from users.models import Formateur


class DureesCalculeesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        pays = Pays.objects.create(nom='Sénégal', code='SN')
        inst = Institution.objects.create(nom="Sup'Info", pays=pays)
        annee = AnneeScolaire.objects.create(
            institution=inst, annee_format_classique='2025-2026', est_active=True,
        )
        classe = Classe.objects.create(
            nom='L3', institution=inst, annee_scolaire=annee,
        )
        groupe = Groupe.objects.create(
            nom='G1', institution=inst, annee_scolaire=annee, classe=classe,
        )
        matiere = Matiere.objects.create(institution=inst, nom='Dev')
        formateur = Formateur.objects.create(
            email='form.duree@example.com', nom='F', prenom='D',
            institution=inst, is_active=True,
        )
        cls.cours = Cours.objects.create(
            titre='Cours', groupe=groupe, enseignant=formateur,
            matiere=matiere, institution=inst, annee_scolaire=annee,
        )
        cls.module = Module.objects.create(
            titre='Module', cours=cls.cours, institution=inst,
            annee_scolaire=annee,
        )
        cls.seq1 = Sequence.objects.create(
            titre='S1', module=cls.module, institution=inst,
            annee_scolaire=annee, ordre=1,
        )
        cls.seq2 = Sequence.objects.create(
            titre='S2', module=cls.module, institution=inst,
            annee_scolaire=annee, ordre=2,
        )
        BlocContenu.objects.create(
            sequence=cls.seq1, titre='B1', type_bloc='texte',
            ordre=1, duree_estimee_minutes=10,
        )
        BlocContenu.objects.create(
            sequence=cls.seq1, titre='B2', type_bloc='texte',
            ordre=2, duree_estimee_minutes=20,
        )
        BlocContenu.objects.create(
            sequence=cls.seq2, titre='B3', type_bloc='texte',
            ordre=1, duree_estimee_minutes=5,
        )

    def test_duree_sequence_somme_des_blocs(self):
        self.assertEqual(self.seq1.duree_totale_minutes, 30)
        self.assertEqual(self.seq2.duree_totale_minutes, 5)

    def test_duree_module_somme_des_sequences_et_blocs(self):
        self.assertEqual(self.module.duree_totale_minutes, 35)

    def test_api_module_expose_la_duree_calculee(self):
        data = ModuleSerializer(self.module).data
        self.assertEqual(data['duree_estimee'], 35)
        self.assertEqual(data['duree_totale_minutes'], 35)

    def test_api_sequence_expose_la_duree_calculee(self):
        data = SequenceSerializer(self.seq1).data
        self.assertEqual(data['duree_estimee'], 30)
        self.assertEqual(data['duree_totale_minutes'], 30)

    def test_duree_se_met_a_jour_apres_ajout_d_un_bloc(self):
        BlocContenu.objects.create(
            sequence=self.seq2, titre='B4', type_bloc='texte',
            ordre=2, duree_estimee_minutes=15,
        )
        self.assertEqual(self.seq2.duree_totale_minutes, 20)
        self.assertEqual(self.module.duree_totale_minutes, 50)
