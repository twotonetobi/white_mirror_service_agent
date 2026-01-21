# White Mirror Service Agent

## Complete Implementation Specification v1.0

**Date:** December 2025  
**Purpose:** Lightweight daemon for discovering, managing, and monitoring White Mirror generation services across multiple machines

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Installation & Deployment](#3-installation--deployment)
4. [Configuration](#4-configuration)
5. [Service Discovery](#5-service-discovery)
6. [CAPABILITY.yaml Schema](#6-capabilityyaml-schema)
7. [LLM-Assisted Parsing](#7-llm-assisted-parsing)
8. [REST API Reference](#8-rest-api-reference)
9. [Gradio UI Specification](#9-gradio-ui-specification)
10. [Process Management](#10-process-management)
11. [Resource Monitoring](#11-resource-monitoring)
12. [Implementation Details](#12-implementation-details)
13. [File Structure](#13-file-structure)
14. [Example Scenarios](#14-example-scenarios)

---

## 1. Executive Summary

### What is the Service Agent?

The Service Agent is a **lightweight Python daemon** that runs on every machine in the White Mirror network. Its purpose is to:

1. **Discover** generation services in configured folders
2. **Parse** service documentation (READMEs) using LLM to understand capabilities
3. **Generate** structured `CAPABILITY.yaml` files for each service
4. **Manage** service lifecycle (start, stop, restart)
5. **Monitor** system resources (RAM, VRAM)
6. **Report** available services to the White Mirror Orchestrator

### Key Design Principles

| Principle | Description |
|-----------|-------------|
| **Cross-Platform** | Runs on macOS, Windows, Linux |
| **Lightweight** | Minimal resource usage (~50MB RAM) |
| **LLM-Assisted** | Uses Gemini Flash for intelligent parsing |
| **Cache-First** | CAPABILITY.yaml is source of truth, only regenerated on demand |
| **No Auth** | Trusts VPN network security |
| **Auto-Start** | Critical services start automatically |

### Communication Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WHITE MIRROR ORCHESTRATOR                               │
│                                                                              │
│   1. GET /discover → List all services across all agents                    │
│   2. Direct REST calls to service endpoints (not through agent)             │
│   3. POST /services/{id}/start → Start a service via agent                  │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │         Discovery Protocol       │
                    │         (REST API on :9100)      │
                    └────────────────┬────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
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

## 2. Architecture Overview

### Component Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           SERVICE AGENT                                     │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         GRADIO UI (:9100)                            │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │   │
│  │  │Services │ │Resources│ │ Config  │ │  Logs   │ │Refresh  │       │   │
│  │  │  Tab    │ │   Tab   │ │   Tab   │ │   Tab   │ │Caps Tab │       │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│  ┌───────────────────────────────────┴───────────────────────────────────┐ │
│  │                        FastAPI REST API (:9100)                        │ │
│  │  GET /discover  GET /status  POST /services/{id}/start  etc.          │ │
│  └───────────────────────────────────┬───────────────────────────────────┘ │
│                                      │                                      │
│  ┌───────────────┬───────────────────┼───────────────────┬───────────────┐ │
│  │               │                   │                   │               │ │
│  ▼               ▼                   ▼                   ▼               │ │
│ ┌─────────┐  ┌─────────┐      ┌───────────┐      ┌─────────────┐        │ │
│ │ Folder  │  │   LLM   │      │  Service  │      │  Resource   │        │ │
│ │ Scanner │  │ Parser  │      │  Manager  │      │  Monitor    │        │ │
│ │         │  │(Gemini) │      │           │      │             │        │ │
│ └────┬────┘  └────┬────┘      └─────┬─────┘      └──────┬──────┘        │ │
│      │            │                 │                   │               │ │
│      │            │           ┌─────┴─────┐            │               │ │
│      │            │           │subprocess │            │               │ │
│      │            │           │  manager  │            │               │ │
│      │            │           └───────────┘            │               │ │
│      │            │                                    │               │ │
│      └────────────┴────────────────┬───────────────────┘               │ │
│                                    │                                    │ │
│                        ┌───────────┴───────────┐                       │ │
│                        │   Service Registry    │                       │ │
│                        │   (in-memory cache)   │                       │ │
│                        └───────────────────────┘                       │ │
│                                    │                                    │ │
│  ┌─────────────────────────────────┴─────────────────────────────────┐ │ │
│  │                    Watched Service Folders                         │ │ │
│  │  /tools/comfyui_bridge/     → CAPABILITY.yaml ✓                   │ │ │
│  │  /tools/gaussian_splat/     → CAPABILITY.yaml ✓                   │ │ │
│  │  /tools/suno_bridge/        → CAPABILITY.yaml (generating...)     │ │ │
│  └───────────────────────────────────────────────────────────────────┘ │ │
└────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. STARTUP
   Agent starts → Loads config → Scans folders → Reads CAPABILITY.yaml files
                                                        ↓
                                               Missing? → Flag for LLM generation
                                                        ↓
                                               Auto-start "always_running" services

2. DISCOVERY REQUEST (from White Mirror)
   GET /discover → Return all services with capabilities from cached CAPABILITY.yaml

3. REFRESH CAPABILITY (manual trigger via UI)
   User clicks "Refresh" → LLM parses folder → Generates new CAPABILITY.yaml

4. SERVICE LIFECYCLE
   POST /services/{id}/start → Find service → Run start command → Track PID
   POST /services/{id}/stop  → Find PID → Terminate process → Update status
```

---

## 3. Installation & Deployment

### Prerequisites

- Python 3.10+
- pip or uv package manager
- Network access to OpenRouter (for LLM)
- GPU drivers (for VRAM monitoring, optional)

### Quick Install

```bash
# Clone or download
git clone https://github.com/your-org/white-mirror-agent.git
cd white-mirror-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows

# Install dependencies
pip install -r requirements.txt

# Create config from template
cp config.yaml.example config.yaml

# Edit config with your settings
# - Set machine_id
# - Add service_folders
# - Set OpenRouter API key (or use environment variable)

# Run the agent
python main.py
```

### Requirements

```
# requirements.txt
fastapi>=0.109.0
uvicorn>=0.27.0
gradio>=4.0.0
httpx>=0.26.0
pyyaml>=6.0
psutil>=5.9.0
pynvml>=11.5.0;platform_system=="Linux" or platform_system=="Windows"
litellm>=1.0.0
watchdog>=3.0.0
pydantic>=2.0.0
python-dotenv>=1.0.0
```

### Platform-Specific Notes

**macOS:**
- VRAM monitoring uses `system_profiler` for Apple Silicon
- Metal GPU memory is reported differently than NVIDIA

**Windows:**
- Requires NVIDIA drivers for `pynvml`
- Use `.\venv\Scripts\Activate.ps1` for PowerShell

**Linux:**
- Full `nvidia-smi` support via `pynvml`
- Can run as systemd service

### Running as a Service

**Linux (systemd):**

```ini
# /etc/systemd/system/white-mirror-agent.service
[Unit]
Description=White Mirror Service Agent
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/white-mirror-agent
Environment="PATH=/path/to/white-mirror-agent/venv/bin"
Environment="OPENROUTER_API_KEY=sk-or-..."
ExecStart=/path/to/white-mirror-agent/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Windows (Task Scheduler):**

Create a scheduled task that runs at startup:
```
Program: C:\path\to\venv\Scripts\python.exe
Arguments: main.py
Start in: C:\path\to\white-mirror-agent
```

**macOS (launchd):**

```xml
<!-- ~/Library/LaunchAgents/com.whitemirror.agent.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.whitemirror.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/venv/bin/python</string>
        <string>/path/to/white-mirror-agent/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/white-mirror-agent</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

---

## 4. Configuration

### Config File Location

The agent looks for configuration in this order:
1. `./config.yaml` (current directory)
2. `~/.white_mirror_agent/config.yaml` (user home)
3. Environment variables (prefix: `WM_AGENT_`)

### Configuration Schema

```yaml
# config.yaml

# ============================================================================
# MACHINE IDENTITY
# ============================================================================
machine_id: "ws-5090-main"          # REQUIRED: Unique identifier for this machine
machine_name: "RTX 5090 Workstation" # Human-readable name
machine_description: "Primary GPU workstation for image/video generation"

# ============================================================================
# AGENT SETTINGS
# ============================================================================
agent:
  port: 9100                        # Port for REST API and Gradio UI
  host: "0.0.0.0"                   # Listen address (0.0.0.0 for all interfaces)
  log_level: "INFO"                 # DEBUG, INFO, WARNING, ERROR
  log_file: null                    # Optional: path to log file

# ============================================================================
# SERVICE FOLDERS
# ============================================================================
# List of directories to scan for services
# Each folder should contain a service with README.md
service_folders:
  - "D:/white_mirror_services"
  - "D:/tools/comfyui_bridge"
  - "/home/user/services"

# ============================================================================
# ALWAYS RUNNING SERVICES
# ============================================================================
# Services to auto-start when agent starts
# Use service_id (folder name) as identifier
always_running:
  - "comfyui_bridge"
  - "gaussian_splat"

# ============================================================================
# RESOURCE MANAGEMENT
# ============================================================================
resources:
  gpu_vram_reserve_gb: 2            # Always keep this much VRAM free
  ram_reserve_gb: 4                 # Always keep this much RAM free
  monitor_interval_seconds: 30      # How often to check resources

# ============================================================================
# LLM CONFIGURATION (for parsing service folders)
# ============================================================================
llm:
  provider: "openrouter"            # Only openrouter supported currently
  model: "google/gemini-3-flash-preview"
  api_key: "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"
  timeout_seconds: 120              # Longer timeout for full folder analysis
  max_retries: 3

# ============================================================================
# HEALTH CHECK SETTINGS
# ============================================================================
health_check:
  enabled: true
  interval_seconds: 60              # How often to ping running services
  timeout_seconds: 5                # Timeout for health check requests

# ============================================================================
# UI SETTINGS
# ============================================================================
ui:
  enabled: true                     # Enable Gradio UI
  share: false                      # Create public Gradio link (not recommended)
  auth: null                        # Optional: [["username", "password"]]
```

### Environment Variables

All config values can be overridden with environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `WM_AGENT_MACHINE_ID` | Override machine_id | `ws-5090-main` |
| `WM_AGENT_PORT` | Override agent port | `9100` |
| `OPENROUTER_API_KEY` | OpenRouter API key | `sk-or-...` |
| `WM_AGENT_LOG_LEVEL` | Log level | `DEBUG` |

### Minimal Config Example

```yaml
# Minimal config.yaml
machine_id: "my-workstation"
service_folders:
  - "./services"
```

---

## 5. Service Discovery

### How Services Are Discovered

1. **Folder Scan**: Agent scans all `service_folders` for subdirectories
2. **Validation**: Each subdirectory must have at least a `README.md` or `main.py`
3. **Capability Check**: Look for existing `CAPABILITY.yaml`
4. **Status**: Service marked as "discovered" (capability unknown) or "ready" (capability known)

### Service Identification

Each service is identified by:

```
service_id = folder_name (lowercase, sanitized)
```

Example:
```
/tools/ComfyUI-Bridge/  →  service_id: "comfyui-bridge"
/tools/gaussian_splat/  →  service_id: "gaussian_splat"
```

### Discovery Algorithm

```python
def discover_services():
    services = []
    
    for folder in config.service_folders:
        for entry in os.scandir(folder):
            if not entry.is_dir():
                continue
            
            service_path = Path(entry.path)
            service_id = sanitize_id(entry.name)
            
            # Check for valid service indicators
            has_readme = (service_path / "README.md").exists()
            has_main = (service_path / "main.py").exists()
            has_capability = (service_path / "CAPABILITY.yaml").exists()
            
            if not (has_readme or has_main):
                continue  # Not a valid service
            
            service = {
                "id": service_id,
                "path": str(service_path),
                "has_capability": has_capability,
                "capability": load_capability(service_path) if has_capability else None,
                "status": "ready" if has_capability else "discovered"
            }
            
            services.append(service)
    
    return services
```

### Service States

| State | Description |
|-------|-------------|
| `discovered` | Folder found, but no CAPABILITY.yaml yet |
| `ready` | CAPABILITY.yaml exists and is valid |
| `starting` | Service is being started |
| `running` | Service is running and healthy |
| `stopping` | Service is being stopped |
| `stopped` | Service was running but is now stopped |
| `failed` | Service failed to start or crashed |
| `error` | CAPABILITY.yaml is invalid or service misconfigured |

---

## 6. CAPABILITY.yaml Schema

### Overview

`CAPABILITY.yaml` is the structured manifest that describes a service's capabilities. It is generated by the LLM from analyzing the entire service folder. **Critically**, it includes port configuration that enables dynamic port allocation.

### Full Schema

```yaml
# CAPABILITY.yaml - Auto-generated by Service Agent
# Do not edit manually. Use "Refresh Capability" in UI to regenerate.

# ============================================================================
# METADATA
# ============================================================================
schema_version: "1.0"
generated_at: "2025-12-30T14:30:00Z"
generated_by: "service-agent/1.0.0"
folder_hash: "abc123..."              # Hash of analyzed files for change detection

# ============================================================================
# SERVICE IDENTITY
# ============================================================================
service:
  id: "comfyui_bridge"                # Folder name (auto-set)
  name: "ComfyUI Bridge Service"      # Human-readable name
  description: "Middleware service bridging White Mirror with ComfyUI workstations"
  version: "1.0.0"                    # If detected from code/docs
  author: "White Mirror Team"         # If detected

# ============================================================================
# RUNTIME CONFIGURATION
# ============================================================================
runtime:
  # How to start the service
  start_command: "python main.py"
  
  # Working directory (relative to service folder)
  working_directory: "."
  
  # =========================================================================
  # PORT CONFIGURATION - Critical for dynamic allocation
  # =========================================================================
  # Services support flexible ports via environment variables or CLI args.
  # The orchestrator assigns actual ports at startup time.
  ports:
    api:
      default: 8200                   # Default port (used if not overridden)
      env_var: "COMFYUI_BRIDGE_API_PORT"  # Environment variable to set port
      cli_arg: "--api-port"           # CLI argument alternative
      description: "REST API server port"
    ui:
      default: 7880
      env_var: "COMFYUI_BRIDGE_GRADIO_PORT"
      cli_arg: "--ui-port"
      description: "Gradio UI server port"
  
  # Environment variables needed (excluding port variables)
  environment:
    - name: "COMFYUI_BRIDGE_LOG_LEVEL"
      default: "INFO"
      description: "Logging level"
    - name: "COMFYUI_BRIDGE_OUTPUT_RETENTION_DAYS"
      default: "7"
      description: "Days to keep local assets"
  
  # Virtual environment setup
  venv:
    path: "venv"                      # Relative path to venv
    python: "python"                  # Python executable in venv
    requirements: "requirements.txt"  # Dependencies file
  
  # Startup behavior
  startup:
    wait_for_ready: true              # Wait for health check before reporting "running"
    ready_timeout_seconds: 60
    ready_check_interval_seconds: 2

# ============================================================================
# NETWORK ENDPOINTS
# ============================================================================
endpoints:
  # REST API
  api:
    port_key: "api"                   # References runtime.ports.api
    base_path: "/api/comfyui"
    health_check: "/health"
    docs: "/docs"
  
  # Gradio UI (optional)
  ui:
    port_key: "ui"                    # References runtime.ports.ui
    path: "/"

# ============================================================================
# CAPABILITIES
# ============================================================================
# What this service can do - used by White Mirror for routing
capabilities:
  # Input types this service accepts
  inputs:
    - type: "text"
      description: "Text prompts for generation"
    - type: "image"
      description: "Input images for img2img, 3D generation"
      formats: ["png", "jpg", "webp"]
  
  # Output types this service produces
  outputs:
    - type: "image"
      description: "Generated images"
      formats: ["png"]
    - type: "video"
      description: "Generated videos"
      formats: ["mp4"]
    - type: "3d_model"
      description: "3D models"
      formats: ["glb"]
    - type: "audio"
      description: "Sound effects"
      formats: ["wav"]
  
  # Available operations/triggers
  operations:
    - id: "image"
      name: "Generate Image"
      description: "Text-to-image generation using SD3"
      endpoint: "/api/comfyui/generate/by-trigger?trigger=image"
      method: "POST"
      inputs: ["text"]
      outputs: ["image"]
      estimated_time_seconds: 30
    
    - id: "image_fast"
      name: "Generate Image (Fast)"
      description: "Fast text-to-image using Flux Turbo"
      endpoint: "/api/comfyui/generate/by-trigger?trigger=image_fast"
      method: "POST"
      inputs: ["text"]
      outputs: ["image"]
      estimated_time_seconds: 5
    
    - id: "video"
      name: "Generate Video"
      description: "Image-to-video using AnimateDiff"
      endpoint: "/api/comfyui/generate/by-trigger?trigger=video"
      method: "POST"
      inputs: ["text", "image"]
      outputs: ["video"]
      estimated_time_seconds: 120
    
    - id: "3d"
      name: "Generate 3D Model"
      description: "Image-to-3D using Hunyuan3D"
      endpoint: "/api/comfyui/generate/by-trigger?trigger=3d"
      method: "POST"
      inputs: ["image"]
      outputs: ["3d_model"]
      estimated_time_seconds: 180
    
    - id: "sfx"
      name: "Generate Sound Effect"
      description: "Text-to-audio using AudioLDM"
      endpoint: "/api/comfyui/generate/by-trigger?trigger=sfx"
      method: "POST"
      inputs: ["text"]
      outputs: ["audio"]
      estimated_time_seconds: 15

# ============================================================================
# RESOURCE REQUIREMENTS
# ============================================================================
resources:
  # Minimum requirements to run
  min_vram_gb: 8
  min_ram_gb: 16
  
  # Typical usage when running
  typical_vram_gb: 12
  typical_ram_gb: 8
  
  # GPU requirements
  gpu_required: true
  gpu_types: ["nvidia"]              # nvidia, amd, apple

# ============================================================================
# DEPENDENCIES
# ============================================================================
dependencies:
  # External services this depends on
  external:
    - name: "ComfyUI Workstation"
      description: "At least one ComfyUI server must be accessible"
      required: true
  
  # System dependencies
  system:
    - name: "CUDA"
      version: ">=11.8"
      required: false
      description: "For GPU acceleration"

# ============================================================================
# TAGS (for filtering/categorization)
# ============================================================================
tags:
  - "image-generation"
  - "video-generation"
  - "3d-generation"
  - "audio-generation"
  - "comfyui"
```

### Minimal CAPABILITY.yaml

For simple services, a minimal version:

```yaml
schema_version: "1.0"
generated_at: "2025-12-30T14:30:00Z"

service:
  id: "my_service"
  name: "My Service"
  description: "Does something useful"

runtime:
  start_command: "python main.py"
  ports:
    api:
      default: 8000
      env_var: "SERVICE_PORT"
      cli_arg: "--port"

endpoints:
  api:
    port_key: "api"
    health_check: "/health"

capabilities:
  operations:
    - id: "generate"
      endpoint: "/generate"
      method: "POST"
```

---

## 7. LLM-Assisted Folder Analysis

### Overview

The Service Agent uses **Gemini 3 Flash** to intelligently analyze entire service folders and generate structured `CAPABILITY.yaml` files. Unlike simple README parsing, this approach:

1. **Scans all files** in the service folder (Python, YAML, JSON, markdown, etc.)
2. **Understands code structure** by analyzing main.py, routers, endpoints
3. **Extracts configuration** from config files, .env examples, CLI arguments
4. **Identifies dependencies** from requirements.txt, pyproject.toml
5. **Detects port patterns** from code and configuration

### When LLM Analysis is Triggered

1. **Initial Discovery**: Service folder found without CAPABILITY.yaml
2. **Manual Refresh**: User clicks "Refresh Capability" button in UI
3. **Never automatic**: Only runs when explicitly requested

### Files Analyzed

The LLM receives content from these files (if they exist):

| Priority | Files | Purpose |
|----------|-------|---------|
| **High** | `main.py`, `app.py`, `server.py` | Entry points, endpoints, ports |
| **High** | `README.md`, `PLAN.md`, `knowledge.md` | Documentation, architecture |
| **Medium** | `config/*.yaml`, `config/*.json` | Configuration schemas |
| **Medium** | `src/api/*.py`, `routes/*.py` | API endpoint definitions |
| **Medium** | `requirements.txt`, `pyproject.toml` | Dependencies |
| **Low** | `.env.example`, `.env.template` | Environment variables |
| **Low** | `Dockerfile`, `docker-compose.yaml` | Deployment info |

### LLM Prompt Template

```python
CAPABILITY_GENERATION_PROMPT = """
You are analyzing a software service folder to generate a structured capability manifest.

## Service Location
Folder: {service_path}
Service ID: {service_id}

## Directory Structure
{directory_tree}

## File Contents

{file_contents}

## Your Task

Analyze ALL the provided files to understand:
1. What this service does (purpose, capabilities)
2. How to start it (command, virtual environment)
3. What ports it uses (REST API, Gradio UI, etc.)
4. What API endpoints are available
5. What input/output types it handles
6. What environment variables it needs

IMPORTANT: 
- The service supports FLEXIBLE PORTS via environment variables or CLI arguments
- Identify the environment variable names for port configuration (e.g., API_PORT, GRADIO_PORT)
- Default ports are just defaults - actual ports will be assigned dynamically

Generate a CAPABILITY.yaml file following this exact schema:

```yaml
schema_version: "1.0"
generated_at: "{timestamp}"
generated_by: "service-agent/1.0.0"

service:
  id: "{service_id}"
  name: "<human readable name from docs>"
  description: "<one line description>"
  version: "<version if found, else '1.0.0'>"

runtime:
  start_command: "<command to start, e.g., 'python main.py'>"
  working_directory: "."
  
  # Port configuration - CRITICAL for dynamic allocation
  ports:
    api:
      default: <default port number>
      env_var: "<ENV_VAR_NAME for port>"        # e.g., "COMFYUI_BRIDGE_API_PORT"
      cli_arg: "<cli argument>"                  # e.g., "--api-port"
    ui:
      default: <default UI port if exists>
      env_var: "<ENV_VAR_NAME for UI port>"     # e.g., "COMFYUI_BRIDGE_GRADIO_PORT"  
      cli_arg: "<cli argument>"                  # e.g., "--ui-port"
  
  environment:
    - name: "<ENV_VAR_NAME>"
      default: "<default value>"
      description: "<what it does>"
  
  venv:
    path: "venv"
    python: "python"
    requirements: "requirements.txt"

endpoints:
  api:
    port_key: "api"                              # References runtime.ports.api
    base_path: "<base path like /api/comfyui>"
    health_check: "<health endpoint path>"
    docs: "<docs endpoint if exists>"
  ui:
    port_key: "ui"                               # References runtime.ports.ui
    path: "/"

capabilities:
  inputs:
    - type: "<input type: text, image, audio, video, 3d_model>"
      description: "<description>"
      formats: ["<file formats if applicable>"]
  
  outputs:
    - type: "<output type>"
      description: "<description>"
      formats: ["<file formats>"]
  
  operations:
    - id: "<operation id like 'image', 'video'>"
      name: "<human readable name>"
      description: "<what it does>"
      endpoint: "<full endpoint path>"
      method: "<HTTP method>"
      inputs: ["<input types>"]
      outputs: ["<output types>"]
      estimated_time_seconds: <estimate>

resources:
  min_vram_gb: <number or null if no GPU needed>
  min_ram_gb: <estimate>
  gpu_required: <true/false>

tags:
  - "<relevant tags>"
```

Important guidelines:
- Extract ACTUAL port numbers and their configuration methods from the code
- Identify ALL REST API endpoints by analyzing route definitions
- List ALL operations/triggers the service supports
- Be accurate about input/output types based on actual code
- If the service has a Gradio UI, include it in endpoints
- Include ALL environment variables that affect behavior

Output ONLY the YAML content, no explanations or markdown code blocks.
"""
```

### Folder Analysis Code

```python
import os
from pathlib import Path
from typing import Optional
import litellm

class FolderAnalyzer:
    """Analyzes entire service folders using LLM."""
    
    # OpenRouter configuration
    API_KEY = "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"
    MODEL = "google/gemini-3-flash-preview"
    
    # Files to analyze (in priority order)
    PRIORITY_FILES = [
        # Entry points
        "main.py", "app.py", "server.py", "run.py",
        # Documentation
        "README.md", "PLAN.md", "knowledge.md", "docs/README.md",
        # Configuration
        "config.yaml", "config.json", "settings.yaml",
        "config/config.yaml", "config/settings.yaml",
        # API definitions
        "src/api/routes.py", "src/api/endpoints.py", "src/api/__init__.py",
        "api/routes.py", "routes.py", "endpoints.py",
        # Dependencies
        "requirements.txt", "pyproject.toml", "setup.py",
        # Environment
        ".env.example", ".env.template", "env.example",
        # Docker
        "Dockerfile", "docker-compose.yaml", "docker-compose.yml",
    ]
    
    # Additional patterns to search
    FILE_PATTERNS = [
        "src/**/*.py",
        "api/**/*.py", 
        "config/**/*.yaml",
        "config/**/*.json",
    ]
    
    # Max content per file (tokens ~= chars/4)
    MAX_FILE_CHARS = 8000
    MAX_TOTAL_CHARS = 60000  # ~15k tokens for context
    
    def __init__(self, config):
        self.config = config
        
    async def analyze_folder(self, service_path: Path) -> str:
        """Analyze entire service folder and generate CAPABILITY.yaml."""
        
        # Build directory tree
        dir_tree = self._build_directory_tree(service_path)
        
        # Gather file contents
        file_contents = self._gather_file_contents(service_path)
        
        # Build prompt
        prompt = CAPABILITY_GENERATION_PROMPT.format(
            service_path=str(service_path),
            service_id=service_path.name.lower().replace(" ", "_").replace("-", "_"),
            directory_tree=dir_tree,
            file_contents=file_contents,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
        
        # Call LLM
        response = await litellm.acompletion(
            model=f"openrouter/{self.MODEL}",
            api_key=self.API_KEY,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.1,
        )
        
        yaml_content = response.choices[0].message.content
        yaml_content = self._clean_yaml(yaml_content)
        
        # Validate
        self._validate_yaml(yaml_content)
        
        return yaml_content
    
    def _build_directory_tree(self, path: Path, prefix: str = "", max_depth: int = 3) -> str:
        """Build a text representation of the directory structure."""
        lines = []
        
        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return f"{prefix}[Permission Denied]\n"
        
        # Filter out common non-essential directories
        skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 
                     '.pytest_cache', '.mypy_cache', 'dist', 'build', 'eggs'}
        
        for entry in entries:
            if entry.name.startswith('.') and entry.name not in ['.env.example']:
                continue
            if entry.is_dir() and entry.name in skip_dirs:
                continue
                
            if entry.is_dir():
                lines.append(f"{prefix}📁 {entry.name}/")
                if max_depth > 0:
                    lines.append(self._build_directory_tree(
                        entry, prefix + "  ", max_depth - 1
                    ))
            else:
                size = entry.stat().st_size
                lines.append(f"{prefix}📄 {entry.name} ({size} bytes)")
        
        return "\n".join(lines)
    
    def _gather_file_contents(self, service_path: Path) -> str:
        """Gather contents of relevant files."""
        contents = []
        total_chars = 0
        
        # First pass: priority files
        for filename in self.PRIORITY_FILES:
            file_path = service_path / filename
            if file_path.exists() and file_path.is_file():
                content = self._read_file_safe(file_path)
                if content:
                    header = f"\n### FILE: {filename}\n```\n"
                    footer = "\n```\n"
                    chunk = header + content[:self.MAX_FILE_CHARS] + footer
                    
                    if total_chars + len(chunk) > self.MAX_TOTAL_CHARS:
                        break
                    
                    contents.append(chunk)
                    total_chars += len(chunk)
        
        # Second pass: search for additional Python files in src/
        if total_chars < self.MAX_TOTAL_CHARS:
            src_path = service_path / "src"
            if src_path.exists():
                for py_file in src_path.rglob("*.py"):
                    rel_path = py_file.relative_to(service_path)
                    if str(rel_path) in [f for f, _ in contents]:
                        continue
                    
                    content = self._read_file_safe(py_file)
                    if content and len(content) > 100:  # Skip tiny files
                        header = f"\n### FILE: {rel_path}\n```python\n"
                        footer = "\n```\n"
                        chunk = header + content[:self.MAX_FILE_CHARS] + footer
                        
                        if total_chars + len(chunk) > self.MAX_TOTAL_CHARS:
                            break
                        
                        contents.append(chunk)
                        total_chars += len(chunk)
        
        return "".join(contents)
    
    def _read_file_safe(self, path: Path) -> Optional[str]:
        """Safely read a file, handling encoding issues."""
        try:
            return path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding='latin-1')
            except:
                return None
        except Exception:
            return None
    
    def _clean_yaml(self, content: str) -> str:
        """Remove markdown code blocks and clean up."""
        content = content.strip()
        if content.startswith("```yaml"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()
    
    def _validate_yaml(self, content: str) -> None:
        """Validate YAML is parseable and has required fields."""
        import yaml
        data = yaml.safe_load(content)
        
        required = ["schema_version", "service", "runtime", "endpoints"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate port configuration exists
        if "ports" not in data.get("runtime", {}):
            raise ValueError("Missing runtime.ports configuration")
```

### Caching Strategy

1. **CAPABILITY.yaml is persistent** - Stored in service folder
2. **Full folder hash** - Hash of all analyzed files for change detection  
3. **Manual refresh only** - User must explicitly request regeneration
4. **LLM cost consideration** - Each analysis uses ~15-20k tokens

---

## 8. REST API Reference

### Base URL

```
http://<host>:9100
```

### Authentication

None required (trusts VPN network).

---

### GET /discover

Returns all discovered services with their capabilities and current port assignments.

**Response:**

```json
{
  "agent": {
    "machine_id": "ws-5090-main",
    "machine_name": "RTX 5090 Workstation",
    "version": "1.0.0",
    "uptime_seconds": 3600
  },
  "services": [
    {
      "id": "comfyui_bridge",
      "name": "ComfyUI Bridge Service",
      "description": "Middleware service for ComfyUI",
      "status": "running",
      "path": "/tools/comfyui_bridge",
      "assigned_ports": {
        "api": 8200,
        "ui": 7880
      },
      "capability": {
        "runtime": {
          "ports": {
            "api": {
              "default": 8200,
              "env_var": "COMFYUI_BRIDGE_API_PORT",
              "cli_arg": "--api-port"
            },
            "ui": {
              "default": 7880,
              "env_var": "COMFYUI_BRIDGE_GRADIO_PORT",
              "cli_arg": "--ui-port"
            }
          }
        },
        "endpoints": {
          "api": {
            "port_key": "api",
            "health_check": "/health"
          }
        },
        "operations": [
          {
            "id": "image",
            "name": "Generate Image",
            "endpoint": "/api/comfyui/generate/by-trigger?trigger=image",
            "method": "POST"
          }
        ]
      },
      "health": {
        "status": "healthy",
        "last_check": "2025-12-30T14:30:00Z"
      }
    },
    {
      "id": "suno_bridge",
      "name": "Suno Bridge",
      "status": "stopped",
      "path": "/tools/suno_bridge",
      "assigned_ports": null,
      "capability": {
        "runtime": {
          "ports": {
            "api": {
              "default": 8102,
              "env_var": "SUNO_BRIDGE_PORT"
            }
          }
        }
      },
      "needs_capability_generation": false
    },
    {
      "id": "new_service",
      "name": "new_service",
      "status": "discovered",
      "path": "/tools/new_service",
      "assigned_ports": null,
      "capability": null,
      "needs_capability_generation": true
    }
  ],
  "resources": {
    "gpu": {
      "name": "NVIDIA RTX 5090",
      "vram_total_gb": 32,
      "vram_used_gb": 12.5,
      "vram_free_gb": 19.5
    },
    "ram": {
      "total_gb": 64,
      "used_gb": 24,
      "free_gb": 40
    }
  }
}
```

---

### GET /status

Returns agent status and resource usage.

**Response:**

```json
{
  "status": "healthy",
  "machine_id": "ws-5090-main",
  "uptime_seconds": 3600,
  "services": {
    "total": 5,
    "running": 2,
    "stopped": 2,
    "failed": 1
  },
  "resources": {
    "gpu": {
      "vram_free_gb": 19.5,
      "vram_total_gb": 32
    },
    "ram": {
      "free_gb": 40,
      "total_gb": 64
    },
    "cpu_percent": 15.5
  }
}
```

---

### GET /services

List all services with status.

**Response:**

```json
{
  "services": [
    {
      "id": "comfyui_bridge",
      "name": "ComfyUI Bridge",
      "status": "running",
      "pid": 12345,
      "uptime_seconds": 1800,
      "ports": [8200, 7880]
    },
    {
      "id": "gaussian_splat",
      "name": "Gaussian Splat Service",
      "status": "stopped",
      "pid": null
    }
  ]
}
```

---

### GET /services/{service_id}

Get detailed info for a specific service.

**Response:**

```json
{
  "id": "comfyui_bridge",
  "name": "ComfyUI Bridge Service",
  "status": "running",
  "pid": 12345,
  "path": "/tools/comfyui_bridge",
  "start_time": "2025-12-30T12:00:00Z",
  "uptime_seconds": 9000,
  "capability": { ... },
  "health": {
    "status": "healthy",
    "last_check": "2025-12-30T14:30:00Z",
    "response_time_ms": 45
  },
  "logs_tail": [
    "2025-12-30 14:30:00 INFO Started API server on port 8200",
    "2025-12-30 14:30:01 INFO Started Gradio UI on port 7880"
  ]
}
```

---

### POST /services/{service_id}/start

Start a service with optional port assignments.

**Request Body:**

```json
{
  "port_assignments": {
    "api": 8200,
    "ui": 7880
  },
  "env": {
    "CUSTOM_VAR": "value"
  }
}
```

**Port Assignment Logic:**
- If `port_assignments` provided → Use specified ports
- If not provided → Agent uses default ports from CAPABILITY.yaml
- The orchestrator should always provide port assignments to prevent conflicts

**Response:**

```json
{
  "success": true,
  "service_id": "comfyui_bridge",
  "status": "starting",
  "pid": 12345,
  "assigned_ports": {
    "api": 8200,
    "ui": 7880
  },
  "message": "Service starting on ports api=8200, ui=7880"
}
```

---

### POST /services/{service_id}/stop

Stop a running service.

**Response:**

```json
{
  "success": true,
  "service_id": "comfyui_bridge",
  "status": "stopped",
  "message": "Service stopped successfully"
}
```

---

### POST /services/{service_id}/restart

Restart a service (stop + start).

**Response:**

```json
{
  "success": true,
  "service_id": "comfyui_bridge",
  "status": "running",
  "message": "Service restarted successfully"
}
```

---

### GET /services/{service_id}/health

Health check for a specific service.

**Response:**

```json
{
  "service_id": "comfyui_bridge",
  "status": "healthy",
  "response_time_ms": 45,
  "details": {
    "api": "healthy",
    "ui": "healthy"
  }
}
```

---

### GET /services/{service_id}/logs

Get recent logs for a service.

**Query Parameters:**
- `lines`: Number of lines (default: 100)
- `level`: Filter by level (DEBUG, INFO, WARNING, ERROR)

**Response:**

```json
{
  "service_id": "comfyui_bridge",
  "logs": [
    {
      "timestamp": "2025-12-30T14:30:00Z",
      "level": "INFO",
      "message": "Started API server on port 8200"
    }
  ]
}
```

---

### POST /services/{service_id}/refresh-capability

Regenerate CAPABILITY.yaml using LLM.

**Response:**

```json
{
  "success": true,
  "service_id": "comfyui_bridge",
  "message": "Capability refreshed successfully",
  "capability": { ... }
}
```

---

### GET /resources

Current resource usage.

**Response:**

```json
{
  "gpu": {
    "available": true,
    "name": "NVIDIA RTX 5090",
    "driver_version": "550.76",
    "vram_total_gb": 32,
    "vram_used_gb": 12.5,
    "vram_free_gb": 19.5,
    "utilization_percent": 45,
    "temperature_celsius": 65
  },
  "ram": {
    "total_gb": 64,
    "used_gb": 24,
    "free_gb": 40,
    "percent_used": 37.5
  },
  "cpu": {
    "percent": 15.5,
    "cores": 16
  },
  "disk": {
    "total_gb": 2000,
    "free_gb": 500
  }
}
```

---

### GET /config

Get current agent configuration.

**Response:**

```json
{
  "machine_id": "ws-5090-main",
  "machine_name": "RTX 5090 Workstation",
  "service_folders": ["/tools"],
  "always_running": ["comfyui_bridge"],
  "agent_port": 9100
}
```

---

### PUT /config

Update agent configuration (partial update).

**Request Body:**

```json
{
  "machine_name": "Updated Name",
  "always_running": ["comfyui_bridge", "gaussian_splat"]
}
```

**Response:**

```json
{
  "success": true,
  "message": "Configuration updated",
  "restart_required": false
}
```

---

### POST /scan

Trigger a rescan of service folders.

**Response:**

```json
{
  "success": true,
  "services_found": 5,
  "new_services": ["new_service"],
  "removed_services": []
}
```

---

## 9. Gradio UI Specification

### Layout

```
┌────────────────────────────────────────────────────────────────────────────┐
│  White Mirror Service Agent - ws-5090-main                    [Status: ●] │
├────────────────────────────────────────────────────────────────────────────┤
│  [Services] [Resources] [Config] [Logs] [Refresh Capabilities]            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │                         TAB CONTENT                                   │ │
│  │                                                                       │ │
│  │                                                                       │ │
│  │                                                                       │ │
│  │                                                                       │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### Tab 1: Services

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Services                                                      [Scan Folders]│
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ Service              Status      Port     Actions                      │   │
│ ├───────────────────────────────────────────────────────────────────────┤   │
│ │ comfyui_bridge       ● Running   8200     [Stop] [Restart] [Logs]     │   │
│ │ gaussian_splat       ● Running   8300     [Stop] [Restart] [Logs]     │   │
│ │ suno_bridge          ○ Stopped   -        [Start] [Refresh Cap]       │   │
│ │ tts_bridge           ⚠ No Cap    -        [Generate Capability]       │   │
│ │ video_gen            ✗ Failed    -        [View Error] [Retry]        │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ Selected: comfyui_bridge                                                     │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ Path: /tools/comfyui_bridge                                            │   │
│ │ PID: 12345                                                             │   │
│ │ Uptime: 2h 15m                                                         │   │
│ │ Endpoints: API=8200, UI=7880                                           │   │
│ │ Operations: image, image_fast, video, 3d, sfx                          │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab 2: Resources

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ System Resources                                          [Refresh: 30s]    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ GPU: NVIDIA RTX 5090                                                         │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ VRAM: ████████████░░░░░░░░ 12.5 / 32 GB (39%)                         │   │
│ │ Util: ████████░░░░░░░░░░░░ 45%                                         │   │
│ │ Temp: 65°C                                                             │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ System Memory                                                                │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ RAM:  ███████░░░░░░░░░░░░░ 24 / 64 GB (37.5%)                         │   │
│ │ Swap: █░░░░░░░░░░░░░░░░░░░ 2 / 16 GB                                  │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ CPU: 15.5% (16 cores)                                                        │
│ Disk: 500 GB free / 2 TB                                                     │
│                                                                              │
│ Reserved: VRAM 2GB, RAM 4GB                                                  │
│ Available for services: VRAM 17.5GB, RAM 36GB                                │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab 3: Config

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Agent Configuration                                              [Save]     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Machine ID:        [ws-5090-main________________]                           │
│ Machine Name:      [RTX 5090 Workstation________]                           │
│ Description:       [Primary GPU workstation_____]                           │
│                                                                              │
│ Agent Port:        [9100]                                                    │
│                                                                              │
│ Service Folders:                                                             │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ D:/white_mirror_services                                    [Remove]  │   │
│ │ D:/tools/comfyui_bridge                                     [Remove]  │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│ [Add Folder...]                                                              │
│                                                                              │
│ Always Running Services:                                                     │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ ☑ comfyui_bridge                                                       │   │
│ │ ☑ gaussian_splat                                                       │   │
│ │ ☐ suno_bridge                                                          │   │
│ │ ☐ tts_bridge                                                           │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ Resource Reserves:                                                           │
│ GPU VRAM Reserve: [2] GB                                                     │
│ RAM Reserve:      [4] GB                                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab 4: Logs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Logs                                              [Clear] [Export] [Auto ●] │
├─────────────────────────────────────────────────────────────────────────────┤
│ Service: [All Services ▼]  Level: [INFO ▼]  Lines: [100 ▼]                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ 2025-12-30 14:30:00 [INFO] [agent] Service agent started on port 9100       │
│ 2025-12-30 14:30:01 [INFO] [agent] Scanning service folders...              │
│ 2025-12-30 14:30:02 [INFO] [agent] Found 5 services                         │
│ 2025-12-30 14:30:03 [INFO] [comfyui_bridge] Auto-starting service           │
│ 2025-12-30 14:30:05 [INFO] [comfyui_bridge] Service started (PID: 12345)    │
│ 2025-12-30 14:30:10 [INFO] [comfyui_bridge] Health check: healthy           │
│ 2025-12-30 14:30:15 [INFO] [gaussian_splat] Auto-starting service           │
│ 2025-12-30 14:30:18 [INFO] [gaussian_splat] Service started (PID: 12346)    │
│ ...                                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Tab 5: Refresh Capabilities

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Capability Generation                                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│ Select a service to regenerate its CAPABILITY.yaml using LLM:               │
│                                                                              │
│ Service: [comfyui_bridge ▼]                                                  │
│                                                                              │
│ Current Status: ● Has CAPABILITY.yaml (generated 2025-12-28)                │
│                                                                              │
│ [Refresh Capability]  [View Current]  [Edit Manually]                       │
│                                                                              │
│ ┌───────────────────────────────────────────────────────────────────────┐   │
│ │ CAPABILITY.yaml Preview                                                │   │
│ │                                                                        │   │
│ │ schema_version: "1.0"                                                  │   │
│ │ service:                                                               │   │
│ │   id: "comfyui_bridge"                                                 │   │
│ │   name: "ComfyUI Bridge Service"                                       │   │
│ │   description: "Middleware service..."                                 │   │
│ │ ...                                                                    │   │
│ └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│ LLM Model: google/gemini-2.0-flash-exp:free                                 │
│                                                                              │
│ ⚠️ Refreshing will overwrite the current CAPABILITY.yaml                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Process Management

### Starting a Service

```python
import subprocess
import os

class ServiceManager:
    def start_service(self, service: Service) -> int:
        """Start a service and return PID."""
        
        capability = service.capability
        runtime = capability.runtime
        
        # Build environment
        env = os.environ.copy()
        for var in runtime.environment:
            if var.name not in env:
                env[var.name] = var.default
        
        # Determine working directory
        cwd = service.path
        if runtime.working_directory != ".":
            cwd = service.path / runtime.working_directory
        
        # Build command
        if runtime.venv:
            if os.name == "nt":  # Windows
                python = service.path / runtime.venv.path / "Scripts" / "python.exe"
            else:
                python = service.path / runtime.venv.path / "bin" / "python"
            
            # Replace "python" in command with venv python
            cmd = runtime.start_command.replace("python", str(python), 1)
        else:
            cmd = runtime.start_command
        
        # Start process
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        
        service.pid = process.pid
        service.status = "starting"
        service.process = process
        
        # Start log capture thread
        self._start_log_capture(service)
        
        return process.pid
    
    def stop_service(self, service: Service) -> bool:
        """Stop a running service."""
        
        if service.process is None:
            return False
        
        service.status = "stopping"
        
        # Try graceful shutdown first
        service.process.terminate()
        
        try:
            service.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # Force kill
            service.process.kill()
            service.process.wait()
        
        service.status = "stopped"
        service.pid = None
        service.process = None
        
        return True
```

### Health Checking

```python
import httpx

class HealthChecker:
    async def check_service(self, service: Service) -> dict:
        """Check if a service is healthy."""
        
        if not service.capability:
            return {"status": "unknown", "reason": "no capability"}
        
        endpoint = service.capability.endpoints.api
        health_url = f"http://localhost:{endpoint.port}{endpoint.health_check}"
        
        try:
            async with httpx.AsyncClient() as client:
                start = time.time()
                response = await client.get(health_url, timeout=5)
                response_time = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    return {
                        "status": "healthy",
                        "response_time_ms": response_time,
                        "details": response.json()
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "reason": f"HTTP {response.status_code}"
                    }
        except httpx.TimeoutException:
            return {"status": "unhealthy", "reason": "timeout"}
        except httpx.ConnectError:
            return {"status": "unhealthy", "reason": "connection refused"}
        except Exception as e:
            return {"status": "error", "reason": str(e)}
```

---

## 10a. Dynamic Port Allocation

### Overview

Services support **flexible port configuration** via environment variables or CLI arguments. The **White Mirror Orchestrator** is responsible for assigning ports to avoid conflicts, while the **Service Agent** executes the start command with the assigned ports.

### Port Allocation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      WHITE MIRROR ORCHESTRATOR                               │
│                                                                              │
│  1. GET /discover from all agents                                           │
│  2. Collect all service port configurations                                 │
│  3. Build port allocation map (no conflicts)                                │
│  4. POST /services/{id}/start with assigned ports                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SERVICE AGENT                                      │
│                                                                              │
│  1. Receive start request with port assignments                             │
│  2. Build environment variables from port config                            │
│  3. Start service with assigned ports                                       │
│  4. Verify service started on correct ports                                 │
│  5. Report actual ports in /discover response                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Port Assignment Request

When the orchestrator starts a service, it provides port assignments:

```http
POST /services/comfyui_bridge/start
Content-Type: application/json

{
  "port_assignments": {
    "api": 8200,
    "ui": 7880
  }
}
```

The agent uses these assignments to configure environment variables:

```python
# Agent builds environment from port_assignments
env = {
    "COMFYUI_BRIDGE_API_PORT": "8200",   # From capability.runtime.ports.api.env_var
    "COMFYUI_BRIDGE_GRADIO_PORT": "7880"  # From capability.runtime.ports.ui.env_var
}
```

### Port Allocation Strategy (Orchestrator)

The orchestrator maintains a port allocation registry:

```python
class PortAllocator:
    """Manages port allocation across all agents."""
    
    # Port ranges per agent
    PORT_RANGES = {
        "api": (8200, 8299),      # REST APIs: 8200-8299
        "ui": (7800, 7899),       # Gradio UIs: 7800-7899
    }
    
    def __init__(self):
        # {agent_address: {service_id: {port_key: port}}}
        self.allocations: dict[str, dict[str, dict[str, int]]] = {}
        # {agent_address: set of used ports}
        self.used_ports: dict[str, set[int]] = {}
    
    def allocate_ports(
        self,
        agent_address: str,
        service_id: str,
        port_config: dict
    ) -> dict[str, int]:
        """Allocate ports for a service, avoiding conflicts."""
        
        if agent_address not in self.used_ports:
            self.used_ports[agent_address] = set()
        
        assignments = {}
        
        for port_key, config in port_config.items():
            # Check if service already has allocation
            existing = self._get_existing_allocation(
                agent_address, service_id, port_key
            )
            if existing:
                assignments[port_key] = existing
                continue
            
            # Find next available port
            port_range = self.PORT_RANGES.get(port_key, (9000, 9999))
            default_port = config.get("default", port_range[0])
            
            # Try default first
            if default_port not in self.used_ports[agent_address]:
                port = default_port
            else:
                # Find next available in range
                port = self._find_available_port(
                    agent_address, port_range[0], port_range[1]
                )
            
            assignments[port_key] = port
            self.used_ports[agent_address].add(port)
        
        # Store allocation
        if agent_address not in self.allocations:
            self.allocations[agent_address] = {}
        self.allocations[agent_address][service_id] = assignments
        
        return assignments
    
    def release_ports(self, agent_address: str, service_id: str):
        """Release ports when service stops."""
        if agent_address in self.allocations:
            if service_id in self.allocations[agent_address]:
                ports = self.allocations[agent_address].pop(service_id)
                for port in ports.values():
                    self.used_ports[agent_address].discard(port)
    
    def _find_available_port(
        self,
        agent_address: str,
        start: int,
        end: int
    ) -> int:
        """Find next available port in range."""
        used = self.used_ports.get(agent_address, set())
        for port in range(start, end + 1):
            if port not in used:
                return port
        raise PortExhaustionError(f"No ports available in range {start}-{end}")
```

### Agent Start Command Building

```python
class ServiceManager:
    def start_service(
        self,
        service: Service,
        port_assignments: dict[str, int]
    ) -> int:
        """Start service with assigned ports."""
        
        capability = service.capability
        runtime = capability["runtime"]
        ports_config = runtime.get("ports", {})
        
        # Build environment with port assignments
        env = os.environ.copy()
        
        for port_key, port_value in port_assignments.items():
            if port_key in ports_config:
                env_var = ports_config[port_key].get("env_var")
                if env_var:
                    env[env_var] = str(port_value)
        
        # Add other environment variables
        for var in runtime.get("environment", []):
            if var["name"] not in env:
                env[var["name"]] = var.get("default", "")
        
        # Build start command (optionally with CLI args)
        cmd = runtime["start_command"]
        
        # Some services prefer CLI args over env vars
        for port_key, port_value in port_assignments.items():
            if port_key in ports_config:
                cli_arg = ports_config[port_key].get("cli_arg")
                if cli_arg and "--" in cmd:  # Only if CLI args already in use
                    cmd = f"{cmd} {cli_arg} {port_value}"
        
        # Start process
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=service.path,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        
        # Store actual ports for reporting
        service.assigned_ports = port_assignments
        service.pid = process.pid
        service.status = "starting"
        
        return process.pid
```

### Discovery Response with Actual Ports

After starting, the agent reports actual ports in discovery:

```json
{
  "services": [
    {
      "id": "comfyui_bridge",
      "name": "ComfyUI Bridge Service",
      "status": "running",
      "assigned_ports": {
        "api": 8200,
        "ui": 7880
      },
      "capability": {
        "runtime": {
          "ports": {
            "api": {"default": 8200, "env_var": "COMFYUI_BRIDGE_API_PORT"},
            "ui": {"default": 7880, "env_var": "COMFYUI_BRIDGE_GRADIO_PORT"}
          }
        }
      }
    },
    {
      "id": "gaussian_splat",
      "name": "Gaussian Splat Service", 
      "status": "running",
      "assigned_ports": {
        "api": 8201,
        "ui": 7881
      }
    }
  ]
}
```

### Conflict Prevention

The orchestrator ensures no conflicts by:

1. **Global tracking**: Maintains port allocations per agent
2. **Discovery sync**: On startup, reads current allocations from running services
3. **Range separation**: Different port types use different ranges
4. **Persistence**: Stores allocations in config/state file

```yaml
# config/port_allocations.yaml (persisted by orchestrator)
allocations:
  "100.92.125.254:9100":  # Windows agent
    comfyui_bridge:
      api: 8200
      ui: 7880
    gaussian_splat:
      api: 8201
      ui: 7881
  "localhost:9100":  # Local agent
    suno_bridge:
      api: 8202
```

---

### GPU Monitoring (NVIDIA)

```python
try:
    import pynvml
    NVIDIA_AVAILABLE = True
except ImportError:
    NVIDIA_AVAILABLE = False

class GPUMonitor:
    def __init__(self):
        if NVIDIA_AVAILABLE:
            pynvml.nvmlInit()
            self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    
    def get_stats(self) -> dict:
        if not NVIDIA_AVAILABLE:
            return {"available": False}
        
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
            temp = pynvml.nvmlDeviceGetTemperature(
                self.handle, pynvml.NVML_TEMPERATURE_GPU
            )
            name = pynvml.nvmlDeviceGetName(self.handle)
            
            return {
                "available": True,
                "name": name,
                "vram_total_gb": info.total / (1024**3),
                "vram_used_gb": info.used / (1024**3),
                "vram_free_gb": info.free / (1024**3),
                "utilization_percent": util.gpu,
                "temperature_celsius": temp
            }
        except Exception as e:
            return {"available": False, "error": str(e)}
```

### System Memory Monitoring

```python
import psutil

class SystemMonitor:
    def get_memory_stats(self) -> dict:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "ram": {
                "total_gb": mem.total / (1024**3),
                "used_gb": mem.used / (1024**3),
                "free_gb": mem.available / (1024**3),
                "percent_used": mem.percent
            },
            "swap": {
                "total_gb": swap.total / (1024**3),
                "used_gb": swap.used / (1024**3),
                "percent_used": swap.percent
            }
        }
    
    def get_cpu_stats(self) -> dict:
        return {
            "percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count()
        }
    
    def get_disk_stats(self, path: str = "/") -> dict:
        disk = psutil.disk_usage(path)
        return {
            "total_gb": disk.total / (1024**3),
            "free_gb": disk.free / (1024**3),
            "percent_used": disk.percent
        }
```

---

## 12. Implementation Details

### Main Entry Point

```python
# main.py

import asyncio
import logging
from pathlib import Path

import gradio as gr
import uvicorn
from fastapi import FastAPI

from agent.config import load_config
from agent.api import create_api_router
from agent.ui import create_gradio_ui
from agent.service_manager import ServiceManager
from agent.discovery import ServiceDiscovery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Load configuration
    config = load_config()
    
    # Initialize components
    discovery = ServiceDiscovery(config)
    manager = ServiceManager(config, discovery)
    
    # Create FastAPI app
    app = FastAPI(
        title="White Mirror Service Agent",
        version="1.0.0"
    )
    
    # Add API routes
    api_router = create_api_router(manager, discovery)
    app.include_router(api_router)
    
    # Create Gradio UI
    if config.ui.enabled:
        gradio_app = create_gradio_ui(manager, discovery, config)
        app = gr.mount_gradio_app(app, gradio_app, path="/ui")
    
    # Initial discovery
    logger.info("Scanning service folders...")
    services = discovery.scan()
    logger.info(f"Found {len(services)} services")
    
    # Auto-start always-running services
    for service_id in config.always_running:
        service = discovery.get_service(service_id)
        if service and service.capability:
            logger.info(f"Auto-starting {service_id}...")
            manager.start_service(service)
    
    # Run server
    uvicorn.run(
        app,
        host=config.agent.host,
        port=config.agent.port,
        log_level=config.agent.log_level.lower()
    )

if __name__ == "__main__":
    main()
```

### Core Classes

```python
# agent/models.py

from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path
from datetime import datetime
from enum import Enum

class ServiceStatus(str, Enum):
    DISCOVERED = "discovered"
    READY = "ready"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    ERROR = "error"

@dataclass
class Service:
    id: str
    path: Path
    status: ServiceStatus = ServiceStatus.DISCOVERED
    capability: Optional[dict] = None
    pid: Optional[int] = None
    process: Optional[Any] = None
    start_time: Optional[datetime] = None
    error: Optional[str] = None
    logs: list[str] = field(default_factory=list)
    
    @property
    def name(self) -> str:
        if self.capability and "service" in self.capability:
            return self.capability["service"].get("name", self.id)
        return self.id
    
    @property
    def has_capability(self) -> bool:
        return self.capability is not None
    
    @property
    def needs_capability(self) -> bool:
        return not self.has_capability
```

---

## 13. File Structure

```
white-mirror-agent/
├── main.py                     # Entry point
├── config.yaml                 # Agent configuration
├── config.yaml.example         # Config template
├── requirements.txt            # Python dependencies
├── README.md                   # This document
│
├── agent/
│   ├── __init__.py
│   ├── config.py              # Configuration loading
│   ├── models.py              # Data models
│   ├── api.py                 # FastAPI routes
│   ├── ui.py                  # Gradio UI
│   ├── discovery.py           # Service discovery
│   ├── service_manager.py     # Process management
│   ├── capability_generator.py # LLM-based capability generation
│   ├── health_checker.py      # Health monitoring
│   ├── resource_monitor.py    # GPU/RAM monitoring
│   └── utils.py               # Utility functions
│
├── templates/
│   └── CAPABILITY.yaml.j2     # Template for manual editing
│
└── tests/
    ├── test_discovery.py
    ├── test_api.py
    └── test_capability.py
```

---

## 14. Example Scenarios

### Scenario 1: First-Time Setup

```
1. User installs agent on Windows workstation
2. Creates config.yaml:
   - machine_id: "ws-5090"
   - service_folders: ["D:/tools"]
   - always_running: ["comfyui_bridge"]
3. Starts agent: python main.py
4. Agent scans D:/tools, finds:
   - comfyui_bridge/ (has CAPABILITY.yaml ✓)
   - gaussian_splat/ (no CAPABILITY.yaml)
5. Agent auto-starts comfyui_bridge
6. User opens http://localhost:9100/ui
7. Sees gaussian_splat needs capability
8. Clicks "Generate Capability" → LLM parses → CAPABILITY.yaml created
9. Now gaussian_splat is ready
```

### Scenario 2: White Mirror Discovery

```
1. White Mirror Orchestrator starts
2. Reads agent addresses from config:
   - localhost:9100 (Mac)
   - 100.92.125.254:9100 (Windows via NordVPN)
3. Calls GET /discover on each agent
4. Receives:
   - Mac: suno_bridge (running), tts_bridge (stopped)
   - Windows: comfyui_bridge (running), gaussian_splat (running)
5. Builds capability map for routing generation requests
6. When user requests image generation:
   - Routes to Windows agent's comfyui_bridge
   - Direct REST call: POST http://100.92.125.254:8200/api/comfyui/generate/by-trigger
```

### Scenario 3: Service Restart via UI

```
1. User notices comfyui_bridge is slow
2. Opens agent UI: http://localhost:9100/ui
3. Goes to Services tab
4. Clicks [Restart] on comfyui_bridge
5. Agent:
   - Sends SIGTERM to process
   - Waits for graceful shutdown
   - Starts process again
   - Waits for health check to pass
6. Status changes: Running → Stopping → Starting → Running
7. VRAM freed and reallocated
```

---

## Appendix A: Error Codes

| Code | Message | Resolution |
|------|---------|------------|
| `E001` | Service folder not found | Check path in config |
| `E002` | CAPABILITY.yaml parse error | Regenerate capability |
| `E003` | Service start failed | Check logs, verify requirements |
| `E004` | Health check failed | Service may have crashed |
| `E005` | LLM API error | Check OpenRouter key |
| `E006` | Insufficient VRAM | Stop other services |
| `E007` | Port already in use | Change service port |

---

## Appendix B: Capability Validation

Required fields in CAPABILITY.yaml:

```yaml
# REQUIRED
schema_version: string
service:
  id: string
  name: string
runtime:
  start_command: string
endpoints:
  api:
    port: integer
    health_check: string

# OPTIONAL but recommended
service.description: string
runtime.venv: object
endpoints.ui: object
capabilities: object
resources: object
```

---

**Document Version:** 1.0  
**Last Updated:** December 2025  
**Status:** Ready for Implementation
