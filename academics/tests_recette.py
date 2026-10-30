"""Tests de recette : département sans responsable, filière par département,
paramètres généraux (langue / fuseau horaire)."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from academics.models import (
    AnneeScolaire,
    Departement,
    Filiere,
    Institution,
    Pays,
)
from users.models import Admin, UserRole


class _RecetteBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pays = Pays.objects.create(nom="Sénégal", code="SN")
        cls.institution = Institution.objects.create(nom="Sup'Info", pays=cls.pays)
        cls.annee = AnneeScolaire.objects.create(
            institution=cls.institution,
            annee_format_classique="2025-2026",
            est_active=True,
        )
        cls.role_admin = UserRole.objects.get_or_create(name="Admin")[0]
        cls.admin = Admin.objects.create(
            email="admin.recette@example.com",
            nom="Admin",
            prenom="Recette",
            role=cls.role_admin,
            institution=cls.institution,
            is_active=True,
            is_staff=True,
        )

    def setUp(self):
        # Le filtrage mono-établissement lit le tenant : on l'aligne sur le test.
        self._tenant_patch = patch(
            "core.tenant.default_institution_id", return_value=self.institution.id,
        )
        self._tenant_patch.start()
        self.addCleanup(self._tenant_patch.stop)

        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)


class DepartementRecetteTests(_RecetteBase):
    def test_creation_sans_responsable_et_institution_auto(self):
        r = self.client.post(
            "/api/v1/departements/",
            {"nom": "Département Informatique"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)

        dep = Departement.objects.get(pk=r.data["data"]["id"])
        self.assertIsNone(dep.responsable_academique_id)
        self.assertEqual(dep.institution_id, self.institution.id)

        listing = self.client.get("/api/v1/departements/")
        self.assertEqual(listing.status_code, 200)
        self.assertTrue(any(x["id"] == dep.id for x in listing.data["data"]))

        upd = self.client.patch(
            f"/api/v1/departements/{dep.id}/",
            {"nom": "Département Informatique et Réseaux"},
            format="json",
        )
        self.assertEqual(upd.status_code, 200, upd.data)

        dele = self.client.delete(f"/api/v1/departements/{dep.id}/")
        self.assertIn(dele.status_code, (200, 204))
        self.assertFalse(Departement.objects.filter(pk=dep.id).exists())


class FiliereRecetteTests(_RecetteBase):
    def test_creation_filiere_par_departement_sans_domaine(self):
        dep = Departement.objects.create(
            nom="Informatique", institution=self.institution,
        )
        r = self.client.post(
            "/api/v1/filieres/",
            {"nom": "Génie Logiciel", "departement": dep.id},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)

        filiere = Filiere.objects.get(pk=r.data["data"]["id"])
        self.assertEqual(filiere.departement_id, dep.id)
        self.assertIsNone(filiere.domaine_etude_id)
        self.assertEqual(filiere.institution_id, self.institution.id)
        self.assertEqual(r.data["data"]["departement_label"], "Informatique")
        self.assertIsNone(r.data["data"]["domaine_etude"])

    def test_filiere_refuse_departement_autre_institution(self):
        autre = Institution.objects.create(nom="Autre", pays=self.pays)
        dep = Departement.objects.create(nom="Autre département", institution=autre)
        r = self.client.post(
            "/api/v1/filieres/",
            {"nom": "Filière hors établissement", "departement": dep.id},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)


class ParametresGenerauxRecetteTests(_RecetteBase):
    def test_langue_et_fuseau_enregistres_et_recharges(self):
        r = self.client.patch(
            "/api/v1/settings/institution/",
            {"langue_defaut": "en", "fuseau_horaire": "Africa/Dakar"},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)

        g = self.client.get("/api/v1/settings/institution/")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.data["data"]["langue_defaut"], "en")
        self.assertEqual(g.data["data"]["fuseau_horaire"], "Africa/Dakar")

    def test_langue_non_supportee_refusee(self):
        r = self.client.patch(
            "/api/v1/settings/institution/",
            {"langue_defaut": "ar"},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
