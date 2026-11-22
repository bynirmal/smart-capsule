"""Lifecycle management for the single floating Sidekick window."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SidekickWindowManager:
    """Creates the widget lazily and guarantees exactly one instance."""

    def __init__(self, app) -> None:
        self.app = app
        self._widget = None
        # Tracked explicitly: Tk's winfo_viewable() lags behind withdraw(), which
        # would otherwise make a second toggle hide an already hidden window.
        self._visible = False

    @property
    def widget(self):
        return self._widget

    @property
    def visible(self) -> bool:
        return bool(self._widget is not None and self._visible and self._widget.winfo_exists())

    def _mark_hidden(self) -> None:
        self._visible = False

    def show(self):
        if self._widget is None or not self._widget.winfo_exists():
            from sidekick.floating_widget import FloatingSidekick

            self._widget = FloatingSidekick(self.app, on_hide=self._mark_hidden)
        self._widget.show()
        self._visible = True
        return self._widget

    def hide(self) -> None:
        if self._widget is not None and self._widget.winfo_exists():
            self._widget.hide()
        self._visible = False

    def toggle(self) -> bool:
        """Show the widget when hidden; hide it when visible. Returns visibility."""
        if self.visible:
            self.hide()
            return False
        self.show()
        return True

    def destroy(self) -> None:
        if self._widget is not None:
            try:
                self._widget.destroy()
            except Exception:  # pragma: no cover - shutdown race
                logger.debug("Sidekick destroy failed", exc_info=True)
            self._widget = None
        self._visible = False
