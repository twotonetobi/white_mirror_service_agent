# White Mirror Service Agent - Implementation Plan

**Last Updated**: January 21, 2026  
**Status**: Production Ready - Cross-Platform Support Complete  
**Spec Document**: `00_plan/SERVICE_AGENT_SPEC.md`

---

## Implementation Phases

### Phase 1: Core Foundation ✅
> Minimum viable agent that can discover services and expose REST API

- [x] Project Setup (requirements.txt, config.yaml.example, package structure)
- [x] Configuration System (`agent/config.py`)
- [x] Data Models (`agent/models.py`)
- [x] Service Discovery (`agent/discovery.py`)
- [x] Basic REST API (`agent/api.py`)

### Phase 2: Process Management ✅
> Start, stop, and monitor service processes

- [x] Service Manager (`agent/service_manager.py`)
- [x] Dynamic Port Allocation
- [x] Process Management API
- [x] Health Checking

### Phase 3: LLM Capability Generation ✅
> Auto-generate CAPABILITY.yaml from complete service folders

- [x] Folder Analyzer (`agent/capability_generator.py`)
- [x] LLM Integration (OpenRouter/Gemini 3 Flash Preview)
- [x] Capability API

### Phase 4: Resource Monitoring ✅
> Track GPU and system resources

- [x] GPU Monitor (NVIDIA + Apple Silicon)
- [x] System Monitor (RAM, CPU, Disk)
- [x] Resource API

### Phase 5: Gradio UI ✅
> Web interface for managing services

- [x] Services Tab (with clickable endpoint links)
- [x] Folders Tab (add/remove service folders)
- [x] Resources Tab (GPU/RAM/CPU/Disk bars)
- [x] Logs Tab
- [x] Config Tab

### Phase 6: Auto-Start & Polish ✅
> Production readiness

- [x] Auto-Start Services
- [x] Configuration API
- [x] Error Handling
- [x] Documentation

### Phase 7: Testing & Deployment ✅
> Quality assurance and deployment

- [x] Unit Tests (72 tests)
- [x] Deployment configs (systemd, launchd, Windows Task Scheduler)

---

## Current Progress

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 | **COMPLETE** | Core foundation |
| Phase 2 | **COMPLETE** | Process management |
| Phase 3 | **COMPLETE** | LLM capability generation (full folder analysis) |
| Phase 4 | **COMPLETE** | Resource monitoring |
| Phase 5 | **COMPLETE** | Gradio UI with endpoint links |
| Phase 6 | **COMPLETE** | Auto-start, Config API |
| Phase 7 | **COMPLETE** | Tests & deployment |

---

## LLM Capability Generation Details

The capability generator sends the **complete service folder** to Gemini 3 Flash Preview:

### Files Read (Priority Order)
```
main.py, app.py, server.py, run.py
README.md, PLAN.md, knowledge.md, docs/README.md
config.yaml, config.json, settings.yaml
src/api/routes.py, api/routes.py, routes.py, endpoints.py
requirements.txt, pyproject.toml, setup.py
.env.example, .env.template
Dockerfile, docker-compose.yaml
+ Python files from src/ directory
```

### Limits
- **Max total context**: 120,000 characters
- **Max per file**: 15,000 characters
- **Directory tree depth**: 3 levels
- **Excludes**: .git, venv, node_modules, __pycache__, .pytest_cache

### What LLM Extracts
- Port numbers and configuration methods (env vars, CLI args)
- API endpoints and route definitions
- Input/output types and formats
- Environment variables
- Service metadata and version

---

## Files Created

```
white-mirror-agent/
├── main.py                        # Entry point (FastAPI + Gradio)
├── config.yaml                    # Active configuration
├── config.yaml.example            # Template configuration
├── requirements.txt               # Python dependencies
├── PLAN.md                        # This file
├── KNOWLEDGE.md                   # Project knowledge base
│
├── agent/
│   ├── __init__.py               # Package init
│   ├── config.py                 # Configuration loading
│   ├── models.py                 # Data models (Service, Capability)
│   ├── api.py                    # FastAPI REST routes
│   ├── ui.py                     # Gradio UI
│   ├── discovery.py              # Service folder scanning
│   ├── service_manager.py        # Process lifecycle management
│   ├── capability_generator.py   # LLM-based capability generation
│   └── resource_monitor.py       # GPU/RAM/CPU monitoring
│
├── tests/                        # Unit tests (72 tests)
│
├── deploy/
│   ├── systemd/                  # Linux systemd unit
│   ├── launchd/                  # macOS launchd plist
│   └── windows/                  # Windows installer script
│
├── start.sh / start.bat / start.ps1    # Platform startup scripts
├── setup.sh / setup.bat / setup.ps1    # Platform setup scripts
├── config-macos.yaml                   # macOS-specific config
├── config-windows.yaml                 # Windows-specific config
├── config-linux.yaml                   # Linux-specific config
├── venv-macos/                         # macOS virtual environment
├── venv-windows/                       # Windows virtual environment
└── venv-linux/                         # Linux virtual environment
```

---

## Live Testing Status (January 2026)

**Verified Working:**
- ✅ All 72 unit tests pass
- ✅ ServiceAgent starts successfully on port 9100
- ✅ Gradio UI accessible at `/ui` with clickable endpoint links
- ✅ `/discover` endpoint returns services with full capability info
- ✅ Service discovery finds services in configured folders
- ✅ LLM generation works (Gemini 3 Flash Preview via OpenRouter)

**CAPABILITY.yaml Created For:**
- ✅ 11_ComfyUI_Bridge (ready, 4 operations)
- ✅ 11_ChatterboxTTS (ready, 6 operations)
- ✅ 11_SunoAPIBridge (ready, 4 operations)
- ✅ 11_VideoAPIBridge (ready, 5 operations)
- ✅ 11_StableFast3D_Mac (ready, 5 operations)
- ✅ 11_GaussianSplat_Sharp_Mac (ready, 5 operations)
- ✅ 11_Z-Image-Turbo_Flux2Dev_Mac (ready, 6 operations)

**Configured Services (ports persisted in .env files):**
| Service | API Port | UI Port | Status |
|---------|----------|---------|--------|
| ComfyUI Bridge | 8104 | 7802 | ready |
| ChatterboxTTS | 8100 | 7803 | ready |
| SunoAPIBridge | 8101 | 7800 | ready |
| VideoAPIBridge | 8102 | 7804 | ready |
| Stable Fast 3D | 8103 | 7801 | ready |
| Gaussian Splat | 8199 | 7849 | ready |
| Z-Image FLUX | 8197 | 7847 | ready |

---

## UI Features

**Services Tab:**
- Auto-selects first service on load
- Shows service info with clickable endpoint links:
  - **Gradio UI**: http://localhost:{ui_port} (opens in new tab)
  - **REST API**: http://localhost:{api_port} (opens in new tab)
- Start/Stop buttons
- Generate CAPABILITY.yaml button (triggers LLM)
- 1-line LLM Status
- CAPABILITY.yaml viewer

**Folders Tab:**
- Service folder list
- Add/Remove folder buttons
- Status feedback

---

## Quick Start

### macOS / Linux
```bash
./setup.sh    # First time only
./start.sh    # Starts agent, opens browser
```

### Windows
```powershell
.\setup.ps1   # First time only
.\start.ps1   # Starts agent, opens browser
```

---

## Configuration

Set `OPENROUTER_API_KEY` environment variable for LLM capability generation.

Edit `config-<platform>.yaml` for platform-specific settings.

Add services to `always_running` list for auto-start on agent startup.
