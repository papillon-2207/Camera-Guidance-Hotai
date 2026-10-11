"""Reusable instructions and input validation for camera framing guidance."""
import base64
from google.genai import types

from .config import PROMPTS_DIR


def load_framing_instructions(language="en") -> str:
    """Read on each new Live connection so prompt edits need only a reconnect."""
    if language not in {"en", "zh-TW"}:
        raise ValueError("Unsupported language")
    language_name = "English" if language == "en" else "Traditional Chinese, never Simplified Chinese"
    instructions = (PROMPTS_DIR / "framing.txt").read_text(encoding="utf-8").strip()
    product = (PROMPTS_DIR / "pad_analysis.txt").read_text(encoding="utf-8").strip()
    return f"{instructions}\n\n{product}\n\nSpeak and write all replies in {language_name}."


def framing_request(subject: str) -> str:
    template = (PROMPTS_DIR / "framing_request.txt").read_text(encoding="utf-8")
    return template.format(subject=subject).strip()


def decode_frame(encoded):
    frame = base64.b64decode(encoded, validate=True)
    if len(frame) > 512000 or not frame.startswith(b"\xff\xd8"):
        raise ValueError("Expected a JPEG camera frame under 512 KB")
    return frame


async def guide_camera(session, frame, subject="menstrual pads"):
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


async def analyze_pads(session, frame):
    """Analyze visible packaging in one ordered image/text turn."""
    request = (PROMPTS_DIR / "pad_analysis_request.txt").read_text(encoding="utf-8").strip()
    await session.send_client_content(
        turns=types.Content(role="user", parts=[
            types.Part.from_bytes(data=frame, mime_type="image/jpeg"),
            types.Part(text=request),
        ]),
        turn_complete=True,
    )
