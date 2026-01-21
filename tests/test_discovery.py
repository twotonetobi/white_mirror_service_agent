"""Unit tests for ServiceDiscovery."""

import tempfile
from pathlib import Path

import pytest
import yaml

from agent.discovery import ServiceDiscovery, CAPABILITY_FILENAME
from agent.models import ServiceStatus


class TestServiceDiscovery:
    """Tests for ServiceDiscovery class."""

    def test_scan_finds_service_with_capability(self, agent_config, service_folder):
        """Discovery should find services with CAPABILITY.yaml."""
        discovery = ServiceDiscovery(agent_config)
        services = discovery.scan()

        assert len(services) == 1
        service = services[0]
        assert service.id == "test_service"
        assert service.status == ServiceStatus.READY
        assert service.capability is not None
        assert service.capability.service_name == "Test Service"

    def test_scan_finds_service_without_capability(self, temp_dir):
        """Discovery should find services without CAPABILITY.yaml."""
        # Create a fresh temp dir just for this test
        import tempfile

        with tempfile.TemporaryDirectory() as fresh_temp:
            fresh_temp_path = Path(fresh_temp)
            service_path = fresh_temp_path / "unconfigured_service"
            service_path.mkdir()
            (service_path / "main.py").write_text("print('hello')")
            (service_path / "README.md").write_text("# Unconfigured Service")

            from agent.config import (
                AgentConfig,
                AgentSettings,
                HealthCheckSettings,
                LLMSettings,
            )

            config = AgentConfig(
                machine_id="test-machine",
                machine_name="Test Machine",
                machine_description="Test",
                service_folders=[str(fresh_temp_path)],
                always_running=[],
                agent=AgentSettings(port=9100, host="127.0.0.1"),
                health_check=HealthCheckSettings(
                    interval_seconds=30, timeout_seconds=5
                ),
                llm=LLMSettings(model="google/gemini-flash-1.5", timeout_seconds=60),
            )
            discovery = ServiceDiscovery(config)
            services = discovery.scan()

            assert len(services) == 1
            service = services[0]
            assert service.id == "unconfigured_service"
            assert service.status == ServiceStatus.DISCOVERED
            assert service.capability is None

    def test_scan_skips_hidden_folders(self, temp_dir):
        """Discovery should skip folders starting with . or _."""
        # Create a fresh temp dir just for this test
        import tempfile

        with tempfile.TemporaryDirectory() as fresh_temp:
            fresh_temp_path = Path(fresh_temp)

            # Create hidden folder
            hidden = fresh_temp_path / ".hidden_service"
            hidden.mkdir()
            (hidden / "main.py").write_text("print('hidden')")

            # Create underscore folder
            underscore = fresh_temp_path / "_private_service"
            underscore.mkdir()
            (underscore / "main.py").write_text("print('private')")

            # Create visible folder
            visible = fresh_temp_path / "visible_service"
            visible.mkdir()
            (visible / "main.py").write_text("print('visible')")

            from agent.config import (
                AgentConfig,
                AgentSettings,
                HealthCheckSettings,
                LLMSettings,
            )

            config = AgentConfig(
                machine_id="test-machine",
                machine_name="Test Machine",
                machine_description="Test",
                service_folders=[str(fresh_temp_path)],
                always_running=[],
                agent=AgentSettings(port=9100, host="127.0.0.1"),
                health_check=HealthCheckSettings(
                    interval_seconds=30, timeout_seconds=5
                ),
                llm=LLMSettings(model="google/gemini-flash-1.5", timeout_seconds=60),
            )
            discovery = ServiceDiscovery(config)
            services = discovery.scan()

            assert len(services) == 1
            assert services[0].id == "visible_service"

    def test_scan_requires_valid_service_markers(self, agent_config, temp_dir):
        """Discovery should only find folders with README.md, main.py, app.py, or CAPABILITY.yaml."""
        agent_config.service_folders = [str(temp_dir)]

        # Folder with no markers
        empty = temp_dir / "empty_folder"
        empty.mkdir()
        (empty / "random.txt").write_text("nothing")

        # Folder with README.md
        with_readme = temp_dir / "with_readme"
        with_readme.mkdir()
        (with_readme / "README.md").write_text("# Service")

        # Folder with app.py
        with_app = temp_dir / "with_app"
        with_app.mkdir()
        (with_app / "app.py").write_text("from flask import Flask")

        discovery = ServiceDiscovery(agent_config)
        services = discovery.scan()

        ids = {s.id for s in services}
        assert "empty_folder" not in ids
        assert "with_readme" in ids
        assert "with_app" in ids

    def test_sanitize_id(self, agent_config):
        """Service IDs should be sanitized to lowercase with underscores."""
        discovery = ServiceDiscovery(agent_config)

        assert discovery._sanitize_id("My Service") == "my_service"
        assert discovery._sanitize_id("service-name") == "service-name"
        assert discovery._sanitize_id("Service With  Spaces") == "service_with_spaces"
        assert discovery._sanitize_id("___leading") == "leading"
        assert discovery._sanitize_id("trailing___") == "trailing"

    def test_get_service(self, agent_config, service_folder):
        """get_service should return service by ID."""
        discovery = ServiceDiscovery(agent_config)
        discovery.scan()

        service = discovery.get_service("test_service")
        assert service is not None
        assert service.id == "test_service"

        not_found = discovery.get_service("nonexistent")
        assert not_found is None

    def test_get_all_services(self, agent_config, service_folder):
        """get_all_services should return list of all discovered services."""
        discovery = ServiceDiscovery(agent_config)
        discovery.scan()

        services = discovery.get_all_services()
        assert len(services) == 1
        assert services[0].id == "test_service"

    def test_refresh_service_reloads_capability(
        self, agent_config, service_folder, sample_capability_yaml
    ):
        """refresh_service should reload CAPABILITY.yaml from disk."""
        discovery = ServiceDiscovery(agent_config)
        discovery.scan()

        # Modify capability file
        cap_file = service_folder / CAPABILITY_FILENAME
        cap_data = yaml.safe_load(cap_file.read_text())
        cap_data["service"]["name"] = "Updated Service Name"
        cap_file.write_text(yaml.dump(cap_data))

        # Refresh
        service = discovery.refresh_service("test_service")

        assert service is not None
        assert service.capability.service_name == "Updated Service Name"

    def test_update_service_capability(self, agent_config, service_folder):
        """update_service_capability should write new CAPABILITY.yaml."""
        discovery = ServiceDiscovery(agent_config)
        discovery.scan()

        new_yaml = """schema_version: "1.0"
service:
  id: "test_service"
  name: "New Name"
runtime:
  start_command: "python app.py"
  ports:
    api:
      default: 9000
endpoints:
  api:
    health_check: "/status"
"""
        service = discovery.update_service_capability("test_service", new_yaml)

        assert service.capability.service_name == "New Name"
        assert service.capability.start_command == "python app.py"

    def test_add_service_folder(self, agent_config, temp_dir):
        """add_service_folder should add new folder and scan it."""
        discovery = ServiceDiscovery(agent_config)
        discovery.scan()

        # Create new service folder
        new_folder = temp_dir / "new_services"
        new_folder.mkdir()
        new_service = new_folder / "new_svc"
        new_service.mkdir()
        (new_service / "main.py").write_text("print('new')")

        # Add folder
        discovery.add_service_folder(str(new_folder))

        # New folder should be in config
        assert str(new_folder.resolve()) in agent_config.service_folders

    def test_add_service_folder_invalid_path(self, agent_config):
        """add_service_folder should raise ValueError for invalid paths."""
        discovery = ServiceDiscovery(agent_config)

        with pytest.raises(ValueError):
            discovery.add_service_folder("/nonexistent/path")

    def test_scan_handles_missing_folder(self, agent_config):
        """scan should gracefully handle missing service folders."""
        agent_config.service_folders = ["/nonexistent/folder"]
        discovery = ServiceDiscovery(agent_config)

        # Should not raise
        services = discovery.scan()
        assert services == []

    def test_capability_parsing(self, agent_config, service_folder):
        """Capability should be fully parsed from CAPABILITY.yaml."""
        discovery = ServiceDiscovery(agent_config)
        discovery.scan()

        service = discovery.get_service("test_service")
        cap = service.capability

        assert cap.schema_version == "1.0"
        assert cap.service_id == "test_service"
        assert cap.service_name == "Test Service"
        assert cap.description == "A test service for unit testing"
        assert cap.version == "1.0.0"
        assert cap.start_command == "python main.py"
        assert "api" in cap.ports
        assert cap.ports["api"].default == 8000
        assert cap.ports["api"].env_var == "API_PORT"
        assert cap.health_check_path == "/health"
        assert cap.api_base_path == "/api"
        assert cap.gpu_required is False
        assert "test" in cap.tags
