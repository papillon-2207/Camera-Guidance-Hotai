"""One explicit authorization-key client configuration for the app and scripts."""

import inspect

from google import genai
from google.genai import types

from .config import Settings


def create_client(
    settings: Settings,
    *,
    api_version: str = "v1beta1",
    timeout: float = 30,
    backend: str = "cloud",
) -> genai.Client:
    if backend not in {"cloud", "developer"}:
        raise ValueError("Unknown Gemini backend.")
    selector = "enterprise" if "enterprise" in inspect.signature(genai.Client).parameters else "vertexai"
    options = {selector: backend == "cloud"}
    if backend == "cloud":
        options.update(project=settings.project, location=settings.location)
    client = genai.Client(
        **options,
        api_key=settings.api_key,
        http_options=types.HttpOptions(api_version=api_version, timeout=int(timeout * 1000)),
    )
    # Fail explicitly if SDK configuration changes, rather than falling back to ADC.
    api = client._api_client
    valid = api.api_key == settings.api_key and bool(api.vertexai) == (backend == "cloud")
    if backend == "cloud":
        valid = valid and api.project == settings.project and api.location == settings.location
    if not valid:
        client.close()
        raise RuntimeError("SDK did not preserve the requested authorization-key configuration.")
    return client


async def close_client(client: genai.Client) -> None:
    try:
        await client.aio.aclose()
    finally:
        client.close()
