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
    $content = @"
source = "$downloads"
dest = "$downloads/_Filed"

[schedule]
mode = "auto"
notify = true

[model]
backend = "ollama"
"@
    # Windows PowerShell 5.1's `-Encoding utf8` writes a UTF-8 BOM, which
    # Python's tomllib rejects as invalid syntax; write explicitly without
    # one so this works on both 5.1 and PowerShell 7+.
    [System.IO.File]::WriteAllText($ConfigPath, $content, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Wrote default config to $ConfigPath -- edit it (backend, model name) before relying on 'auto' mode."
}

Write-Host "Next: run register-task.ps1 to set up the weekly scheduled task."
