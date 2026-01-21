import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from agent.config import AgentConfig
from agent.discovery import ServiceDiscovery
from agent.models import Service, ServiceStatus
from agent.resource_monitor import ResourceMonitor

logger = logging.getLogger("agent.service_manager")


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return False
        except OSError:
            return True


class ServiceManager:
    def __init__(
        self,
        config: AgentConfig,
        discovery: ServiceDiscovery,
        resource_monitor: ResourceMonitor,
    ):
        self.config = config
        self.discovery = discovery
        self.resource_monitor = resource_monitor
        self._log_threads: dict[str, threading.Thread] = {}

    async def start_service(
        self, service_id: str, port_assignments: Optional[dict[str, int]] = None
    ) -> Service:
        service = self.discovery.get_service(service_id)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        if not service.capability:
            raise ValueError(f"Service {service_id} has no CAPABILITY.yaml")

        if service.is_running:
            raise ValueError(f"Service {service_id} is already running")

        capability = service.capability

        ok, reason = self.resource_monitor.check_resources_available(
            required_vram_gb=capability.min_vram_gb,
            required_ram_gb=capability.min_ram_gb,
            gpu_required=capability.gpu_required,
        )
        if not ok:
            raise ValueError(f"Cannot start {service_id}: {reason}")

        env = os.environ.copy()

        configured_ports = self._get_configured_ports(service)
        assigned_ports = port_assignments or {}
        for port_key, port_config in capability.ports.items():
            if port_key not in assigned_ports:
                assigned_ports[port_key] = configured_ports.get(
                    port_key, port_config.default
                )

            if port_config.env_var:
                env[port_config.env_var] = str(assigned_ports[port_key])

        for var in capability.environment:
            var_name = var.get("name")
            var_default = var.get("default", "")
            if var_name and var_name not in env:
                env[var_name] = str(var_default)

        cwd = service.path
        if capability.working_directory and capability.working_directory != ".":
            cwd = service.path / capability.working_directory

        cmd = capability.start_command

        if capability.venv_path:
            venv_path = service.path / capability.venv_path
            if sys.platform == "win32":
                python = venv_path / "Scripts" / "python.exe"
            else:
                python = venv_path / "bin" / "python"

            if python.exists():
                cmd = cmd.replace("python ", f"{python} ", 1)
                cmd = cmd.replace("python3 ", f"{python} ", 1)

        logger.info(f"Starting {service_id}: {cmd}")
        logger.debug(f"  Working directory: {cwd}")
        logger.debug(f"  Ports: {assigned_ports}")

        service.status = ServiceStatus.STARTING
        service.assigned_ports = assigned_ports
        service.error = None

        try:
            process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            service.process = process
            service.pid = process.pid
            service.start_time = datetime.now()

            self._start_log_capture(service)

            if capability.health_check_path:
                await self._wait_for_ready(service)
            else:
                await asyncio.sleep(2)
                if process.poll() is not None:
                    raise RuntimeError(f"Process exited with code {process.returncode}")

            service.status = ServiceStatus.RUNNING
            logger.info(f"Service {service_id} started (PID: {service.pid})")

        except Exception as e:
            service.status = ServiceStatus.FAILED
            service.error = str(e)
            logger.error(f"Failed to start {service_id}: {e}")
            raise

        return service

    async def _wait_for_ready(self, service: Service, timeout: float = 60):
        if not service.capability or not service.capability.health_check_path:
            return

        api_port = service.assigned_ports.get("api")
        if not api_port:
            return

        health_url = (
            f"http://localhost:{api_port}{service.capability.health_check_path}"
        )

        start_time = asyncio.get_event_loop().time()

        async with httpx.AsyncClient() as client:
            while asyncio.get_event_loop().time() - start_time < timeout:
                if service.process and service.process.poll() is not None:
                    raise RuntimeError(f"Process exited during startup")

                try:
                    response = await client.get(health_url, timeout=2)
                    if response.status_code == 200:
                        logger.debug(f"Health check passed for {service.id}")
                        return
                except (httpx.ConnectError, httpx.TimeoutException):
                    pass

                await asyncio.sleep(1)

        raise TimeoutError(
            f"Service {service.id} did not become ready within {timeout}s"
        )

    def _start_log_capture(self, service: Service):
        def capture_logs():
            if not service.process or not service.process.stdout:
                return

            for line in service.process.stdout:
                line = line.rstrip()
                service.logs.append(line)
                if len(service.logs) > 1000:
                    service.logs = service.logs[-500:]
                logger.debug(f"[{service.id}] {line}")

        thread = threading.Thread(target=capture_logs, daemon=True)
        thread.start()
        self._log_threads[service.id] = thread

    async def stop_service(self, service_id: str, force: bool = False) -> Service:
        service = self.discovery.get_service(service_id)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        if not service.process:
            service.status = ServiceStatus.STOPPED
            return service

        service.status = ServiceStatus.STOPPING
        logger.info(f"Stopping {service_id} (PID: {service.pid})")

        try:
            if sys.platform == "win32":
                service.process.terminate()
            else:
                service.process.send_signal(signal.SIGTERM)

            try:
                service.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning(
                    f"Service {service_id} did not stop gracefully, force killing"
                )
                service.process.kill()
                service.process.wait(timeout=5)

            service.status = ServiceStatus.STOPPED
            service.pid = None
            service.process = None
            service.assigned_ports = {}
            logger.info(f"Service {service_id} stopped")

        except Exception as e:
            service.status = ServiceStatus.FAILED
            service.error = str(e)
            logger.error(f"Failed to stop {service_id}: {e}")
            raise

        return service

    async def restart_service(
        self, service_id: str, port_assignments: Optional[dict[str, int]] = None
    ) -> Service:
        service = self.discovery.get_service(service_id)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        old_ports = service.assigned_ports.copy() if service.assigned_ports else None

        if service.is_running:
            await self.stop_service(service_id)
            await asyncio.sleep(1)

        ports_to_use = port_assignments or old_ports
        return await self.start_service(service_id, ports_to_use)

    async def stop_all_services(self):
        services = self.discovery.get_all_services()
        for service in services:
            if service.is_running:
                try:
                    await self.stop_service(service.id)
                except Exception as e:
                    logger.error(f"Failed to stop {service.id}: {e}")

    async def check_service_health(self, service_id: str) -> dict:
        service = self.discovery.get_service(service_id)
        if not service:
            return {"status": "error", "reason": "Service not found"}

        if not service.is_running:
            return {"status": "not_running"}

        if service.process and service.process.poll() is not None:
            service.status = ServiceStatus.FAILED
            service.error = f"Process exited with code {service.process.returncode}"
            return {"status": "crashed", "exit_code": service.process.returncode}

        if not service.capability or not service.capability.health_check_path:
            return {"status": "unknown", "reason": "No health check configured"}

        api_port = service.assigned_ports.get("api")
        if not api_port:
            return {"status": "unknown", "reason": "No API port assigned"}

        health_url = (
            f"http://localhost:{api_port}{service.capability.health_check_path}"
        )

        try:
            async with httpx.AsyncClient() as client:
                start = asyncio.get_event_loop().time()
                response = await client.get(
                    health_url, timeout=self.config.health_check.timeout_seconds
                )
                response_time = (asyncio.get_event_loop().time() - start) * 1000

                if response.status_code == 200:
                    service.health_status = "healthy"
                    service.last_health_check = datetime.now()
                    return {
                        "status": "healthy",
                        "response_time_ms": round(response_time, 2),
                    }
                else:
                    service.health_status = "unhealthy"
                    return {
                        "status": "unhealthy",
                        "reason": f"HTTP {response.status_code}",
                    }
        except httpx.TimeoutException:
            service.health_status = "unhealthy"
            return {"status": "unhealthy", "reason": "timeout"}
        except httpx.ConnectError:
            service.health_status = "unhealthy"
            return {"status": "unhealthy", "reason": "connection refused"}
        except Exception as e:
            service.health_status = "error"
            return {"status": "error", "reason": str(e)}

    def get_service_logs(self, service_id: str, lines: int = 100) -> list[str]:
        service = self.discovery.get_service(service_id)
        if not service:
            return []
        return service.logs[-lines:]

    def get_port_conflicts(self) -> dict[int, list[str]]:
        conflicts: dict[int, list[str]] = {}
        services = self.discovery.get_all_services()

        for service in services:
            if not service.capability:
                continue

            configured_ports = self._get_configured_ports(service)

            for port_key, port in configured_ports.items():
                if port not in conflicts:
                    conflicts[port] = []
                conflicts[port].append(f"{service.id}:{port_key}")

        return {
            port: svc_list for port, svc_list in conflicts.items() if len(svc_list) > 1
        }

    def _get_configured_ports(self, service: Service) -> dict[str, int]:
        if not service.capability:
            return {}

        env_path = service.path / ".env"
        env_vars = {}

        if env_path.exists():
            try:
                content = env_path.read_text(encoding='utf-8')
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        env_vars[key] = value
            except Exception:
                pass

        configured_ports = {}
        for port_key, port_config in service.capability.ports.items():
            env_var = port_config.env_var
            default_port = port_config.default

            if env_var and env_var in env_vars:
                try:
                    configured_ports[port_key] = int(env_vars[env_var])
                except ValueError:
                    configured_ports[port_key] = default_port
            else:
                configured_ports[port_key] = default_port

        return configured_ports

    def get_next_available_port(
        self, port_type: str, exclude: Optional[set[int]] = None
    ) -> int:
        exclude = exclude or set()
        ranges = self.config.port_ranges

        if port_type == "api":
            port_min, port_max = ranges.api_port_min, ranges.api_port_max
        elif port_type == "ui":
            port_min, port_max = ranges.ui_port_min, ranges.ui_port_max
        else:
            port_min, port_max = 8000, 9000

        for port in range(port_min, port_max + 1):
            if port in exclude:
                continue
            if not is_port_in_use(port):
                return port

        raise RuntimeError(
            f"No available {port_type} ports in range {port_min}-{port_max}"
        )

    def assign_non_conflicting_ports(self) -> dict[str, dict[str, int]]:
        services = self.discovery.get_all_services()
        assignments: dict[str, dict[str, int]] = {}
        used_ports: set[int] = set()

        for service in services:
            if not service.capability:
                continue

            service_ports = {}
            for port_key, port_config in service.capability.ports.items():
                default_port = port_config.default

                if default_port not in used_ports and not is_port_in_use(default_port):
                    service_ports[port_key] = default_port
                    used_ports.add(default_port)
                else:
                    new_port = self.get_next_available_port(port_key, used_ports)
                    service_ports[port_key] = new_port
                    used_ports.add(new_port)
                    logger.info(
                        f"Reassigned {service.id}:{port_key} from {default_port} to {new_port}"
                    )

            assignments[service.id] = service_ports

        return assignments

    async def start_service_auto_ports(self, service_id: str) -> Service:
        service = self.discovery.get_service(service_id)
        if not service or not service.capability:
            raise ValueError(f"Service {service_id} not found or has no capability")

        running_services = [
            s for s in self.discovery.get_all_services() if s.is_running
        ]
        used_ports: set[int] = set()
        for s in running_services:
            used_ports.update(s.assigned_ports.values())

        port_assignments = {}
        for port_key, port_config in service.capability.ports.items():
            default_port = port_config.default
            if self._is_port_in_machine_range(default_port, port_key):
                if default_port not in used_ports and not is_port_in_use(default_port):
                    port_assignments[port_key] = default_port
                else:
                    new_port = self.get_next_available_port(port_key, used_ports)
                    port_assignments[port_key] = new_port
                    logger.info(
                        f"Auto-assigned {service_id}:{port_key} to {new_port} (default {default_port} in use)"
                    )
            else:
                new_port = self.get_next_available_port(port_key, used_ports)
                port_assignments[port_key] = new_port
                logger.info(
                    f"Assigned {service_id}:{port_key} to {new_port} (default {default_port} outside machine range)"
                )
            used_ports.add(port_assignments[port_key])

        return await self.start_service(service_id, port_assignments)

    def _is_port_in_machine_range(self, port: int, port_type: str) -> bool:
        if port_type == "api":
            port_min = self.config.port_ranges.api_port_min
            port_max = self.config.port_ranges.api_port_max
        elif port_type == "ui":
            port_min = self.config.port_ranges.ui_port_min
            port_max = self.config.port_ranges.ui_port_max
        else:
            return True
        return port_min <= port <= port_max
