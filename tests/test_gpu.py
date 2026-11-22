"""GPU detection tests.

They assert the *contract* (always a usable fallback, never an exception)
rather than specific hardware, so the suite passes on CPU-only CI and on
machines with a GPU.
"""

from __future__ import annotations

from ai.gpu_manager import Device, GpuManager, GpuReport, detect


def test_detect_returns_report_with_cpu_fallback() -> None:
    report = detect()
    assert isinstance(report, GpuReport)
    assert report.devices, "at least the CPU device must be reported"
    assert report.recommended is not None
    cpu_devices = [device for device in report.devices if device.backend == "cpu"]
    assert cpu_devices, "CPU must always be available as a fallback"
    assert report.status_line
    assert isinstance(report.notes, tuple)


def test_recommended_prefers_gpu_when_present() -> None:
    gpu = Device(name="Test GPU", backend="cuda", index=0, is_gpu=True, total_memory_mb=8192, used_memory_mb=512)
    cpu = Device(name="Test CPU", backend="cpu")
    report = GpuReport(devices=(gpu, cpu), cuda_available=True, accelerator_count=1)
    assert report.recommended is gpu
    assert report.has_gpu is True
    assert "8192" in gpu.vram_label


def test_cpu_only_report_is_not_an_error() -> None:
    report = GpuReport(devices=(Device(name="Test CPU", backend="cpu"),))
    assert report.has_gpu is False
    assert report.recommended.backend == "cpu"
    assert "CPU" in report.status_line


def test_manager_caches_and_refreshes() -> None:
    manager = GpuManager()
    first = manager.report
    assert manager.report is first, "a cached report should be reused"
    refreshed = manager.refresh()
    assert isinstance(refreshed, GpuReport)
    assert manager.recommended_device() == ("cpu" if not refreshed.has_gpu else manager.recommended_device())
