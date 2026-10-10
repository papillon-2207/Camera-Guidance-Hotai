"""Regression checks for configuration and prompt loading after relocation."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.config import Settings, load_settings
from app.diagnostics import error_message
from app.framing import framing_request, guide_camera, load_framing_instructions
from app.gemini_client import create_client


class ConfigurationTests(unittest.TestCase):
    def test_environment_override_and_secret_safe_repr(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                "GEMINI_API_KEY=file-secret\nGOOGLE_CLOUD_PROJECT=example-project\n"
                "GOOGLE_CLOUD_LOCATION=us-central1\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"GEMINI_API_KEY": "environment-secret"}, clear=True):
                settings = load_settings(path)
            self.assertEqual(settings.api_key, "environment-secret")
            self.assertNotIn("environment-secret", repr(settings))
            self.assertEqual(settings.project, "example-project")

    def test_missing_configuration_is_actionable(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                load_settings(Path(folder) / ".env")

    def test_client_keeps_explicit_cloud_key_and_region(self):
        settings = Settings("test-key-never-sent", "example-project", "us-central1")
        with create_client(settings) as client:
            self.assertTrue(client._api_client.vertexai)
            self.assertEqual(client._api_client.api_key, settings.api_key)
            self.assertEqual(client._api_client.project, settings.project)
            self.assertEqual(client._api_client.location, settings.location)

    def test_diagnostics_redact_key(self):
        text = error_message(RuntimeError("Rejected secret-value"), "secret-value")
        self.assertNotIn("secret-value", text)

    def test_prompts_resolve_outside_project_working_directory(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as folder:
            try:
                os.chdir(folder)
                self.assertIn("The bottle is centered.", load_framing_instructions())
                self.assertIn("'bottle'", framing_request("bottle"))
            finally:
                os.chdir(previous)


class FramingTests(unittest.IsolatedAsyncioTestCase):
    async def test_subject_and_frame_stay_in_one_ordered_turn(self):
        session = AsyncMock()
        await guide_camera(session, b"example-jpeg-bytes", "bottle")
        kwargs = session.send_client_content.call_args.kwargs
        self.assertTrue(kwargs["turn_complete"])
        parts = kwargs["turns"].parts
        self.assertEqual(parts[0].inline_data.data, b"example-jpeg-bytes")
        self.assertIn("bottle", parts[1].text)
        self.assertIn("take the picture now", parts[1].text)

    async def test_empty_subject_sends_nothing(self):
        session = AsyncMock()
        with self.assertRaises(ValueError):
            await guide_camera(session, b"example", "  ")
        session.send_client_content.assert_not_awaited()
