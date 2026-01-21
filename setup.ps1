$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║       White Mirror Service Agent - Windows Setup              ║" -ForegroundColor Cyan  
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Platform:    windows" -ForegroundColor White
Write-Host "  Virtual Env: venv-windows" -ForegroundColor White
Write-Host ""

$VenvDir = "venv-windows"

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Host "❌ Python not found" -ForegroundColor Red
    Write-Host "   Please install Python 3.10+ and add to PATH" -ForegroundColor Red
    exit 1
}

$PythonVersion = (python --version 2>&1) -replace "Python ", ""
Write-Host "  Python Ver:  $PythonVersion" -ForegroundColor White
Write-Host ""

if (Test-Path $VenvDir) {
    Write-Host "⚠️  Virtual environment already exists: $VenvDir" -ForegroundColor Yellow
    $reply = Read-Host "Recreate it? [y/N]"
    if ($reply -eq "y" -or $reply -eq "Y") {
        Write-Host "🗑️  Removing existing venv..." -ForegroundColor Yellow
        Remove-Item -Path $VenvDir -Recurse -Force
    } else {
        Write-Host "✅ Using existing venv" -ForegroundColor Green
        & "$VenvDir\Scripts\Activate.ps1"
        pip install -q --upgrade pip
        pip install -q -r requirements.txt
        Write-Host "✅ Dependencies updated" -ForegroundColor Green
        exit 0
    }
}

Write-Host "📦 Creating virtual environment..." -ForegroundColor Cyan
python -m venv $VenvDir

Write-Host "🔧 Activating..." -ForegroundColor Cyan
& "$VenvDir\Scripts\Activate.ps1"

Write-Host "📥 Upgrading pip..." -ForegroundColor Cyan
pip install -q --upgrade pip

Write-Host "📥 Installing dependencies..." -ForegroundColor Cyan
pip install -q -r requirements.txt

Write-Host "📥 Installing NVIDIA GPU support..." -ForegroundColor Cyan
pip install -q pynvml

$ConfigFile = "config-windows.yaml"
if (-not (Test-Path $ConfigFile) -and (Test-Path "config.yaml.example")) {
    Write-Host "📝 Creating platform config: $ConfigFile" -ForegroundColor Cyan
    Copy-Item "config.yaml.example" $ConfigFile
    
    $hostname = [System.Net.Dns]::GetHostName().ToLower() -replace " ", "-"
    (Get-Content $ConfigFile) -replace 'machine_id:.*', "machine_id: `"$hostname-win`"" | Set-Content $ConfigFile
    (Get-Content $ConfigFile) -replace 'machine_name:.*', 'machine_name: "Windows Workstation"' | Set-Content $ConfigFile
}

Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║                    ✅ Setup Complete!                         ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  To start the Service Agent:" -ForegroundColor White
Write-Host ""
Write-Host "    .\start.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  The UI will automatically open in your browser at:" -ForegroundColor White
Write-Host "    http://localhost:9100/ui" -ForegroundColor Yellow
Write-Host ""
