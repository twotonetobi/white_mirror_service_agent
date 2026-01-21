# White Mirror Service Agent

A cross-platform daemon for managing AI generation services in the White Mirror ecosystem.

## Features

- **Cross-Platform**: Runs on macOS, Windows, and Linux
- **Service Discovery**: Automatically discovers services in configured folders
- **Process Management**: Start, stop, restart services with health monitoring
- **Resource Monitoring**: GPU (NVIDIA/Apple Silicon), RAM, CPU, Disk metrics
- **LLM-Powered Capability Generation**: Auto-generate CAPABILITY.yaml by analyzing full service folders
- **Modern Web UI**: Beautiful dark-themed Gradio interface with clickable endpoint links
- **REST API**: Full API for orchestrator integration (`/discover` endpoint)

## Quick Start

### macOS / Linux

```bash
# Setup (creates venv)
./setup.sh

# Start (auto-opens browser)
./start.sh
```

### Windows

```powershell
# Setup (creates venv)
.\setup.ps1

# Start (auto-opens browser)
.\start_rs11.ps1
```

Or using Command Prompt:
```batch
setup.bat
start_rs11.bat
```

## Project Structure

```
11_0_ServiceAgent/
├── main.py                     # Entry point
├── config.yaml.example         # Configuration template (copy to config.yaml)
├── requirements.txt            # Python dependencies
│
├── start.sh                    # macOS/Linux startup script
├── start_rs11.bat              # Windows CMD startup script
├── start_rs11.ps1              # Windows PowerShell startup script
├── setup.sh                    # macOS/Linux setup script
├── setup.bat                   # Windows CMD setup script
├── setup.ps1                   # Windows PowerShell setup script
│
├── agent/
│   ├── api.py                  # REST API endpoints
│   ├── ui.py                   # Gradio web interface
│   ├── config.py               # Configuration with platform detection
│   ├── discovery.py            # Service folder scanning
│   ├── service_manager.py      # Process lifecycle management
│   ├── capability_generator.py # LLM-based capability generation
│   ├── resource_monitor.py     # GPU/RAM/CPU monitoring
│   ├── models.py               # Data models (Service, Capability)
│   ├── machine_id.py           # Machine identification
│   └── port_configurator.py    # Port conflict resolution
│
├── venv-{platform}/            # Virtual environment (venv-macos, venv-windows, venv-linux)
│
├── deploy/
│   ├── systemd/                # Linux systemd service files
│   ├── launchd/                # macOS launchd plist files
│   └── windows/                # Windows Task Scheduler setup
│
└── tests/                      # Unit tests (72 tests)
```

## Configuration

**First time setup:** Copy `config.yaml.example` to `config.yaml` and edit with your settings:
```bash
cp config.yaml.example config.yaml
# Edit config.yaml with your service_folders and API keys
```

The agent auto-detects your platform and machine ID, then looks for configuration in this order:

1. `./config.{machine_id}.yaml` - Machine-specific config
2. `./config-{platform}.yaml` - Platform-specific (macos, windows, linux)
3. `./config.yaml` - Default config
4. `~/.white_mirror_agent/config.{machine_id}.yaml`
5. `~/.white_mirror_agent/config-{platform}.yaml`
6. `~/.white_mirror_agent/config.yaml`

See [CAPABILITIES.md](./CAPABILITIES.md) for full configuration schema.

### Example Configuration

```yaml
machine_id: "my-workstation"
machine_name: "My GPU Workstation"

agent:
  port: 9100
  host: "0.0.0.0"
  log_level: "INFO"

service_folders:
  - "./services"
  - "/path/to/your/services"

always_running:
  - "comfyui_bridge"

ui:
  enabled: true
  open_browser: true
  theme: "soft"

llm:
  provider: "openrouter"
  model: "google/gemini-3-flash-preview"
```

## LLM Capability Generation

The agent uses **Gemini 3 Flash Preview** (via OpenRouter) to analyze service folders and generate `CAPABILITY.yaml` files.

### What Gets Sent to the LLM

The capability generator reads the **complete service folder** (not just README):

1. **Directory tree** (3 levels deep, excludes venv, node_modules, .git, etc.)

2. **Priority files** (read in order, up to 120K chars total):
   - `main.py`, `app.py`, `server.py`, `run.py`
   - `README.md`, `PLAN.md`, `knowledge.md`
   - `config.yaml`, `config.json`, `settings.yaml`
   - `src/api/routes.py`, `routes.py`, `endpoints.py`
   - `requirements.txt`, `pyproject.toml`
   - `.env.example`, `Dockerfile`, `docker-compose.yaml`

3. **Python files from src/** directory (if space remaining)

Each file is capped at 15K characters. The LLM analyzes actual code to extract:
- Port configuration (env vars, CLI args, defaults)
- API endpoints and routes
- Input/output types
- Environment variables
- Service metadata

### Generated CAPABILITY.yaml

```yaml
schema_version: "1.0"
service:
  id: "comfyui_bridge"
  name: "ComfyUI Bridge Service"
  description: "..."

runtime:
  start_command: "python main.py"
  ports:
    api:
      default: 8200
      env_var: "COMFYUI_BRIDGE_API_PORT"
    ui:
      default: 7880
      env_var: "COMFYUI_BRIDGE_GRADIO_PORT"

endpoints:
  api:
    port_key: "api"
    base_path: "/api/comfyui"
    health_check: "/health"

capabilities:
  inputs:
    - type: "text"
    - type: "image"
  outputs:
    - type: "image"
    - type: "video"
  operations:
    - id: "generate"
      endpoint: "/api/comfyui/generate"
      method: "POST"
```

## Monitored Services

The agent can manage these White Mirror services (ports are auto-assigned to avoid conflicts):

| Service | Configured Ports (API/UI) | Description |
|---------|---------------------------|-------------|
| ComfyUI Bridge | 8104 / 7802 | Image, video, 3D generation via ComfyUI |
| ChatterboxTTS | 8100 / 7803 | Text-to-speech with voice cloning |
| SunoAPIBridge | 8101 / 7800 | AI music generation via Suno |
| VideoAPIBridge | 8102 / 7804 | Video generation (Kling, Veo) |
| Stable Fast 3D | 8103 / 7801 | Image to 3D mesh conversion |
| Gaussian Splat | 8199 / 7849 | 3D Gaussian splat reconstruction |
| Z-Image FLUX | 8197 / 7847 | Text-to-image with FLUX model |

## REST API

Core endpoints (see [CAPABILITIES.md](./CAPABILITIES.md) for complete API reference with 26 endpoints):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/discover` | GET | List all services with full capabilities (for orchestrator) |
| `/status` | GET | Agent status and resources |
| `/services` | GET | List all services |
| `/services/{id}` | GET | Service details |
| `/services/{id}/start` | POST | Start a service |
| `/services/{id}/stop` | POST | Stop a service |
| `/services/{id}/restart` | POST | Restart a service |
| `/services/{id}/health` | GET | Check service health |
| `/services/{id}/logs` | GET | Get service logs |
| `/services/{id}/refresh-capability` | POST | Regenerate CAPABILITY.yaml |
| `/resources` | GET | System resource metrics |
| `/config` | GET/PUT | Agent configuration |
| `/scan` | POST | Rescan service folders |

Additional endpoints for port management, machine config, and README synchronization are documented in CAPABILITIES.md.

### /discover Response (for White Mirror Orchestrator)

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
      "status": "ready",
      "capability": {
        "endpoints": {
          "api": { "port": 8200, "health_check": "/health" },
          "ui": { "port": 7880 }
        },
        "operations": [...],
        "inputs": [...],
        "outputs": [...]
      }
    }
  ],
  "resources": { "gpu": {...}, "memory": {...} }
}
```

## Web UI

Access the modern web interface at `http://localhost:9100/ui`

**Header**: Shows machine info on the left, LLM Provider badge on the right

**Tabs:**
- **Services**: Select service, view details with clickable endpoint links, Start/Stop, Generate CAPABILITY.yaml
- **Folders**: Add/remove service folders
- **Resources**: GPU, RAM, CPU, Disk monitoring with visual bars
- **Logs**: View service logs
- **Config**: View agent configuration

**Services Tab Features:**
- Auto-loads first service on startup
- Shows clickable links: **Gradio UI** and **REST API** (open in new tab)
- 1-line LLM Status for generation feedback
- CAPABILITY.yaml viewer with syntax highlighting

## Platform-Specific Notes

### macOS (Apple Silicon)
- Uses `system_profiler` for GPU detection
- VRAM monitoring limited (total only, not usage)
- Full CPU/RAM monitoring via psutil

### Windows (NVIDIA)
- Full GPU monitoring via pynvml
- VRAM usage, temperature, utilization
- Runs as Scheduled Task for auto-start

### Linux (NVIDIA)
- Full GPU monitoring via pynvml
- Runs as systemd service for auto-start

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | API key for LLM capability generation |
| `WM_AGENT_PORT` | Override agent port (default: 9100) |
| `WM_AGENT_MACHINE_ID` | Override machine ID |
| `WM_AGENT_LOG_LEVEL` | Override log level |
| `OPEN_BROWSER` | Set to "false" to disable auto-browser-open |

## Development

```bash
# Run tests (macOS)
source venv-macos/bin/activate
pytest tests/ -v

# Run tests (Windows)
.\venv-windows\Scripts\Activate.ps1
pytest tests/ -v

# Run with debug logging
WM_AGENT_LOG_LEVEL=DEBUG python main.py
```

## License

Part of the White Mirror project.
