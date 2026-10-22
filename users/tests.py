from django.test import TestCase

# Create your tests here.


# ════════════════════════════════════════════════════════════════════════════
# Tests — gestion normalisée des erreurs API (custom_exception_handler)
# ════════════════════════════════════════════════════════════════════════════
from django.test import TestCase
from rest_framework.exceptions import ValidationError, NotFound, PermissionDenied, NotAuthenticated
from users.utils import custom_exception_handler


class ExceptionHandlerFormatTests(TestCase):
    def test_validation_error_est_normalise(self):
        resp = custom_exception_handler(ValidationError({"email": ["Adresse déjà utilisée."]}), {})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.data["success"])
        self.assertEqual(resp.data["code"], "VALIDATION_ERROR")
        self.assertIn("email", resp.data["errors"])
        self.assertIn("email", resp.data["message"].lower())

    def test_not_found_code(self):
        resp = custom_exception_handler(NotFound(), {})
        self.assertEqual(resp.data["code"], "NOT_FOUND")
        self.assertFalse(resp.data["success"])

    def test_permission_denied_code(self):
        resp = custom_exception_handler(PermissionDenied(), {})
        self.assertEqual(resp.data["code"], "PERMISSION_DENIED")

    def test_not_authenticated_code(self):
        resp = custom_exception_handler(NotAuthenticated(), {})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.data["code"], "NOT_AUTHENTICATED")
