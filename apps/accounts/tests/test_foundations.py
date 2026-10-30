from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase, override_settings

from apps.accounts.services import check_database


@override_settings(
    SECURE_SSL_REDIRECT=False,
    ALLOWED_HOSTS=["testserver"],
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class FoundationTests(SimpleTestCase):
    def test_home_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BroYouOweMe")

    @patch("apps.accounts.services.connection")
    def test_health_service_executes_database_probe(self, connection):
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        self.assertTrue(check_database())
        cursor.execute.assert_called_once_with("SELECT 1")

    @patch("apps.accounts.views.check_database", return_value=True)
    def test_health_success(self, probe):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")
        probe.assert_called_once()

    @patch("apps.accounts.views.check_database", side_effect=OperationalError("secret connection details"))
    def test_database_failure_is_503_without_connection_details(self, probe):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertNotContains(response, "secret", status_code=503)

    @patch("apps.accounts.views.check_database")
    def test_health_rejects_writes(self, probe):
        self.assertEqual(self.client.post("/health").status_code, 405)
        probe.assert_not_called()

    @override_settings(SECURE_SSL_REDIRECT=True)
    @patch("apps.accounts.views.check_database", return_value=True)
    def test_container_health_probe_does_not_redirect(self, probe):
        self.assertEqual(self.client.get("/health").status_code, 200)
