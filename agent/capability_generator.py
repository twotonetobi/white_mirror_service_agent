import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import litellm

from agent.config import AgentConfig

logger = logging.getLogger("agent.capability_generator")

PRIORITY_FILES = [
    "main.py",
    "app.py",
    "server.py",
    "run.py",
    "README.md",
    "PLAN.md",
    "knowledge.md",
    "docs/README.md",
    "config.yaml",
    "config.json",
    "settings.yaml",
    "config/config.yaml",
    "config/settings.yaml",
    "src/api/routes.py",
    "src/api/endpoints.py",
    "src/api/__init__.py",
    "api/routes.py",
    "routes.py",
    "endpoints.py",
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    ".env.example",
    ".env.template",
    "env.example",
    "Dockerfile",
    "docker-compose.yaml",
    "docker-compose.yml",
]

SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    "eggs",
    ".tox",
}

MAX_FILE_CHARS = 15000
MAX_TOTAL_CHARS = 120000

CAPABILITY_PROMPT = """You are analyzing a software service folder to generate a structured capability manifest.

## Service Location
Folder: {service_path}
Service ID: {service_id}

## Directory Structure
{directory_tree}

## File Contents

{file_contents}

## Your Task

Analyze ALL the provided files to understand:
1. What this service does (purpose, capabilities)
2. How to start it (command, virtual environment)
3. What ports it uses (REST API, Gradio UI, etc.)
4. What API endpoints are available
5. What input/output types it handles
6. What environment variables it needs

IMPORTANT: 
- The service supports FLEXIBLE PORTS via environment variables or CLI arguments
- Identify the environment variable names for port configuration (e.g., API_PORT, GRADIO_PORT)
- Default ports are just defaults - actual ports will be assigned dynamically

Generate a CAPABILITY.yaml file following this exact schema:

```yaml
schema_version: "1.0"
generated_at: "{timestamp}"
generated_by: "service-agent/1.0.0"

service:
  id: "{service_id}"
  name: "<human readable name from docs>"
  description: "<one line description>"
  version: "<version if found, else '1.0.0'>"

runtime:
  start_command: "<command to start, e.g., 'python main.py'>"
  working_directory: "."
  
  ports:
    api:
      default: <default port number>
      env_var: "<ENV_VAR_NAME for port>"
      cli_arg: "<cli argument>"
      description: "REST API server port"
  
  environment:
    - name: "<ENV_VAR_NAME>"
      default: "<default value>"
      description: "<what it does>"
  
  venv:
    path: "venv"
    python: "python"
    requirements: "requirements.txt"

endpoints:
  api:
    port_key: "api"
    base_path: "<base path like /api>"
    health_check: "<health endpoint path>"
    docs: "<docs endpoint if exists>"

capabilities:
  inputs:
    - type: "<input type: text, image, audio, video, 3d_model>"
      description: "<description>"
      formats: ["<file formats if applicable>"]
  
  outputs:
    - type: "<output type>"
      description: "<description>"
      formats: ["<file formats>"]
  
  operations:
    - id: "<operation id>"
      name: "<human readable name>"
      description: "<what it does>"
      endpoint: "<full endpoint path>"
      method: "<HTTP method>"
      inputs: ["<input types>"]
      outputs: ["<output types>"]
      estimated_time_seconds: <estimate>

resources:
  min_vram_gb: <number or null if no GPU needed>
  min_ram_gb: <estimate>
  gpu_required: <true/false>

tags:
  - "<relevant tags>"
```

Important guidelines:
- Extract ACTUAL port numbers and their configuration methods from the code
- Identify ALL REST API endpoints by analyzing route definitions
- List ALL operations/triggers the service supports
- Be accurate about input/output types based on actual code
- If the service has a Gradio UI, include it in endpoints
- Include ALL environment variables that affect behavior
- If you cannot determine something, use sensible defaults

Output ONLY the YAML content, no explanations or markdown code blocks.
"""


class CapabilityGenerator:
    def __init__(self, config: AgentConfig):
        self.config = config

    async def generate_capability(self, service_path: Path) -> str:
        service_id = service_path.name.lower().replace(" ", "_").replace("-", "_")

        dir_tree = self._build_directory_tree(service_path)
        file_contents = self._gather_file_contents(service_path)
        timestamp = datetime.now(timezone.utc).isoformat()

        prompt = CAPABILITY_PROMPT.format(
            service_path=str(service_path),
            service_id=service_id,
            directory_tree=dir_tree,
            file_contents=file_contents,
            timestamp=timestamp,
        )

        api_key = self.config.get_llm_api_key()
        if not api_key:
            raise ValueError(
                "No LLM API key configured. Set OPENROUTER_API_KEY environment variable."
            )

        logger.info(
            f"Generating capability for {service_id} using {self.config.llm.model}"
        )

        response = await litellm.acompletion(
            model=f"openrouter/{self.config.llm.model}",
            api_key=api_key,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=16000,
            temperature=0.1,
            timeout=self.config.llm.timeout_seconds,
        )

        yaml_content = response.choices[0].message.content
        yaml_content = self._clean_yaml(yaml_content)

        self._validate_yaml(yaml_content)

        logger.info(f"Successfully generated capability for {service_id}")
        return yaml_content

    def _build_directory_tree(
        self, path: Path, prefix: str = "", max_depth: int = 3
    ) -> str:
        lines = []

        try:
            entries = sorted(path.iterdir(), key=lambda e: (not e.is_dir(), e.name))
        except PermissionError:
            return f"{prefix}[Permission Denied]\n"

        for entry in entries:
            if entry.name.startswith(".") and entry.name not in [
                ".env.example",
                ".env.template",
            ]:
                continue
            if entry.is_dir() and entry.name in SKIP_DIRS:
                continue

            if entry.is_dir():
                lines.append(f"{prefix}{entry.name}/")
                if max_depth > 0:
                    subtree = self._build_directory_tree(
                        entry, prefix + "  ", max_depth - 1
                    )
                    if subtree:
                        lines.append(subtree)
            else:
                try:
                    size = entry.stat().st_size
                    lines.append(f"{prefix}{entry.name} ({size} bytes)")
                except OSError:
                    lines.append(f"{prefix}{entry.name}")

        return "\n".join(lines)

    def _gather_file_contents(self, service_path: Path) -> str:
        contents = []
        total_chars = 0
        seen_files = set()

        for filename in PRIORITY_FILES:
            file_path = service_path / filename
            if file_path.exists() and file_path.is_file():
                content = self._read_file_safe(file_path)
                if content:
                    seen_files.add(str(file_path))
                    chunk = self._format_file_content(filename, content)

                    if total_chars + len(chunk) > MAX_TOTAL_CHARS:
                        break

                    contents.append(chunk)
                    total_chars += len(chunk)

        if total_chars < MAX_TOTAL_CHARS:
            src_path = service_path / "src"
            if src_path.exists():
                for py_file in src_path.rglob("*.py"):
                    if str(py_file) in seen_files:
                        continue

                    content = self._read_file_safe(py_file)
                    if content and len(content) > 100:
                        rel_path = py_file.relative_to(service_path)
                        chunk = self._format_file_content(
                            str(rel_path), content, "python"
                        )

                        if total_chars + len(chunk) > MAX_TOTAL_CHARS:
                            break

                        contents.append(chunk)
                        total_chars += len(chunk)

        return "".join(contents)

    def _format_file_content(self, filename: str, content: str, lang: str = "") -> str:
        truncated = content[:MAX_FILE_CHARS]
        if len(content) > MAX_FILE_CHARS:
            truncated += "\n... [truncated]"
        return f"\n### FILE: {filename}\n```{lang}\n{truncated}\n```\n"

    def _read_file_safe(self, path: Path) -> Optional[str]:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="latin-1")
            except Exception:
                return None
        except Exception:
            return None

    def _clean_yaml(self, content: str) -> str:
        content = content.strip()
        if content.startswith("```yaml"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def _validate_yaml(self, content: str):
        import yaml

        data = yaml.safe_load(content)

        required = ["schema_version", "service", "runtime", "endpoints"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        if "ports" not in data.get("runtime", {}):
            logger.warning(
                "Generated CAPABILITY.yaml missing runtime.ports - adding defaults"
            )
