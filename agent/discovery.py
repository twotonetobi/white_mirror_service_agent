import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from agent.config import AgentConfig
from agent.models import Service, ServiceStatus, ServiceCapability

logger = logging.getLogger("agent.discovery")

CAPABILITY_FILENAME = "CAPABILITY.yaml"


class ServiceDiscovery:
    def __init__(self, config: AgentConfig):
        self.config = config
        self._services: dict[str, Service] = {}

    def scan(self) -> list[Service]:
        self._services.clear()

        for folder_path in self.config.service_folders:
            folder = Path(folder_path)
            if not folder.exists():
                logger.warning(f"Service folder does not exist: {folder}")
                continue

            if not folder.is_dir():
                logger.warning(f"Service folder is not a directory: {folder}")
                continue

            if self._is_valid_service(folder):
                service = self._create_service(folder)
                self._services[service.id] = service
                logger.debug(f"Discovered service: {service.id} at {folder}")
            else:
                self._scan_folder(folder)

        return list(self._services.values())

    def _scan_folder(self, folder: Path):
        for entry in folder.iterdir():
            if not entry.is_dir():
                continue

            if entry.name.startswith(".") or entry.name.startswith("_"):
                continue

            if self._is_valid_service(entry):
                service = self._create_service(entry)
                self._services[service.id] = service
                logger.debug(f"Discovered service: {service.id} at {entry}")

    def _is_valid_service(self, path: Path) -> bool:
        has_readme = (path / "README.md").exists()
        has_main = (path / "main.py").exists()
        has_app = (path / "app.py").exists()
        has_capability = (path / CAPABILITY_FILENAME).exists()

        return has_readme or has_main or has_app or has_capability

    def _create_service(self, path: Path) -> Service:
        service_id = self._sanitize_id(path.name)

        capability = None
        capability_file = path / CAPABILITY_FILENAME
        if capability_file.exists():
            try:
                capability = self._load_capability(capability_file, service_id)
            except Exception as e:
                logger.error(f"Failed to load CAPABILITY.yaml for {service_id}: {e}")

        status = ServiceStatus.READY if capability else ServiceStatus.DISCOVERED

        return Service(id=service_id, path=path, status=status, capability=capability)

    def _load_capability(self, path: Path, service_id: str) -> ServiceCapability:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return ServiceCapability.from_yaml(data, service_id)

    def _sanitize_id(self, name: str) -> str:
        sanitized = name.lower()
        sanitized = re.sub(r"[^a-z0-9_-]", "_", sanitized)
        sanitized = re.sub(r"_+", "_", sanitized)
        sanitized = sanitized.strip("_-")
        return sanitized

    def get_service(self, service_id: str) -> Optional[Service]:
        return self._services.get(service_id)

    def get_all_services(self) -> list[Service]:
        return list(self._services.values())

    def add_service_folder(self, folder_path: str) -> list[Service]:
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Invalid folder path: {folder_path}")

        if folder_path not in self.config.service_folders:
            self.config.service_folders.append(str(folder.resolve()))

        new_services = []
        self._scan_folder(folder)

        return new_services

    def refresh_service(self, service_id: str) -> Optional[Service]:
        service = self._services.get(service_id)
        if not service:
            return None

        capability_file = service.path / CAPABILITY_FILENAME
        if capability_file.exists():
            try:
                service.capability = self._load_capability(capability_file, service_id)
                if service.status == ServiceStatus.DISCOVERED:
                    service.status = ServiceStatus.READY
            except Exception as e:
                logger.error(f"Failed to reload CAPABILITY.yaml for {service_id}: {e}")
                service.error = str(e)
                service.status = ServiceStatus.ERROR

        return service

    def update_service_capability(
        self, service_id: str, capability_yaml: str
    ) -> Service:
        service = self._services.get(service_id)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        capability_file = service.path / CAPABILITY_FILENAME
        with open(capability_file, "w", encoding="utf-8") as f:
            f.write(capability_yaml)

        refreshed = self.refresh_service(service_id)
        if refreshed is None:
            raise ValueError(f"Failed to refresh service: {service_id}")
        return refreshed
