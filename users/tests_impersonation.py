"""Connexion admin « en tant que » : garde-fous et audit."""
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from locations.models import Pays
from users.models import Admin, Apprenant, ImpersonationLog, UserRole
from academics.models import Institution, AnneeScolaire


class ImpersonationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        pays = Pays.objects.create(nom='Sénégal', code='SN')
        cls.inst = Institution.objects.create(nom="Sup'Info", pays=pays)
        cls.autre_inst = Institution.objects.create(nom='Autre', pays=pays)
        cls.annee = AnneeScolaire.objects.create(
            institution=cls.inst, annee_format_classique='2025-2026', est_active=True,
        )
        cls.admin_role = UserRole.objects.get_or_create(name='Admin')[0]
        cls.appr_role = UserRole.objects.get_or_create(name='Apprenant')[0]

        cls.admin = Admin.objects.create(
            email='admin.imp@example.com', nom='Admin', prenom='Imp',
            role=cls.admin_role, institution=cls.inst, is_active=True, is_staff=True,
        )
        cls.autre_admin = Admin.objects.create(
            email='admin2.imp@example.com', nom='Admin2', prenom='Imp',
            role=cls.admin_role, institution=cls.inst, is_active=True, is_staff=True,
        )
        cls.apprenant = Apprenant.objects.create(
            email='app.imp@example.com', nom='App', prenom='Test',
            role=cls.appr_role, institution=cls.inst, is_active=True,
        )
        cls.apprenant_autre = Apprenant.objects.create(
            email='app.autre@example.com', nom='Autre', prenom='Test',
            role=cls.appr_role, institution=cls.autre_inst, is_active=True,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_admin_peut_impersonner_un_apprenant(self):
        r = self.client.post(f'/api/v1/impersonation/{self.apprenant.pk}/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data['data']['impersonation'])
        self.assertEqual(r.data['data']['user']['id'], self.apprenant.pk)
        self.assertTrue(Token.objects.filter(user=self.apprenant).exists())
        self.assertTrue(
            ImpersonationLog.objects.filter(
                admin=self.admin, target=self.apprenant,
            ).exists()
        )

    def test_admin_ne_peut_pas_impersonner_un_autre_admin(self):
        r = self.client.post(f'/api/v1/impersonation/{self.autre_admin.pk}/')
        self.assertEqual(r.status_code, 403, r.data)

    def test_apprenant_ne_peut_pas_impersonner(self):
        self.client.force_authenticate(user=self.apprenant)
        r = self.client.post(f'/api/v1/impersonation/{self.autre_admin.pk}/')
        self.assertEqual(r.status_code, 403, r.data)

    def test_admin_ne_peut_pas_impersonner_hors_etablissement(self):
        r = self.client.post(f'/api/v1/impersonation/{self.apprenant_autre.pk}/')
        self.assertEqual(r.status_code, 403, r.data)

    def test_admin_ne_peut_pas_impersonner_son_propre_compte(self):
        r = self.client.post(f'/api/v1/impersonation/{self.admin.pk}/')
        self.assertEqual(r.status_code, 400, r.data)
