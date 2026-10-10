"""Deployment rendering and container environment regression checks."""

import json
import os
import subprocess
import sys
import unittest

from app.config import PROJECT_ROOT
from scripts.render_cloudrun import render_service


class DeploymentTests(unittest.TestCase):
    def test_manifest_references_secret_and_has_no_unresolved_tokens(self):
        template = (PROJECT_ROOT / "deploy/cloudrun.service.yaml").read_text(encoding="utf-8")
        values = {
            "SERVICE": "gemini-live-camera",
            "SERVICE_ACCOUNT": "test@example-project.iam.gserviceaccount.com",
            "IMAGE": "us-central1-docker.pkg.dev/example-project/hotai/camera:test",
            "PROJECT": "example-project",
            "GEMINI_LOCATION": "us-central1",
            "ORIGIN": "https://camera.example.run.app",
            "SECRET": "gemini-live-api-key",
            "SECRET_VERSION": "1",
        }
        rendered = render_service(template, values)
        self.assertNotIn("__", rendered)
        self.assertIn("secretKeyRef:", rendered)
        self.assertIn('name: "gemini-live-api-key"', rendered)
        self.assertIn("timeoutSeconds: 3600", rendered)

    def test_template_scalar_is_quoted_safely(self):
        output = render_service("value: __ORIGIN__", {"ORIGIN": 'https://example.com\nother: "value"'})
        self.assertEqual(output.count("\n"), 0)
        self.assertEqual(json.loads(output.removeprefix("value: ")), 'https://example.com\nother: "value"')

    def test_cloud_runtime_honors_host_port_and_origin(self):
        env = {
            **os.environ,
            "HOST": "0.0.0.0",
            "PORT": "8080",
            "ALLOWED_ORIGINS": "https://camera.example.run.app/",
        }
        result = subprocess.run(
            [sys.executable, "-c", "from app.config import HOST, PORT, ALLOWED_ORIGINS; "
             "assert HOST == '0.0.0.0'; assert PORT == 8080; "
             "assert 'https://camera.example.run.app' in ALLOWED_ORIGINS; "
             "assert 'http://localhost:3000' in ALLOWED_ORIGINS"],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
