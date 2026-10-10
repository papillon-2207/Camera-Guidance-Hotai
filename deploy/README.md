# Cloud Run deployment

This follows the structure in `C:\Users\ASUS\Documents\ML`: a Dockerfile, local
Compose service, Cloud Build pipeline, and rendered Cloud Run service manifest.
The Gemini service uses the existing authorization key through Secret Manager.

Default configuration:

| Setting | Value |
| --- | --- |
| Project | `papillon-2207` |
| Cloud Run region | `us-central1` |
| Gemini region | `us-central1` |
| Service / image | `gemini-live-camera` |
| Artifact Registry repository | `hotai` |
| Runtime service account | `gemini-live-service@papillon-2207.iam.gserviceaccount.com` |
| Secret | `gemini-live-api-key`, numeric version `1` |
| Runtime resources | 1 CPU, 512 MiB, 0–2 instances, 10 concurrent requests per instance |
| Request timeout | 3,600 seconds |
| New-service access | Private IAM access unless you explicitly select `-Public` |

Cloud Run and Gemini regions can be configured independently. Each browser Live
session is a long-lived WebSocket request. Cloud Run supports WebSockets, but the
request timeout still applies; Gemini may end its own session earlier. Reconnect
from the interface after a timeout. `/healthz` tests the web server without
opening a Gemini session or consuming model quota.

## 1. Install tools and authenticate

Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install)
and authenticate from PowerShell:

```powershell
gcloud auth login
gcloud config set project papillon-2207
```

Ensure project billing is enabled. Run the remaining commands from the `hotai`
project root. They provision Cloud resources when you execute them; preparing
these files alone does not deploy or change IAM.

```powershell
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com --project papillon-2207
gcloud artifacts repositories create hotai --repository-format=docker --location=us-central1 --project=papillon-2207
```

If the repository already exists, reuse it rather than recreating it.

## 2. Store the API key securely

Create a secret container if it does not already exist:

```powershell
gcloud secrets create gemini-live-api-key --replication-policy=automatic --project=papillon-2207
```

Upload only `GEMINI_API_KEY` from your local `.env`:

```powershell
python -m scripts.upload_gemini_secret
```

The helper passes the key to `gcloud` through stdin. It does not put the key in a
command argument, terminal output, or plaintext staging file. Keep the returned
numeric secret version for deployment. A new upload creates a new version; it
does not replace the old one.

Grant the runtime service account access to this secret:

```powershell
gcloud secrets add-iam-policy-binding gemini-live-api-key --project=papillon-2207 --member=serviceAccount:gemini-live-service@papillon-2207.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

The runtime identity retrieves the secret. Gemini requests still authenticate
with the service-account-bound authorization key, preserving the tested behavior.
The runtime service account is expected to already exist. The secret is never
copied into the Docker image or uploaded source archive. Source and Docker ignore
files exclude `.env`, Git history, and local caches.

## 3. Configure a build service account

Use an existing suitable build account or create one dedicated to this pipeline:

```powershell
gcloud iam service-accounts create hotai-build --display-name="Hotai Cloud Build" --project=papillon-2207
```

For that account, grant the permissions needed by this build/deploy pipeline:

```powershell
gcloud projects add-iam-policy-binding papillon-2207 --member=serviceAccount:hotai-build@papillon-2207.iam.gserviceaccount.com --role=roles/run.admin
gcloud projects add-iam-policy-binding papillon-2207 --member=serviceAccount:hotai-build@papillon-2207.iam.gserviceaccount.com --role=roles/logging.logWriter
gcloud projects add-iam-policy-binding papillon-2207 --member=serviceAccount:hotai-build@papillon-2207.iam.gserviceaccount.com --role=roles/storage.objectViewer
gcloud artifacts repositories add-iam-policy-binding hotai --location=us-central1 --project=papillon-2207 --member=serviceAccount:hotai-build@papillon-2207.iam.gserviceaccount.com --role=roles/artifactregistry.writer
gcloud iam service-accounts add-iam-policy-binding gemini-live-service@papillon-2207.iam.gserviceaccount.com --project=papillon-2207 --member=serviceAccount:hotai-build@papillon-2207.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser
```

The storage role permits reading uploaded build source; administrators can narrow
it to the build staging bucket instead of the project. The build account does not
need to read the Gemini secret. Your own deployment identity must be allowed to
submit builds and act as the build account. An administrator can grant you
`roles/cloudbuild.builds.editor` and `roles/iam.serviceAccountUser` on that account,
plus the provisioning/IAM permissions needed for the preceding setup commands.

## 4. Build and deploy

```powershell
.\deploy\deploy.ps1 -BuildServiceAccount hotai-build@papillon-2207.iam.gserviceaccount.com -SecretVersion 1
```

If your PowerShell policy blocks scripts, launch the reviewed script explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\deploy.ps1 -BuildServiceAccount hotai-build@papillon-2207.iam.gserviceaccount.com -SecretVersion 1
```

Use the actual secret version returned by the upload helper. Optional parameters:
`-Project`, `-Region`, `-Repository`, `-Service`, `-ServiceAccount`, `-GeminiLocation`,
`-Secret`, and `-SecretVersion`. The script uses a timestamped image tag and checks
for the repository and secret version before submitting the build.

The Cloud Build pipeline:

1. Builds and pushes a Linux container to Artifact Registry.
2. Renders `deploy/cloudrun.service.yaml` with the image and secret reference.
3. Deploys the service using the runtime service account.
4. Reads the actual service URL and sets `ALLOWED_ORIGINS` to that exact HTTPS origin.

The final origin update creates another revision. Browser Live connections should
be tested after the full pipeline completes. The first revision accepts only local
test origins. A new service is private by default; deployments preserve an existing
service's IAM bindings. Omitting `-Public` does not remove previously granted access.

For private testing, authenticate as a principal with Cloud Run Invoker access and
use Google's local proxy:

```powershell
gcloud run services proxy gemini-live-camera --project=papillon-2207 --region=us-central1 --port=3000
```

Stop any local Python/Docker server occupying port 3000 first. Open
`http://localhost:3000`. The proxy attaches your Google credentials to requests.
Private IAM services are not directly usable by a normal browser WebSocket without
an authentication proxy or another browser sign-in integration.

For a URL that opens directly in a phone/browser, explicitly select public access:

```powershell
.\deploy\deploy.ps1 -BuildServiceAccount hotai-build@papillon-2207.iam.gserviceaccount.com -SecretVersion 1 -Public
```

This grants `allUsers` the Cloud Run Invoker role. The current app has no separate
user login, so anyone with access can initiate Gemini sessions using the backend's
quota. Organization policies may prohibit this grant. The hosted HTTPS page uses
`wss://` for Live connections and enables browser camera/microphone permissions.

## Local container test

Docker Desktop must be running. Stop the existing Python server on port 3000, then:

```powershell
docker compose up --build -d
docker compose ps
```

Open `http://localhost:3000` and check `http://localhost:3000/healthz`.
Compose injects `.env` at runtime; the container image contains no `.env` file.
The Dockerfile listens on `0.0.0.0:8080`, honors Cloud Run's injected `PORT`, runs
as a non-root user, and starts the existing aiohttp server directly. Gunicorn is
not needed for this aiohttp WebSocket app.

```powershell
docker compose logs --tail 50
docker compose down
```

## Cloud Build triggers

Configure the root `cloudbuild.yaml` and select the configured build service
account. Override `_TAG` with `$SHORT_SHA` for commit-triggered builds. Other
substitutions are listed at the top of the build file. For another project, update
`_SERVICE_ACCOUNT`; the default names the service account in `papillon-2207`.
Cloud Build never receives the API-key value; only Cloud Run accesses its secret.

## Check deployment

```powershell
gcloud run services describe gemini-live-camera --project=papillon-2207 --region=us-central1 --format="value(status.url)"
gcloud run services logs read gemini-live-camera --project=papillon-2207 --region=us-central1 --limit=30
```

A health response verifies the web server. A real Live test additionally requires
connecting in the interface and receiving audio/transcription. Test camera and
microphone permissions on the target device. Prompt edits require rebuilding the
image and deploying a new revision.

## Official references

- [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Cloud Run WebSockets and timeout](https://docs.cloud.google.com/run/docs/triggering/websockets)
- [Cloud Run Secret Manager integration](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Build deployment and IAM requirements](https://docs.cloud.google.com/build/docs/deploying-builds/deploy-cloud-run)
- [Secret version upload](https://docs.cloud.google.com/sdk/gcloud/reference/secrets/versions/add)
- [Private-service local proxy](https://docs.cloud.google.com/sdk/gcloud/reference/run/services/proxy)
