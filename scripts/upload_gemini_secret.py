"""Add the .env Gemini key to an existing Secret Manager secret via stdin."""

import argparse
import shutil
import subprocess
import sys

from app.config import load_settings
from app.diagnostics import error_message, redact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret", default="gemini-live-api-key")
    args = parser.parse_args()
    key = ""
    try:
        gcloud = shutil.which("gcloud")
        if not gcloud:
            raise RuntimeError("Install the Google Cloud CLI and run gcloud auth login first.")
        if not args.secret or not all(char.isalnum() or char in "_-" for char in args.secret):
            raise ValueError("Use a Secret Manager secret name, not a resource path.")
        settings = load_settings()
        key = settings.api_key
        result = subprocess.run(
            [
                gcloud, "secrets", "versions", "add", args.secret,
                "--project", settings.project, "--data-file=-", "--quiet",
                "--format=value(name)",
            ],
            input=key.encode("utf-8"),
            capture_output=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(redact(result.stderr.decode("utf-8", errors="replace"), key))
        print("Secret version created: " + redact(result.stdout.decode("utf-8", errors="replace").strip(), key))
        print("Use the returned numeric version with deploy/deploy.ps1 -SecretVersion VERSION.")
        return 0
    except Exception as error:
        print(error_message(error, key), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
