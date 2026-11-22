"""Helpers for running slow work off the Tk main loop.

Every long operation (GPU probing, database aggregation, AI processing) runs in
a daemon thread and delivers its result back through ``widget.after``, which is
the only Tk call that is safe from a worker thread.  That keeps the window
responsive and avoids the classic "app freezes while thinking" problem.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

Callback = Callable[[Any], None] | None
ErrorCallback = Callable[[Exception], None] | None


def run_in_background(
    widget,
    task: Callable[[], Any],
    on_success: Callback = None,
    on_error: ErrorCallback = None,
    on_finally: Callable[[], None] | None = None,
) -> threading.Thread:
    """Run ``task`` in a daemon thread and deliver the outcome on the UI thread.

    ``widget`` is any live Tk widget used to schedule the delivery.  If it has
    been destroyed in the meantime the result is simply dropped.
    """

    def _deliver(callback: Callable[[], None]) -> None:
        try:
            widget.after(0, callback)
        except Exception:  # pragma: no cover - window closed mid-flight
            logger.debug("Dropping result: widget no longer exists")

    def _worker() -> None:
        result: Any = None
        error: Exception | None = None
        try:
            result = task()
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            logger.exception("Background task failed")
            error = exc

        def _dispatch() -> None:
            try:
                if error is not None:
                    if on_error is not None:
                        on_error(error)
                elif on_success is not None:
                    on_success(result)
            finally:
                if on_finally is not None:
                    on_finally()

        _deliver(_dispatch)

    thread = threading.Thread(target=_worker, name="smart-capsule-worker", daemon=True)
    thread.start()
    return thread


class Debouncer:
    """Schedule a callback after a quiet period (used by search boxes)."""

    def __init__(self, widget, delay_ms: int = 300) -> None:
        self._widget = widget
        self._delay = delay_ms
        self._job: str | None = None

    def call(self, callback: Callable[[], None]) -> None:
        self.cancel()
        try:
            self._job = self._widget.after(self._delay, callback)
        except Exception:  # pragma: no cover - window closed
            self._job = None

    def cancel(self) -> None:
        if self._job is not None:
            try:
                self._widget.after_cancel(self._job)
            except Exception:  # pragma: no cover - window already gone
                pass
            self._job = None
