"""Reusable instructions and input validation for camera framing guidance."""
import base64
from google.genai import types

from .config import PROMPTS_DIR


def load_framing_instructions() -> str:
    """Read on each new Live connection so prompt edits need only a reconnect."""
    return (PROMPTS_DIR / "framing.txt").read_text(encoding="utf-8").strip()


def framing_request(subject: str) -> str:
    template = (PROMPTS_DIR / "framing_request.txt").read_text(encoding="utf-8")
    return template.format(subject=subject).strip()


def decode_frame(encoded):
    frame = base64.b64decode(encoded, validate=True)
    if len(frame) > 512000 or not frame.startswith(b"\xff\xd8"):
        raise ValueError("Expected a JPEG camera frame under 512 KB")
    return frame


async def guide_camera(session, frame, subject="bottle"):
    """Send one current camera frame and request one spoken framing instruction."""
    subject = str(subject).strip()[:120]
    if not subject:
        raise ValueError("Specify the photo subject")
    # A single ordered content turn ties this request to this exact image.
    await session.send_client_content(
        turns=types.Content(role="user", parts=[
            types.Part.from_bytes(data=frame, mime_type="image/jpeg"),
            types.Part(text=framing_request(subject)),
        ]),
        turn_complete=True,
    )
