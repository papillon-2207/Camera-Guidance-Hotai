"""Render the Cloud Run template; contains secret references, never secret values."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render_service(template: str, values: dict[str, str]) -> str:
    tokens = set(re.findall(r"__([A-Z_]+)__", template))
    missing = tokens - values.keys()
    if missing:
        raise ValueError("Missing template values: " + ", ".join(sorted(missing)))
    # Replace once and JSON-quote each scalar, which is valid YAML and avoids injection.
    return re.sub(
        r"__([A-Z_]+)__",
        lambda match: json.dumps(values[match.group(1)]),
        template,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--service", default="gemini-live-camera")
    parser.add_argument("--image", required=True)
    parser.add_argument("--service-account", required=True)
    parser.add_argument("--gemini-location", default="us-central1")
    parser.add_argument("--secret", default="gemini-live-api-key")
    parser.add_argument("--secret-version", default="1")
    parser.add_argument("--origin", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    values = {
        "PROJECT": args.project,
        "SERVICE": args.service,
        "IMAGE": args.image,
        "SERVICE_ACCOUNT": args.service_account,
        "GEMINI_LOCATION": args.gemini_location,
        "SECRET": args.secret,
        "SECRET_VERSION": args.secret_version,
        "ORIGIN": args.origin,
    }
    template = (ROOT / "deploy" / "cloudrun.service.yaml").read_text(encoding="utf-8")
    args.output.write_text(render_service(template, values), encoding="utf-8")


if __name__ == "__main__":
    main()
