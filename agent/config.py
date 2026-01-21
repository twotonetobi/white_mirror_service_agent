from pathlib import Path
from typing import Optional
import os
import platform
import yaml
from pydantic import BaseModel, Field, field_validator

from agent.machine_id import get_machine_identifier, get_short_machine_id


def detect_platform() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    elif system == "linux":
        return "linux"
    return "unknown"


CURRENT_PLATFORM = detect_platform()
MACHINE_INFO = get_machine_identifier()
MACHINE_SHORT_ID = MACHINE_INFO["short_id"]


MACHINE_PORT_RANGES = {
    "macos": {
        "api_port_min": 8100,
        "api_port_max": 8199,
        "ui_port_min": 7800,
        "ui_port_max": 7849,
    },
    "windows-1": {
        "api_port_min": 8200,
        "api_port_max": 8299,
        "ui_port_min": 7850,
        "ui_port_max": 7899,
    },
    "windows-2": {
        "api_port_min": 8300,
        "api_port_max": 8399,
        "ui_port_min": 7900,
        "ui_port_max": 7949,
    },
    "linux": {
        "api_port_min": 8400,
        "api_port_max": 8499,
        "ui_port_min": 7950,
        "ui_port_max": 7999,
    },
}


class AgentSettings(BaseModel):
    port: int = 9100
    host: str = "0.0.0.0"
    log_level: str = "INFO"
    log_file: Optional[str] = None


class PortRangeSettings(BaseModel):
    api_port_min: int = 8100
    api_port_max: int = 8299
    ui_port_min: int = 7800
    ui_port_max: int = 7999
    auto_resolve_conflicts: bool = True
    sync_readme_on_resolve: bool = True


class ResourceSettings(BaseModel):
    gpu_vram_reserve_gb: float = 2.0
    ram_reserve_gb: float = 4.0
    monitor_interval_seconds: int = 30


class LLMSettings(BaseModel):
    provider: str = "openrouter"
    model: str = "google/gemini-3-flash-preview"
    api_key: Optional[str] = None
    timeout_seconds: int = 120
    max_retries: int = 3


class HealthCheckSettings(BaseModel):
    enabled: bool = True
    interval_seconds: int = 60
    timeout_seconds: int = 5


class UISettings(BaseModel):
    enabled: bool = True
    share: bool = False
    auth: Optional[list] = None
    open_browser: bool = True
    theme: str = "soft"


class AgentConfig(BaseModel):
    machine_id: str
    machine_name: str = "Service Agent"
    machine_description: str = ""
    platform: str = CURRENT_PLATFORM

    agent: AgentSettings = Field(default_factory=AgentSettings)
    service_folders: list[str] = Field(default_factory=list)
    always_running: list[str] = Field(default_factory=list)
    resources: ResourceSettings = Field(default_factory=ResourceSettings)
    port_ranges: PortRangeSettings = Field(default_factory=PortRangeSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    health_check: HealthCheckSettings = Field(default_factory=HealthCheckSettings)
    ui: UISettings = Field(default_factory=UISettings)

    _config_file: Optional[Path] = None

    class Config:
        arbitrary_types_allowed = True
        underscore_attrs_are_private = True

    @field_validator("service_folders", mode="before")
    @classmethod
    def resolve_paths(cls, v):
        if v is None:
            return []
        return [str(Path(p).resolve()) if not Path(p).is_absolute() else p for p in v]

    def get_llm_api_key(self) -> Optional[str]:
        return self.llm.api_key or os.getenv("OPENROUTER_API_KEY")

    def save_config(self):
        if self._config_file is None:
            self._config_file = Path("./config.yaml")

        data = {
            "machine_id": self.machine_id,
            "machine_name": self.machine_name,
            "machine_description": self.machine_description,
            "agent": {
                "port": self.agent.port,
                "host": self.agent.host,
                "log_level": self.agent.log_level,
            },
            "service_folders": self.service_folders,
            "always_running": self.always_running,
            "resources": {
                "gpu_vram_reserve_gb": self.resources.gpu_vram_reserve_gb,
                "ram_reserve_gb": self.resources.ram_reserve_gb,
                "monitor_interval_seconds": self.resources.monitor_interval_seconds,
            },
            "port_ranges": {
                "api_port_min": self.port_ranges.api_port_min,
                "api_port_max": self.port_ranges.api_port_max,
                "ui_port_min": self.port_ranges.ui_port_min,
                "ui_port_max": self.port_ranges.ui_port_max,
            },
            "llm": {
                "provider": self.llm.provider,
                "model": self.llm.model,
            },
            "health_check": {
                "enabled": self.health_check.enabled,
                "interval_seconds": self.health_check.interval_seconds,
                "timeout_seconds": self.health_check.timeout_seconds,
            },
            "ui": {
                "enabled": self.ui.enabled,
                "share": self.ui.share,
            },
        }

        with open(self._config_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def get_default_port_ranges_for_machine(machine_id: str, platform_name: str) -> dict:
    machine_config_path = Path(f"./config.{machine_id}.yaml")
    if machine_config_path.exists():
        with open(machine_config_path, "r") as f:
            machine_data = yaml.safe_load(f) or {}
            if "port_ranges" in machine_data:
                return machine_data["port_ranges"]

    if platform_name in MACHINE_PORT_RANGES:
        return MACHINE_PORT_RANGES[platform_name]

    return {
        "api_port_min": 8100,
        "api_port_max": 8299,
        "ui_port_min": 7800,
        "ui_port_max": 7999,
    }


def load_config(config_path: Optional[str] = None) -> AgentConfig:
    platform_name = CURRENT_PLATFORM
    machine_id = MACHINE_SHORT_ID

    search_paths = [
        config_path,
        f"./config.{machine_id}.yaml",
        f"./config-{platform_name}.yaml",
        "./config.yaml",
        Path.home() / ".white_mirror_agent" / f"config.{machine_id}.yaml",
        Path.home() / ".white_mirror_agent" / f"config-{platform_name}.yaml",
        Path.home() / ".white_mirror_agent" / "config.yaml",
    ]

    config_file = None
    for path in search_paths:
        if path and Path(path).exists():
            config_file = Path(path)
            break

    if config_file:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}
        config_file = Path("./config.yaml")

    data["platform"] = platform_name

    env_overrides = {
        "machine_id": os.getenv("WM_AGENT_MACHINE_ID"),
        "machine_name": os.getenv("WM_AGENT_MACHINE_NAME"),
    }

    for key, value in env_overrides.items():
        if value is not None:
            data[key] = value

    port_env = os.getenv("WM_AGENT_PORT")
    if port_env:
        data.setdefault("agent", {})["port"] = int(port_env)

    if os.getenv("WM_AGENT_LOG_LEVEL"):
        data.setdefault("agent", {})["log_level"] = os.getenv("WM_AGENT_LOG_LEVEL")

    if "machine_id" not in data:
        data["machine_id"] = f"{MACHINE_INFO['hostname']}-{machine_id}"

    if "port_ranges" not in data:
        data["port_ranges"] = get_default_port_ranges_for_machine(
            machine_id, platform_name
        )

    config = AgentConfig(**data)
    config._config_file = Path(config_file) if config_file else Path("./config.yaml")
    return config


def generate_machine_config(output_path: Optional[str] = None) -> Path:
    machine_id = MACHINE_SHORT_ID
    platform_name = CURRENT_PLATFORM

    if output_path is None:
        output_path = f"./config.{machine_id}.yaml"

    port_ranges = get_default_port_ranges_for_machine(machine_id, platform_name)

    config_data = {
        "machine_id": f"{MACHINE_INFO['hostname']}-{machine_id}",
        "machine_name": f"{platform_name.title()} Machine ({machine_id})",
        "machine_description": f"Auto-generated config for {MACHINE_INFO['hostname']}",
        "agent": {
            "port": 9100,
            "host": "0.0.0.0",
            "log_level": "INFO",
        },
        "port_ranges": port_ranges,
        "service_folders": [],
        "always_running": [],
    }

    output_file = Path(output_path)
    with open(output_file, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

    return output_file
