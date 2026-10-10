<# Builds and deploys the reviewed Cloud Run configuration. No secret values in arguments. #>
[CmdletBinding()]
param(
    [ValidatePattern('^[a-z][a-z0-9-]+$')]
    [string]$Project = 'papillon-2207',
    [ValidatePattern('^[a-z]+-[a-z]+[0-9]+$')]
    [string]$Region = 'us-central1',
    [ValidatePattern('^[a-z][a-z0-9-]+$')]
    [string]$Repository = 'hotai',
    [ValidatePattern('^[a-z][a-z0-9-]+$')]
    [string]$Service = 'gemini-live-camera',
    [string]$ServiceAccount = '',
    [string]$BuildServiceAccount = '',
    [ValidatePattern('^[a-zA-Z0-9_-]+$')]
    [string]$Secret = 'gemini-live-api-key',
    [ValidatePattern('^[0-9]+$')]
    [string]$SecretVersion = '1',
    [ValidatePattern('^[a-z]+-[a-z]+[0-9]+$')]
    [string]$GeminiLocation = 'us-central1',
    [switch]$Public
)

$ErrorActionPreference = 'Stop'
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw 'Install the Google Cloud CLI and run gcloud auth login first. See deploy/README.md.'
}
if (-not $ServiceAccount) {
    $ServiceAccount = "gemini-live-service@$Project.iam.gserviceaccount.com"
}
if ($ServiceAccount -notmatch '^[a-zA-Z0-9-]+@[a-zA-Z0-9-]+\.iam\.gserviceaccount\.com$') {
    throw 'Invalid runtime service account email.'
}
if ($BuildServiceAccount -and $BuildServiceAccount -notmatch '^[a-zA-Z0-9-]+@[a-zA-Z0-9-]+\.iam\.gserviceaccount\.com$') {
    throw 'Invalid build service account email.'
}

function Invoke-Gcloud {
    param([string[]]$Arguments)
    & gcloud @Arguments
    if ($LASTEXITCODE -ne 0) { throw "gcloud command failed (exit $LASTEXITCODE)." }
}

$sourcePath = Split-Path -Parent $PSScriptRoot
$tag = Get-Date -Format 'yyyyMMdd-HHmmss'
$substitutions = "_REGION=$Region,_REPOSITORY=$Repository,_SERVICE=$Service,_IMAGE=$Service,_TAG=$tag,_GEMINI_LOCATION=$GeminiLocation,_SERVICE_ACCOUNT=$ServiceAccount,_SECRET=$Secret,_SECRET_VERSION=$SecretVersion"

# Prerequisites are provisioned explicitly using the runbook, not silently created here.
Invoke-Gcloud -Arguments @('artifacts', 'repositories', 'describe', $Repository, '--project', $Project, '--location', $Region)
Invoke-Gcloud -Arguments @('secrets', 'versions', 'describe', $SecretVersion, '--secret', $Secret, '--project', $Project, '--format=value(state)')

$buildArguments = @('builds', 'submit', $sourcePath, '--project', $Project, '--region', $Region,
    '--config', (Join-Path $sourcePath 'cloudbuild.yaml'), '--substitutions', $substitutions)
if ($BuildServiceAccount) {
    $buildArguments += "--service-account=projects/$Project/serviceAccounts/$BuildServiceAccount"
}
Invoke-Gcloud -Arguments $buildArguments

if ($Public) {
    # Explicit opt-in: visitors can use the Gemini-backed application.
    Invoke-Gcloud -Arguments @('run', 'services', 'add-iam-policy-binding', $Service,
        '--project', $Project, '--region', $Region, '--member=allUsers', '--role=roles/run.invoker')
}
Invoke-Gcloud -Arguments @('run', 'services', 'describe', $Service,
    '--project', $Project, '--region', $Region, '--format=value(status.url)')
