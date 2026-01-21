# Windows Deployment

## Prerequisites

- Windows 10/11 or Windows Server 2016+
- Python 3.10+ installed and in PATH
- Administrator privileges

## Installation

### Option 1: PowerShell Script (Recommended)

1. Open PowerShell as Administrator
2. Navigate to the service-agent directory
3. Run the installation script:

```powershell
.\deploy\windows\install-service.ps1
```

Custom installation path:
```powershell
.\deploy\windows\install-service.ps1 -InstallPath "D:\Services\WhiteMirror"
```

### Option 2: Manual Installation

1. **Create installation directory**
```powershell
mkdir C:\WhiteMirror\service-agent
mkdir C:\WhiteMirror\service-agent\logs
```

2. **Copy files**
```powershell
Copy-Item -Path . -Destination C:\WhiteMirror\service-agent -Recurse
```

3. **Create virtual environment**
```powershell
cd C:\WhiteMirror\service-agent
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
```

4. **Configure**
```powershell
Copy-Item config.yaml.example config.yaml
notepad config.yaml
```

5. **Create scheduled task** (run as Administrator)
```powershell
$Action = New-ScheduledTaskAction -Execute "C:\WhiteMirror\service-agent\venv\Scripts\python.exe" -Argument "C:\WhiteMirror\service-agent\main.py" -WorkingDirectory "C:\WhiteMirror\service-agent"
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "WhiteMirrorServiceAgent" -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings
```

## Management

### Start Service
```powershell
Start-ScheduledTask -TaskName "WhiteMirrorServiceAgent"
```

### Stop Service
```powershell
Stop-ScheduledTask -TaskName "WhiteMirrorServiceAgent"
```

### Check Status
```powershell
Get-ScheduledTask -TaskName "WhiteMirrorServiceAgent" | Select-Object State
```

### View Logs
```powershell
Get-Content C:\WhiteMirror\service-agent\logs\*.log -Tail 100
```

### View in Task Scheduler GUI
1. Press Win+R, type `taskschd.msc`, press Enter
2. Navigate to Task Scheduler Library
3. Find "WhiteMirrorServiceAgent"

## Uninstallation

```powershell
.\deploy\windows\install-service.ps1 -Uninstall
```

Or manually:
```powershell
Unregister-ScheduledTask -TaskName "WhiteMirrorServiceAgent" -Confirm:$false
Remove-Item -Path C:\WhiteMirror\service-agent -Recurse -Force
```

## Troubleshooting

### Service won't start
1. Check Python is installed: `python --version`
2. Check virtual environment exists: `Test-Path C:\WhiteMirror\service-agent\venv`
3. Test manual run:
```powershell
cd C:\WhiteMirror\service-agent
.\venv\Scripts\python main.py
```

### Port already in use
```powershell
netstat -ano | findstr :9100
taskkill /PID <pid> /F
```

### Check task history
1. Open Task Scheduler
2. Right-click the task > Properties
3. Go to History tab

### Enable task history (if disabled)
```powershell
wevtutil set-log Microsoft-Windows-TaskScheduler/Operational /enabled:true
```

## Firewall Configuration

If accessing from other machines, allow port 9100:

```powershell
New-NetFirewallRule -DisplayName "White Mirror Service Agent" -Direction Inbound -Protocol TCP -LocalPort 9100 -Action Allow
```
