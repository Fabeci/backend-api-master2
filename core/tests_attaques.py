"""Tests d'attaques courantes : injection SQL, XSS stocké, IDOR/RBAC,
mass assignment, authentification, upload et CORS.

Lancer :
    python manage.py test core.tests_attaques --settings=master_backend_api.test_settings -v2
"""
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from academics.models import (
    AnneeScolaire,
    Classe,
    Departement,
    Filiere,
    Groupe,
    Inscription,
    Institution,
    Pays,
)
from users.models import Admin, Apprenant, Formateur, UserRole


API = "/api/v1"


class _AttaqueBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pays = Pays.objects.create(nom="Sénégal", code="SN")

        cls.institution = Institution.objects.create(nom="Sup'Info Attaque", pays=cls.pays)
        cls.autre_institution = Institution.objects.create(nom="Autre École", pays=cls.pays)

        cls.annee = AnneeScolaire.objects.create(
            institution=cls.institution,
            annee_format_classique="2025-2026",
            est_active=True,
        )
        cls.autre_annee = AnneeScolaire.objects.create(
            institution=cls.autre_institution,
            annee_format_classique="2025-2026",
            est_active=True,
        )

        cls.role_admin = UserRole.objects.get_or_create(name="Admin")[0]
        cls.role_apprenant = UserRole.objects.get_or_create(name="Apprenant")[0]
        cls.role_formateur = UserRole.objects.get_or_create(name="Formateur")[0]

        cls.admin = Admin.objects.create(
            email="admin.attaque@example.com", nom="Admin", prenom="Attaque",
            role=cls.role_admin, institution=cls.institution,
            is_active=True, is_staff=True,
        )
        cls.autre_admin = Admin.objects.create(
            email="admin.autre@example.com", nom="Autre", prenom="Admin",
            role=cls.role_admin, institution=cls.autre_institution,
            is_active=True, is_staff=True,
        )
        cls.apprenant = Apprenant.objects.create(
            email="apprenant.attaque@example.com", nom="Diallo", prenom="Awa",
            role=cls.role_apprenant, institution=cls.institution, is_active=True,
        )
        cls.apprenant2 = Apprenant.objects.create(
            email="apprenant2.attaque@example.com", nom="Fall", prenom="Moussa",
            role=cls.role_apprenant, institution=cls.institution, is_active=True,
        )
        cls.autre_apprenant = Apprenant.objects.create(
            email="apprenant.autre@example.com", nom="Ndiaye", prenom="Aminata",
            role=cls.role_apprenant, institution=cls.autre_institution, is_active=True,
        )
        cls.formateur = Formateur.objects.create(
            email="formateur.attaque@example.com", nom="Sow", prenom="Ibrahima",
            role=cls.role_formateur, institution=cls.institution, is_active=True,
        )
        cls.formateur.institutions.add(cls.institution)

        cls.departement = Departement.objects.create(
            nom="Informatique", institution=cls.institution,
        )
        cls.filiere = Filiere.objects.create(
            nom="Génie Logiciel", institution=cls.institution,
            departement=cls.departement,
        )
        cls.classe = Classe.objects.create(
            nom="L1 Info A", institution=cls.institution, annee_scolaire=cls.annee,
        )
        cls.classe.filieres.set([cls.filiere])
        cls.classe2 = Classe.objects.create(
            nom="L1 Info B", institution=cls.institution, annee_scolaire=cls.annee,
        )
        cls.classe2.filieres.set([cls.filiere])
        cls.groupe = Groupe.objects.create(
            nom="G1", institution=cls.institution,
            annee_scolaire=cls.annee, classe=cls.classe,
        )
        cls.groupe2 = Groupe.objects.create(
            nom="G2", institution=cls.institution,
            annee_scolaire=cls.annee, classe=cls.classe2,
        )
        cls.apprenant.groupe = cls.groupe
        cls.apprenant.save(update_fields=["groupe"])

        cls.inscription = Inscription.objects.create(
            apprenant=cls.apprenant, institution=cls.institution,
            annee_scolaire=cls.annee, classe=cls.classe, statut="actif",
        )
        cls.inscription2 = Inscription.objects.create(
            apprenant=cls.apprenant2, institution=cls.institution,
            annee_scolaire=cls.annee, classe=cls.classe2, statut="actif",
        )

        cls.autre_departement = Departement.objects.create(
            nom="Droit", institution=cls.autre_institution,
        )
        cls.autre_filiere = Filiere.objects.create(
            nom="Droit privé", institution=cls.autre_institution,
            departement=cls.autre_departement,
        )
        cls.autre_classe = Classe.objects.create(
            nom="L1 Droit", institution=cls.autre_institution,
            annee_scolaire=cls.autre_annee,
        )
        cls.autre_classe.filieres.set([cls.autre_filiere])
        cls.autre_inscription = Inscription.objects.create(
            apprenant=cls.autre_apprenant, institution=cls.autre_institution,
            annee_scolaire=cls.autre_annee, classe=cls.autre_classe, statut="actif",
        )

    def setUp(self):
        self._p_inst = patch(
            "core.tenant.default_institution_id", return_value=self.institution.id,
        )
        self._p_annee = patch(
            "core.tenant.default_annee_scolaire", return_value=self.annee,
        )
        self._p_inst.start()
        self._p_annee.start()
        self.addCleanup(self._p_inst.stop)
        self.addCleanup(self._p_annee.stop)
        cache.clear()
        self.client = APIClient()

    def as_(self, user):
        self.client.force_authenticate(user=user)
        return self.client


# ============================================================================
# 1. INJECTION SQL
# ============================================================================
class SQLInjectionTests(_AttaqueBase):
    def test_login_injection_sql_ne_contourne_pas_l_authentification(self):
        payloads = [
            ("' OR '1'='1", "x"),
            ("admin.attaque@example.com", "' OR 1=1 --"),
            ("admin.attaque@example.com' --", "x"),
        ]
        for email, password in payloads:
            with self.subTest(email=email):
                r = self.client.post(
                    f"{API}/login/",
                    {"email": email, "password": password},
                    format="json",
                )
                self.assertNotEqual(r.status_code, 200, r.data)
                self.assertIn(r.status_code, (400, 401, 429), r.data)

    def test_parametres_de_requete_injectes_ne_provoquent_pas_de_500(self):
        client = self.as_(self.admin)
        urls = [
            f"{API}/departements/?search=%27%20OR%201%3D1%20--",
            f"{API}/departements/?ordering=nom%3BDROP%20TABLE%20academics_departement%3B--",
            f"{API}/classes/?institution=1%20OR%201%3D1",
            f"{API}/search/?q=%27%20OR%201%3D1%20--",
            f"{API}/departements/1%27%20OR%20%271%27%3D%271/",
        ]
        for url in urls:
            with self.subTest(url=url):
                r = client.get(url)
                self.assertNotEqual(r.status_code, 500, r.content[:500])
                self.assertIn(r.status_code, (200, 400, 404), r.content[:500])

        # La table et l'objet de référence existent toujours.
        self.assertTrue(Departement.objects.filter(pk=self.departement.pk).exists())

    def test_payload_sql_est_stocke_comme_texte_et_non_execute(self):
        payload = "Robert'); DROP TABLE academics_departement;--"
        r = self.as_(self.admin).post(
            f"{API}/departements/", {"nom": payload}, format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        cree = Departement.objects.get(pk=r.data["data"]["id"])
        self.assertEqual(cree.nom, payload)
        self.assertTrue(Departement.objects.filter(pk=self.departement.pk).exists())
        cree.delete()


# ============================================================================
# 2. XSS STOCKÉ (côté API : aucune exécution, JSON littéral)
# ============================================================================
class XSSStoredTests(_AttaqueBase):
    def test_payload_xss_reste_du_texte_json(self):
        payload = '<script>alert(1)</script><img src=x onerror=alert(2)>'
        client = self.as_(self.admin)
        r = client.post(f"{API}/departements/", {"nom": payload}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        dep_id = r.data["data"]["id"]

        g = client.get(f"{API}/departements/{dep_id}/")
        self.assertEqual(g.status_code, 200, g.data)
        self.assertEqual(g.data["data"]["nom"], payload)
        self.assertIn("application/json", g["Content-Type"])

        Departement.objects.filter(pk=dep_id).delete()


# ============================================================================
# 3. IDOR / PÉRIMÈTRE
# ============================================================================
class IDORTests(_AttaqueBase):
    def test_apprenant_ne_voit_pas_l_inscription_d_un_autre(self):
        client = self.as_(self.apprenant)
        self.assertEqual(
            client.get(f"{API}/inscriptions-etab/{self.inscription.id}/").status_code,
            200,
        )
        self.assertEqual(
            client.get(f"{API}/inscriptions-etab/{self.inscription2.id}/").status_code,
            404,
        )

    def test_apprenant_ne_voit_pas_une_autre_classe(self):
        client = self.as_(self.apprenant)
        # Sa propre classe peut être autorisée ou refusée par le RBAC,
        # mais celle d'un autre apprenant ne doit jamais être accessible.
        self.assertIn(
            client.get(f"{API}/classes/{self.classe.id}/").status_code,
            (200, 403),
        )
        self.assertIn(
            client.get(f"{API}/classes/{self.classe2.id}/").status_code,
            (403, 404),
        )

    def test_admin_ne_voit_pas_les_objets_d_un_autre_etablissement(self):
        client = self.as_(self.admin)
        for url in (
            f"{API}/departements/{self.autre_departement.id}/",
            f"{API}/filieres/{self.autre_filiere.id}/",
            f"{API}/classes/{self.autre_classe.id}/",
            f"{API}/inscriptions-etab/{self.autre_inscription.id}/",
        ):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 404)


# ============================================================================
# 4. MASS ASSIGNMENT / ÉLÉVATION DE PRIVILÈGES
# ============================================================================
class MassAssignmentTests(_AttaqueBase):
    def test_apprenant_ne_peut_pas_changer_sa_classe_ou_son_groupe(self):
        client = self.as_(self.apprenant)
        r = client.patch(
            f"{API}/apprenants/{self.apprenant.id}/",
            {
                "inscription_classe": self.classe2.id,
                "groupe_id": self.groupe2.id,
                "is_superuser": True,
                "is_staff": True,
                "role": "Admin",
            },
            format="json",
        )
        self.assertIn(r.status_code, (200, 403), r.data)

        self.apprenant.refresh_from_db()
        self.assertEqual(self.apprenant.groupe_id, self.groupe.id)
        self.assertFalse(self.apprenant.is_superuser)
        self.assertFalse(self.apprenant.is_staff)
        self.assertEqual(self.apprenant.role.name, "Apprenant")
        self.inscription.refresh_from_db()
        self.assertEqual(self.inscription.classe_id, self.classe.id)

    def test_formateur_ne_peut_pas_s_ajouter_un_groupe(self):
        client = self.as_(self.formateur)
        r = client.patch(
            f"{API}/formateurs/{self.formateur.id}/",
            {
                "groupe_ids": [self.groupe.id],
                "institution_ids": [self.autre_institution.id],
            },
            format="json",
        )
        self.assertIn(r.status_code, (200, 403), r.data)

        self.formateur.refresh_from_db()
        self.assertFalse(self.formateur.groupes.filter(pk=self.groupe.pk).exists())
        self.assertFalse(
            self.formateur.institutions.filter(pk=self.autre_institution.pk).exists()
        )

    def test_admin_ne_peut_pas_creer_une_classe_dans_un_autre_etablissement(self):
        client = self.as_(self.admin)
        r = client.post(
            f"{API}/classes/",
            {
                "nom": "Classe hors établissement",
                "institution": self.autre_institution.id,
                "annee_scolaire": self.autre_annee.id,
                "filieres": [self.autre_filiere.id],
                "matieres": [],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(Classe.objects.filter(nom="Classe hors établissement").exists())

    def test_admin_ne_peut_pas_inscrire_un_apprenant_autre_etablissement(self):
        client = self.as_(self.admin)
        r = client.post(
            f"{API}/inscriptions-etab/",
            {
                "apprenant": self.autre_apprenant.id,
                "institution": self.institution.id,
                "annee_scolaire": self.annee.id,
                "classe": self.classe.id,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(
            Inscription.objects.filter(
                apprenant=self.autre_apprenant, institution=self.institution,
            ).exists()
        )


# ============================================================================
# 5. AUTHENTIFICATION / TOKENS / BRUTE FORCE
# ============================================================================
class AuthentificationTests(_AttaqueBase):
    def test_token_invalide_refuse(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token token-bidon-123")
        r = client.get(f"{API}/departements/")
        self.assertEqual(r.status_code, 401)

    @override_settings(AUTH_TOKEN_TTL=1, AUTH_TOKEN_RENEW_AFTER=0)
    def test_token_expire_refuse(self):
        Token.objects.filter(user=self.admin).delete()
        token = Token.objects.create(user=self.admin)
        Token.objects.filter(pk=token.pk).update(
            created=timezone.now() - timedelta(seconds=10)
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        r = client.get(f"{API}/departements/")
        self.assertEqual(r.status_code, 401)
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())

    def test_brute_force_login_est_limite(self):
        cache.clear()
        for _ in range(6):
            r = self.client.post(
                f"{API}/login/",
                {"email": "brute@example.com", "password": "Mauvais@123"},
                format="json",
            )
        self.assertEqual(r.status_code, 429, r.data)

    def test_password_reset_ne_revele_pas_l_existence_du_compte(self):
        cache.clear()
        connu = self.client.post(
            f"{API}/password-reset/",
            {"email": self.admin.email},
            format="json",
        )
        inconnu = self.client.post(
            f"{API}/password-reset/",
            {"email": "inconnu@example.com"},
            format="json",
        )
        self.assertEqual(connu.status_code, 200, connu.data)
        self.assertEqual(inconnu.status_code, 200, inconnu.data)
        self.assertEqual(connu.data.get("message"), inconnu.data.get("message"))


# ============================================================================
# 6. UPLOAD / CORS / EN-TÊTES
# ============================================================================
class UploadEtConfigTests(_AttaqueBase):
    def test_logo_refuse_extension_php(self):
        client = self.as_(self.admin)
        fichier = SimpleUploadedFile(
            "shell.php", b"<?php echo 'pwn'; ?>", content_type="application/x-php",
        )
        r = client.patch(
            f"{API}/institutions/{self.institution.id}/upload-logo/",
            {"logo": fichier}, format="multipart",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.institution.refresh_from_db()
        self.assertFalse(self.institution.logo)

    def test_logo_refuse_faux_fichier_png(self):
        client = self.as_(self.admin)
        fichier = SimpleUploadedFile(
            "faux.png", b"ceci n'est pas une image", content_type="image/png",
        )
        r = client.patch(
            f"{API}/institutions/{self.institution.id}/upload-logo/",
            {"logo": fichier}, format="multipart",
        )
        self.assertEqual(r.status_code, 400, r.data)
        self.institution.refresh_from_db()
        self.assertFalse(self.institution.logo)

    def test_cors_refuse_origine_inconnue_et_accepte_frontend(self):
        r = self.client.get(f"{API}/", HTTP_ORIGIN="http://evil.example")
        self.assertNotIn("Access-Control-Allow-Origin", r)

        r = self.client.get(f"{API}/", HTTP_ORIGIN="http://localhost:4200")
        self.assertEqual(
            r.get("Access-Control-Allow-Origin"), "http://localhost:4200",
        )

    def test_entete_anti_clickjacking(self):
        r = self.client.get(f"{API}/")
        self.assertEqual(r.get("X-Frame-Options"), "DENY")
