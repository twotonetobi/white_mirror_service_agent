#!/usr/bin/env python3
import argparse
import asyncio
import logging
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import gradio as gr
import uvicorn
from fastapi import FastAPI

from agent.config import load_config, AgentConfig, CURRENT_PLATFORM
from agent.api import create_api_router
from agent.ui import create_gradio_ui
from agent.service_manager import ServiceManager
from agent.discovery import ServiceDiscovery
from agent.resource_monitor import ResourceMonitor
from agent.port_configurator import PortConfigurator


def parse_args():
    parser = argparse.ArgumentParser(description="White Mirror Service Agent")
    parser.add_argument(
        "--sync-readmes",
        action="store_true",
        help="Sync README port references with current .env configurations and exit",
    )
    parser.add_argument(
        "--resolve-conflicts",
        action="store_true",
        help="Resolve port conflicts (updates .env AND README files) and exit",
    )
    parser.add_argument(
        "--generate-machine-config",
        action="store_true",
        help="Generate a machine-specific config file for this machine and exit",
    )
    parser.add_argument(
        "--show-machine-info",
        action="store_true",
        help="Show machine identification info and exit",
    )
    return parser.parse_args()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agent")


class ServiceAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.discovery = ServiceDiscovery(config)
        self.resource_monitor = ResourceMonitor(config)
        self.service_manager = ServiceManager(
            config, self.discovery, self.resource_monitor
        )
        self.port_configurator = PortConfigurator(
            self.discovery,
            {
                "api_port_min": config.port_ranges.api_port_min,
                "api_port_max": config.port_ranges.api_port_max,
                "ui_port_min": config.port_ranges.ui_port_min,
                "ui_port_max": config.port_ranges.ui_port_max,
            },
        )

    async def startup(self):
        logger.info(f"Starting White Mirror Service Agent v1.0.0")
        logger.info(f"Machine ID: {self.config.machine_id}")

        for service_id in self.config.always_running:
            service = self.discovery.get_service(service_id)
            if service and service.has_capability:
                logger.info(f"Auto-starting {service_id}...")
                try:
                    await self.service_manager.start_service(service_id)
                except Exception as e:
                    logger.error(f"Failed to auto-start {service_id}: {e}")
            elif service and not service.has_capability:
                logger.warning(f"Cannot auto-start {service_id}: no CAPABILITY.yaml")

    async def shutdown(self):
        logger.info("Shutting down Service Agent...")
        await self.service_manager.stop_all_services()
        logger.info("Service Agent stopped")


def create_app(config: AgentConfig) -> FastAPI:
    agent = ServiceAgent(config)

    logger.info("Scanning service folders...")
    services = agent.discovery.scan()
    logger.info(f"Found {len(services)} services")
    for service in services:
        logger.info(f"  - {service.id}: {service.status.value}")

    if config.port_ranges.auto_resolve_conflicts:
        conflicts = agent.service_manager.get_port_conflicts()
        if conflicts:
            logger.info(f"Found {len(conflicts)} port conflicts, auto-resolving...")
            results = agent.port_configurator.resolve_all_conflicts()
            for service_id, result in results.items():
                if result.get("updated"):
                    logger.info(f"  Resolved ports for {service_id}:")
                    for change in result.get("changes", []):
                        logger.info(
                            f"    {change['port_key']}: {change['old_port']} -> {change['new_port']}"
                        )
                    if (
                        result.get("readme_updated")
                        and config.port_ranges.sync_readme_on_resolve
                    ):
                        logger.info(
                            f"    README: {result['readme_changes']} references updated"
                        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await agent.startup()
        yield
        await agent.shutdown()

    app = FastAPI(
        title="White Mirror Service Agent",
        description="Lightweight daemon for managing White Mirror generation services",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.state.agent = agent
    app.state.config = config

    api_router = create_api_router(agent)
    app.include_router(api_router)

    if config.ui.enabled:
        gradio_app = create_gradio_ui(agent)
        app = gr.mount_gradio_app(app, gradio_app, path="/ui")

    return app


def open_browser_delayed(url: str, delay: float = 2.0):
    def _open():
        import time

        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()


def run_sync_readmes(config: AgentConfig) -> int:
    discovery = ServiceDiscovery(config)
    discovery.scan()

    port_configurator = PortConfigurator(
        discovery,
        {
            "api_port_min": config.port_ranges.api_port_min,
            "api_port_max": config.port_ranges.api_port_max,
            "ui_port_min": config.port_ranges.ui_port_min,
            "ui_port_max": config.port_ranges.ui_port_max,
        },
    )

    logger.info("Syncing README files with .env port configurations...")
    results = port_configurator.sync_all_readmes()

    total_synced = 0
    for service_id, result in results.items():
        if result.get("synced"):
            total_synced += 1
            logger.info(f"  {service_id}: Updated {result['changes']} port references")
            for change in result.get("port_changes", []):
                logger.info(
                    f"    - {change['port_key']}: {change['old_port']} -> {change['new_port']}"
                )
        else:
            logger.info(f"  {service_id}: No changes needed")

    logger.info(f"Sync complete. Updated {total_synced} README files.")
    return 0


def run_resolve_conflicts(config: AgentConfig) -> int:
    discovery = ServiceDiscovery(config)
    discovery.scan()

    port_configurator = PortConfigurator(
        discovery,
        {
            "api_port_min": config.port_ranges.api_port_min,
            "api_port_max": config.port_ranges.api_port_max,
            "ui_port_min": config.port_ranges.ui_port_min,
            "ui_port_max": config.port_ranges.ui_port_max,
        },
    )

    logger.info("Resolving port conflicts...")
    results = port_configurator.resolve_all_conflicts()

    total_updated = 0
    for service_id, result in results.items():
        if result.get("updated"):
            total_updated += 1
            logger.info(f"  {service_id}:")
            for change in result.get("changes", []):
                logger.info(
                    f"    - {change['port_key']}: {change['old_port']} -> {change['new_port']}"
                )
            if result.get("readme_updated"):
                logger.info(
                    f"    - README: {result['readme_changes']} references updated"
                )

    logger.info(f"Conflict resolution complete. Updated {total_updated} services.")
    return 0


def main():
    args = parse_args()
    config = load_config()

    log_level = config.agent.log_level.upper()
    logging.getLogger().setLevel(getattr(logging, log_level, logging.INFO))

    if config.agent.log_file:
        file_handler = logging.FileHandler(config.agent.log_file)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(file_handler)

    if args.show_machine_info:
        from agent.config import MACHINE_INFO, MACHINE_PORT_RANGES
        import json

        print("=== Machine Identification ===")
        print(json.dumps(MACHINE_INFO, indent=2))
        print("\n=== Platform Port Ranges ===")
        print(json.dumps(MACHINE_PORT_RANGES, indent=2))
        sys.exit(0)

    if args.generate_machine_config:
        from agent.config import generate_machine_config, MACHINE_SHORT_ID

        output_path = generate_machine_config()
        logger.info(f"Generated machine config: {output_path}")
        logger.info(f"Machine ID: {MACHINE_SHORT_ID}")
        sys.exit(0)

    if args.sync_readmes:
        sys.exit(run_sync_readmes(config))

    if args.resolve_conflicts:
        sys.exit(run_resolve_conflicts(config))

    app = create_app(config)

    logger.info(f"Platform: {CURRENT_PLATFORM}")
    logger.info(f"Starting server on {config.agent.host}:{config.agent.port}")

    ui_url = f"http://localhost:{config.agent.port}/ui"
    if config.ui.enabled:
        logger.info(f"Gradio UI available at {ui_url}")

        if config.ui.open_browser:
            open_browser_delayed(ui_url, delay=2.5)

    uvicorn.run(
        app,
        host=config.agent.host,
        port=config.agent.port,
        log_level=log_level.lower(),
    )


if __name__ == "__main__":
    main()
