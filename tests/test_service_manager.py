"""Unit tests for ServiceManager."""

import asyncio
import subprocess
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

from agent.service_manager import ServiceManager
from agent.models import Service, ServiceStatus, ServiceCapability, PortConfig


class TestServiceManagerStart:
    """Tests for starting services."""

    @pytest.mark.asyncio
    async def test_start_service_not_found(self, service_manager, discovery):
        """Start should raise ValueError for unknown service."""
        with pytest.raises(ValueError, match="Service not found"):
            await service_manager.start_service("nonexistent")

    @pytest.mark.asyncio
    async def test_start_service_no_capability(
        self, service_manager, discovery, service_folder_no_capability, agent_config
    ):
        """Start should raise ValueError if service has no capability."""
        agent_config.service_folders = [str(service_folder_no_capability.parent)]
        discovery.scan()

        with pytest.raises(ValueError, match="has no CAPABILITY.yaml"):
            await service_manager.start_service("unconfigured_service")

    @pytest.mark.asyncio
    async def test_start_service_already_running(
        self, service_manager, discovery, service_folder
    ):
        """Start should raise ValueError if service is already running."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.status = ServiceStatus.RUNNING

        with pytest.raises(ValueError, match="already running"):
            await service_manager.start_service("test_service")

    @pytest.mark.asyncio
    async def test_start_service_insufficient_resources(
        self, service_manager, discovery, service_folder, resource_monitor
    ):
        """Start should check resource availability."""
        discovery.scan()
        service = discovery.get_service("test_service")

        # Mock insufficient resources
        resource_monitor.check_resources_available.return_value = (
            False,
            "Insufficient VRAM",
        )

        # Set GPU requirement
        service.capability.gpu_required = True
        service.capability.min_vram_gb = 8.0

        with pytest.raises(ValueError, match="Insufficient VRAM"):
            await service_manager.start_service("test_service")

    @pytest.mark.asyncio
    async def test_start_service_success(
        self, service_manager, discovery, service_folder
    ):
        """Start should launch process and update service state."""
        discovery.scan()

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            # Patch health check wait
            with patch.object(
                service_manager, "_wait_for_ready", new_callable=AsyncMock
            ):
                service = await service_manager.start_service("test_service")

        assert service.status == ServiceStatus.RUNNING
        assert service.pid == 12345
        assert service.assigned_ports == {"api": 8000}
        assert service.start_time is not None

    @pytest.mark.asyncio
    async def test_start_service_custom_ports(
        self, service_manager, discovery, service_folder
    ):
        """Start should accept custom port assignments."""
        discovery.scan()

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            with patch.object(
                service_manager, "_wait_for_ready", new_callable=AsyncMock
            ):
                service = await service_manager.start_service(
                    "test_service", port_assignments={"api": 9000}
                )

        assert service.assigned_ports["api"] == 9000

    @pytest.mark.asyncio
    async def test_start_service_sets_env_vars(
        self, service_manager, discovery, service_folder
    ):
        """Start should set environment variables from port config."""
        discovery.scan()

        captured_env = {}

        def capture_popen(*args, **kwargs):
            captured_env.update(kwargs.get("env", {}))
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = None
            mock_process.stdout = iter([])
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch.object(
                service_manager, "_wait_for_ready", new_callable=AsyncMock
            ):
                await service_manager.start_service("test_service")

        assert captured_env.get("API_PORT") == "8000"

    @pytest.mark.asyncio
    async def test_start_service_process_exit(
        self, service_manager, discovery, service_folder
    ):
        """Start should detect early process exit."""
        discovery.scan()
        # Remove health check to trigger early exit check
        service = discovery.get_service("test_service")
        service.capability.health_check_path = None

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_process.poll.return_value = 1  # Process exited
            mock_process.returncode = 1
            mock_process.stdout = iter([])
            mock_popen.return_value = mock_process

            with pytest.raises(RuntimeError, match="Process exited"):
                await service_manager.start_service("test_service")


class TestServiceManagerStop:
    """Tests for stopping services."""

    @pytest.mark.asyncio
    async def test_stop_service_not_found(self, service_manager):
        """Stop should raise ValueError for unknown service."""
        with pytest.raises(ValueError, match="Service not found"):
            await service_manager.stop_service("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_service_not_running(
        self, service_manager, discovery, service_folder
    ):
        """Stop should handle already stopped service gracefully."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.process = None

        result = await service_manager.stop_service("test_service")
        assert result.status == ServiceStatus.STOPPED

    @pytest.mark.asyncio
    async def test_stop_service_success(
        self, service_manager, discovery, service_folder
    ):
        """Stop should terminate process gracefully."""
        discovery.scan()
        service = discovery.get_service("test_service")

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait.return_value = 0
        service.process = mock_process
        service.status = ServiceStatus.RUNNING
        service.pid = 12345

        result = await service_manager.stop_service("test_service")

        assert result.status == ServiceStatus.STOPPED
        assert result.pid is None
        assert result.process is None
        mock_process.send_signal.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_service_force_kill(
        self, service_manager, discovery, service_folder
    ):
        """Stop should force kill if graceful shutdown fails."""
        discovery.scan()
        service = discovery.get_service("test_service")

        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 10),
            None,
        ]
        service.process = mock_process
        service.status = ServiceStatus.RUNNING

        result = await service_manager.stop_service("test_service")

        mock_process.kill.assert_called_once()
        assert result.status == ServiceStatus.STOPPED


class TestServiceManagerRestart:
    """Tests for restarting services."""

    @pytest.mark.asyncio
    async def test_restart_preserves_ports(
        self, service_manager, discovery, service_folder
    ):
        """Restart should preserve old port assignments by default."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.status = ServiceStatus.RUNNING
        service.assigned_ports = {"api": 9000}

        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        service.process = mock_process

        with patch.object(
            service_manager, "stop_service", new_callable=AsyncMock
        ) as mock_stop:
            mock_stop.return_value = service

            with patch.object(
                service_manager, "start_service", new_callable=AsyncMock
            ) as mock_start:
                mock_start.return_value = service
                await service_manager.restart_service("test_service")

                mock_start.assert_called_once_with("test_service", {"api": 9000})


class TestServiceManagerHealth:
    """Tests for health checking."""

    @pytest.mark.asyncio
    async def test_health_check_not_found(self, service_manager):
        """Health check should handle unknown service."""
        result = await service_manager.check_service_health("nonexistent")
        assert result["status"] == "error"
        assert "not found" in result["reason"]

    @pytest.mark.asyncio
    async def test_health_check_not_running(
        self, service_manager, discovery, service_folder
    ):
        """Health check should report not running."""
        discovery.scan()

        result = await service_manager.check_service_health("test_service")
        assert result["status"] == "not_running"

    @pytest.mark.asyncio
    async def test_health_check_process_crashed(
        self, service_manager, discovery, service_folder
    ):
        """Health check should detect crashed process."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.status = ServiceStatus.RUNNING

        mock_process = MagicMock()
        mock_process.poll.return_value = 1
        mock_process.returncode = 1
        service.process = mock_process

        result = await service_manager.check_service_health("test_service")
        assert result["status"] == "crashed"
        assert result["exit_code"] == 1

    @pytest.mark.asyncio
    async def test_health_check_no_endpoint(
        self, service_manager, discovery, service_folder
    ):
        """Health check should handle missing health endpoint config."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.status = ServiceStatus.RUNNING
        service.capability.health_check_path = None

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        service.process = mock_process

        result = await service_manager.check_service_health("test_service")
        assert result["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_health_check_success(
        self, service_manager, discovery, service_folder, mock_httpx_client
    ):
        """Health check should return healthy on successful check."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.status = ServiceStatus.RUNNING
        service.assigned_ports = {"api": 8000}

        mock_process = MagicMock()
        mock_process.poll.return_value = None
        service.process = mock_process

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value.__aenter__.return_value = mock_httpx_client

            result = await service_manager.check_service_health("test_service")

        assert result["status"] == "healthy"


class TestServiceManagerLogs:
    """Tests for log retrieval."""

    def test_get_logs_not_found(self, service_manager):
        """get_service_logs should return empty list for unknown service."""
        logs = service_manager.get_service_logs("nonexistent")
        assert logs == []

    def test_get_logs_returns_tail(self, service_manager, discovery, service_folder):
        """get_service_logs should return last N lines."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.logs = [f"line {i}" for i in range(200)]

        logs = service_manager.get_service_logs("test_service", lines=50)
        assert len(logs) == 50
        assert logs[-1] == "line 199"


class TestStopAllServices:
    """Tests for stopping all services."""

    @pytest.mark.asyncio
    async def test_stop_all_services(self, service_manager, discovery, service_folder):
        """stop_all_services should stop all running services."""
        discovery.scan()
        service = discovery.get_service("test_service")
        service.status = ServiceStatus.RUNNING

        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        service.process = mock_process

        await service_manager.stop_all_services()

        assert service.status == ServiceStatus.STOPPED
