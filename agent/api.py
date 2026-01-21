import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

if TYPE_CHECKING:
    from agent.service_manager import ServiceManager
    from agent.discovery import ServiceDiscovery
    from agent.resource_monitor import ResourceMonitor

logger = logging.getLogger("agent.api")


class StartServiceRequest(BaseModel):
    port_assignments: Optional[dict[str, int]] = None
    env: Optional[dict[str, str]] = None


class ConfigUpdateRequest(BaseModel):
    machine_name: Optional[str] = None
    machine_description: Optional[str] = None
    always_running: Optional[list[str]] = None


def create_api_router(agent) -> APIRouter:
    router = APIRouter()

    @router.get("/discover")
    async def discover(request: Request):
        config = agent.config
        discovery = agent.discovery
        resource_monitor = agent.resource_monitor
        service_manager = agent.service_manager

        services_data = []
        for service in discovery.get_all_services():
            service_dict = service.to_dict()

            if service.capability:
                configured_ports = service_manager._get_configured_ports(service)
                api_port_config = service.capability.ports.get("api")
                ui_port_config = service.capability.ports.get("ui")

                service_dict["capability"] = {
                    "runtime": {
                        "start_command": service.capability.start_command,
                        "working_directory": service.capability.working_directory,
                        "ports": {
                            key: {
                                "default": pc.default,
                                "configured": configured_ports.get(key, pc.default),
                                "env_var": pc.env_var,
                                "cli_arg": pc.cli_arg,
                            }
                            for key, pc in service.capability.ports.items()
                        },
                    },
                    "endpoints": {
                        "api": {
                            "port": configured_ports.get(
                                "api",
                                api_port_config.default if api_port_config else 8000,
                            ),
                            "port_key": "api",
                            "health_check": service.capability.health_check_path,
                            "base_path": service.capability.api_base_path,
                            "docs": "/docs",
                        },
                        **(
                            {
                                "ui": {
                                    "port": configured_ports.get(
                                        "ui",
                                        ui_port_config.default
                                        if ui_port_config
                                        else None,
                                    ),
                                    "port_key": "ui",
                                    "path": "/",
                                }
                            }
                            if ui_port_config
                            else {}
                        ),
                    },
                    "operations": service.capability.operations,
                    "inputs": service.capability.inputs
                    if hasattr(service.capability, "inputs")
                    else [],
                    "outputs": service.capability.outputs
                    if hasattr(service.capability, "outputs")
                    else [],
                }

            services_data.append(service_dict)

        return {
            "agent": {
                "machine_id": config.machine_id,
                "machine_name": config.machine_name,
                "version": "1.0.0",
                "uptime_seconds": None,
            },
            "services": services_data,
            "resources": resource_monitor.get_all_stats(),
        }

    @router.get("/status")
    async def status(request: Request):
        config = agent.config
        discovery = agent.discovery
        resource_monitor = agent.resource_monitor

        services = discovery.get_all_services()

        return {
            "status": "healthy",
            "machine_id": config.machine_id,
            "machine_name": config.machine_name,
            "services": {
                "total": len(services),
                "running": sum(1 for s in services if s.is_running),
                "stopped": sum(
                    1 for s in services if s.status.value in ["stopped", "ready"]
                ),
                "failed": sum(1 for s in services if s.status.value == "failed"),
            },
            "resources": resource_monitor.get_all_stats(),
        }

    @router.get("/services")
    async def list_services(request: Request):
        discovery = agent.discovery

        return {"services": [s.to_dict() for s in discovery.get_all_services()]}

    @router.get("/services/{service_id}")
    async def get_service(service_id: str, request: Request):
        discovery = agent.discovery
        service_manager = agent.service_manager

        service = discovery.get_service(service_id)
        if not service:
            raise HTTPException(
                status_code=404, detail=f"Service not found: {service_id}"
            )

        result = service.to_dict()
        result["logs_tail"] = service_manager.get_service_logs(service_id, lines=20)

        return result

    @router.post("/services/{service_id}/start")
    async def start_service(
        service_id: str, body: StartServiceRequest, request: Request
    ):
        service_manager = agent.service_manager

        try:
            service = await service_manager.start_service(
                service_id, port_assignments=body.port_assignments
            )
            return {
                "success": True,
                "service_id": service_id,
                "status": service.status.value,
                "pid": service.pid,
                "assigned_ports": service.assigned_ports,
                "message": f"Service started on ports {service.assigned_ports}",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"Failed to start service {service_id}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/services/{service_id}/stop")
    async def stop_service(service_id: str, request: Request):
        service_manager = agent.service_manager

        try:
            service = await service_manager.stop_service(service_id)
            return {
                "success": True,
                "service_id": service_id,
                "status": service.status.value,
                "message": "Service stopped successfully",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"Failed to stop service {service_id}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/services/{service_id}/restart")
    async def restart_service(
        service_id: str, body: StartServiceRequest, request: Request
    ):
        service_manager = agent.service_manager

        try:
            service = await service_manager.restart_service(
                service_id, port_assignments=body.port_assignments
            )
            return {
                "success": True,
                "service_id": service_id,
                "status": service.status.value,
                "pid": service.pid,
                "assigned_ports": service.assigned_ports,
                "message": "Service restarted successfully",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"Failed to restart service {service_id}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/services/{service_id}/health")
    async def check_health(service_id: str, request: Request):
        service_manager = agent.service_manager

        result = await service_manager.check_service_health(service_id)
        result["service_id"] = service_id
        return result

    @router.get("/services/{service_id}/logs")
    async def get_logs(service_id: str, request: Request, lines: int = 100):
        service_manager = agent.service_manager
        discovery = agent.discovery

        service = discovery.get_service(service_id)
        if not service:
            raise HTTPException(
                status_code=404, detail=f"Service not found: {service_id}"
            )

        return {
            "service_id": service_id,
            "logs": service_manager.get_service_logs(service_id, lines=lines),
        }

    @router.post("/services/{service_id}/refresh-capability")
    async def refresh_capability(service_id: str, request: Request):
        from agent.capability_generator import CapabilityGenerator

        discovery = agent.discovery
        config = agent.config

        service = discovery.get_service(service_id)
        if not service:
            raise HTTPException(
                status_code=404, detail=f"Service not found: {service_id}"
            )

        try:
            generator = CapabilityGenerator(config)
            capability_yaml = await generator.generate_capability(service.path)

            updated_service = discovery.update_service_capability(
                service_id, capability_yaml
            )

            return {
                "success": True,
                "service_id": service_id,
                "message": "Capability refreshed successfully",
                "capability": updated_service.capability.raw_yaml
                if updated_service.capability
                else None,
            }
        except Exception as e:
            logger.exception(f"Failed to refresh capability for {service_id}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/resources")
    async def get_resources(request: Request):
        resource_monitor = agent.resource_monitor
        return resource_monitor.get_all_stats()

    @router.get("/config")
    async def get_config(request: Request):
        config = agent.config

        return {
            "machine_id": config.machine_id,
            "machine_name": config.machine_name,
            "machine_description": config.machine_description,
            "service_folders": config.service_folders,
            "always_running": config.always_running,
            "agent_port": config.agent.port,
        }

    @router.put("/config")
    async def update_config(body: ConfigUpdateRequest, request: Request):
        config = agent.config

        if body.machine_name is not None:
            config.machine_name = body.machine_name
        if body.machine_description is not None:
            config.machine_description = body.machine_description
        if body.always_running is not None:
            config.always_running = body.always_running

        return {
            "success": True,
            "message": "Configuration updated",
            "restart_required": False,
        }

    @router.post("/scan")
    async def scan_folders(request: Request):
        discovery = agent.discovery

        old_count = len(discovery.get_all_services())
        services = discovery.scan()
        new_count = len(services)

        return {
            "success": True,
            "services_found": new_count,
            "new_services": new_count - old_count,
        }

    @router.post("/folders/add")
    async def add_folder(folder_path: str, request: Request):
        discovery = agent.discovery

        try:
            discovery.add_service_folder(folder_path)
            services = discovery.scan()
            return {
                "success": True,
                "folder": folder_path,
                "services_found": len(services),
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/ports/conflicts")
    async def get_port_conflicts(request: Request):
        """Get services with conflicting default ports."""
        service_manager = agent.service_manager
        conflicts = service_manager.get_port_conflicts()

        return {
            "has_conflicts": len(conflicts) > 0,
            "conflicts": {str(port): services for port, services in conflicts.items()},
            "message": f"Found {len(conflicts)} port conflicts"
            if conflicts
            else "No port conflicts",
        }

    @router.get("/ports/assignments")
    async def get_port_assignments(request: Request):
        """Get recommended non-conflicting port assignments for all services."""
        service_manager = agent.service_manager
        discovery = agent.discovery

        assignments = service_manager.assign_non_conflicting_ports()

        result = []
        for service_id, ports in assignments.items():
            service = discovery.get_service(service_id)
            if not service or not service.capability:
                continue

            service_info = {"service_id": service_id, "name": service.name, "ports": {}}

            for port_key, assigned_port in ports.items():
                default_port = service.capability.ports[port_key].default
                service_info["ports"][port_key] = {
                    "default": default_port,
                    "assigned": assigned_port,
                    "changed": default_port != assigned_port,
                }

            result.append(service_info)

        return {"assignments": result, "total_services": len(result)}

    @router.post("/services/{service_id}/start-auto")
    async def start_service_auto_ports(service_id: str, request: Request):
        """Start a service with automatic port assignment to avoid conflicts."""
        service_manager = agent.service_manager

        try:
            service = await service_manager.start_service_auto_ports(service_id)
            return {
                "success": True,
                "service_id": service_id,
                "status": service.status.value,
                "pid": service.pid,
                "assigned_ports": service.assigned_ports,
                "message": f"Service started with auto-assigned ports: {service.assigned_ports}",
            }
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.exception(f"Failed to start service {service_id} with auto ports")
            raise HTTPException(status_code=500, detail=str(e))

    @router.put("/ports/ranges")
    async def update_port_ranges(request: Request):
        """Update port range configuration."""
        config = agent.config
        body = await request.json()

        if "api_port_min" in body:
            config.port_ranges.api_port_min = body["api_port_min"]
        if "api_port_max" in body:
            config.port_ranges.api_port_max = body["api_port_max"]
        if "ui_port_min" in body:
            config.port_ranges.ui_port_min = body["ui_port_min"]
        if "ui_port_max" in body:
            config.port_ranges.ui_port_max = body["ui_port_max"]

        config.save_config()

        return {
            "success": True,
            "port_ranges": {
                "api_port_min": config.port_ranges.api_port_min,
                "api_port_max": config.port_ranges.api_port_max,
                "ui_port_min": config.port_ranges.ui_port_min,
                "ui_port_max": config.port_ranges.ui_port_max,
            },
        }

    @router.post("/ports/resolve")
    async def resolve_port_conflicts(request: Request):
        """Permanently resolve port conflicts by updating service .env files."""
        port_configurator = agent.port_configurator
        service_manager = agent.service_manager

        conflicts_before = service_manager.get_port_conflicts()
        if not conflicts_before:
            return {
                "success": True,
                "message": "No port conflicts to resolve",
                "changes": [],
            }

        try:
            results = port_configurator.resolve_all_conflicts()

            changes = []
            for service_id, result in results.items():
                if result.get("updated"):
                    changes.append(
                        {
                            "service_id": service_id,
                            "env_file": result["env_file"],
                            "port_changes": result["changes"],
                        }
                    )

            return {
                "success": True,
                "message": f"Resolved port conflicts for {len(changes)} service(s)",
                "conflicts_before": {
                    str(port): services for port, services in conflicts_before.items()
                },
                "changes": changes,
            }
        except Exception as e:
            logger.exception("Failed to resolve port conflicts")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/services/{service_id}/ports")
    async def get_service_ports(service_id: str, request: Request):
        """Get current port configuration for a service from its .env file."""
        port_configurator = agent.port_configurator

        port_config = port_configurator.get_current_port_config(service_id)
        if not port_config:
            raise HTTPException(
                status_code=404, detail=f"Service not found: {service_id}"
            )

        return {
            "service_id": service_id,
            "ports": port_config,
        }

    @router.post("/ports/sync-readmes")
    async def sync_readmes(request: Request):
        """Sync README port references with current .env configurations."""
        port_configurator = agent.port_configurator

        try:
            results = port_configurator.sync_all_readmes()

            synced_count = sum(1 for r in results.values() if r.get("synced"))
            total_changes = sum(r.get("changes", 0) for r in results.values())

            return {
                "success": True,
                "message": f"Synced {synced_count} README files with {total_changes} port changes",
                "services_synced": synced_count,
                "total_changes": total_changes,
                "details": results,
            }
        except Exception as e:
            logger.exception("Failed to sync READMEs")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/services/{service_id}/sync-readme")
    async def sync_service_readme(service_id: str, request: Request):
        """Sync a single service's README with its .env port configuration."""
        port_configurator = agent.port_configurator

        try:
            result = port_configurator.sync_readme_with_env(service_id)

            if result.get("error"):
                raise HTTPException(status_code=404, detail=result["error"])

            return {
                "success": True,
                "service_id": service_id,
                "synced": result.get("synced", False),
                "changes": result.get("changes", 0),
                "port_changes": result.get("port_changes", []),
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"Failed to sync README for {service_id}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/machine/info")
    async def get_machine_info(request: Request):
        """Get machine identification info and platform port ranges."""
        from agent.config import MACHINE_INFO, MACHINE_PORT_RANGES, CURRENT_PLATFORM

        config = agent.config

        return {
            "machine": MACHINE_INFO,
            "platform": CURRENT_PLATFORM,
            "port_ranges": {
                "current": {
                    "api_port_min": config.port_ranges.api_port_min,
                    "api_port_max": config.port_ranges.api_port_max,
                    "ui_port_min": config.port_ranges.ui_port_min,
                    "ui_port_max": config.port_ranges.ui_port_max,
                },
                "all_platforms": MACHINE_PORT_RANGES,
            },
        }

    @router.post("/machine/generate-config")
    async def generate_machine_config_endpoint(request: Request):
        """Generate a machine-specific config file for this machine."""
        from agent.config import generate_machine_config, MACHINE_SHORT_ID

        try:
            output_path = generate_machine_config()

            return {
                "success": True,
                "message": f"Generated machine config: {output_path}",
                "machine_id": MACHINE_SHORT_ID,
                "config_path": str(output_path),
            }
        except Exception as e:
            logger.exception("Failed to generate machine config")
            raise HTTPException(status_code=500, detail=str(e))

    return router
