"""List models with the shared project-root environment and explicit backend."""

import argparse
import json
import sys

from app.config import load_settings
from app.diagnostics import error_message
from app.gemini_client import create_client


def list_models(settings, backend="cloud"):
    version = "v1beta1" if backend == "cloud" else "v1beta"
    with create_client(settings, backend=backend, api_version=version) as client:
        return [
            model.model_dump(mode="json", by_alias=True, exclude_none=True)
            for model in client.models.list(config={"page_size": 100, "query_base": True})
        ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print all returned model metadata")
    parser.add_argument(
        "--backend", choices=["cloud", "developer"], default="cloud",
        help="Cloud authorization-key backend (default); developer requires a compatible key",
    )
    args = parser.parse_args()
    key = ""
    try:
        settings = load_settings()
        key = settings.api_key
        models = list_models(settings, args.backend)
    except Exception as error:
        print(error_message(error, key), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(models, indent=2, ensure_ascii=True))
    else:
        print(f"Found {len(models)} models via {args.backend}. Listing does not prove inference access.\n")
        for model in sorted(models, key=lambda item: item.get("name", "")):
            print(model.get("name", "(unnamed)"))
            actions = model.get("supportedActions", model.get("supportedGenerationMethods", []))
            print("  Methods: " + ", ".join(actions))
            print(
                f"  Token limits: input={model.get('inputTokenLimit', 'N/A')}, "
                f"output={model.get('outputTokenLimit', 'N/A')}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
