# Gemini Live camera assistant

Local Python 3.11+ app for camera/microphone conversation and spoken photo framing
guidance through the Google Cloud Gemini Live API. The browser talks to a Python
backend; the authorization key stays on the backend.

## Project layout

```text
hotai/
  app/
    config.py                # Project-root environment and shared settings
    server.py                # Local HTTP routes and startup
    gemini_client.py         # Explicit Cloud authorization-key client
    live_bridge.py           # Browser input, Gemini output, session cleanup
    framing.py               # Send a frame and request guidance
    diagnostics.py           # Credential-safe error messages
    prompts/
      framing.txt            # Editable Live session instructions
      framing_request.txt    # Editable per-frame request template
  frontend/
    index.html
    styles.css
    js/
      app.js                 # UI, camera capture, connection state
      audio.js               # Microphone capture and response playback
      mic-worklet.js         # Convert microphone input to 16 kHz PCM
  scripts/
    test_gemini_live.py       # Real REST + WebSocket diagnostic
    list_models.py           # Model listing diagnostic
  tests/                     # Offline regression checks
  .env                       # Local credentials, ignored by Git
  .env.example
  requirements.txt
```

## Install and configure

Run these commands from the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `.env` does not exist, copy `.env.example` to `.env`. Do not overwrite an
existing key. Configure:

```ini
GEMINI_API_KEY=YOUR_API_KEY
GOOGLE_CLOUD_PROJECT=papillon-2207
GOOGLE_CLOUD_LOCATION=us-central1
```

Settings are loaded relative to the project root, regardless of working directory.
Environment variables override `.env`. All app and diagnostic commands use this
same configuration. The old `api-key` variable is replaced by `GEMINI_API_KEY`.

The configured key should be a service-account-bound authorization key restricted
to `aiplatform.googleapis.com`. The expected service account for this project is
`gemini-live-service@papillon-2207.iam.gserviceaccount.com`, with the Agent Platform
User role (`roles/aiplatform.user`). The diagnostics test access; they do not
inspect the key's actual service-account binding or the project's IAM policy.

## Start the local interface

```powershell
.\.venv\Scripts\python.exe -m app.server
```

If dependencies are installed in your current Python, use `python -m app.server`.
Open **http://localhost:3000**. Ctrl+C stops the server.

1. Click **Enable camera & mic** and allow browser permissions.
2. Click **Connect to Gemini**.
3. To converse, select **Start microphone** or **Share camera**, or type a message.
4. To frame a photo, enter a subject (default: bottle) and select **Start framing guidance**.
5. Follow the spoken directions. When framing is acceptable, Gemini says:
   **"The bottle is centered. You can take the picture now."**
6. Select **Take photo**, then **Download photo** to save it.

Guidance checks one fresh frame at a time and waits for the response and audio
playback before asking again. Microphone and ordinary camera streaming pause during
guidance to avoid competing turns. **Stop framing guidance** stops future checks;
an in-flight response can still finish. **Stop all** closes the session and releases
the devices. A photo is captured manually at the available camera resolution and
stays local until downloaded. No recordings are saved by the backend.

Use headphones to reduce echo. Preview, transmitted frames, and photos use the
same unmirrored orientation and camera aspect ratio. Gemini estimates framing;
it does not measure exact centering or verify autofocus. Test physical devices
in Chrome or Edge and check browser/OS permissions if capture fails.

The server binds to loopback only. Opening localhost on a phone points to the phone
itself. Access from a separate phone requires an HTTPS/LAN setup and an origin
configuration change. Live calls consume API quota and may incur charges.

## Edit the AI instructions

- **`app/prompts/framing.txt`**: behavior, camera directions, framing criteria,
  and the centered-photo confirmation. Loaded whenever a new Live session connects.
  After editing, disconnect and reconnect Gemini; restarting Python is unnecessary.
- **`app/prompts/framing_request.txt`**: request sent with each new frame. Keep
  `{subject!r}` as the subject placeholder. This template uses Python `str.format`;
  use `{{` and `}}` for literal braces. Edits apply to the next requested frame.

`app.framing.guide_camera(session, jpeg_bytes, subject)` sends the image and its
request in one ordered turn. Prompt text is kept out of that Python function.

## Diagnostics and checks

From the project root, using the Python environment with dependencies installed:

```powershell
python -m scripts.test_gemini_live
python -m scripts.list_models
python -m scripts.list_models --json
python -m unittest discover -s tests -v
```

The Live diagnostic first makes a small REST model request, then separately
establishes a real WebSocket session, sends a greeting, receives audio/transcription
through turn completion, and closes the session. A regular API success cannot
substitute for Live success. Exit code 0 means all checks passed; 1 means a failed
or unverified check; 130 means interrupted. Options include `--timeout 60`,
`--probe-model MODEL_ID`, and `--live-model MODEL_ID`.

The model-listing script defaults to Cloud with the same explicit key, project,
and region. `--backend developer` is an explicit optional diagnostic for a compatible
Developer API key; it is never a fallback for the app. A model listing does not
guarantee inference permission. Listing failures are independent of Live access.

Tests use temporary configuration and fake sessions, make no Google API calls,
and cover relocated assets, secret redaction, prompt paths, framing state, and
task cancellation. The diagnostic scripts perform real, potentially billed calls.

## Authentication and endpoints

`app/gemini_client.py` supplies the authorization key, project, and region explicitly
to `google-genai`. It selects `enterprise=True` (or the earlier `vertexai=True`
SDK name), then verifies the effective SDK settings. There is no ADC fallback.
SDK 2.28.0's Vertex Live key path sends `x-goog-api-key`; the direct REST probe uses
the same documented header. Authorization keys authenticate as their bound
service account, unlike ordinary unbound API keys.

Default Live model: `gemini-live-2.5-flash-native-audio`.
Default REST probe: `gemini-2.5-flash`.
Model defaults live in `app/config.py`.

```text
REST:
https://us-central1-aiplatform.googleapis.com/v1/projects/papillon-2207/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent

Live:
wss://us-central1-aiplatform.googleapis.com/ws/google.cloud.aiplatform.v1beta1.LlmBidiService/BidiGenerateContent
```

Audio input is mono PCM16 at 16 kHz; Gemini audio plays at 24 kHz. Ordinary camera
sharing sends JPEG frames once per second. The model documentation checked on
October 10, 2026 lists the Live model as GA in `us-central1`, with retirement on
December 13, 2026. Recheck the official availability page when updating the model.

## Troubleshooting

| Failure | Check |
| --- | --- |
| 400 | Model, region, and modalities. Native audio uses AUDIO with transcription. |
| 401 | Actual key string, key validity, and service-account binding. |
| 403 | IAM role, API restrictions, API enabled, billing, organization/VPC policy. |
| 404 | Model/endpoint spelling, regional availability, and retirement date. |
| 429 | Request and concurrent-session quota, billing, and regional capacity. |
| WebSocket failure | Allow TLS WebSocket upgrades to the regional Cloud host. |
| Timeout | Inspect the redacted error and increase the diagnostic `--timeout`. |
| Port 3000 occupied | Stop the previous local app before starting this one. |
| Missing imports | Install requirements in the same Python environment you run. |

Private project files and prompt files are not served by the HTTP routes. Errors
redact the configured key. Avoid HTTP/WebSocket debug logging that might expose headers.

## Official references

- [Authorization keys](https://docs.cloud.google.com/docs/authentication/api-keys)
- [API-key REST header](https://docs.cloud.google.com/docs/authentication/api-keys-use)
- [Live model availability and lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-flash-live-api)
- [Live SDK tutorial](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/live-api/get-started-sdk)
- [Live protocol](https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/models/multimodal-live)
- [Official Python SDK](https://github.com/googleapis/python-genai)
