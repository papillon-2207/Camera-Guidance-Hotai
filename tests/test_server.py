"""Ensure relocated browser assets load and private project files stay unserved."""

import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from app.server import create_app
from app.config import Settings


class ServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = TestClient(TestServer(create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()

    async def test_frontend_asset_paths(self):
        for path in ("/", "/styles.css", "/js/app.js", "/js/audio.js", "/js/mic-worklet.js"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 200, path)
            await response.read()
        page = await self.client.get("/")
        self.assertIn('src="/js/app.js"', await page.text())

    async def test_private_files_are_not_served(self):
        for path in ("/.env", "/app/config.py", "/app/prompts/framing.txt"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 404, path)

    async def test_foreign_origin_cannot_open_live_session(self):
        response = await self.client.get("/live", headers={"Origin": "http://example.com"})
        self.assertEqual(response.status, 403)

    async def test_health_probe_requires_no_gemini_credentials(self):
        response = await self.client.get("/healthz")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"status": "ok"})

    async def test_configured_https_origin_can_open_live_session(self):
        origin = "https://gemini-live-camera.example.run.app"

        @asynccontextmanager
        async def session(settings, language="en"):
            yield AsyncMock()

        with (
            patch("app.live_bridge.ALLOWED_ORIGINS", {origin}),
            patch("app.live_bridge.load_settings", return_value=Settings("test-key", "example-project", "us-central1")),
            patch("app.live_bridge.open_live_session", session),
            patch("app.live_bridge.LiveBridge.run", new_callable=AsyncMock),
        ):
            ws = await self.client.ws_connect("/live", origin=origin)
            message = await ws.receive_json()
            self.assertEqual(message["type"], "ready")
            await ws.close()
