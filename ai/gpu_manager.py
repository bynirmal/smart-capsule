"""GPU / compute-device detection and monitoring.

Detection is layered so that the application never depends on a heavy AI stack:

1. PyTorch (CUDA, ROCm, Apple MPS) when it is importable - richest information.
2. ``nvidia-smi`` parsing when PyTorch is absent but an NVIDIA driver exists.
3. CPU-only reporting as the guaranteed fallback.

Every failure mode (missing torch, blocked DLL, driver timeout, no CUDA device)
becomes a human-readable note instead of an exception, because a GPU is an
optimisation and never a requirement.
"""

from __future__ import annotations

import csv
import io
import logging
import platform
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Device:
    """One compute device reported by a backend."""

    name: str
    backend: str
    index: int = 0
    is_gpu: bool = False
    total_memory_mb: int | None = None
    used_memory_mb: int | None = None

    @property
    def vram_label(self) -> str:
        if not self.is_gpu:
            return "system memory"
        if self.total_memory_mb is None:
            return "VRAM unknown"
        if self.used_memory_mb is None:
            return f"{self.total_memory_mb} MB VRAM"
        return f"{self.used_memory_mb} / {self.total_memory_mb} MB VRAM"

    @property
    def backend_label(self) -> str:
        return {
            "cuda": "CUDA",
            "rocm": "ROCm",
            "mps": "Apple MPS",
            "nvidia-smi": "NVIDIA (driver)",
            "cpu": "CPU",
        }.get(self.backend, self.backend.upper())


@dataclass(frozen=True, slots=True)
class GpuReport:
    """Snapshot of everything the UI needs to describe compute capability."""

    devices: tuple[Device, ...] = ()
    cuda_available: bool = False
    torch_installed: bool = False
    torch_version: str | None = None
    cuda_version: str | None = None
    accelerator_count: int = 0
    notes: tuple[str, ...] = ()
    platform_label: str = ""
    probed_at: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def recommended(self) -> Device:
        for device in self.devices:
            if device.is_gpu:
                return device
        return self.devices[-1] if self.devices else Device(name="CPU", backend="cpu")

    @property
    def has_gpu(self) -> bool:
        return any(device.is_gpu for device in self.devices)

    @property
    def status_line(self) -> str:
        if self.has_gpu:
            gpu = self.recommended
            return f"{gpu.name} · {gpu.backend_label}"
        return "CPU only"

    @property
    def summary(self) -> str:
        if self.has_gpu:
            return f"GPU acceleration available · {self.recommended.vram_label}"
        return "Running on CPU · GPU acceleration not available"


def _nvidia_smi_devices() -> tuple[list[Device], list[str]]:
    """Query the NVIDIA driver directly (no PyTorch required)."""
    notes: list[str] = []
    executable = shutil.which("nvidia-smi")
    if not executable:
        return [], notes
    command = [
        executable,
        "--query-gpu=name,memory.total,memory.used",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - driver specific
        notes.append(f"nvidia-smi could not be executed: {exc}")
        return [], notes

    if completed.returncode != 0:
        notes.append("nvidia-smi reported no usable GPU.")
        return [], notes

    devices: list[Device] = []
    for index, row in enumerate(csv.reader(io.StringIO(completed.stdout))):
        if len(row) < 3:
            continue
        name = row[0].strip()
        try:
            total = int(float(row[1].strip()))
            used = int(float(row[2].strip()))
        except ValueError:
            total, used = None, None
        devices.append(
            Device(
                name=name or f"NVIDIA GPU {index}",
                backend="nvidia-smi",
                index=index,
                is_gpu=True,
                total_memory_mb=total,
                used_memory_mb=used,
            )
        )
    if devices:
        notes.append("Detected through the NVIDIA driver; install PyTorch to enable CUDA compute.")
    return devices, notes


def _torch_devices() -> tuple[list[Device], dict[str, Any], list[str]]:
    """Inspect PyTorch, returning devices, metadata and notes."""
    devices: list[Device] = []
    meta: dict[str, Any] = {}
    notes: list[str] = []

    try:
        import torch  # noqa: PLC0415 - optional heavy import
    except ImportError as exc:
        message = str(exc)
        if "DLL load failed" in message or "Application Control" in message:
            notes.append("PyTorch is installed but blocked by this machine's security policy.")
        else:
            notes.append("PyTorch is not installed - CPU processing with the rule-based engine.")
        return devices, meta, notes
    except Exception as exc:  # pragma: no cover - exotic import failures
        notes.append(f"PyTorch import failed: {exc}")
        return devices, meta, notes

    meta["torch_version"] = getattr(torch, "__version__", "unknown")
    meta["torch_installed"] = True

    cuda = getattr(torch, "cuda", None)
    if cuda is not None:
        meta["cuda_version"] = getattr(getattr(torch, "version", None), "cuda", None)
        try:
            if cuda.is_available():
                for index in range(cuda.device_count()):
                    props = cuda.get_device_properties(index)
                    total = int(props.total_memory / (1024 * 1024))
                    used = None
                    try:
                        used = int(cuda.memory_allocated(index) / (1024 * 1024))
                    except Exception:  # pragma: no cover - older torch builds
                        used = None
                    devices.append(
                        Device(
                            name=props.name,
                            backend="cuda",
                            index=index,
                            is_gpu=True,
                            total_memory_mb=total,
                            used_memory_mb=used,
                        )
                    )
                notes.append(f"CUDA {meta.get('cuda_version') or ''} found with {len(devices)} device(s).")
            else:
                notes.append("PyTorch is installed but CUDA is not available on this machine.")
        except Exception as exc:  # pragma: no cover - driver/runtime mismatch
            notes.append(f"CUDA probe failed: {exc}")

    mps = getattr(getattr(torch, "backends", None), "mps", None)
    if mps is not None and platform.system() == "Darwin":
        try:
            if mps.is_available():
                devices.append(Device(name="Apple Silicon GPU", backend="mps", is_gpu=True))
                notes.append("Apple Metal (MPS) backend available.")
        except Exception as exc:  # pragma: no cover - macOS specific
            notes.append(f"MPS probe failed: {exc}")

    return devices, meta, notes


class GpuManager:
    """Caches detection results and can be refreshed from the UI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._report: GpuReport | None = None

    @property
    def report(self) -> GpuReport:
        report = self._report
        if report is None:
            report = self.refresh()
        return report

    def refresh(self) -> GpuReport:
        """Probe hardware again, then cache the result."""
        report = detect()
        with self._lock:
            self._report = report
        return report

    def recommended_device(self) -> str:
        report = self.report
        if report.has_gpu:
            return f"cuda:{report.recommended.index}" if report.recommended.backend == "cuda" else report.recommended.backend
        return "cpu"


def detect() -> GpuReport:
    """Run a full detection pass. Never raises."""
    notes: list[str] = []
    devices: list[Device] = []

    torch_devices, meta, torch_notes = _torch_devices()
    notes.extend(torch_notes)
    devices.extend(torch_devices)

    try:
        smi_devices, smi_notes = _nvidia_smi_devices()
    except Exception as exc:  # pragma: no cover - defensive
        smi_devices, smi_notes = [], [f"GPU driver probe failed: {exc}"]

    if not devices:
        # Without PyTorch, still show the hardware so the user understands what
        # is present; it simply is not usable for compute yet.
        devices.extend(smi_devices)
        notes.extend(smi_notes)

    cpu_name = platform.processor() or platform.machine() or "CPU"
    cores = 0
    try:
        import os

        cores = os.cpu_count() or 0
    except Exception:  # pragma: no cover - defensive
        cores = 0
    cpu = Device(name=f"{cpu_name.strip()} · {cores} threads" if cores else cpu_name.strip(), backend="cpu")
    devices.append(cpu)

    if not any(device.is_gpu for device in devices):
        notes.append("No CUDA-capable GPU detected. All AI work will run on the CPU.")

    # Deduplicate notes while preserving order.
    seen: set[str] = set()
    unique_notes = tuple(note for note in notes if not (note in seen or seen.add(note)))

    return GpuReport(
        devices=tuple(devices),
        cuda_available=any(device.backend == "cuda" for device in devices),
        torch_installed=bool(meta.get("torch_installed")),
        torch_version=meta.get("torch_version"),
        cuda_version=meta.get("cuda_version"),
        accelerator_count=sum(1 for device in devices if device.is_gpu),
        notes=unique_notes,
        platform_label=f"{platform.system()} {platform.release()} · {platform.machine()}",
        probed_at=__import__("datetime").datetime.now().strftime("%H:%M:%S"),
        extras={k: v for k, v in meta.items() if k != "torch_installed"},
    )
