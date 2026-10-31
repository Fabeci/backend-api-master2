"""Tests des filières multiples d'une classe et de la filière d'inscription.

Couvre :
- une classe peut regrouper plusieurs filières du même établissement ;
- une classe refuse les filières/matières d'un autre établissement ;
- une inscription peut préciser sa filière, qui doit appartenir à la classe ;
- une classe à filière unique renseigne automatiquement la filière.
"""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from academics.models import (
    AnneeScolaire,
    Classe,
    Filiere,
    Institution,
    Matiere,
    Pays,
)
from users.models import Admin, Apprenant, UserRole


class _FiliereInscriptionBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pays = Pays.objects.create(nom="Sénégal", code="SN")
        cls.institution = Institution.objects.create(nom="Sup'Info", pays=cls.pays)
        cls.autre_institution = Institution.objects.create(nom="Autre école", pays=cls.pays)
        cls.annee = AnneeScolaire.objects.create(
            institution=cls.institution,
            annee_format_classique="2025-2026",
            est_active=True,
        )

        cls.role_admin = UserRole.objects.get_or_create(name="Admin")[0]
        cls.role_apprenant = UserRole.objects.get_or_create(name="Apprenant")[0]

        cls.admin = Admin.objects.create(
            email="admin.filiere@example.com",
            nom="Admin",
            prenom="Filière",
            role=cls.role_admin,
            institution=cls.institution,
            is_active=True,
            is_staff=True,
        )
        cls.apprenant = Apprenant.objects.create(
            email="apprenant.filiere@example.com",
            nom="Diallo",
            prenom="Awa",
            role=cls.role_apprenant,
            institution=cls.institution,
            is_active=True,
        )

        cls.filiere_info = Filiere.objects.create(
            nom="Informatique", institution=cls.institution,
        )
        cls.filiere_data = Filiere.objects.create(
            nom="Data Science", institution=cls.institution,
        )
        cls.filiere_autre = Filiere.objects.create(
            nom="Droit", institution=cls.autre_institution,
        )

        cls.classe_unique = Classe.objects.create(
            nom="L1 Informatique",
            institution=cls.institution,
            annee_scolaire=cls.annee,
        )
        cls.classe_unique.filieres.set([cls.filiere_info])

        cls.classe_multi = Classe.objects.create(
            nom="L3 Sciences du numérique",
            institution=cls.institution,
            annee_scolaire=cls.annee,
        )
        cls.classe_multi.filieres.set([cls.filiere_info, cls.filiere_data])

    def setUp(self):
        # Le filtrage mono-établissement lit le tenant : on l'aligne sur le test.
        self._tenant_patch = patch(
            "core.tenant.default_institution_id", return_value=self.institution.id,
        )
        self._tenant_patch.start()
        self.addCleanup(self._tenant_patch.stop)

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _post_inscription(self, **overrides):
        payload = {
            "apprenant": self.apprenant.id,
            "institution": self.institution.id,
            "annee_scolaire": self.annee.id,
            "classe": self.classe_multi.id,
        }
        payload.update(overrides)
        return self.client.post("/api/v1/inscriptions-etab/", payload, format="json")


class ClasseFiliereTests(_FiliereInscriptionBase):
    def test_classe_accepte_plusieurs_filieres_meme_institution(self):
        r = self.client.post(
            "/api/v1/classes/",
            {
                "nom": "Classe transversale",
                "institution": self.institution.id,
                "annee_scolaire": self.annee.id,
                "filieres": [self.filiere_info.id, self.filiere_data.id],
                "matieres": [],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertCountEqual(
            r.data["data"]["filieres"],
            [self.filiere_info.id, self.filiere_data.id],
        )
        self.assertEqual(len(r.data["data"]["filieres_data"]), 2)

    def test_classe_refuse_filiere_autre_institution(self):
        r = self.client.post(
            "/api/v1/classes/",
            {
                "nom": "Classe hors établissement",
                "institution": self.institution.id,
                "annee_scolaire": self.annee.id,
                "filieres": [self.filiere_info.id, self.filiere_autre.id],
                "matieres": [],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("filieres", r.data.get("errors", {}))

    def test_classe_refuse_matiere_autre_institution(self):
        matiere_autre = Matiere.objects.create(
            nom="Droit civil", institution=self.autre_institution,
        )
        r = self.client.post(
            "/api/v1/classes/",
            {
                "nom": "Classe matière hors établissement",
                "institution": self.institution.id,
                "annee_scolaire": self.annee.id,
                "filieres": [self.filiere_info.id],
                "matieres": [matiere_autre.id],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("matieres", r.data.get("errors", {}))


class InscriptionFiliereTests(_FiliereInscriptionBase):
    def test_inscription_auto_remplit_filiere_unique(self):
        r = self._post_inscription(classe=self.classe_unique.id)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["data"]["filiere"], self.filiere_info.id)
        self.assertEqual(r.data["data"]["filiere_display"], "Informatique")

    def test_inscription_accepte_filiere_de_la_classe_multi(self):
        r = self._post_inscription(filiere=self.filiere_data.id)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["data"]["filiere"], self.filiere_data.id)

    def test_inscription_refuse_filiere_hors_classe(self):
        r = self._post_inscription(
            classe=self.classe_unique.id,
            filiere=self.filiere_data.id,
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("filiere", r.data.get("errors", {}))

    def test_inscription_refuse_filiere_autre_institution(self):
        r = self._post_inscription(filiere=self.filiere_autre.id)
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn("filiere", r.data.get("errors", {}))

    def test_inscription_libre_avec_filiere(self):
        """Sans classe, une filière de l'établissement reste acceptée."""
        r = self._post_inscription(classe=None, filiere=self.filiere_data.id)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["data"]["filiere"], self.filiere_data.id)
