$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "outputs" | Out-Null

docker compose -f compose.yaml up -d --build

Write-Host ""
Write-Host "Stack started. First startup downloads Docling and Ollama models."
Write-Host "Agent API: http://localhost:8100"
