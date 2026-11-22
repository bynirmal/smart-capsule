"""GPU Monitor: live view of the detected compute devices."""

from __future__ import annotations

from ai.gpu_manager import GpuReport
from gui.base_page import BasePage
from gui.theme import COLORS, font
from gui.widgets import Badge, Card, KeyValueRow, ghost_button
from gui.workers import run_in_background
import customtkinter as ctk


class GpuMonitorPage(BasePage):
    page_key = "gpu"
    title = "GPU Monitor"
    subtitle = "Compute devices, backends and automatic CPU fallback"

    def build(self) -> None:
        ghost_button(self.header_actions, "↻  Re-detect hardware", self._redetect).pack(side="right")

        self._summary_card = Card(self.body, "Acceleration summary", "Auto-selected backend", accent=COLORS["success"])
        self._summary_card.pack(fill="x", pady=(0, 12), padx=6)

        self.row_device = KeyValueRow(self._summary_card.body, "Recommended device")
        self.row_device.pack(fill="x", pady=3)
        self.row_backend = KeyValueRow(self._summary_card.body, "Backend")
        self.row_backend.pack(fill="x", pady=3)
        self.row_torch = KeyValueRow(self._summary_card.body, "PyTorch")
        self.row_torch.pack(fill="x", pady=3)
        self.row_cuda = KeyValueRow(self._summary_card.body, "CUDA runtime")
        self.row_cuda.pack(fill="x", pady=3)
        self.row_platform = KeyValueRow(self._summary_card.body, "Platform")
        self.row_platform.pack(fill="x", pady=3)

        self._devices_card = Card(self.body, "Detected devices", "Probed through PyTorch, the NVIDIA driver and the OS", padding=18)
        self._devices_card.pack(fill="x", pady=(0, 12), padx=6)
        self._devices_body = ctk.CTkFrame(self._devices_card.body, fg_color="transparent")
        self._devices_body.pack(fill="x")

        self._notes_card = Card(self.body, "Detection notes", "Why this configuration was chosen", padding=18, accent=COLORS["violet"])
        self._notes_card.pack(fill="x", pady=(0, 12), padx=6)
        self._notes_body = ctk.CTkFrame(self._notes_card.body, fg_color="transparent")
        self._notes_body.pack(fill="x")

        self._render(self.app.gpu.report)

    def on_show(self) -> None:
        self._render(self.app.gpu.report)

    def _redetect(self) -> None:
        self.app.set_status("Re-detecting compute devices…")
        run_in_background(self, self.app.gpu.refresh, self._on_detected, self._on_error)

    def _on_detected(self, report: GpuReport) -> None:
        self._render(report)
        self.app.set_status(
            "Hardware detection complete", kind="success" if report.has_gpu else "info"
        )

    def _on_error(self, error: Exception) -> None:
        self.app.set_status(f"Detection failed: {error}", kind="error")

    # ------------------------------------------------------------------ #
    def _render(self, report: GpuReport) -> None:
        device = report.recommended
        self.row_device.set(device.name)
        self.row_backend.set(device.backend_label, COLORS["success"] if report.has_gpu else COLORS["text_dim"])
        self.row_torch.set(
            report.torch_version or "not installed (CPU rule-based engine active)",
            COLORS["text"] if report.torch_installed else COLORS["warning"],
        )
        self.row_cuda.set(report.cuda_version or "not available", COLORS["text"] if report.cuda_version else COLORS["text_dim"])
        self.row_platform.set(report.platform_label)

        for child in self._devices_body.winfo_children():
            child.destroy()

        for index, item in enumerate(report.devices):
            row = ctk.CTkFrame(
                self._devices_body,
                fg_color=COLORS["panel_alt"],
                corner_radius=10,
                border_width=1,
                border_color=COLORS["border"],
            )
            row.pack(fill="x", pady=3)

            top = ctk.CTkFrame(row, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(9, 1))
            ctk.CTkLabel(
                top, text=item.name, font=font(12, "bold"), text_color=COLORS["text"], anchor="w"
            ).pack(side="left")
            Badge(
                top,
                item.backend_label,
                color=COLORS["success"] if item.is_gpu else COLORS["text_dim"],
            ).pack(side="left", padx=(8, 0))
            if index == 0 and item.is_gpu:
                Badge(top, "RECOMMENDED", color=COLORS["accent"]).pack(side="right")

            ctk.CTkLabel(
                row,
                text=item.vram_label,
                font=font(10),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(fill="x", padx=12, pady=(0, 9))

        for child in self._notes_body.winfo_children():
            child.destroy()

        if not report.notes:
            ctk.CTkLabel(
                self._notes_body,
                text="No issues detected.",
                font=font(11),
                text_color=COLORS["text_muted"],
                anchor="w",
            ).pack(fill="x")
            return

        for note in report.notes:
            line = ctk.CTkFrame(self._notes_body, fg_color="transparent")
            line.pack(fill="x", pady=2)
            ctk.CTkLabel(line, text="•", font=font(11), text_color=COLORS["violet"], width=12).pack(side="left")
            ctk.CTkLabel(
                line,
                text=note,
                font=font(11),
                text_color=COLORS["text_dim"],
                anchor="w",
                justify="left",
                wraplength=780,
            ).pack(side="left", fill="x")

        ctk.CTkLabel(
            self._notes_body,
            text=f"Last probe: {report.probed_at}",
            font=font(10),
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(fill="x", pady=(8, 0))
