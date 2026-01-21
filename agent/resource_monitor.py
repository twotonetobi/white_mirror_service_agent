import logging
import platform
import subprocess
from typing import Optional

import psutil

from agent.config import AgentConfig

logger = logging.getLogger("agent.resources")

PYNVML_AVAILABLE = False
pynvml = None

try:
    import pynvml as _pynvml
    pynvml = _pynvml
    PYNVML_AVAILABLE = True
except ImportError:
    pass


class ResourceMonitor:
    def __init__(self, config: AgentConfig):
        self.config = config
        self._nvidia_initialized = False
        self._nvidia_handle = None
        self._init_attempted = False
        self._try_init_nvidia()

    def _try_init_nvidia(self) -> bool:
        if self._nvidia_initialized:
            return True
        if not PYNVML_AVAILABLE:
            return False
        
        try:
            pynvml.nvmlInit()
            device_count = pynvml.nvmlDeviceGetCount()
            if device_count > 0:
                self._nvidia_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._nvidia_initialized = True
                name = pynvml.nvmlDeviceGetName(self._nvidia_handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")
                logger.info(f"NVIDIA GPU monitoring initialized: {name}")
                return True
        except Exception as e:
            if not self._init_attempted:
                logger.warning(f"Failed to initialize NVIDIA monitoring: {e}")
        
        self._init_attempted = True
        return False

    def get_gpu_stats(self) -> dict:
        if not self._nvidia_initialized:
            self._try_init_nvidia()
        
        if self._nvidia_initialized and pynvml:
            return self._get_nvidia_stats()
        elif platform.system() == "Darwin":
            return self._get_apple_stats()
        elif platform.system() == "Windows":
            return self._get_nvidia_stats_fallback()
        else:
            return {"available": False, "reason": "No GPU monitoring available"}

    def _get_nvidia_stats(self) -> dict:
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(self._nvidia_handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(self._nvidia_handle)
            temp = pynvml.nvmlDeviceGetTemperature(
                self._nvidia_handle, pynvml.NVML_TEMPERATURE_GPU
            )
            name = pynvml.nvmlDeviceGetName(self._nvidia_handle)
            if isinstance(name, bytes):
                name = name.decode("utf-8")

            return {
                "available": True,
                "type": "nvidia",
                "name": name,
                "vram_total_gb": round(info.total / (1024**3), 2),
                "vram_used_gb": round(info.used / (1024**3), 2),
                "vram_free_gb": round(info.free / (1024**3), 2),
                "utilization_percent": util.gpu,
                "temperature_celsius": temp,
            }
        except Exception as e:
            logger.error(f"Failed to get NVIDIA stats: {e}")
            self._nvidia_initialized = False
            self._nvidia_handle = None
            return self._get_nvidia_stats_fallback()

    def _get_nvidia_stats_fallback(self) -> dict:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used,utilization.gpu,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 6:
                    name = parts[0].strip()
                    total_mb = float(parts[1].strip())
                    free_mb = float(parts[2].strip())
                    used_mb = float(parts[3].strip())
                    util = int(parts[4].strip())
                    temp = int(parts[5].strip())
                    return {
                        "available": True,
                        "type": "nvidia",
                        "name": name,
                        "vram_total_gb": round(total_mb / 1024, 2),
                        "vram_used_gb": round(used_mb / 1024, 2),
                        "vram_free_gb": round(free_mb / 1024, 2),
                        "utilization_percent": util,
                        "temperature_celsius": temp,
                    }
        except Exception as e:
            logger.debug(f"nvidia-smi fallback failed: {e}")
        
        return {"available": False, "reason": "No NVIDIA GPU detected"}

    def _get_apple_stats(self) -> dict:
        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return {"available": False, "reason": "system_profiler failed"}

            import json

            data = json.loads(result.stdout)
            displays = data.get("SPDisplaysDataType", [])

            if not displays:
                return {"available": False, "reason": "No GPU found"}

            gpu = displays[0]
            gpu_name = gpu.get("sppci_model", "Apple GPU")

            vram_str = gpu.get("spdisplays_vram", gpu.get("sppci_vram", "0"))
            if isinstance(vram_str, str):
                import re

                match = re.search(r"(\d+)", vram_str)
                vram_mb = int(match.group(1)) if match else 0
            else:
                vram_mb = vram_str

            return {
                "available": True,
                "type": "apple",
                "name": gpu_name,
                "vram_total_gb": round(vram_mb / 1024, 2) if vram_mb > 0 else None,
                "vram_used_gb": None,
                "vram_free_gb": None,
                "utilization_percent": None,
                "temperature_celsius": None,
            }
        except Exception as e:
            logger.error(f"Failed to get Apple GPU stats: {e}")
            return {"available": False, "error": str(e)}

    def get_memory_stats(self) -> dict:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        return {
            "ram": {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "free_gb": round(mem.available / (1024**3), 2),
                "percent_used": mem.percent,
            },
            "swap": {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "percent_used": swap.percent,
            },
        }

    def get_cpu_stats(self) -> dict:
        return {
            "percent": psutil.cpu_percent(interval=0.1),
            "cores": psutil.cpu_count(),
            "cores_physical": psutil.cpu_count(logical=False),
        }

    def get_disk_stats(self, path: str = None) -> dict:
        if path is None:
            path = "C:\\" if platform.system() == "Windows" else "/"
        try:
            disk = psutil.disk_usage(path)
            return {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "percent_used": disk.percent,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_all_stats(self) -> dict:
        return {
            "gpu": self.get_gpu_stats(),
            "memory": self.get_memory_stats(),
            "cpu": self.get_cpu_stats(),
            "disk": self.get_disk_stats(),
        }

    def check_resources_available(
        self,
        required_vram_gb: Optional[float] = None,
        required_ram_gb: Optional[float] = None,
        gpu_required: bool = False,
    ) -> tuple[bool, str]:
        memory = self.get_memory_stats()
        available_ram = memory["ram"]["free_gb"] - self.config.resources.ram_reserve_gb

        if required_ram_gb and available_ram < required_ram_gb:
            return (
                False,
                f"Insufficient RAM: {available_ram:.1f}GB available, {required_ram_gb}GB required",
            )

        gpu = self.get_gpu_stats()
        gpu_available = gpu.get("available", False)

        if gpu_required and not gpu_available:
            return False, "GPU required but not available"

        if required_vram_gb and gpu_available:
            vram_free = gpu.get("vram_free_gb")
            if vram_free is not None:
                available_vram = vram_free - self.config.resources.gpu_vram_reserve_gb
                if available_vram < required_vram_gb:
                    return (
                        False,
                        f"Insufficient VRAM: {available_vram:.1f}GB available, {required_vram_gb}GB required",
                    )

        return True, "Resources available"
