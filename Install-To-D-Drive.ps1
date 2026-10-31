# Universal Fiat Crypto Terminal - Windows Installer
# Target: D:\Downloads\Universal Fiat Crypto Terminal
# Run in PowerShell as: powershell -ExecutionPolicy Bypass -File Install-To-D-Drive.ps1
# Or right-click -> Run with PowerShell

$ErrorActionPreference = "Stop"
$Target = "D:\Downloads\Universal Fiat Crypto Terminal"
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Installing Universal Fiat Crypto Terminal..." -ForegroundColor Cyan
Write-Host "Source: $Source"
Write-Host "Target: $Target"

# 1. Create target
New-Item -ItemType Directory -Force -Path $Target | Out-Null

# 2. Copy files (exclude installer itself re-copy loop safe + .git + node_modules if present)
$exclude = @("Install-To-D-Drive.ps1", ".git", "node_modules", "dist", ".next", ".turbo", "__pycache__")
Get-ChildItem -Path $Source -Force | ForEach-Object {
  if ($exclude -contains $_.Name) { Write-Host "Skip $($_.Name)"; return }
  $dest = Join-Path $Target $_.Name
  if ($_.PSIsContainer) {
    Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
  } else {
    Copy-Item -Path $_.FullName -Destination $dest -Force
  }
  Write-Host "Copied $($_.Name)"
}

# 3. Verify
Write-Host "`nInstalled files:" -ForegroundColor Green
Get-ChildItem $Target | Format-Table Name, LastWriteTime

Write-Host "`nDone! Next steps:" -ForegroundColor Yellow
Write-Host "1. cd '$Target'"
Write-Host "2. cp .env.example .env   (or: copy .env.example .env)"
Write-Host "3. Install deps: pnpm install  (needs Node>=20 + pnpm 9)"
Write-Host "   Python backend: pip install -r modal_backend/requirements.txt"
Write-Host "4. Start infra: docker compose -f infra/docker-compose.yml up -d postgres redis temporal opa otel"
Write-Host "5. pnpm test, then run API + Terminal per README.md"
