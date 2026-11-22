"""Smart Capsule - application entry point.

Usage
-----
    python main.py                 start the desktop application
    python main.py --smoke         build every screen, verify it, exit
    python main.py --debug         start with verbose logging
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import APP_NAME, BUILD_STAGE, TAGLINE, VERSION, logs_dir  # noqa: E402

logger = logging.getLogger("smart_capsule")


def configure_logging(debug: bool = False) -> None:
    log_file = logs_dir() / "smart_capsule.log"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    try:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    except OSError:  # pragma: no cover - read-only data folder
        pass
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)


def run_smoke_test(app) -> int:
    """Visit every registered page once; report failures instead of crashing."""
    from gui.navigation import NAV_ITEMS

    failures: list[tuple[str, str]] = []
    app.update_idletasks()
    for item in NAV_ITEMS:
        try:
            app.navigate(item.key)
            app.update_idletasks()
            app.update()
        except Exception as exc:  # noqa: BLE001 - reported below
            logger.exception("Page %s failed during smoke test", item.key)
            failures.append((item.key, repr(exc)))

    try:
        app.update_idletasks()
        app.after(120, app.destroy)
        app.update()
    except Exception:  # pragma: no cover - window teardown races
        pass

    for key, message in failures:
        print(f"SMOKE FAIL  {key}: {message}")
    if failures:
        print(f"SMOKE RESULT: {len(failures)} page(s) failed")
        return 1
    print(f"SMOKE RESULT: OK - {len(NAV_ITEMS)} pages built and routed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smart-capsule", description=f"{APP_NAME} - {TAGLINE}")
    parser.add_argument("--smoke", action="store_true", help="build every screen, verify, then exit")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--web", action="store_true", help="start the browser interface instead of the desktop window")
    parser.add_argument("--port", type=int, default=None, help="port for --web (default 8765 or $PORT)")
    parser.add_argument("--open", action="store_true", help="open the browser when used with --web")
    args = parser.parse_args(argv)

    configure_logging(args.debug)
    logger.info("Starting %s v%s (%s)", APP_NAME, VERSION, BUILD_STAGE)

    if args.web:
        from webapp.server import main as web_main

        web_args: list[str] = []
        if args.port is not None:
            web_args += ["--port", str(args.port)]
        if args.open:
            web_args.append("--open")
        return web_main(web_args)

    try:
        from gui.main_window import SmartCapsuleApp
    except Exception:
        logger.exception("The desktop UI could not be initialised")
        return 2

    try:
        app = SmartCapsuleApp()
    except Exception:
        logger.exception("Fatal error while creating the main window")
        return 3

    if args.smoke:
        return run_smoke_test(app)

    try:
        app.mainloop()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        logger.info("Interrupted by user")
    finally:
        logger.info("Shutting down")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
