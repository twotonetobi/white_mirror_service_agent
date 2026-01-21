"""Unit tests for REST API endpoints."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api import create_api_router
from agent.models import Service, ServiceStatus, ServiceCapability, PortConfig


@pytest.fixture
def app(mock_agent, discovery, service_folder):
    """Create FastAPI app with API router."""
    # Scan to populate discovery
    discovery.scan()

    app = FastAPI()
    router = create_api_router(mock_agent)
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestDiscoverEndpoint:
    """Tests for GET /discover endpoint."""

    def test_discover_returns_agent_info(self, client, agent_config):
        """Discover should return agent information."""
        response = client.get("/discover")
        assert response.status_code == 200

        data = response.json()
        assert "agent" in data
        assert data["agent"]["machine_id"] == "test-machine"
        assert data["agent"]["machine_name"] == "Test Machine"

    def test_discover_returns_services(self, client):
        """Discover should return list of services."""
        response = client.get("/discover")
        assert response.status_code == 200

        data = response.json()
        assert "services" in data
        assert len(data["services"]) == 1
        assert data["services"][0]["id"] == "test_service"

    def test_discover_returns_resources(self, client):
        """Discover should return resource information."""
        response = client.get("/discover")
        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert "cpu" in data["resources"]
        assert "ram" in data["resources"]


class TestStatusEndpoint:
    """Tests for GET /status endpoint."""

    def test_status_returns_healthy(self, client):
        """Status should return healthy when agent is running."""
        response = client.get("/status")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["machine_id"] == "test-machine"

    def test_status_includes_service_counts(self, client):
        """Status should include service count summary."""
        response = client.get("/status")
        assert response.status_code == 200

        data = response.json()
        assert "services" in data
        assert data["services"]["total"] == 1


class TestServicesEndpoint:
    """Tests for /services endpoints."""

    def test_list_services(self, client):
        """GET /services should return all services."""
        response = client.get("/services")
        assert response.status_code == 200

        data = response.json()
        assert "services" in data
        assert len(data["services"]) == 1

    def test_get_service_by_id(self, client, mock_agent):
        """GET /services/{id} should return specific service."""
        mock_agent.service_manager.get_service_logs.return_value = []

        response = client.get("/services/test_service")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "test_service"
        assert data["name"] == "Test Service"

    def test_get_service_not_found(self, client):
        """GET /services/{id} should return 404 for unknown service."""
        response = client.get("/services/nonexistent")
        assert response.status_code == 404


class TestServiceControlEndpoints:
    """Tests for service start/stop/restart endpoints."""

    def test_start_service(self, client, mock_agent, sample_service):
        """POST /services/{id}/start should start service."""
        mock_agent.service_manager.start_service = AsyncMock(
            return_value=Service(
                id="test_service",
                path=sample_service.path,
                status=ServiceStatus.RUNNING,
                capability=sample_service.capability,
                pid=12345,
                assigned_ports={"api": 8000},
            )
        )

        response = client.post("/services/test_service/start", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["pid"] == 12345
        assert data["assigned_ports"]["api"] == 8000

    def test_start_service_with_port_assignment(
        self, client, mock_agent, sample_service
    ):
        """Start should accept custom port assignments."""
        mock_agent.service_manager.start_service = AsyncMock(
            return_value=Service(
                id="test_service",
                path=sample_service.path,
                status=ServiceStatus.RUNNING,
                capability=sample_service.capability,
                pid=12345,
                assigned_ports={"api": 9000},
            )
        )

        response = client.post(
            "/services/test_service/start",
            json={"port_assignments": {"api": 9000}},
        )
        assert response.status_code == 200

        mock_agent.service_manager.start_service.assert_called_once()
        call_args = mock_agent.service_manager.start_service.call_args
        assert call_args.kwargs["port_assignments"] == {"api": 9000}

    def test_start_service_error(self, client, mock_agent):
        """Start should return error on failure."""
        mock_agent.service_manager.start_service = AsyncMock(
            side_effect=ValueError("Service not found")
        )

        response = client.post("/services/test_service/start", json={})
        assert response.status_code == 400

    def test_stop_service(self, client, mock_agent, sample_service):
        """POST /services/{id}/stop should stop service."""
        mock_agent.service_manager.stop_service = AsyncMock(
            return_value=Service(
                id="test_service",
                path=sample_service.path,
                status=ServiceStatus.STOPPED,
                capability=sample_service.capability,
            )
        )

        response = client.post("/services/test_service/stop")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["status"] == "stopped"

    def test_restart_service(self, client, mock_agent, sample_service):
        """POST /services/{id}/restart should restart service."""
        mock_agent.service_manager.restart_service = AsyncMock(
            return_value=Service(
                id="test_service",
                path=sample_service.path,
                status=ServiceStatus.RUNNING,
                capability=sample_service.capability,
                pid=54321,
                assigned_ports={"api": 8000},
            )
        )

        response = client.post("/services/test_service/restart", json={})
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["pid"] == 54321


class TestHealthEndpoint:
    """Tests for GET /services/{id}/health endpoint."""

    def test_health_check(self, client, mock_agent):
        """Health check should return service health status."""
        mock_agent.service_manager.check_service_health = AsyncMock(
            return_value={"status": "healthy", "response_time_ms": 50.0}
        )

        response = client.get("/services/test_service/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["service_id"] == "test_service"


class TestLogsEndpoint:
    """Tests for GET /services/{id}/logs endpoint."""

    def test_get_logs(self, client, mock_agent):
        """Logs endpoint should return service logs."""
        mock_agent.service_manager.get_service_logs.return_value = [
            "Starting server...",
            "Listening on port 8000",
        ]

        response = client.get("/services/test_service/logs")
        assert response.status_code == 200

        data = response.json()
        assert data["service_id"] == "test_service"
        assert len(data["logs"]) == 2

    def test_get_logs_with_limit(self, client, mock_agent):
        """Logs endpoint should accept lines parameter."""
        mock_agent.service_manager.get_service_logs.return_value = ["line1"]

        response = client.get("/services/test_service/logs?lines=50")
        assert response.status_code == 200

        mock_agent.service_manager.get_service_logs.assert_called_with(
            "test_service", lines=50
        )

    def test_get_logs_service_not_found(self, client, mock_agent, discovery):
        """Logs should return 404 for unknown service."""
        response = client.get("/services/nonexistent/logs")
        assert response.status_code == 404


class TestConfigEndpoints:
    """Tests for /config endpoints."""

    def test_get_config(self, client, agent_config):
        """GET /config should return current configuration."""
        response = client.get("/config")
        assert response.status_code == 200

        data = response.json()
        assert data["machine_id"] == "test-machine"
        assert data["machine_name"] == "Test Machine"

    def test_update_config(self, client, agent_config):
        """PUT /config should update configuration."""
        response = client.put(
            "/config",
            json={"machine_name": "Updated Name", "machine_description": "New desc"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify config was updated
        assert agent_config.machine_name == "Updated Name"
        assert agent_config.machine_description == "New desc"


class TestScanEndpoint:
    """Tests for POST /scan endpoint."""

    def test_scan_folders(self, client, discovery):
        """POST /scan should rescan service folders."""
        response = client.post("/scan")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "services_found" in data


class TestResourcesEndpoint:
    """Tests for GET /resources endpoint."""

    def test_get_resources(self, client, resource_monitor):
        """Resources endpoint should return system stats."""
        response = client.get("/resources")
        assert response.status_code == 200

        data = response.json()
        assert "cpu" in data
        assert "ram" in data
