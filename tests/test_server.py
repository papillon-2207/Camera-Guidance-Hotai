"""Ensure relocated browser assets load and private project files stay unserved."""

import unittest

from aiohttp.test_utils import TestClient, TestServer

from app.server import create_app


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
