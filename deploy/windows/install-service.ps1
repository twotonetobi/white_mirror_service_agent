# White Mirror Service Agent - Windows Installation Script
# Run as Administrator

param(
    [string]$InstallPath = "C:\WhiteMirror\service-agent",
    [string]$TaskName = "WhiteMirrorServiceAgent",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param([string]$Message)
    Write-Host "[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[+] $Message" -ForegroundColor Green
}

function Write-Error {
    param([string]$Message)
    Write-Host "[-] $Message" -ForegroundColor Red
}

# Check for admin privileges
if (-NOT ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "This script requires Administrator privileges. Please run as Administrator."
    exit 1
}

if ($Uninstall) {
    Write-Status "Uninstalling White Mirror Service Agent..."
    
    # Remove scheduled task
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Success "Removed scheduled task"
    }
    
    # Remove installation directory (optional - commented out for safety)
    # Remove-Item -Path $InstallPath -Recurse -Force
    # Write-Success "Removed installation directory"
    
    Write-Success "Uninstallation complete"
    exit 0
}

Write-Status "Installing White Mirror Service Agent..."

# Create installation directory
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    Write-Success "Created installation directory: $InstallPath"
}

# Create logs directory
$LogsPath = Join-Path $InstallPath "logs"
if (-not (Test-Path $LogsPath)) {
    New-Item -ItemType Directory -Path $LogsPath -Force | Out-Null
}

# Copy files (assumes running from source directory)
$SourcePath = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Write-Status "Copying files from $SourcePath..."

$filesToCopy = @(
    "main.py",
    "config.yaml.example",
    "requirements.txt",
    "agent"
)

foreach ($file in $filesToCopy) {
    $source = Join-Path $SourcePath $file
    $dest = Join-Path $InstallPath $file
    if (Test-Path $source) {
        Copy-Item -Path $source -Destination $dest -Recurse -Force
        Write-Success "Copied $file"
    }
}

# Create config.yaml if it doesn't exist
$ConfigPath = Join-Path $InstallPath "config.yaml"
if (-not (Test-Path $ConfigPath)) {
    Copy-Item -Path (Join-Path $InstallPath "config.yaml.example") -Destination $ConfigPath
    Write-Success "Created config.yaml from template"
}

# Check for Python
$PythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonPath) {
    Write-Error "Python not found. Please install Python 3.10+ and add to PATH."
    exit 1
}
Write-Success "Found Python: $PythonPath"

# Create virtual environment
$VenvPath = Join-Path $InstallPath "venv"
if (-not (Test-Path $VenvPath)) {
    Write-Status "Creating virtual environment..."
    & python -m venv $VenvPath
    Write-Success "Created virtual environment"
}

# Install dependencies
$PipPath = Join-Path $VenvPath "Scripts\pip.exe"
$RequirementsPath = Join-Path $InstallPath "requirements.txt"
Write-Status "Installing dependencies..."
& $PipPath install -r $RequirementsPath --quiet
Write-Success "Installed dependencies"

# Create scheduled task
Write-Status "Creating scheduled task..."

$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$MainScript = Join-Path $InstallPath "main.py"

# Task action
$Action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "`"$MainScript`"" `
    -WorkingDirectory $InstallPath

# Task trigger - at system startup
$Trigger = New-ScheduledTaskTrigger -AtStartup

# Task settings
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

# Task principal - run as SYSTEM for background service
$Principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Remove existing task if present
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

# Register task
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "White Mirror Service Agent - Manages AI generation services"

Write-Success "Created scheduled task: $TaskName"

# Start the task immediately
Write-Status "Starting service..."
Start-ScheduledTask -TaskName $TaskName
Start-Sleep -Seconds 2

# Verify it's running
$taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
if ($taskInfo.LastRunTime -gt (Get-Date).AddMinutes(-1)) {
    Write-Success "Service started successfully"
} else {
    Write-Status "Service may take a moment to start. Check status with:"
    Write-Host "  Get-ScheduledTask -TaskName $TaskName | Select-Object State"
}

Write-Host ""
Write-Success "Installation complete!"
Write-Host ""
Write-Host "Configuration file: $ConfigPath"
Write-Host "Logs directory: $LogsPath"
Write-Host "Web UI: http://localhost:9100/ui"
Write-Host ""
Write-Host "Management commands:"
Write-Host "  Start:   Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Stop:    Stop-ScheduledTask -TaskName $TaskName"
Write-Host "  Status:  Get-ScheduledTask -TaskName $TaskName | Select-Object State"
Write-Host "  Logs:    Get-Content $LogsPath\*.log -Tail 50"
