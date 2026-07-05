# Control Network - Triage Copilot (PowerShell). Run:  ./run.ps1
Set-Location -Path $PSScriptRoot
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { Write-Host "Python not found. Install Python 3.11+ from https://python.org (Add to PATH)."; exit 1 }
python run.py
