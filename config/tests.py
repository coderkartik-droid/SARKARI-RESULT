import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase
from django.urls import reverse


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ProductionSettingsTests(SimpleTestCase):
    def load_production_settings(self, secret_key, allowed_hosts):
        env = os.environ.copy()
        env.update(
            {
                "DJANGO_SETTINGS_MODULE": "config.settings.production",
                "DJANGO_SECRET_KEY": secret_key,
                "DJANGO_ALLOWED_HOSTS": allowed_hosts,
                "DB_ENGINE": "django.db.backends.sqlite3",
                "DB_NAME": ":memory:",
            }
        )
        return subprocess.run(
            [
                sys.executable,
                "-c",
                "import config.settings.production; print('settings-loaded')",
            ],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_missing_secret_is_rejected(self):
        result = self.load_production_settings("", "example.com")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_SECRET_KEY", result.stderr)
        self.assertNotIn("settings-loaded", result.stdout)

    def test_short_secret_is_rejected(self):
        result = self.load_production_settings("too-short", "example.com")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("at least 50 characters", result.stderr)

    def test_wildcard_allowed_host_is_rejected(self):
        result = self.load_production_settings("x" * 64, "*")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DJANGO_ALLOWED_HOSTS", result.stderr)

    def test_valid_production_configuration_loads(self):
        result = self.load_production_settings("x" * 64, "example.com,www.example.com")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("settings-loaded", result.stdout)


class HealthEndpointTests(SimpleTestCase):
    def test_health_without_trailing_slash_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ok"})

    def test_health_with_trailing_slash_returns_ok(self):
        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content), {"status": "ok"})

    def test_health_is_served_directly_without_a_redirect(self):
        for url in ("/health", "/health/"):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(response.has_header("Location"))

    def test_health_named_urls_resolve(self):
        self.assertEqual(reverse("health"), "/health")
        self.assertEqual(reverse("health_slash"), "/health/")

    def test_health_payload_is_exactly_the_status_key(self):
        response = self.client.get("/health/")

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(sorted(json.loads(response.content)), ["status"])

    def test_health_body_exposes_no_configuration_or_credentials(self):
        response = self.client.get("/health")
        body = response.content.decode("utf-8").lower()

        for leaked in ("secret", "api_key", "password", "database", "debug", "token"):
            self.assertNotIn(leaked, body)
        self.assertNotIn("traceback", body)

    def test_health_rejects_non_get_requests(self):
        response = self.client.post("/health")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_health_does_not_require_authentication(self):
        # No session, no login: a liveness probe must stay reachable.
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
