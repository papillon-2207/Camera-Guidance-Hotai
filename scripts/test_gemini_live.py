"""Real Vertex AI authorization-key REST and Live WebSocket smoke test."""

import argparse
import asyncio
import sys

import httpx
from google.genai import types

from app.config import LIVE_MODEL, PROBE_MODEL, load_settings
from app.diagnostics import HINTS, error_message, redact
from app.gemini_client import close_client, create_client

LABELS = [
    "Environment Configuration",
    "API Key Authentication",
    "Model Access (regular request)",
    "Live WebSocket Connection",
    "Send Message",
    "Receive Response",
    "Graceful Session Close",
]


def explain(error, key):
    print(error_message(error, key))


async def run(args):
    config_error = None
    key = project = location = ""
    try:
        settings = load_settings()
        key, project, location = settings.api_key, settings.project, settings.location
    except (OSError, ValueError) as error:
        config_error = error
    status = ["UNTESTED"] * len(LABELS)
    print("=================================\n GEMINI LIVE API CONNECTION TEST\n=================================")
    print(f"Project: {redact(project, key)}\nRegion: {redact(location, key)}")
    print("Authentication: Service-account-bound API key (no ADC)")
    print("Expected service account: gemini-live-service@papillon-2207.iam.gserviceaccount.com")
    print("Binding and IAM role are configuration claims; this test does not inspect key administration.")

    def report():
        print()
        for i, (label, result) in enumerate(zip(LABELS, status), 1):
            print(f"[{i}] {label}: {result}")
        working = all(item == "PASS" for item in status[3:])
        print("\nRESULT: " + ("GEMINI LIVE API WORKING" if working else "GEMINI LIVE API NOT VERIFIED"))
        return 0 if working and all(item == "PASS" for item in status) else 1

    if config_error:
        status[0] = "FAIL"
        print(error_message(config_error))
        return report()
    status[0] = "PASS"
    host = settings.api_host
    print(f"REST probe model: {args.probe_model}\nLive model: {args.live_model}")
    print(f"Live endpoint: wss://{host}/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent")

    # Documented REST key header; no OAuth token or ADC fallback.
    try:
        async with httpx.AsyncClient(timeout=args.timeout) as http:
            response = await http.post(
                f"https://{host}/v1/{settings.model_path(args.probe_model)}:generateContent",
                headers={"x-goog-api-key": key},
                json={"contents": [{"role": "user", "parts": [{"text": "Reply with OK."}]}],
                      "generationConfig": {"maxOutputTokens": 32}},
            )
            if response.is_success:
                status[1] = status[2] = "PASS"
                print("REST authenticated model request succeeded (API/project/model usable for this request).")
            else:
                status[1] = "FAIL" if response.status_code == 401 else "UNVERIFIED"
                status[2] = "FAIL"
                print(redact(f"REST HTTP {response.status_code}: {response.text[:4000]}", key))
                print(HINTS.get(response.status_code, "Unexpected HTTP response."))
    except Exception as error:
        status[2] = "FAIL"
        explain(error, key)

    client = None
    stage = 3
    try:
        client = create_client(settings, timeout=args.timeout)
        async with asyncio.timeout(args.timeout):
            async with client.aio.live.connect(
                model=settings.model_path(args.live_model),
                config=types.LiveConnectConfig(
                    response_modalities=["AUDIO"], output_audio_transcription=types.AudioTranscriptionConfig(),
                ),
            ) as session:
                # SDK connect waits for setupComplete, not merely a socket handshake.
                status[3] = "PASS"
                status[1] = "PASS"  # Live setup independently proves the key is accepted.
                stage = 4
                await session.send_client_content(
                    turns=types.Content(role="user", parts=[types.Part(text="Hello Gemini, please introduce yourself briefly.")]),
                    turn_complete=True,
                )
                status[4] = "PASS"
                stage = 5
                payload_received = False
                turn_complete = False
                audio_bytes = 0
                mime_types = set()
                async for message in session.receive():
                    server = message.server_content
                    if server:
                        transcript = server.output_transcription
                        if transcript and transcript.text:
                            print("Transcription: " + redact(transcript.text, key))
                            payload_received = True
                        if server.model_turn:
                            for part in server.model_turn.parts or []:
                                if part.text:
                                    print("Text: " + redact(part.text, key))
                                    payload_received = True
                                if part.inline_data and part.inline_data.data:
                                    audio_bytes += len(part.inline_data.data)
                                    mime_types.add(part.inline_data.mime_type or "unknown")
                                    payload_received = True
                        if server.turn_complete:
                            turn_complete = True
                if audio_bytes:
                    print(f"Audio: {audio_bytes} bytes; MIME: {', '.join(sorted(mime_types))}")
                if not payload_received or not turn_complete:
                    raise RuntimeError("Session ended without a payload and completed model turn.")
                status[5] = "PASS"
                stage = 6
            status[6] = "PASS"
    except Exception as error:
        status[stage] = "FAIL"
        explain(error, key)
    finally:
        if client:
            try:
                await close_client(client)
            except Exception as error:
                status[6] = "FAIL"
                explain(error, key)
    return report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=45, help="Seconds per request/session")
    parser.add_argument("--probe-model", default=PROBE_MODEL)
    parser.add_argument("--live-model", default=LIVE_MODEL)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nTest interrupted; Live success not verified.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
