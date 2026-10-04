# Installs uv (if missing), syncs the project environment, and writes a
# default config.toml if one doesn't already exist. Run once from the repo
# checkout on the Windows PC, then follow with register-task.ps1.
param(
    [string]$ConfigPath = "$env:USERPROFILE\.config\sort-sys-alpha\config.toml"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}

Write-Host "Syncing project environment in $RepoRoot..."
Push-Location $RepoRoot
try {
    uv sync --all-groups
}
finally {
    Pop-Location
}

if (Test-Path $ConfigPath) {
    Write-Host "Config already exists at $ConfigPath; leaving it alone."
}
else {
    $configDir = Split-Path -Parent $ConfigPath
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    $downloads = "$env:USERPROFILE\Downloads" -replace '\\', '/'
    @"
source = "$downloads"
dest = "$downloads/_Filed"

[schedule]
mode = "auto"
notify = true

[model]
backend = "ollama"
"@ | Set-Content -Path $ConfigPath -Encoding utf8
    Write-Host "Wrote default config to $ConfigPath -- edit it (backend, model name) before relying on 'auto' mode."
}

Write-Host "Next: run register-task.ps1 to set up the weekly scheduled task."
