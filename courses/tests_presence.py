"""Feuille de présence : une séance future ne marque pas les apprenants absents."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from academics.models import (
    AnneeScolaire, Classe, Groupe, Institution, Matiere, Pays,
)
from courses.models import Cours, InscriptionCours, Participation, Session
from users.models import Apprenant, Formateur, UserRole


class PresenceInitialeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        pays = Pays.objects.create(nom='Sénégal', code='SN')
        inst = Institution.objects.create(nom="Sup'Info", pays=pays)
        annee = AnneeScolaire.objects.create(
            institution=inst, annee_format_classique='2025-2026', est_active=True,
        )
        classe = Classe.objects.create(nom='L3', institution=inst, annee_scolaire=annee)
        groupe = Groupe.objects.create(
            nom='G1', institution=inst, annee_scolaire=annee, classe=classe,
        )
        matiere = Matiere.objects.create(institution=inst, nom='Dev')
        formateur = Formateur.objects.create(
            email='form.presence@example.com', nom='F', prenom='P',
            institution=inst, is_active=True,
        )
        role = UserRole.objects.get_or_create(name='Apprenant')[0]
        apprenant = Apprenant.objects.create(
            email='app.presence@example.com', nom='A', prenom='P',
            role=role, institution=inst, groupe=groupe,
            annee_scolaire_active=annee, is_active=True,
        )
        cls.cours = Cours.objects.create(
            titre='Cours', groupe=groupe, enseignant=formateur,
            matiere=matiere, institution=inst, annee_scolaire=annee,
        )
        InscriptionCours.objects.create(
            apprenant=apprenant, cours=cls.cours, statut='en_cours',
            institution=inst, annee_scolaire=annee,
        )
        cls.apprenant = apprenant
        cls.formateur = formateur

    def test_seance_future_cree_une_presence_en_attente(self):
        session = Session.objects.create(
            titre='Séance future', cours=self.cours, formateur=self.formateur,
            date_debut=timezone.now() + timedelta(days=2),
            date_fin=timezone.now() + timedelta(days=2, hours=2),
            institution=self.cours.institution,
            annee_scolaire=self.cours.annee_scolaire,
        )
        participation = Participation.objects.get(
            session=session, apprenant=self.apprenant,
        )
        self.assertEqual(participation.statut, 'en_attente')
        self.assertEqual(participation.source, 'auto')

    def test_seance_passee_cree_aussi_une_presence_non_marquee(self):
        session = Session.objects.create(
            titre='Séance passée', cours=self.cours, formateur=self.formateur,
            date_debut=timezone.now() - timedelta(days=2),
            date_fin=timezone.now() - timedelta(days=2) + timedelta(hours=2),
            institution=self.cours.institution,
            annee_scolaire=self.cours.annee_scolaire,
        )
        participation = Participation.objects.get(
            session=session, apprenant=self.apprenant,
        )
        self.assertEqual(participation.statut, 'en_attente')
