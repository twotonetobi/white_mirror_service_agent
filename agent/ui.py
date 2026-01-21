import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import gradio as gr
import yaml

from agent.config import MACHINE_INFO, MACHINE_PORT_RANGES, generate_machine_config

if TYPE_CHECKING:
    pass

logger = logging.getLogger("agent.ui")


def create_gradio_ui(agent) -> gr.Blocks:
    def get_services_list():
        services = agent.discovery.get_all_services()
        return [s.id for s in services]

    def get_services_status_html():
        services = agent.discovery.get_all_services()
        items = []
        for s in services:
            short_name = s.id.replace("11_", "").replace("_", " ").title()[:15]
            if s.is_running:
                color = "#22c55e"
                icon = "●"
                ui_port = s.assigned_ports.get("ui")
                if ui_port:
                    ui_url = f"http://localhost:{ui_port}"
                    items.append(
                        f'<a href="{ui_url}" target="_blank" style="color:{color}; margin-right:12px; font-size:13px; text-decoration:none;">{icon} {short_name}</a>'
                    )
                else:
                    items.append(
                        f'<span style="color:{color}; margin-right:12px; font-size:13px;">{icon} {short_name}</span>'
                    )
            elif s.status.value == "failed":
                color = "#ef4444"
                icon = "●"
                items.append(
                    f'<span style="color:{color}; margin-right:12px; font-size:13px;">{icon} {short_name}</span>'
                )
            else:
                color = "#6b7280"
                icon = "○"
                items.append(
                    f'<span style="color:{color}; margin-right:12px; font-size:13px;">{icon} {short_name}</span>'
                )
        return "".join(items)

    def get_service_info(service_id: str):
        if not service_id:
            return "Select a service to view details", "", "ready"

        service = agent.discovery.get_service(service_id)
        if not service:
            return f"Service not found: {service_id}", "", "ready"

        status_emoji = {
            "running": "🟢",
            "stopped": "⚪",
            "ready": "🔵",
            "discovered": "⚠️",
            "failed": "🔴",
            "starting": "🟡",
        }.get(service.status.value, "❓")

        info = f"""### {status_emoji} {service.name}

**ID:** `{service.id}`
**Status:** {service.status.value}
**Path:** `{service.path}`
**Has Capability:** {"Yes" if service.has_capability else "No"}
"""

        if service.capability and service.capability.ports:
            configured_ports = agent.service_manager._get_configured_ports(service)
            info += "\n#### 🔗 Endpoints\n"

            if "ui" in configured_ports:
                ui_port = (
                    service.assigned_ports.get("ui")
                    if service.is_running
                    else configured_ports["ui"]
                )
                ui_url = f"http://localhost:{ui_port}"
                link_style = "" if service.is_running else " (not running)"
                info += f'**Gradio UI:** <a href="{ui_url}" target="_blank">{ui_url}</a>{link_style}\n\n'

            if "api" in configured_ports:
                api_port = (
                    service.assigned_ports.get("api")
                    if service.is_running
                    else configured_ports["api"]
                )
                api_url = f"http://localhost:{api_port}"
                docs_url = f"{api_url}/docs"
                link_style = "" if service.is_running else " (not running)"
                info += f'**REST API:** <a href="{api_url}" target="_blank">{api_url}</a>{link_style}\n\n'
                info += f'**API Docs:** <a href="{docs_url}" target="_blank">{docs_url}</a>{link_style}\n\n'

        if service.is_running:
            info += f"""
#### ⚡ Runtime
**PID:** {service.pid}
**Uptime:** {service.uptime_seconds:.0f}s
"""
        if service.error:
            info += f"\n**Error:** {service.error}"

        cap_yaml = ""
        if service.capability and service.capability.raw_yaml:
            cap_yaml = yaml.dump(
                service.capability.raw_yaml, default_flow_style=False, sort_keys=False
            )

        return info, cap_yaml, service.status.value

    def get_folders_list():
        return [[f] for f in agent.config.service_folders]

    def add_folder(folder_path: str):
        if not folder_path or not folder_path.strip():
            return get_folders_list(), "⚠️ Please enter a folder path"

        folder_path = folder_path.strip()
        path = Path(folder_path).expanduser().resolve()

        if not path.exists():
            return get_folders_list(), f"❌ Folder does not exist: {path}"

        if not path.is_dir():
            return get_folders_list(), f"❌ Not a directory: {path}"

        str_path = str(path)
        if str_path in agent.config.service_folders:
            return get_folders_list(), f"⚠️ Folder already added: {path}"

        agent.config.service_folders.append(str_path)
        agent.config.save_config()
        agent.discovery.scan()

        return get_folders_list(), f"✅ Added: {path}"

    def remove_folder(folder_data):
        if not folder_data or len(folder_data) == 0:
            return get_folders_list(), "⚠️ Select a folder to remove"

        try:
            if isinstance(folder_data, list) and len(folder_data) > 0:
                if isinstance(folder_data[0], list):
                    folder_path = folder_data[0][0]
                else:
                    folder_path = folder_data[0]
            else:
                return get_folders_list(), "⚠️ Invalid selection"

            if folder_path in agent.config.service_folders:
                agent.config.service_folders.remove(folder_path)
                agent.config.save_config()
                agent.discovery.scan()
                return get_folders_list(), f"✅ Removed: {folder_path}"
            else:
                return get_folders_list(), f"⚠️ Folder not in list: {folder_path}"
        except Exception as e:
            return get_folders_list(), f"❌ Error: {e}"

    def scan_all_folders():
        services = agent.discovery.scan()
        return gr.update(
            choices=get_services_list()
        ), f"✅ Found {len(services)} services"

    async def start_service(service_id: str):
        if not service_id:
            return (
                "⚠️ Select a service first",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )
        try:
            await agent.service_manager.start_service(service_id)
            return (
                f"✅ Started {service_id}",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )
        except Exception as e:
            return (
                f"❌ Error: {e}",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )

    async def start_service_auto(service_id: str):
        if not service_id:
            return (
                "⚠️ Select a service first",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )
        try:
            service = await agent.service_manager.start_service_auto_ports(service_id)
            ports_str = ", ".join(f"{k}={v}" for k, v in service.assigned_ports.items())
            return (
                f"✅ Started {service_id} on ports: {ports_str}",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )
        except Exception as e:
            return (
                f"❌ Error: {e}",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )

    def get_port_conflicts_info():
        conflicts = agent.port_configurator.get_configured_port_conflicts()
        if not conflicts:
            return "✅ No port conflicts detected"

        lines = ["⚠️ **Port Conflicts Detected:**"]
        for port, services in conflicts.items():
            lines.append(f"- Port **{port}**: {', '.join(services)}")
        lines.append("\n*Click 'Fix Port Conflicts' to permanently update .env files*")
        return "\n".join(lines)

    def fix_port_conflicts():
        conflicts = agent.port_configurator.get_configured_port_conflicts()
        if not conflicts:
            return "✅ No port conflicts to fix", get_port_conflicts_info()

        try:
            results = agent.port_configurator.resolve_all_conflicts()

            changes = []
            for service_id, result in results.items():
                if result.get("updated"):
                    for change in result["changes"]:
                        changes.append(
                            f"  • {service_id}: {change['port_key']} "
                            f"{change['old_port']} → {change['new_port']}"
                        )

            if changes:
                msg = f"✅ Fixed port conflicts:\n" + "\n".join(changes)
                msg += "\n\n*Restart services to use new ports*"
            else:
                msg = "✅ No changes needed"

            return msg, get_port_conflicts_info()
        except Exception as e:
            return f"❌ Error: {e}", get_port_conflicts_info()

    def sync_all_readmes():
        try:
            results = agent.port_configurator.sync_all_readmes()

            changes = []
            for service_id, result in results.items():
                if result.get("synced"):
                    for change in result.get("port_changes", []):
                        changes.append(
                            f"  • {service_id}: {change['port_key']} "
                            f"{change['old_port']} → {change['new_port']}"
                        )

            if changes:
                msg = f"✅ Synced README files:\n" + "\n".join(changes)
            else:
                msg = "✅ All READMEs already in sync with .env files"

            return msg
        except Exception as e:
            return f"❌ Error: {e}"

    async def stop_service(service_id: str):
        if not service_id:
            return (
                "⚠️ Select a service first",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )
        try:
            await agent.service_manager.stop_service(service_id)
            return (
                f"✅ Stopped {service_id}",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )
        except Exception as e:
            return (
                f"❌ Error: {e}",
                gr.update(choices=get_services_list()),
                get_services_status_html(),
            )

    async def start_all_services():
        services = agent.discovery.get_all_services()
        started = []
        failed = []
        for service in services:
            if service.is_running:
                continue
            if not service.has_capability:
                continue
            try:
                await agent.service_manager.start_service_auto_ports(service.id)
                started.append(service.id)
                await asyncio.sleep(1)
            except Exception as e:
                failed.append(f"{service.id}: {e}")

        msg = ""
        if started:
            msg += f"✅ Started: {', '.join(started)}"
        if failed:
            msg += f"\n❌ Failed: {', '.join(failed)}"
        if not started and not failed:
            msg = "ℹ️ All services already running or no capability"
        return msg, gr.update(choices=get_services_list()), get_services_status_html()

    async def stop_all_services():
        services = agent.discovery.get_all_services()
        stopped = []
        for service in services:
            if not service.is_running:
                continue
            try:
                await agent.service_manager.stop_service(service.id)
                stopped.append(service.id)
            except Exception as e:
                pass

        if stopped:
            msg = f"✅ Stopped: {', '.join(stopped)}"
        else:
            msg = "ℹ️ No running services"
        return msg, gr.update(choices=get_services_list()), get_services_status_html()

    async def generate_capability_streaming(service_id: str):
        if not service_id:
            yield "⚠️ Select a service first", ""
            return  # noqa: B901

        from agent.capability_generator import CapabilityGenerator

        service = agent.discovery.get_service(service_id)
        if not service:
            yield f"❌ Service not found: {service_id}", ""
            return  # noqa: B901

        try:
            generator = CapabilityGenerator(agent.config)

            yield f"🔍 Analyzing service folder: {service.path}", ""
            yield f"📂 Building directory tree...", ""
            yield f"📄 Gathering file contents...", ""
            yield f"🤖 Sending to Gemini 3 Flash Preview...", ""
            yield f"⏳ Waiting for LLM response (this may take 10-30 seconds)...", ""

            capability_yaml = await generator.generate_capability(service.path)

            cap_path = Path(service.path) / "CAPABILITY.yaml"
            cap_path.write_text(capability_yaml, encoding='utf-8')

            agent.discovery.update_service_capability(service_id, capability_yaml)

            yield (
                f"✅ Generated and saved CAPABILITY.yaml for {service_id}",
                capability_yaml,
            )
        except Exception as e:
            logger.exception(f"Error generating capability for {service_id}")
            yield f"❌ Error: {e}", ""

    def get_resources_info():
        stats = agent.resource_monitor.get_all_stats()
        gpu = stats.get("gpu", {})
        mem = stats.get("memory", {}).get("ram", {})
        cpu = stats.get("cpu", {})
        disk = stats.get("disk", {})

        def make_bar(pct):
            filled = int(pct / 5)
            return "█" * filled + "░" * (20 - filled)

        ram_pct = mem.get("percent_used", 0)
        cpu_pct = cpu.get("percent", 0)
        disk_pct = disk.get("percent_used", 0)

        info = f"""## System Resources

### Memory
`{make_bar(ram_pct)}` **{ram_pct:.1f}%**
- Used: {mem.get("used_gb", 0):.1f} GB / {mem.get("total_gb", 0):.1f} GB

### CPU
`{make_bar(cpu_pct)}` **{cpu_pct:.1f}%**
- Cores: {cpu.get("cores", 0)} ({cpu.get("cores_physical", 0)} physical)

### Disk
`{make_bar(disk_pct)}` **{disk_pct:.1f}%**
- Used: {disk.get("used_gb", 0):.1f} GB / Free: {disk.get("free_gb", 0):.1f} GB
"""

        if gpu.get("available"):
            gpu_name = gpu.get("name", "Unknown")
            info += f"\n### GPU: {gpu_name}\n"
            if gpu.get("vram_total_gb"):
                vram_used = gpu.get("vram_used_gb", 0)
                vram_total = gpu.get("vram_total_gb", 0)
                vram_pct = (vram_used / vram_total * 100) if vram_total else 0
                info += f"`{make_bar(vram_pct)}` **{vram_pct:.1f}%**\n"
                info += f"- VRAM: {vram_used:.1f} / {vram_total:.1f} GB\n"
        else:
            info += f"\n### GPU\n*{gpu.get('reason', 'Not available')}*"

        return info

    def get_logs(service_id: str):
        if not service_id:
            return "Select a service to view logs"
        logs = agent.service_manager.get_service_logs(service_id, lines=100)
        return "\n".join(logs) if logs else "No logs available"

    def get_config_info():
        cfg = agent.config
        api_key = cfg.get_llm_api_key()
        api_status = (
            "✅ Configured" if api_key else "❌ Not set (set OPENROUTER_API_KEY)"
        )

        return f"""## Agent Configuration

### Machine
| Property | Value |
|----------|-------|
| ID | `{cfg.machine_id}` |
| Name | {cfg.machine_name} |
| Platform | {cfg.platform} |

### Network
| Property | Value |
|----------|-------|
| Port | {cfg.agent.port} |
| Host | {cfg.agent.host} |

### LLM (for Capability Generation)
| Property | Value |
|----------|-------|
| Provider | {cfg.llm.provider} |
| Model | `{cfg.llm.model}` |
| API Key | {api_status} |

### Resource Reserves
| Resource | Reserved |
|----------|----------|
| GPU VRAM | {cfg.resources.gpu_vram_reserve_gb} GB |
| RAM | {cfg.resources.ram_reserve_gb} GB |
"""

    def get_machine_info():
        cfg = agent.config

        platform_ranges = MACHINE_PORT_RANGES.get(cfg.platform, {})
        ranges_text = "\n".join(
            f"| {platform} | {r['api_port_min']}-{r['api_port_max']} | {r['ui_port_min']}-{r['ui_port_max']} |"
            for platform, r in MACHINE_PORT_RANGES.items()
        )

        return f"""## Machine Identification

### This Machine
| Property | Value |
|----------|-------|
| Short ID | `{MACHINE_INFO["short_id"]}` |
| Full UUID | `{(MACHINE_INFO["full_id"] or "N/A")[:16]}...` |
| Hostname | `{MACHINE_INFO["hostname"]}` |
| Platform | `{MACHINE_INFO["platform"]}` |

### Current Port Ranges
| Range | Min | Max |
|-------|-----|-----|
| API Ports | {cfg.port_ranges.api_port_min} | {cfg.port_ranges.api_port_max} |
| UI Ports | {cfg.port_ranges.ui_port_min} | {cfg.port_ranges.ui_port_max} |

### All Platform Port Ranges
| Platform | API Ports | UI Ports |
|----------|-----------|----------|
{ranges_text}

*Use `--generate-machine-config` or the button below to create `config.{MACHINE_INFO["short_id"]}.yaml`*
"""

    def do_generate_machine_config():
        try:
            output_path = generate_machine_config()
            return f"✅ Generated: `{output_path}`\n\nMachine ID: `{MACHINE_INFO['short_id']}`"
        except Exception as e:
            return f"❌ Error: {e}"

    css = """
    .gradio-container { 
        max-width: 1400px !important; 
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    .header-banner {
        background: linear-gradient(135deg, #0c1222 0%, #1a1f35 50%, #252b4a 100%);
        padding: 28px 32px; 
        border-radius: 16px; 
        margin-bottom: 24px;
        border: 1px solid rgba(99, 102, 241, 0.3);
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    }
    .header-banner h1 {
        background: linear-gradient(135deg, #818cf8 0%, #c084fc 50%, #f472b6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 32px;
        font-weight: 700;
        margin: 0;
    }
    .header-banner p {
        color: #94a3b8;
        margin: 12px 0 0 0;
        font-size: 14px;
    }
    .folder-table { font-family: 'JetBrains Mono', 'Fira Code', monospace; }
    .llm-status {
        background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
        border: 1px solid #4f46e5;
        border-radius: 12px;
        padding: 16px;
        margin: 12px 0;
    }
    """

    with gr.Blocks(title=f"Service Agent - {agent.config.machine_id}", css=css) as app:
        gr.HTML(f"""
        <div class="header-banner">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h1>⚡ White Mirror Service Agent</h1>
                    <p>
                        <strong>{agent.config.machine_name}</strong> ({agent.config.machine_id}) &nbsp;•&nbsp; 
                        Platform: {agent.config.platform.upper()}
                    </p>
                </div>
            </div>
        </div>
        """)

        with gr.Row():
            with gr.Column(scale=3):
                services_status_html = gr.HTML(value=get_services_status_html, every=5)
            with gr.Column(scale=1):
                with gr.Row():
                    start_all_btn = gr.Button(
                        "▶▶ Start All", variant="primary", size="sm"
                    )
                    stop_all_btn = gr.Button("⏹⏹ Stop All", variant="stop", size="sm")

        with gr.Tabs():
            with gr.TabItem("🔧 Services", id="services"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Discovered Services")
                        services = get_services_list()
                        service_dropdown = gr.Dropdown(
                            label="Select Service",
                            choices=services,
                            value=services[0] if services else None,
                            interactive=True,
                            allow_custom_value=False,
                        )
                        with gr.Row():
                            start_btn = gr.Button(
                                "▶ Start", variant="primary", size="sm"
                            )
                            stop_btn = gr.Button("⏹ Stop", variant="stop", size="sm")
                        start_auto_btn = gr.Button(
                            "▶ Start (Auto Ports)", variant="secondary", size="sm"
                        )
                        scan_btn = gr.Button(
                            "🔄 Rescan All Folders", variant="secondary"
                        )
                        port_conflicts_md = gr.Markdown(value=get_port_conflicts_info)
                        with gr.Row():
                            fix_ports_btn = gr.Button(
                                "🔧 Fix Port Conflicts", variant="secondary", size="sm"
                            )
                            sync_readmes_btn = gr.Button(
                                "📄 Sync READMEs", variant="secondary", size="sm"
                            )
                        status_msg = gr.Textbox(
                            label="Status", interactive=False, lines=2
                        )

                    with gr.Column(scale=2):
                        initial_info, initial_yaml, initial_status = (
                            get_service_info(services[0])
                            if services
                            else ("Select a service to view details", "", "ready")
                        )
                        service_info = gr.Markdown(initial_info)
                        service_status = gr.Textbox(visible=False, value=initial_status)

                gr.Markdown("---")
                with gr.Row():
                    gen_cap_btn = gr.Button(
                        "🤖 Generate / Update with Gemini 3 Flash Preview",
                        variant="primary",
                    )
                gen_status = gr.Textbox(
                    label="LLM Status",
                    interactive=False,
                    lines=1,
                )
                gr.Markdown("### 📄 CAPABILITY.yaml")
                capability_yaml = gr.Code(
                    label="",
                    language="yaml",
                    lines=18,
                    value=initial_yaml,
                    interactive=False,
                )

                service_dropdown.change(
                    get_service_info,
                    inputs=[service_dropdown],
                    outputs=[service_info, capability_yaml, service_status],
                )
                scan_btn.click(scan_all_folders, outputs=[service_dropdown, status_msg])
                start_btn.click(
                    start_service,
                    inputs=[service_dropdown],
                    outputs=[status_msg, service_dropdown, services_status_html],
                )
                start_auto_btn.click(
                    start_service_auto,
                    inputs=[service_dropdown],
                    outputs=[status_msg, service_dropdown, services_status_html],
                )
                stop_btn.click(
                    stop_service,
                    inputs=[service_dropdown],
                    outputs=[status_msg, service_dropdown, services_status_html],
                )
                start_all_btn.click(
                    start_all_services,
                    outputs=[status_msg, service_dropdown, services_status_html],
                )
                stop_all_btn.click(
                    stop_all_services,
                    outputs=[status_msg, service_dropdown, services_status_html],
                )
                fix_ports_btn.click(
                    fix_port_conflicts,
                    outputs=[status_msg, port_conflicts_md],
                )
                sync_readmes_btn.click(
                    sync_all_readmes,
                    outputs=[status_msg],
                )
                gen_cap_btn.click(
                    generate_capability_streaming,
                    inputs=[service_dropdown],
                    outputs=[gen_status, capability_yaml],
                )

            with gr.TabItem("📁 Folders", id="folders"):
                gr.Markdown("### Service Folder Management")
                gr.Markdown(
                    "Add folders containing services. Services will be discovered automatically on rescan."
                )

                folders_table = gr.Dataframe(
                    headers=["Folder Path"],
                    datatype=["str"],
                    value=get_folders_list,
                    interactive=True,
                    wrap=True,
                    elem_classes=["folder-table"],
                )

                with gr.Row():
                    new_folder_input = gr.Textbox(
                        label="Add New Folder",
                        placeholder="/path/to/service/folder",
                        scale=3,
                    )
                    add_btn = gr.Button("➕ Add Folder", variant="primary", scale=1)

                with gr.Row():
                    remove_btn = gr.Button("🗑️ Remove Selected", variant="stop")

                folder_status = gr.Textbox(
                    label="Status",
                    interactive=False,
                    lines=1,
                )

                add_btn.click(
                    add_folder,
                    inputs=[new_folder_input],
                    outputs=[folders_table, folder_status],
                )
                remove_btn.click(
                    remove_folder,
                    inputs=[folders_table],
                    outputs=[folders_table, folder_status],
                )

            with gr.TabItem("📊 Resources", id="resources"):
                resources_md = gr.Markdown(value=get_resources_info, every=10)
                gr.Button("🔄 Refresh").click(
                    get_resources_info, outputs=[resources_md]
                )

            with gr.TabItem("📋 Logs", id="logs"):
                log_service = gr.Dropdown(
                    label="Select Service",
                    choices=get_services_list(),
                    interactive=True,
                )
                logs_display = gr.Code(
                    label="Service Logs", language="shell", lines=25, interactive=False
                )
                gr.Button("🔄 Refresh Logs").click(
                    get_logs, inputs=[log_service], outputs=[logs_display]
                )
                log_service.change(
                    get_logs, inputs=[log_service], outputs=[logs_display]
                )

            with gr.TabItem("⚙️ Config", id="config"):
                with gr.Row():
                    with gr.Column(scale=1):
                        config_md = gr.Markdown(value=get_config_info)
                        gr.Button("🔄 Refresh Config").click(
                            get_config_info, outputs=[config_md]
                        )
                    with gr.Column(scale=1):
                        machine_info_md = gr.Markdown(value=get_machine_info)
                        gr.Button("🔄 Refresh Machine Info").click(
                            get_machine_info, outputs=[machine_info_md]
                        )

                gr.Markdown("---")
                gr.Markdown("### Machine Config Generation")
                with gr.Row():
                    gen_config_btn = gr.Button(
                        "🔧 Generate Machine Config", variant="primary"
                    )
                    gen_config_status = gr.Textbox(
                        label="Status", interactive=False, lines=2, scale=2
                    )
                gen_config_btn.click(
                    do_generate_machine_config, outputs=[gen_config_status]
                )

    return app
