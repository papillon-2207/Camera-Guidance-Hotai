"""Shared credential-safe diagnostics."""
import re

import httpx

HINTS = {
    400: "Invalid request/model configuration; check modalities and model ID.",
    401: "Authentication rejected; verify this is a service-account-bound authorization key.",
    403: "Check roles/aiplatform.user, aiplatform.googleapis.com key restrictions, API enablement, billing, and organization policy.",
    404: "Model or endpoint unavailable in this region/project; check current model availability.",
    429: "Quota/rate limit exceeded; check regional Live session quota and billing.",
}


def redact(value, key):
    text = str(value).replace(key, "[REDACTED]") if key else str(value)
    text = re.sub(r"AIza[\w-]+", "[REDACTED]", text)
    return re.sub(r"(?i)(key=|bearer\s+)[^\s&'\"]+", r"\1[REDACTED]", text)


def error_message(error: Exception, key: str = "") -> str:
    """Produce a credential-safe explanation for HTTP, WebSocket, and timeout errors."""
    code = getattr(error, "code", None)
    response = getattr(error, "response", None)
    if response is not None:
        code = getattr(response, "status_code", code)
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        hint = "Timed out waiting for connection, setup acknowledgement, or response."
    else:
        hint = HINTS.get(
            code,
            "Check configuration, connectivity, and the server close reason.",
        )
    return redact(f"{type(error).__name__} (status={code}): {error}\n{hint}", key)

