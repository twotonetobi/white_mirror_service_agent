$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "       White Mirror Service Agent - RS11 (Windows)                  " -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Machine ID:  rs11" -ForegroundColor White
Write-Host "  Virtual Env: venv_rs11" -ForegroundColor White
Write-Host ""

$VenvDir = "venv_rs11"

if (-not (Test-Path $VenvDir)) {
    Write-Host "Virtual environment not found: $VenvDir" -ForegroundColor Red
    Write-Host "Please create it with: python -m venv venv_rs11" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting Service Agent..." -ForegroundColor Green
Write-Host ""

& "$VenvDir\Scripts\Activate.ps1"

$env:WM_AGENT_PLATFORM = "windows"
$env:WM_AGENT_MACHINE_ID = "rs11"

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}

$OpenBrowser = if ($env:OPEN_BROWSER) { $env:OPEN_BROWSER } else { "true" }

if ($OpenBrowser -eq "true") {
    Start-Job -ScriptBlock {
        Start-Sleep -Seconds 3
        Start-Process "http://localhost:9100/ui"
    } | Out-Null
}

python main.py $args
