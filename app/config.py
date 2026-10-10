"""Shared settings, resolved relative to the project rather than the working directory."""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
HOST = "127.0.0.1"
PORT = 3000
LIVE_MODEL = "gemini-live-2.5-flash-native-audio"
PROBE_MODEL = "gemini-2.5-flash"
ALLOWED_ORIGINS = {f"http://localhost:{PORT}", f"http://{HOST}:{PORT}"}


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    project: str
    location: str

    @property
    def api_host(self) -> str:
        return f"{self.location}-aiplatform.googleapis.com"

    def model_path(self, model: str) -> str:
        return (
            f"projects/{self.project}/locations/{self.location}"
            f"/publishers/google/models/{model}"
        )


def load_settings(env_file: Path | None = None) -> Settings:
    """Read .env without mutating process environment; explicit environment wins."""
    values = {
        **dotenv_values(env_file or PROJECT_ROOT / ".env", encoding="utf-8-sig"),
        **os.environ,
    }
    names = ("GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
    key, project, location = (str(values.get(name) or "").strip() for name in names)
    if not key or key == "YOUR_API_KEY" or not project or not location:
        raise ValueError("Configure GEMINI_API_KEY, GOOGLE_CLOUD_PROJECT, and GOOGLE_CLOUD_LOCATION in .env.")
    if not re.fullmatch(r"[a-z][a-z0-9-]*", project):
        raise ValueError("GOOGLE_CLOUD_PROJECT must be a valid project ID.")
    if not re.fullmatch(r"[a-z]+-[a-z]+\d+", location):
        raise ValueError("Use a regional GOOGLE_CLOUD_LOCATION such as us-central1.")
    return Settings(api_key=key, project=project, location=location)
