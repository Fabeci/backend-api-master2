# core/tests_rbac.py
# ============================================================================
# Tests d'accès RBAC — matrice (unitaire) + API réelle (par rôle).
# Lancer : python manage.py test core.tests_rbac -v2
# ============================================================================
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from users.models import User, UserRole, RolePermissionOverride
from locations.models import Pays
from academics.models import Institution, AnneeScolaire
from core.rbac import has_permission, display_role, get_scope


class RBACMatrixTests(TestCase):
    """Vérifie la matrice rôle → ressource → action."""

    def setUp(self):
        self.roles = {n: UserRole.objects.get_or_create(name=n)[0]
                      for n in ["SuperAdmin", "Admin", "Responsable", "Formateur", "Apprenant", "Parent"]}
        self.users = {}
        for name in self.roles:
            u = User.objects.create(email=f"{name.lower()}@t.t", nom="N", prenom="P",
                                    role=self.roles[name], is_active=True)
            u.set_password("Test@1234"); u.save()
            self.users[name] = u

    def test_admin_broad_access(self):
        u = self.users["Admin"]
        self.assertTrue(has_permission(u, "parents", "view"))
        self.assertTrue(has_permission(u, "parents", "create"))
        self.assertTrue(has_permission(u, "admins", "view"))
        self.assertTrue(has_permission(u, "users", "manage_permissions"))

    def test_responsable_limited(self):
        u = self.users["Responsable"]
        self.assertTrue(has_permission(u, "apprenants", "view"))
        self.assertTrue(has_permission(u, "parents", "view"))
        self.assertFalse(has_permission(u, "parents", "create"))
        self.assertFalse(has_permission(u, "admins", "view"))
        self.assertFalse(has_permission(u, "users", "manage_permissions"))

    def test_formateur_pedagogique(self):
        u = self.users["Formateur"]
        self.assertTrue(has_permission(u, "cours", "view"))
        self.assertTrue(has_permission(u, "cours", "create"))
        self.assertTrue(has_permission(u, "evaluations", "create"))
        self.assertFalse(has_permission(u, "parents", "view"))
        self.assertFalse(has_permission(u, "admins", "view"))
        self.assertFalse(has_permission(u, "users", "manage_permissions"))
        self.assertEqual(get_scope(u), "assigned")

    def test_apprenant_self(self):
        u = self.users["Apprenant"]
        self.assertTrue(has_permission(u, "cours", "view"))
        self.assertFalse(has_permission(u, "cours", "create"))
        self.assertFalse(has_permission(u, "parents", "view"))
        self.assertEqual(get_scope(u), "self")

    def test_parent_children(self):
        u = self.users["Parent"]
        self.assertTrue(has_permission(u, "cours", "view"))
        self.assertFalse(has_permission(u, "parents", "view"))
        self.assertFalse(has_permission(u, "cours", "edit"))
        self.assertEqual(get_scope(u), "children")

    def test_additive_permission(self):
        u = self.users["Formateur"]
        self.assertFalse(has_permission(u, "parents", "view"))
        u.permissions = ["parents.view"]; u.save()
        self.assertTrue(has_permission(u, "parents", "view"))
        self.assertFalse(has_permission(u, "parents", "create"))

    def test_db_override_wins(self):
        u = self.users["Formateur"]
        self.assertTrue(has_permission(u, "cours", "create"))
        RolePermissionOverride.objects.create(role="Formateur", resource="cours", action="create", allowed=False)
        self.assertFalse(has_permission(u, "cours", "create"))


class RBACApiTests(TestCase):
    """Vérifie l'application réelle des permissions sur les endpoints DRF."""

    def setUp(self):
        self.client = APIClient()
        self.pays = Pays.objects.create(code="TD", nom="Tchad")
        self.inst = Institution.objects.create(nom="Inst RBAC", pays=self.pays)
        self.annee = AnneeScolaire.objects.create(institution=self.inst, annee_format_classique="2025-2026", est_active=True)
        self.roles = {n: UserRole.objects.get_or_create(name=n)[0]
                      for n in ["Admin", "Responsable", "Formateur", "Apprenant", "Parent"]}

    def _auth(self, role_name):
        u = User.objects.create(email=f"api_{role_name.lower()}@t.t", nom="N", prenom="P",
                                role=self.roles[role_name], is_active=True,
                                institution=self.inst, annee_scolaire_active=self.annee)
        u.set_password("Test@1234"); u.save()
        token = Token.objects.create(user=u)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def test_formateur_cannot_list_parents(self):
        c = self._auth("Formateur")
        self.assertEqual(c.get("/api/v1/parents/").status_code, 403)

    def test_responsable_can_list_parents(self):
        c = self._auth("Responsable")
        self.assertEqual(c.get("/api/v1/parents/").status_code, 200)

    def test_responsable_cannot_list_admins(self):
        c = self._auth("Responsable")
        self.assertEqual(c.get("/api/v1/admins/").status_code, 403)

    def test_admin_can_list_admins(self):
        c = self._auth("Admin")
        self.assertEqual(c.get("/api/v1/admins/").status_code, 200)

    def test_apprenant_cannot_create_cours(self):
        c = self._auth("Apprenant")
        self.assertEqual(c.post("/api/v1/cours/", {"titre": "x"}, format="json").status_code, 403)

    def test_unauthenticated_denied(self):
        self.assertIn(APIClient().get("/api/v1/parents/").status_code, (401, 403))
