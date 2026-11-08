"""The guard that refuses a secret, tested on the shapes that reached us.

The guard itself lives at the repository root (scripts/check_secrets.py), one
level above this application, because the hooks and the CI job that call it are
also at the root.
"""
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from check_secrets import SECRET_PATTERNS, is_forbidden  # noqa: E402


def matched_labels(line):
    return [label for label, pattern in SECRET_PATTERNS if pattern.search(line)]


class ForbiddenPaths(unittest.TestCase):
    def test_files_that_never_belong_in_git(self):
        for path in (
            ".env",
            "bot/.env",
            ".env.local",
            ".env.production",
            ".ENV",
            "keys/server.pem",
            "id_rsa",
            "credentials.json",
            "config/service-account-prod.json",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_forbidden(path))

    def test_files_that_are_fine(self):
        for path in (
            ".env.example",
            ".env.sample",
            "bot/.env.template",
            "app/utils/helplines.json",
            "docs/whatsapp_templates.json",
            "README.md",
            "docker-compose.yml",
            "app/services/menu.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_forbidden(path))


class SecretShapes(unittest.TestCase):
    def test_the_shapes_we_have_actually_leaked(self):
        cases = (
            (
                "ACCESS_TOKEN=EAAFakeTokenForTheSecretGuardTest0000000000000000",
                "Meta/WhatsApp access token",
            ),
            (
                "DATABASE_URL=postgresql://hllama:s3cr3t@db.example.net:5432/hllama",
                "Database URL with a password",
            ),
            ("key = 'sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD'", "OpenAI-style key"),
            ("aws = AKIAIOSFODNN7EXAMPLE", "AWS access key"),
            ("-----BEGIN RSA PRIVATE KEY-----", "Private key block"),
            ("GOOGLE_API_KEY=AIzaSyA1234567890abcdefghijklmnopqrstuv", "Google API key"),
        )
        for line, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, matched_labels(line))

    def test_what_must_not_cry_wolf(self):
        """A guard that fires on ordinary lines is switched off within a week,
        and then it protects nothing."""
        for line in (
            "DATABASE_URL=postgresql://localhost:5432/hllama",  # no credentials
            # local placeholders, as in .env.example and docker-compose.yml
            "DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/hllama",
            "DATABASE_URL: postgresql+psycopg://postgres:postgres@db:5432/hllama",
            "ELEVENLABS_API_KEY=",  # an empty template value
            "# set ACCESS_TOKEN to the value from the dashboard",
            "sk-",
            "def test_add_task_to_sketch(self):",
            'SECTIONS = {"1": "Rappels", "2": "Lieux de soins"}',
        ):
            with self.subTest(line=line):
                self.assertEqual(matched_labels(line), [])


if __name__ == "__main__":
    unittest.main()
