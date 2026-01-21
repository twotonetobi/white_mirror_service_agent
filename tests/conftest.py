"""Pytest fixtures for White Mirror Service Agent tests."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

from agent.config import AgentConfig, AgentSettings, HealthCheckSettings, LLMSettings
from agent.discovery import ServiceDiscovery
from agent.models import Service, ServiceStatus, ServiceCapability, PortConfig
from agent.resource_monitor import ResourceMonitor
from agent.service_manager import ServiceManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_capability_yaml():
    """Sample CAPABILITY.yaml content."""
    return """schema_version: "1.0"
generated_at: "2025-01-01T00:00:00Z"
generated_by: "service-agent/1.0.0"

service:
  id: "test_service"
  name: "Test Service"
  description: "A test service for unit testing"
  version: "1.0.0"

runtime:
  start_command: "python main.py"
  working_directory: "."
  ports:
    api:
      default: 8000
      env_var: "API_PORT"
      cli_arg: "--port"
      description: "REST API server port"
  environment:
    - name: "DEBUG"
      default: "false"
      description: "Enable debug mode"
  venv:
    path: "venv"
    python: "python"
    requirements: "requirements.txt"

endpoints:
  api:
    port_key: "api"
    base_path: "/api"
    health_check: "/health"
    docs: "/docs"

capabilities:
  inputs:
    - type: "text"
      description: "Text input"
      formats: []
  outputs:
    - type: "text"
      description: "Text output"
      formats: []
  operations:
    - id: "echo"
      name: "Echo"
      description: "Echo back the input"
      endpoint: "/api/echo"
      method: "POST"
      inputs: ["text"]
      outputs: ["text"]
      estimated_time_seconds: 1

resources:
  min_vram_gb: null
  min_ram_gb: 1
  gpu_required: false

tags:
  - "test"
  - "example"
"""


@pytest.fixture
def service_folder(temp_dir, sample_capability_yaml):
    """Create a mock service folder with all required files."""
    service_path = temp_dir / "test_service"
    service_path.mkdir()

    # Create main.py
    (service_path / "main.py").write_text("""
import os
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/echo")
def echo(text: str):
    return {"result": text}

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
""")

    # Create README.md
    (service_path / "README.md").write_text("# Test Service\n\nA test service.")

    # Create CAPABILITY.yaml
    (service_path / "CAPABILITY.yaml").write_text(sample_capability_yaml)

    return service_path


@pytest.fixture
def service_folder_no_capability(temp_dir):
    """Create a mock service folder without CAPABILITY.yaml."""
    service_path = temp_dir / "unconfigured_service"
    service_path.mkdir()

    (service_path / "main.py").write_text("print('hello')")
    (service_path / "README.md").write_text("# Unconfigured Service")

    return service_path


@pytest.fixture
def agent_config(temp_dir, service_folder):
    """Create an AgentConfig for testing."""
    return AgentConfig(
        machine_id="test-machine",
        machine_name="Test Machine",
        machine_description="Test machine for unit testing",
        service_folders=[str(service_folder.parent)],
        always_running=[],
        agent=AgentSettings(port=9100, host="127.0.0.1"),
        health_check=HealthCheckSettings(interval_seconds=30, timeout_seconds=5),
        llm=LLMSettings(model="google/gemini-flash-1.5", timeout_seconds=60),
    )


@pytest.fixture
def discovery(agent_config):
    """Create a ServiceDiscovery instance."""
    return ServiceDiscovery(agent_config)


@pytest.fixture
def resource_monitor():
    """Create a ResourceMonitor instance (mocked)."""
    monitor = MagicMock(spec=ResourceMonitor)
    monitor.get_all_stats.return_value = {
        "cpu": {"usage_percent": 10.0},
        "ram": {"total_gb": 16.0, "available_gb": 8.0, "usage_percent": 50.0},
        "gpu": None,
        "disk": {"total_gb": 500.0, "free_gb": 250.0, "usage_percent": 50.0},
    }
    monitor.check_resources_available.return_value = (True, None)
    return monitor


@pytest.fixture
def service_manager(agent_config, discovery, resource_monitor):
    """Create a ServiceManager instance."""
    return ServiceManager(agent_config, discovery, resource_monitor)


@pytest.fixture
def sample_service(service_folder):
    """Create a sample Service object."""
    capability = ServiceCapability(
        schema_version="1.0",
        service_id="test_service",
        service_name="Test Service",
        description="A test service",
        version="1.0.0",
        start_command="python main.py",
        working_directory=".",
        ports={"api": PortConfig(default=8000, env_var="API_PORT", cli_arg="--port")},
        environment=[{"name": "DEBUG", "default": "false"}],
        health_check_path="/health",
        api_base_path="/api",
        operations=[],
        min_ram_gb=1.0,
        gpu_required=False,
    )

    return Service(
        id="test_service",
        path=service_folder,
        status=ServiceStatus.READY,
        capability=capability,
    )


@pytest.fixture
def mock_agent(agent_config, discovery, resource_monitor):
    """Create a mock agent object for API testing."""
    agent = MagicMock()
    agent.config = agent_config
    agent.discovery = discovery
    agent.resource_monitor = resource_monitor
    # Use a mock for service_manager to allow setting return_value on methods
    mock_service_manager = MagicMock()
    mock_service_manager.get_service_logs.return_value = []
    agent.service_manager = mock_service_manager
    return agent


class AsyncMockResponse:
    """Mock HTTP response for async testing."""

    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


@pytest.fixture
def mock_httpx_client():
    """Create a mock httpx AsyncClient."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=AsyncMockResponse(200, {"status": "ok"}))
    mock_client.post = AsyncMock(return_value=AsyncMockResponse(200, {}))
    return mock_client
