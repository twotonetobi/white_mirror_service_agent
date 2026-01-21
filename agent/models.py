from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Any
import subprocess


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
class PortConfig:
    default: int
    env_var: Optional[str] = None
    cli_arg: Optional[str] = None
    description: str = ""


@dataclass
class ServiceCapability:
    schema_version: str
    service_id: str
    service_name: str
    description: str = ""
    version: str = "1.0.0"

    start_command: str = "python main.py"
    working_directory: str = "."
    ports: dict[str, PortConfig] = field(default_factory=dict)
    environment: list[dict] = field(default_factory=list)
    venv_path: Optional[str] = None

    health_check_path: Optional[str] = None
    api_base_path: str = ""

    operations: list[dict] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    outputs: list[dict] = field(default_factory=list)

    min_vram_gb: Optional[float] = None
    min_ram_gb: Optional[float] = None
    gpu_required: bool = False

    tags: list[str] = field(default_factory=list)

    raw_yaml: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, data: dict, service_id: str) -> "ServiceCapability":
        service_data = data.get("service", {})
        runtime = data.get("runtime", {})
        endpoints = data.get("endpoints", {})
        capabilities = data.get("capabilities", {})
        resources = data.get("resources", {})

        ports = {}
        for port_key, port_data in runtime.get("ports", {}).items():
            ports[port_key] = PortConfig(
                default=port_data.get("default", 8000),
                env_var=port_data.get("env_var"),
                cli_arg=port_data.get("cli_arg"),
                description=port_data.get("description", ""),
            )

        api_endpoint = endpoints.get("api", {})

        return cls(
            schema_version=data.get("schema_version", "1.0"),
            service_id=service_data.get("id", service_id),
            service_name=service_data.get("name", service_id),
            description=service_data.get("description", ""),
            version=service_data.get("version", "1.0.0"),
            start_command=runtime.get("start_command", "python main.py"),
            working_directory=runtime.get("working_directory", "."),
            ports=ports,
            environment=runtime.get("environment", []),
            venv_path=runtime.get("venv", {}).get("path"),
            health_check_path=api_endpoint.get("health_check"),
            api_base_path=api_endpoint.get("base_path", ""),
            operations=capabilities.get("operations", []),
            inputs=capabilities.get("inputs", []),
            outputs=capabilities.get("outputs", []),
            min_vram_gb=resources.get("min_vram_gb"),
            min_ram_gb=resources.get("min_ram_gb"),
            gpu_required=resources.get("gpu_required", False),
            tags=data.get("tags", []),
            raw_yaml=data,
        )


@dataclass
class Service:
    id: str
    path: Path
    status: ServiceStatus = ServiceStatus.DISCOVERED
    capability: Optional[ServiceCapability] = None

    pid: Optional[int] = None
    process: Optional[subprocess.Popen] = None
    assigned_ports: dict[str, int] = field(default_factory=dict)

    start_time: Optional[datetime] = None
    error: Optional[str] = None
    logs: list[str] = field(default_factory=lambda: [])

    health_status: str = "unknown"
    last_health_check: Optional[datetime] = None

    @property
    def name(self) -> str:
        if self.capability:
            return self.capability.service_name
        return self.id

    @property
    def has_capability(self) -> bool:
        return self.capability is not None

    @property
    def needs_capability(self) -> bool:
        return not self.has_capability

    @property
    def is_running(self) -> bool:
        return self.status == ServiceStatus.RUNNING

    @property
    def uptime_seconds(self) -> Optional[float]:
        if self.start_time and self.is_running:
            return (datetime.now() - self.start_time).total_seconds()
        return None

    def to_dict(self) -> dict:
        result = {
            "id": self.id,
            "name": self.name,
            "path": str(self.path),
            "status": self.status.value,
            "has_capability": self.has_capability,
            "needs_capability_generation": self.needs_capability,
        }

        if self.capability:
            result["description"] = self.capability.description
            result["version"] = self.capability.version
            result["tags"] = self.capability.tags
            result["operations"] = self.capability.operations

        if self.is_running:
            result["pid"] = self.pid
            result["assigned_ports"] = self.assigned_ports
            result["uptime_seconds"] = self.uptime_seconds
            result["health"] = {
                "status": self.health_status,
                "last_check": self.last_health_check.isoformat()
                if self.last_health_check
                else None,
            }

        if self.error:
            result["error"] = self.error

        return result
