import logging
import re
from pathlib import Path
from typing import Any, Optional

from agent.discovery import ServiceDiscovery
from agent.service_manager import is_port_in_use

logger = logging.getLogger("agent.port_configurator")


# Common patterns where ports appear in README files
# These patterns help identify port references in documentation
README_PORT_PATTERNS = [
    # URLs with ports: http://localhost:8200, http://127.0.0.1:7880
    (r"(https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0):)(\d+)", r"\g<1>{new_port}"),
    # Port references in tables: | 8200 | or | `8200` |
    (r"(\|\s*`?)(\d+)(`?\s*\|)", r"\g<1>{new_port}\g<3>"),
    # Port in code blocks/env vars: =8200 or = 8200
    (r"(=\s*)(\d+)(\s*(?:#|$|\n))", r"\g<1>{new_port}\g<3>"),
    # Port flags: --port 8200, --api-port 8200, -p 8200
    (r"(--?(?:api-?|ui-?|gradio-?)?port\s+)(\d+)", r"\g<1>{new_port}"),
    # Colon port references: :8200 (but not in time formats like 10:00)
    (r"(:)(\d{4,5})(?=[\s,\)\]\/\n]|$)", r"\g<1>{new_port}"),
]


class PortConfigurator:
    def __init__(self, discovery: ServiceDiscovery, port_ranges: dict):
        self.discovery = discovery
        self.port_ranges = port_ranges

    def get_env_file_path(self, service_path: Path) -> Path:
        return service_path / ".env"

    def read_env_file(self, env_path: Path) -> dict[str, str]:
        if not env_path.exists():
            example_path = env_path.parent / ".env.example"
            if example_path.exists():
                return self._parse_env_file(example_path)
            return {}
        return self._parse_env_file(env_path)

    def _parse_env_file(self, path: Path) -> dict[str, str]:
        env_vars = {}
        content = path.read_text(encoding='utf-8')
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                env_vars[key] = value
        return env_vars

    def write_env_file(self, env_path: Path, updates: dict[str, int]) -> None:
        if env_path.exists():
            content = env_path.read_text(encoding='utf-8')
            lines = content.splitlines()
        else:
            example_path = env_path.parent / ".env.example"
            if example_path.exists():
                content = example_path.read_text(encoding='utf-8')
                lines = content.splitlines()
            else:
                lines = []

        updated_keys = set()
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue

            key = stripped.split("=")[0].strip()
            if key in updates:
                comment_match = re.match(r"^(\s*#?\s*)", line)
                prefix = comment_match.group(1) if comment_match else ""
                prefix = prefix.lstrip("#").lstrip()
                new_lines.append(f"{key}={updates[key]}")
                updated_keys.add(key)
                logger.info(f"Updated {key}={updates[key]} in {env_path}")
            else:
                new_lines.append(line)

        for key, value in updates.items():
            if key not in updated_keys:
                new_lines.append(f"\n# Port configured by ServiceAgent")
                new_lines.append(f"{key}={value}")
                logger.info(f"Added {key}={value} to {env_path}")

        env_path.write_text("\n".join(new_lines) + "\n", encoding='utf-8')

    def update_readme_ports(
        self, service_path: Path, port_changes: list[dict]
    ) -> dict[str, Any]:
        readme_path = service_path / "README.md"
        if not readme_path.exists():
            logger.debug(f"No README.md found at {readme_path}")
            return {"updated": False, "changes_made": 0, "readme_path": None}

        content = readme_path.read_text(encoding='utf-8')
        original_content = content
        total_changes = 0

        for change in port_changes:
            old_port = change["old_port"]
            new_port = change["new_port"]

            if old_port == new_port:
                continue

            changes_for_port = self._replace_port_in_readme(content, old_port, new_port)
            if changes_for_port["count"] > 0:
                content = changes_for_port["content"]
                total_changes += changes_for_port["count"]
                logger.info(
                    f"README: Replaced {changes_for_port['count']} occurrences of "
                    f"port {old_port} -> {new_port} in {readme_path.name}"
                )

        if content != original_content:
            readme_path.write_text(content, encoding='utf-8')
            logger.info(f"Updated README.md with {total_changes} port changes")
            return {
                "updated": True,
                "changes_made": total_changes,
                "readme_path": str(readme_path),
            }

        return {"updated": False, "changes_made": 0, "readme_path": str(readme_path)}

    def _replace_port_in_readme(
        self, content: str, old_port: int, new_port: int
    ) -> dict[str, Any]:
        count = 0
        old_port_str = str(old_port)
        new_port_str = str(new_port)

        for pattern, replacement_template in README_PORT_PATTERNS:
            replacement = replacement_template.format(new_port=new_port_str)

            def replace_if_match(match):
                nonlocal count
                full_match = match.group(0)
                port_in_match = None
                for g in match.groups():
                    if g and g.isdigit() and len(g) >= 4:
                        port_in_match = g
                        break

                if port_in_match == old_port_str:
                    count += 1
                    return re.sub(r"\d{4,5}", new_port_str, full_match, count=1)
                return full_match

            content = re.sub(pattern, replace_if_match, content)

        return {"content": content, "count": count}

    def get_next_available_port(self, port_type: str, used_ports: set[int]) -> int:
        if port_type == "api":
            port_min = self.port_ranges.get("api_port_min", 8100)
            port_max = self.port_ranges.get("api_port_max", 8299)
        elif port_type == "ui":
            port_min = self.port_ranges.get("ui_port_min", 7800)
            port_max = self.port_ranges.get("ui_port_max", 7999)
        else:
            port_min, port_max = 8000, 9000

        for port in range(port_min, port_max + 1):
            if port not in used_ports and not is_port_in_use(port):
                return port

        raise RuntimeError(
            f"No available {port_type} ports in range {port_min}-{port_max}"
        )

    def resolve_all_conflicts(self) -> dict[str, dict]:
        services = self.discovery.get_all_services()
        used_ports: set[int] = set()
        results = {}

        for service in services:
            if not service.capability:
                continue

            service_result = {
                "service_id": service.id,
                "path": str(service.path),
                "changes": [],
                "env_file": str(self.get_env_file_path(service.path)),
            }

            env_updates = {}

            for port_key, port_config in service.capability.ports.items():
                default_port = port_config.default
                env_var = port_config.env_var

                if not env_var:
                    continue

                if default_port not in used_ports:
                    used_ports.add(default_port)
                    continue

                new_port = self.get_next_available_port(port_key, used_ports)
                used_ports.add(new_port)

                env_updates[env_var] = new_port
                service_result["changes"].append(
                    {
                        "port_key": port_key,
                        "env_var": env_var,
                        "old_port": default_port,
                        "new_port": new_port,
                    }
                )

                logger.info(
                    f"Resolved conflict for {service.id}:{port_key}: "
                    f"{default_port} -> {new_port} (via {env_var})"
                )

            if env_updates:
                env_path = self.get_env_file_path(service.path)
                self.write_env_file(env_path, env_updates)
                service_result["updated"] = True

                readme_result = self.update_readme_ports(
                    service.path, service_result["changes"]
                )
                service_result["readme_updated"] = readme_result["updated"]
                service_result["readme_changes"] = readme_result["changes_made"]
            else:
                service_result["updated"] = False
                service_result["readme_updated"] = False
                service_result["readme_changes"] = 0

            results[service.id] = service_result

        return results

    def get_current_port_config(self, service_id: str) -> Optional[dict]:
        service = self.discovery.get_service(service_id)
        if not service or not service.capability:
            return None

        env_path = self.get_env_file_path(service.path)
        env_vars = self.read_env_file(env_path)

        port_config = {}
        for port_key, port_conf in service.capability.ports.items():
            env_var = port_conf.env_var
            default_port = port_conf.default

            if env_var and env_var in env_vars:
                try:
                    current_port = int(env_vars[env_var])
                except ValueError:
                    current_port = default_port
            else:
                current_port = default_port

            port_config[port_key] = {
                "env_var": env_var,
                "default": default_port,
                "configured": current_port,
                "is_default": current_port == default_port,
            }

        return port_config

    def sync_readme_with_env(self, service_id: str) -> dict[str, Any]:
        service = self.discovery.get_service(service_id)
        if not service or not service.capability:
            return {"synced": False, "error": "Service not found or no capability"}

        env_path = self.get_env_file_path(service.path)
        env_vars = self.read_env_file(env_path)

        port_changes = []
        for port_key, port_conf in service.capability.ports.items():
            env_var = port_conf.env_var
            default_port = port_conf.default

            if env_var and env_var in env_vars:
                try:
                    configured_port = int(env_vars[env_var])
                    if configured_port != default_port:
                        port_changes.append(
                            {
                                "old_port": default_port,
                                "new_port": configured_port,
                                "port_key": port_key,
                                "env_var": env_var,
                            }
                        )
                except ValueError:
                    pass

        if not port_changes:
            return {"synced": False, "changes": 0, "message": "No port overrides found"}

        readme_result = self.update_readme_ports(service.path, port_changes)
        return {
            "synced": readme_result["updated"],
            "changes": readme_result["changes_made"],
            "port_changes": port_changes,
            "readme_path": readme_result["readme_path"],
        }

    def sync_all_readmes(self) -> dict[str, dict]:
        services = self.discovery.get_all_services()
        results = {}

        for service in services:
            if not service.capability:
                continue
            results[service.id] = self.sync_readme_with_env(service.id)

        return results

    def get_configured_port_conflicts(self) -> dict[int, list[str]]:
        conflicts: dict[int, list[str]] = {}
        services = self.discovery.get_all_services()

        for service in services:
            if not service.capability:
                continue

            env_path = self.get_env_file_path(service.path)
            env_vars = self.read_env_file(env_path)

            for port_key, port_conf in service.capability.ports.items():
                env_var = port_conf.env_var
                default_port = port_conf.default

                if env_var and env_var in env_vars:
                    try:
                        port = int(env_vars[env_var])
                    except ValueError:
                        port = default_port
                else:
                    port = default_port

                if port not in conflicts:
                    conflicts[port] = []
                conflicts[port].append(f"{service.id}:{port_key}")

        return {
            port: svc_list for port, svc_list in conflicts.items() if len(svc_list) > 1
        }
