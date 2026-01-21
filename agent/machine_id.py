import hashlib
import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Optional


def get_os_machine_id() -> Optional[str]:
    system = platform.system().lower()

    if system == "darwin":
        return _get_macos_machine_id()
    elif system == "windows":
        return _get_windows_machine_id()
    elif system == "linux":
        return _get_linux_machine_id()

    return None


def _get_macos_machine_id() -> Optional[str]:
    try:
        result = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "IOPlatformUUID" in line:
                uuid = line.split('"')[-2]
                if uuid and len(uuid) > 10:
                    return uuid
    except Exception:
        pass
    return None


def _get_windows_machine_id() -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "reg",
                "query",
                r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Cryptography",
                "/v",
                "MachineGuid",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "MachineGuid" in line:
                parts = line.strip().split()
                if len(parts) >= 3:
                    return parts[-1]
    except Exception:
        pass
    return None


def _get_linux_machine_id() -> Optional[str]:
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        try:
            content = Path(path).read_text().strip()
            if content and len(content) > 10:
                return content
        except Exception:
            continue
    return None


def get_short_machine_id(length: int = 8) -> str:
    full_id = get_os_machine_id()

    if full_id:
        hash_digest = hashlib.sha256(full_id.encode()).hexdigest()
        return hash_digest[:length]

    hostname = socket.gethostname().lower().replace(" ", "-")
    hash_digest = hashlib.sha256(hostname.encode()).hexdigest()
    return hash_digest[:length]


def get_machine_identifier() -> dict:
    os_id = get_os_machine_id()
    hostname = socket.gethostname()
    short_id = get_short_machine_id()
    system = platform.system().lower()

    if system == "darwin":
        platform_name = "macos"
    elif system == "windows":
        platform_name = "windows"
    elif system == "linux":
        platform_name = "linux"
    else:
        platform_name = system

    return {
        "short_id": short_id,
        "full_id": os_id,
        "hostname": hostname,
        "platform": platform_name,
        "config_suffix": f"{platform_name}-{short_id}",
    }
