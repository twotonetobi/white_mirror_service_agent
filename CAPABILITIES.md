# White Mirror Service Agent - Capabilities Reference

**Last Updated**: January 21, 2026

---

## Overview

The White Mirror Service Agent is a cross-platform daemon for discovering, managing, and monitoring AI generation services. This document provides comprehensive API reference, configuration schemas, and integration specifications.

---

## Feature Catalog

| Feature | Description |
|---------|-------------|
| **Cross-Platform** | Runs on macOS, Windows, and Linux |
| **Service Discovery** | Auto-discovers services in configured folders |
| **LLM Capability Generation** | Uses Gemini 3 Flash to analyze service folders and generate CAPABILITY.yaml |
| **Process Management** | Start, stop, restart services with health monitoring |
| **Dynamic Port Allocation** | Automatic port assignment to avoid conflicts |
| **Resource Monitoring** | GPU (NVIDIA/Apple Silicon), RAM, CPU, Disk metrics |
| **Web UI** | Gradio-based interface for service management |
| **REST API** | Full API for orchestrator integration |
| **Port Conflict Resolution** | Detect and resolve port conflicts across services |

---

## REST API Reference

Base URL: `http://localhost:9100` (configurable)

### Discovery & Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/discover` | GET | List all services with full capabilities (orchestrator integration) |
| `/status` | GET | Agent health status and service counts |
| `/resources` | GET | System resource metrics (GPU, RAM, CPU, Disk) |

### Service Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/services` | GET | List all discovered services |
| `/services/{id}` | GET | Get service details with recent logs |
| `/services/{id}/start` | POST | Start service with optional port assignments |
| `/services/{id}/stop` | POST | Stop running service |
| `/services/{id}/restart` | POST | Restart service |
| `/services/{id}/health` | GET | Check service health status |
| `/services/{id}/logs` | GET | Get service logs (query: `lines=100`) |
| `/services/{id}/refresh-capability` | POST | Regenerate CAPABILITY.yaml via LLM |
| `/services/{id}/start-auto` | POST | Start with automatic port assignment |

### Port Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ports/conflicts` | GET | Get services with conflicting default ports |
| `/ports/assignments` | GET | Get recommended non-conflicting port assignments |
| `/ports/ranges` | PUT | Update port range configuration |
| `/ports/resolve` | POST | Resolve port conflicts by updating .env files |
| `/services/{id}/ports` | GET | Get current port configuration for a service |

### Configuration

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/config` | GET | Get agent configuration |
| `/config` | PUT | Update agent configuration |
| `/scan` | POST | Rescan service folders |
| `/folders/add` | POST | Add service folder (query: `folder_path`) |

### Machine Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/machine/info` | GET | Get machine ID, platform, and port ranges |
| `/machine/generate-config` | POST | Generate machine-specific config file |

### README Synchronization

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/ports/sync-readmes` | POST | Sync all README port references with .env configs |
| `/services/{id}/sync-readme` | POST | Sync single service README with .env ports |

---

## API Request/Response Examples

### POST /services/{id}/start

**Request Body:**
```json
{
  "port_assignments": {
    "api": 8201,
    "ui": 7881
  },
  "env": {
    "CUSTOM_VAR": "value"
  }
}
```

**Response:**
```json
{
  "success": true,
  "service_id": "comfyui_bridge",
  "status": "running",
  "pid": 12345,
  "assigned_ports": {"api": 8201, "ui": 7881},
  "message": "Service started on ports {\"api\": 8201, \"ui\": 7881}"
}
```

### GET /discover

**Response:**
```json
{
  "agent": {
    "machine_id": "dev-workstation",
    "machine_name": "Development Workstation",
    "version": "1.0.0",
    "uptime_seconds": null
  },
  "services": [
    {
      "id": "comfyui_bridge",
      "name": "ComfyUI Bridge Service",
      "path": "/path/to/service",
      "status": "ready",
      "has_capability": true,
      "capability": {
        "runtime": {
          "start_command": "python main.py",
          "working_directory": ".",
          "ports": {
            "api": {"default": 8200, "configured": 8200, "env_var": "API_PORT"},
            "ui": {"default": 7880, "configured": 7880, "env_var": "UI_PORT"}
          }
        },
        "endpoints": {
          "api": {"port": 8200, "health_check": "/health", "base_path": "/api"},
          "ui": {"port": 7880, "path": "/"}
        },
        "operations": [...],
        "inputs": [...],
        "outputs": [...]
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

---

## Configuration Schema

Configuration is loaded from the first existing file in this order:
1. `./config.{machine_id}.yaml` - Machine-specific
2. `./config-{platform}.yaml` - Platform-specific (macos, windows, linux)
3. `./config.yaml` - Default
4. `~/.white_mirror_agent/config.{machine_id}.yaml`
5. `~/.white_mirror_agent/config-{platform}.yaml`
6. `~/.white_mirror_agent/config.yaml`

### Full Configuration Schema

```yaml
# MACHINE IDENTITY
machine_id: "my-workstation"              # Unique identifier (required)
machine_name: "My Workstation"            # Human-readable name
machine_description: "Description"

# AGENT SETTINGS
agent:
  port: 9100                              # REST API and UI port
  host: "0.0.0.0"                         # Listen address
  log_level: "INFO"                       # DEBUG, INFO, WARNING, ERROR
  log_file: null                          # Optional log file path

# SERVICE FOLDERS
service_folders:
  - "./services"                          # Relative paths supported
  - "/absolute/path/to/services"

# AUTO-START SERVICES
always_running:                           # Services to start on agent startup
  - "comfyui_bridge"

# RESOURCE MANAGEMENT
resources:
  gpu_vram_reserve_gb: 2                  # VRAM to keep free
  ram_reserve_gb: 4                       # RAM to keep free
  monitor_interval_seconds: 30            # Monitoring frequency

# LLM CONFIGURATION
llm:
  provider: "openrouter"                  # Only openrouter supported
  model: "google/gemini-3-flash-preview"  # Model for capability generation
  api_key: null                           # Set via OPENROUTER_API_KEY env var
  timeout_seconds: 120
  max_retries: 3

# HEALTH CHECK SETTINGS
health_check:
  enabled: true
  interval_seconds: 60                    # Health check frequency
  timeout_seconds: 5                      # Request timeout

# UI SETTINGS
ui:
  enabled: true                           # Enable Gradio UI
  share: false                            # Create public link
  auth: null                              # [["username", "password"]]
```

---

## Platform Port Ranges

Each platform has dedicated port ranges to prevent conflicts when multiple machines are accessible on the same network.

| Platform | API Ports | UI Ports |
|----------|-----------|----------|
| **macOS** | 8100-8199 | 7800-7849 |
| **Windows-1** | 8200-8299 | 7850-7899 |
| **Windows-2** | 8300-8399 | 7900-7949 |
| **Linux** | 8400-8499 | 7950-7999 |

**Default fallback** (if platform not matched): API 8100-8299, UI 7800-7999

### Port Range Configuration

Port ranges can be configured in `config.yaml`:

```yaml
port_ranges:
  api_port_min: 8100
  api_port_max: 8299
  ui_port_min: 7800
  ui_port_max: 7999
  auto_resolve_conflicts: true      # Automatically assign non-conflicting ports
  sync_readme_on_resolve: true      # Update README when resolving conflicts
```

### How Port Assignment Works

1. **Auto-assignment**: When starting a service with `/services/{id}/start-auto`, the agent assigns the next available port within the platform's range
2. **Conflict detection**: `/ports/conflicts` identifies services with overlapping default ports
3. **Resolution**: `/ports/resolve` updates service `.env` files with non-conflicting ports
4. **README sync**: `/ports/sync-readmes` updates documentation to reflect actual port assignments

---

## CAPABILITY.yaml Schema

Each managed service should have a `CAPABILITY.yaml` file describing its capabilities.

```yaml
schema_version: "1.0"

service:
  id: "service_id"                        # Unique identifier
  name: "Service Display Name"
  description: "What this service does"
  version: "1.0.0"

runtime:
  start_command: "python main.py"
  working_directory: "."
  venv:
    path: "./venv"                        # Optional virtual environment
  ports:
    api:
      default: 8200
      env_var: "SERVICE_API_PORT"         # Environment variable for port
      cli_arg: "--port"                   # CLI argument for port
      description: "REST API port"
    ui:
      default: 7880
      env_var: "SERVICE_UI_PORT"
      description: "Web UI port"
  environment:                            # Required environment variables
    - name: "API_KEY"
      required: true
      description: "API key for external service"

endpoints:
  api:
    port_key: "api"                       # References runtime.ports key
    base_path: "/api"
    health_check: "/health"
    docs: "/docs"
  ui:
    port_key: "ui"
    path: "/"

capabilities:
  operations:
    - id: "generate"
      name: "Generate Content"
      endpoint: "/api/generate"
      method: "POST"
      description: "Generate content from input"
      inputs: ["text", "image"]
      outputs: ["image"]
  inputs:
    - type: "text"
      description: "Text prompts"
    - type: "image"
      description: "Input images"
      formats: ["png", "jpg", "webp"]
  outputs:
    - type: "image"
      formats: ["png", "webp"]
    - type: "video"
      formats: ["mp4"]

resources:
  min_vram_gb: 8                          # Minimum VRAM required
  min_ram_gb: 16                          # Minimum RAM required
  gpu_required: true                      # Whether GPU is required

tags:
  - "image-generation"
  - "comfyui"
```

---

## Service States

| State | Description |
|-------|-------------|
| `discovered` | Folder found, no CAPABILITY.yaml yet |
| `ready` | CAPABILITY.yaml exists and is valid |
| `starting` | Service is being started |
| `running` | Service running and healthy |
| `stopping` | Service being stopped |
| `stopped` | Service was running, now stopped |
| `failed` | Failed to start or crashed |
| `error` | CAPABILITY.yaml invalid or other error |

---

## Deployment

### Linux (systemd)

See `deploy/systemd/` for service unit files.

```bash
sudo cp deploy/systemd/service-agent.service /etc/systemd/system/
sudo systemctl enable service-agent
sudo systemctl start service-agent
```

### macOS (launchd)

See `deploy/launchd/` for plist files.

```bash
cp deploy/launchd/com.whitemirror.service-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.whitemirror.service-agent.plist
```

### Windows (Task Scheduler)

See `deploy/windows/` for PowerShell installation scripts.

```powershell
.\deploy\windows\install-service.ps1
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | API key for LLM capability generation |
| `WM_AGENT_PORT` | Override agent port |
| `WM_AGENT_MACHINE_ID` | Override machine ID |
| `WM_AGENT_LOG_LEVEL` | Override log level |
| `OPEN_BROWSER` | Set to "false" to disable auto-browser-open |

---

## Integration with White Mirror Orchestrator

The agent exposes `/discover` endpoint for orchestrator integration:

1. **Orchestrator polls agents**: `GET http://{agent}:9100/discover`
2. **Orchestrator starts service**: `POST http://{agent}:9100/services/{id}/start`
3. **Orchestrator connects to service**: `http://{agent}:{port}{base_path}{endpoint}`
4. **Health monitoring**: `GET http://{agent}:{port}/health`

The agent handles:
- Service lifecycle (start/stop)
- Port conflict resolution
- Health monitoring
- Log collection
- Capability documentation
