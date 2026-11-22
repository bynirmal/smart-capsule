"""Local AI layer: device management, models, extraction and compression."""

from ai.gpu_manager import Device, GpuManager, GpuReport, detect

__all__ = ["Device", "GpuManager", "GpuReport", "detect"]
