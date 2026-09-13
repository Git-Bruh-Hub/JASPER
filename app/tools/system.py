from __future__ import annotations

import os
import platform
import subprocess

try:
    import winreg
except ImportError:  # pragma: no cover - Windows only
    winreg = None
from pathlib import Path

import httpx
import psutil


BYTES_PER_GB = 1024 ** 3


def _windows_cpu_name() -> str | None:
    """Read the friendly CPU name from the Windows registry."""
    if os.name != "nt" or winreg is None:
        return None

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            value = str(value).strip()
            return value or None
    except (FileNotFoundError, OSError):
        return None


def _nvidia_gpus() -> list[dict]:
    """Read NVIDIA GPU information using nvidia-smi when available.

    This is a fixed, read-only query. No shell is used and no user-provided
    command is executed.
    """
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
        "--format=csv,noheader,nounits",
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return []

    if completed.returncode != 0:
        return []

    gpus: list[dict] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 5:
            continue
        name, total, used, utilization, driver = parts
        gpus.append(
            {
                "name": name,
                "vram_total_gb": _number_to_gb(total),
                "vram_used_gb": _number_to_gb(used),
                "utilization_percent": _number_to_float(utilization),
                "driver_version": driver,
            }
        )
    return gpus


def _number_to_gb(value: str) -> float | None:
    try:
        return round(float(value) / 1024, 2)
    except (TypeError, ValueError):
        return None


def _number_to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _storage_devices() -> list[dict]:
    """Return mounted Windows drive volumes using read-only disk queries."""
    drives: list[dict] = []
    seen: set[str] = set()

    # On Windows, psutil.disk_partitions() gives mounted volumes. On other
    # platforms, keep a useful fallback to the root filesystem.
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        partitions = []

    if os.name == "nt":
        for partition in partitions:
            mountpoint = partition.mountpoint
            if not mountpoint or mountpoint.upper() in seen:
                continue
            try:
                usage = psutil.disk_usage(mountpoint)
            except OSError:
                continue
            seen.add(mountpoint.upper())
            drives.append(
                {
                    "path": mountpoint,
                    "total_gb": round(usage.total / BYTES_PER_GB, 2),
                    "used_gb": round(usage.used / BYTES_PER_GB, 2),
                    "free_gb": round(usage.free / BYTES_PER_GB, 2),
                    "free_percent": round((usage.free / usage.total) * 100, 1),
                    "filesystem": partition.fstype or None,
                }
            )
    else:
        try:
            usage = psutil.disk_usage(os.sep)
            drives.append(
                {
                    "path": os.sep,
                    "total_gb": round(usage.total / BYTES_PER_GB, 2),
                    "used_gb": round(usage.used / BYTES_PER_GB, 2),
                    "free_gb": round(usage.free / BYTES_PER_GB, 2),
                    "free_percent": round((usage.free / usage.total) * 100, 1),
                    "filesystem": None,
                }
            )
        except OSError:
            pass

    return drives


def _ollama_models() -> dict:
    """Read locally loaded Ollama models from the loopback API."""
    from app.core.config import OLLAMA_HOST

    try:
        response = httpx.get(f"{OLLAMA_HOST}/api/ps", timeout=1.5)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {
            "available": False,
            "models": [],
        }

    models = []
    for item in payload.get("models", []):
        models.append(
            {
                "name": item.get("name"),
                "size_gb": round(item.get("size", 0) / BYTES_PER_GB, 2)
                if isinstance(item.get("size"), (int, float))
                else None,
                "vram_gb": round(item.get("size_vram", 0) / BYTES_PER_GB, 2)
                if isinstance(item.get("size_vram"), (int, float))
                else None,
                "context": item.get("context_length"),
                "expires_at": item.get("expires_at"),
            }
        )

    return {
        "available": True,
        "models": models,
    }


def get_system_info() -> dict:
    """Return read-only hardware, OS, storage, and local Ollama state.

    Values in this result are observations made at call time. This function
    does not infer or estimate hardware specifications.
    """
    vm = psutil.virtual_memory()
    storage = _storage_devices()

    cpu_name = _windows_cpu_name() or platform.processor() or platform.machine()
    gpus = _nvidia_gpus()

    return {
        "os": platform.platform(),
        "hostname": platform.node(),
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "cpu": cpu_name,
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "ram_total_gb": round(vm.total / BYTES_PER_GB, 2),
        "ram_available_gb": round(vm.available / BYTES_PER_GB, 2),
        "ram_used_percent": vm.percent,
        "gpu": gpus,
        "storage": storage,
        # Keep the old key for compatibility with v0.2.2 consumers.
        "system_drive": storage[0] if storage else None,
        "ollama": _ollama_models(),
    }
