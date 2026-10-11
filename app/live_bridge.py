"""Browser media forwarding and lifecycle management for one Gemini Live session."""

import asyncio
import base64
from contextlib import asynccontextmanager

from aiohttp import WSMsgType, web
from google.genai import types

from .config import ALLOWED_ORIGINS, LIVE_MODEL, Settings, load_settings
from .diagnostics import error_message, redact
from .framing import analyze_pads, decode_frame, guide_camera, load_framing_instructions
from .gemini_client import close_client, create_client


@asynccontextmanager
async def open_live_session(settings: Settings, language="en"):
    """Bound connection setup, and always release both SDK transports."""
    client = create_client(settings)
    try:
        connection = client.aio.live.connect(
            model=settings.model_path(LIVE_MODEL),
            config=types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=load_framing_instructions(language),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            ),
        )
        async with asyncio.timeout(30):
            session = await connection.__aenter__()
        try:
            yield session
        finally:
            await connection.__aexit__(None, None, None)
    finally:
        await close_client(client)


class LiveBridge:
    """Own the input/output tasks and framing state for a single browser socket."""

    def __init__(self, ws, session, api_key: str):
        self.ws = ws
        self.session = session
        self.api_key = api_key
        self.guidance_pending = False
        self.guidance_text = ""
        self.response_kind = "guidance"

    async def run(self):
        tasks = [
            asyncio.create_task(self.receive_browser()),
            asyncio.create_task(self.receive_gemini()),
        ]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def receive_browser(self):
        async for message in self.ws:
            if message.type == WSMsgType.BINARY:
                await self.send_audio(message.data)
            elif message.type == WSMsgType.TEXT:
                await self.handle_browser_message(message.json())
            elif message.type == WSMsgType.ERROR:
                raise ConnectionError("Browser WebSocket error")

    async def send_audio(self, data: bytes):
        if not data or len(data) > 32768 or len(data) % 2:
            raise ValueError("Invalid PCM audio chunk")
        await self.session.send_realtime_input(
            audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000"),
        )

    async def handle_browser_message(self, data):
        if not isinstance(data, dict):
            raise ValueError("Expected a browser message object")
        kind = data.get("type")
        if kind in {"guide", "analyze_pads"}:
            if self.guidance_pending:
                return
            frame = decode_frame(data["data"])
            self.guidance_pending = True
            self.guidance_text = ""
            self.response_kind = "guidance" if kind == "guide" else "pad_analysis"
            if kind == "guide":
                await guide_camera(self.session, frame)
            else:
                await analyze_pads(self.session, frame)
        elif kind == "video":
            await self.session.send_realtime_input(
                video=types.Blob(data=decode_frame(data["data"]), mime_type="image/jpeg"),
            )
        elif kind == "text":
            text = str(data["text"])[:2000]
            await self.session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )
        elif kind == "audio_end":
            await self.session.send_realtime_input(audio_stream_end=True)
        else:
            raise ValueError("Unknown browser message type")

    async def receive_gemini(self):
        # SDK receive() yields one turn; keep listening for later turns.
        while not self.ws.closed:
            received = False
            async for message in self.session.receive():
                received = True
                if message.server_content:
                    await self.handle_server_content(message.server_content)
            if not received:
                raise ConnectionError("Gemini session ended unexpectedly")

    async def handle_server_content(self, server):
        if server.interrupted:
            await self.ws.send_json({"type": "interrupted"})
        await self.send_transcript("you", server.input_transcription)
        await self.send_transcript("gemini", server.output_transcription)
        if server.model_turn:
            for part in server.model_turn.parts or []:
                if part.inline_data and part.inline_data.data:
                    await self.ws.send_json({
                        "type": "audio",
                        "data": base64.b64encode(part.inline_data.data).decode(),
                        "mime": part.inline_data.mime_type,
                    })
        if server.turn_complete:
            self.guidance_pending = False
            await self.ws.send_json({"type": "turn_complete"})

    async def send_transcript(self, speaker, transcript):
        if not transcript or not transcript.text:
            return
        await self.ws.send_json({
            "type": "transcript",
            "speaker": speaker,
            "text": redact(transcript.text, self.api_key),
        })
        if self.guidance_pending and speaker == "gemini":
            self.guidance_text += transcript.text
            await self.ws.send_json({
                "type": self.response_kind,
                "text": redact(self.guidance_text, self.api_key),
            })


async def live(request):
    """Accept configured UI origins, then manage one authenticated Cloud session."""
    if request.headers.get("Origin") not in ALLOWED_ORIGINS:
        raise web.HTTPForbidden(text="This page origin is not allowed. Check ALLOWED_ORIGINS.")
    ws = web.WebSocketResponse(max_msg_size=2 * 1024 * 1024, heartbeat=30)
    await ws.prepare(request)
    key = ""
    try:
        settings = load_settings()
        key = settings.api_key
        language = request.query.get("language", "en")
        if language not in {"en", "zh-TW"}:
            raise ValueError("Unsupported language")
        async with open_live_session(settings, language=language) as session:
            await ws.send_json({
                "type": "ready",
                "text": f"Gemini Live connected | {settings.project} | {settings.location}",
            })
            await LiveBridge(ws, session, key).run()
    except Exception as error:
        if not ws.closed:
            try:
                await ws.send_json({"type": "error", "text": error_message(error, key)})
            except ConnectionError:
                pass  # Browser already disconnected; cleanup still runs below.
    finally:
        await ws.close()
    return ws
