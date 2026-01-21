# White Mirror Service Agent - Knowledge Base

**Last Updated**: January 21, 2026

---

## Project Overview

The **White Mirror Service Agent** is a lightweight Python daemon that runs on every machine in the White Mirror network. It serves as the local service management layer for AI generation services (image, video, audio, 3D models).

### Core Purpose

1. **Discover** generation services in configured folders
2. **Analyze** complete service folders using LLM to understand capabilities
3. **Generate** structured `CAPABILITY.yaml` files for each service
4. **Manage** service lifecycle (start, stop, restart)
5. **Monitor** system resources (RAM, VRAM, GPU)
6. **Report** available services to the White Mirror Orchestrator via `/discover` API

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WHITE MIRROR ORCHESTRATOR                               │
│   (Central coordinator - NOT in this repo)                                  │
│   GET /discover → Collects services from all agents                         │
│   POST /services/{id}/start → Triggers service start via agent              │
└────────────────────────────────────────┬────────────────────────────────────┘
                                         │ REST API (:9100)
         ┌───────────────────────────────┼───────────────────────────────┐
         ▼                               ▼                               ▼
┌───────────────────┐      ┌───────────────────┐      ┌───────────────────┐
│   SERVICE AGENT   │      │   SERVICE AGENT   │      │   SERVICE AGENT   │
│   (Mac - Local)   │      │   (Windows PC)    │      │   (Linux Server)  │
│   Port: 9100      │      │   Port: 9100      │      │   Port: 9100      │
├───────────────────┤      ├───────────────────┤      ├───────────────────┤
│ Services:         │      │ Services:         │      │ Services:         │
│ • suno_bridge     │      │ • comfyui_bridge  │      │ • tts_bridge      │
│ • tts_bridge      │      │ • gaussian_splat  │      │                   │
│                   │      │ • video_gen       │      │                   │
└───────────────────┘      └───────────────────┘      └───────────────────┘
```

---

## Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Cross-Platform** | Runs on macOS, Windows, Linux |
| **Lightweight** | Minimal resource usage (~50MB RAM) |
| **LLM-Assisted** | Uses Gemini 3 Flash Preview to analyze full service folders |
| **Cache-First** | CAPABILITY.yaml is source of truth, only regenerated on demand |
| **No Auth** | Trusts VPN network security |
| **Auto-Start** | Critical services start automatically |

---

## Technology Stack

- **Language**: Python 3.10+
- **Web Framework**: FastAPI + Uvicorn
- **UI**: Gradio 4.x (mounted on FastAPI)
- **LLM**: OpenRouter → Gemini 3 Flash Preview (via litellm)
- **Process Management**: subprocess (cross-platform)
- **Resource Monitoring**: psutil + pynvml (NVIDIA)

---

## Key Components

### 1. Service Discovery (`agent/discovery.py`)
- Scans configured folders for services
- Validates presence of README.md or main.py
- Loads CAPABILITY.yaml if present
- Tracks service states

### 2. CAPABILITY.yaml Generator (`agent/capability_generator.py`)

**What Gets Sent to Gemini 3 Flash:**

The generator reads the **complete service folder** (not just README):

1. **Directory tree** (3 levels deep)
   - Excludes: .git, __pycache__, node_modules, venv, .pytest_cache

2. **Priority files** (in order, up to 120K chars total, 15K per file):
   ```
   main.py, app.py, server.py, run.py
   README.md, PLAN.md, knowledge.md, docs/README.md
   config.yaml, config.json, settings.yaml
   src/api/routes.py, api/routes.py, routes.py, endpoints.py
   requirements.txt, pyproject.toml, setup.py
   .env.example, .env.template
   Dockerfile, docker-compose.yaml
   ```

3. **Additional Python files** from `src/` directory (if space remaining)

**LLM analyzes actual code to extract:**
- Port numbers and configuration methods (env vars, CLI args)
- API endpoints and route definitions
- Input/output types and formats
- Environment variables
- Service metadata and version

**Generated CAPABILITY.yaml includes:**
- Service ID, name, description, version
- Runtime config (start command, ports, env vars)
- Endpoint definitions with actual port numbers
- Operations with HTTP methods and paths
- Input/output type specifications
- Resource requirements (GPU, RAM)

### 3. Service Manager (`agent/service_manager.py`)
- Starts/stops/restarts services via subprocess
- Handles dynamic port assignment
- Captures logs from running processes
- Manages process lifecycle

### 4. Resource Monitor (`agent/resource_monitor.py`)
- GPU monitoring (NVIDIA via pynvml, Apple Silicon via system_profiler)
- RAM/CPU monitoring via psutil
- Reports available resources

### 5. REST API (`agent/api.py`)

Key endpoints:
- `GET /discover` - List all services with full capabilities (for orchestrator)
- `GET /status` - Agent status and resources
- `POST /services/{id}/start` - Start service with port assignments
- `POST /services/{id}/stop` - Stop running service
- `POST /services/{id}/refresh-capability` - Regenerate CAPABILITY.yaml
- `GET /ports/conflicts` - Detect port conflicts across services
- `POST /ports/resolve` - Resolve conflicts by updating .env files

### 6. Port Configurator (`agent/port_configurator.py`)
- Manages persistent port configurations in service `.env` files
- Detects and resolves port conflicts
- Syncs README port references with actual configuration
- Uses platform-specific port ranges (see Dynamic Port Allocation)

### 7. Gradio UI (`agent/ui.py`)

**Header:**
- Left: Title, Machine Name, Platform
- Right: LLM Provider badge (google/gemini-3-flash-preview)

**Tabs:**
- **Services**: Service selector, Start/Stop buttons, endpoint links, Generate CAPABILITY.yaml
- **Folders**: Add/remove service folders
- **Resources**: GPU/RAM/CPU/Disk monitoring with visual bars
- **Logs**: View service stdout/stderr logs
- **Config**: View agent configuration

**Services Tab Features:**
- Auto-selects first service on load
- Shows clickable links for Gradio UI and REST API (open in new tab)
- 1-line LLM Status for generation feedback
- CAPABILITY.yaml viewer with syntax highlighting

---

## Configuration

```yaml
# config.yaml
machine_id: "ws-5090-main"
machine_name: "RTX 5090 Workstation"

agent:
  port: 9100
  host: "0.0.0.0"
  log_level: "INFO"

service_folders:
  - "D:/white_mirror_services"
  - "/tools/comfyui_bridge"

always_running:
  - "comfyui_bridge"

llm:
  provider: "openrouter"
  model: "google/gemini-3-flash-preview"
  api_key: "${OPENROUTER_API_KEY}"
```

---

## Service States

| State | Description |
|-------|-------------|
| `discovered` | Folder found, no CAPABILITY.yaml yet |
| `ready` | CAPABILITY.yaml exists and valid |
| `starting` | Service is being started |
| `running` | Service running and healthy |
| `stopping` | Service being stopped |
| `stopped` | Service was running, now stopped |
| `failed` | Failed to start or crashed |
| `error` | CAPABILITY.yaml invalid |

---

## Dynamic Port Allocation

Services support flexible ports via environment variables:
1. Orchestrator assigns ports to avoid conflicts
2. Agent sets environment variables from CAPABILITY.yaml config
3. Service reads port from env var at startup
4. Agent reports actual ports in /discover response

Example CAPABILITY.yaml port config:
```yaml
runtime:
  ports:
    api:
      default: 8200
      env_var: "COMFYUI_BRIDGE_API_PORT"
      cli_arg: "--api-port"
    ui:
      default: 7880
      env_var: "COMFYUI_BRIDGE_GRADIO_PORT"
```

### Platform Port Ranges

Each platform has dedicated port ranges defined in `agent/config.py` via `MACHINE_PORT_RANGES`:

| Platform | API Ports | UI Ports |
|----------|-----------|----------|
| macOS | 8100-8199 | 7800-7849 |
| Windows-1 | 8200-8299 | 7850-7899 |
| Windows-2 | 8300-8399 | 7900-7949 |
| Linux | 8400-8499 | 7950-7999 |

**Why separate ranges?** When multiple machines run services on the same network, this prevents port collisions. Each machine's services use ports within its platform's range.

### Port Configurator (`agent/port_configurator.py`)

Handles persistent port configuration:
- Reads/writes service `.env` files
- Resolves conflicts by assigning next available port in range
- Syncs README.md port references with actual `.env` values

### Port Resolution Flow

```
1. GET /ports/conflicts
   → Returns services with overlapping default ports

2. POST /ports/resolve
   → For each conflict:
      a. Find next available port in platform range
      b. Update service .env file with new port
      c. Optionally sync README.md

3. POST /services/{id}/start-auto
   → Start service with auto-assigned ports from platform range
```

---

## /discover API Response

The `/discover` endpoint provides everything the White Mirror Orchestrator needs:

```json
{
  "agent": {
    "machine_id": "dev-workstation",
    "machine_name": "Development Workstation",
    "version": "1.0.0"
  },
  "services": [
    {
      "id": "11_comfyui_bridge",
      "name": "ComfyUI Bridge Service",
      "path": "/path/to/service",
      "status": "ready",
      "has_capability": true,
      "capability": {
        "runtime": {
          "start_command": "python main.py",
          "working_directory": ".",
          "ports": {
            "api": {"default": 8200, "env_var": "...", "cli_arg": "..."},
            "ui": {"default": 7880, "env_var": "..."}
          }
        },
        "endpoints": {
          "api": {
            "port": 8200,
            "base_path": "/api/comfyui",
            "health_check": "/health",
            "docs": "/docs"
          },
          "ui": {
            "port": 7880,
            "path": "/"
          }
        },
        "operations": [
          {
            "id": "generate",
            "name": "Generate by Trigger",
            "endpoint": "/api/comfyui/generate/by-trigger",
            "method": "POST",
            "inputs": ["text", "image"],
            "outputs": ["image", "video"]
          }
        ],
        "inputs": [
          {"type": "text", "description": "Prompts"},
          {"type": "image", "description": "Input images", "formats": ["png", "jpg"]}
        ],
        "outputs": [
          {"type": "image", "formats": ["png", "webp"]},
          {"type": "video", "formats": ["mp4"]}
        ]
      }
    }
  ],
  "resources": {
    "gpu": {"name": "Apple M4 Max", "vram_total_gb": 128},
    "memory": {"ram": {"total_gb": 128, "used_gb": 45}},
    "cpu": {"percent": 12.5},
    "disk": {"total_gb": 1000, "free_gb": 450}
  }
}
```

This allows the Orchestrator to:
1. Start service via Agent: `POST /services/{id}/start`
2. Connect directly to service: `http://machine:{port}{base_path}{endpoint}`
3. Check health: `http://machine:{port}/health`

---

## Live Verification (January 2026)

**Verified Working:**
- All 72 unit tests pass
- Agent starts on port 9100
- Discovery finds 7 services with CAPABILITY.yaml in "ready" state
- Gradio UI accessible at `/ui` with clickable endpoint links
- Resource monitoring works (Apple M4 Max detected)
- Port conflict resolution persists to `.env` files

**Configured Services (ports persisted in .env files):**
| Service | Port (API/UI) | Description |
|---------|---------------|-------------|
| ComfyUI Bridge | 8104/7802 | Image, video, 3D generation via ComfyUI |
| ChatterboxTTS | 8100/7803 | Text-to-speech with voice cloning |
| SunoAPIBridge | 8101/7800 | AI music generation via Suno |
| VideoAPIBridge | 8102/7804 | Video generation (Kling, Veo) |
| Stable Fast 3D | 8103/7801 | Image to 3D mesh conversion |
| Gaussian Splat | 8199/7849 | 3D Gaussian splat reconstruction |
| Z-Image FLUX | 8197/7847 | Text-to-image with FLUX model |
