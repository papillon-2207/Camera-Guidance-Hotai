"""Exercise framing state and task cancellation without calling Google."""

import asyncio
import base64
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from google.genai import types

from app.live_bridge import LiveBridge


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_guidance_finishes_and_allows_next_frame(self):
        ws = SimpleNamespace(send_json=AsyncMock())
        session = AsyncMock()
        bridge = LiveBridge(ws, session, "private-key")
        request = {"type": "guide", "subject": "bottle", "data": base64.b64encode(b"\xff\xd8test").decode()}
        await bridge.handle_browser_message(request)
        await bridge.handle_browser_message(request)
        self.assertEqual(session.send_client_content.await_count, 1)
        prompt = session.send_client_content.call_args.kwargs["turns"].parts[1].text
        self.assertIn("menstrual pads", prompt)
        self.assertNotIn("bottle", prompt)
        await bridge.handle_server_content(types.LiveServerContent(
            output_transcription=types.Transcription(text="Centered private-key"),
            turn_complete=True,
        ))
        guidance = [call.args[0] for call in ws.send_json.call_args_list if call.args[0]["type"] == "guidance"]
        self.assertEqual(guidance[0]["text"], "Centered [REDACTED]")
        self.assertFalse(bridge.guidance_pending)
        await bridge.handle_browser_message(request)
        self.assertEqual(session.send_client_content.await_count, 2)

    async def test_pad_analysis_forwards_frame_and_streams_separate_result(self):
        ws = SimpleNamespace(send_json=AsyncMock())
        session = AsyncMock()
        bridge = LiveBridge(ws, session, "secret")
        await bridge.handle_browser_message({
            "type": "analyze_pads", "data": base64.b64encode(b"\xff\xd8test").decode(),
        })
        parts = session.send_client_content.call_args.kwargs["turns"].parts
        self.assertEqual(parts[0].inline_data.data, b"\xff\xd8test")
        self.assertIn("instead of guessing", parts[1].text)
        await bridge.handle_server_content(types.LiveServerContent(
            output_transcription=types.Transcription(text="Visible label secret"), turn_complete=True,
        ))
        results = [c.args[0] for c in ws.send_json.call_args_list if c.args[0]["type"] == "pad_analysis"]
        self.assertEqual(results[0]["text"], "Visible label [REDACTED]")
        self.assertFalse(bridge.guidance_pending)

    async def test_invalid_audio_is_not_forwarded(self):
        session = AsyncMock()
        bridge = LiveBridge(None, session, "")
        with self.assertRaises(ValueError):
            await bridge.send_audio(b"odd")
        session.send_realtime_input.assert_not_awaited()

    async def test_peer_task_is_cancelled_when_browser_disconnects(self):
        bridge = LiveBridge(None, None, "")
        started = asyncio.Event()
        stopped = asyncio.Event()

        async def browser():
            await started.wait()

        async def gemini():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        bridge.receive_browser = browser
        bridge.receive_gemini = gemini
        async with asyncio.timeout(2):
            await bridge.run()
        self.assertTrue(stopped.is_set())
