"""Host metrics collection.

Gathers CPU, RAM, disk, network, internet reachability/latency, Python runtime
info, whether MetaTrader 5 is running, and a short list of notable processes.

``psutil`` is used when available (rich, cross-platform) and the collector
degrades gracefully to stdlib-only readings when it is not installed, so the
agent never hard-fails for a missing optional dependency.
"""

from __future__ import annotations

import platform
import shutil
import socket
import time
from typing import Any

try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except Exception:  # pragma: no cover - environment dependent
    psutil = None  # type: ignore
    _HAS_PSUTIL = False

# Process names that indicate a running MT5 / trading terminal.
_MT5_PROCESS_NAMES = ("terminal64.exe", "terminal.exe", "metatrader", "mt5")

# Hosts we ping to estimate internet reachability + latency.
_PING_TARGETS = (("1.1.1.1", 53), ("8.8.8.8", 53))


class MetricsCollector:
    """Collects a metrics snapshot suitable for the backend machine record."""

    def __init__(self) -> None:
        self._boot_time = _boot_time()
        # Prime psutil's per-CPU counter so the first reading isn't 0.0.
        if _HAS_PSUTIL:
            try:
                psutil.cpu_percent(interval=None)
            except Exception:
                pass

    def snapshot(self) -> dict[str, Any]:
        """Return a full metrics dict (all keys best-effort)."""
        internet_ms, internet_ok = _internet_latency_ms()
        return {
            "cpu": self.cpu_percent(),
            "ram": self.ram_percent(),
            "disk": self.disk_percent(),
            "network": self.network_throughput(),
            "internetMs": internet_ms,
            "internetOk": internet_ok,
            "latencyMs": internet_ms,
            "python": self.python_info(),
            "pythonStatus": "online",
            "mt5Running": self.mt5_running(),
            "processes": self.top_processes(),
            "uptimeSec": self.uptime_sec(),
            "host": socket.gethostname(),
            "os": f"{platform.system()} {platform.release()}",
            "collectedWith": "psutil" if _HAS_PSUTIL else "stdlib",
        }

    # -- individual readings ----------------------------------------------
    def cpu_percent(self) -> float:
        if _HAS_PSUTIL:
            try:
                return round(float(psutil.cpu_percent(interval=None)), 1)
            except Exception:
                return 0.0
        return round(_loadavg_as_percent(), 1)

    def ram_percent(self) -> float:
        if _HAS_PSUTIL:
            try:
                return round(float(psutil.virtual_memory().percent), 1)
            except Exception:
                return 0.0
        return 0.0

    def disk_percent(self, path: str = "/") -> float:
        try:
            if platform.system() == "Windows":
                path = "C:\\"
            usage = shutil.disk_usage(path)
            return round(usage.used / usage.total * 100, 1) if usage.total else 0.0
        except Exception:
            return 0.0

    def network_throughput(self) -> dict[str, float]:
        if not _HAS_PSUTIL:
            return {"sentKb": 0.0, "recvKb": 0.0}
        try:
            io = psutil.net_io_counters()
            return {
                "sentKb": round(io.bytes_sent / 1024, 1),
                "recvKb": round(io.bytes_recv / 1024, 1),
            }
        except Exception:
            return {"sentKb": 0.0, "recvKb": 0.0}

    def python_info(self) -> dict[str, str]:
        return {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        }

    def mt5_running(self) -> bool:
        if not _HAS_PSUTIL:
            return False
        try:
            for proc in psutil.process_iter(["name"]):
                name = (proc.info.get("name") or "").lower()
                if any(tag in name for tag in _MT5_PROCESS_NAMES):
                    return True
        except Exception:
            return False
        return False

    def top_processes(self, limit: int = 5) -> list[dict[str, Any]]:
        if not _HAS_PSUTIL:
            return []
        try:
            procs = []
            for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                info = proc.info
                procs.append({
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "cpu": round(info.get("cpu_percent") or 0.0, 1),
                    "ram": round(info.get("memory_percent") or 0.0, 1),
                })
            procs.sort(key=lambda p: p["cpu"], reverse=True)
            return procs[:limit]
        except Exception:
            return []

    def uptime_sec(self) -> int:
        if self._boot_time:
            return int(time.time() - self._boot_time)
        return 0


def _boot_time() -> float:
    if _HAS_PSUTIL:
        try:
            return float(psutil.boot_time())
        except Exception:
            return 0.0
    return 0.0


def _loadavg_as_percent() -> float:
    """Rough CPU estimate from load average when psutil is unavailable."""
    try:
        import os
        load1, _, _ = os.getloadavg()  # not on Windows
        cores = os.cpu_count() or 1
        return min(100.0, load1 / cores * 100)
    except (AttributeError, OSError):
        return 0.0


def _internet_latency_ms() -> tuple[float, bool]:
    """TCP-connect latency to a well-known host (no ICMP/root needed)."""
    for host, port in _PING_TARGETS:
        start = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=2):
                return round((time.perf_counter() - start) * 1000, 1), True
        except OSError:
            continue
    return 0.0, False
