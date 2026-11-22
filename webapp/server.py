"""HTTP API + static hosting for the Smart Capsule web client.

Run:
    python -m webapp                 # http://127.0.0.1:8765
    python -m webapp --port 9000 --open

Security
--------
* Binds to loopback by default; a non-loopback host is refused unless
  ``--allow-remote`` is passed deliberately.
* Only explicit API routes are exposed; static files are resolved inside
  ``webapp/static`` (path traversal rejects any escape).
* The browser-extension bridge requires a per-install token stored in the data
  directory (``bridge_token.txt``) and compared in constant time.
"""

from __future__ import annotations

import argparse
import base64
import hmac
import json
import logging
import mimetypes
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import APP_NAME, BUILD_STAGE, CAPSULE_FORMAT_VERSION, VERSION, data_dir  # noqa: E402
from core.capsule_generator import generate_capsule, save_document  # noqa: E402
from core.capsule_importer import ImportError_, import_capsule  # noqa: E402
from core.capture_engine import CaptureEngine  # noqa: E402
from core.parser_engine import ParseError, parse_text  # noqa: E402
from core.resume_engine import DESTINATION_URLS, DESTINATIONS, continuation_prompt, context_brief  # noqa: E402
from core.search_engine import search  # noqa: E402
from core.validator import validate_document  # noqa: E402
from database.db import get_database  # noqa: E402
from database.models import parse_datetime  # noqa: E402
from exporters import SUFFIXES, export_document  # noqa: E402

logger = logging.getLogger("smart_capsule.web")

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY = 64 * 1024 * 1024
EXPORT_MEDIA = {
    "json": "application/json",
    "markdown": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "zip": "application/zip",
    "scapsule": "application/octet-stream",
}

# Windows' registry-based mimetypes can report .js as text/plain, which makes
# browsers refuse to execute it. These explicit mappings avoid that.
STATIC_MEDIA = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


# --------------------------------------------------------------------------- #
# Bridge token
# --------------------------------------------------------------------------- #
def bridge_token() -> str:
    """Per-install token used by the browser extension."""
    db = get_database()
    token = db.get_setting("bridge_token", "")
    if not token:
        token = secrets.token_urlsafe(32)
        db.set_setting("bridge_token", token)
    try:
        path = data_dir() / "bridge_token.txt"
        path.write_text(token, encoding="utf-8")
        path.chmod(0o600)
    except OSError:  # pragma: no cover - best effort on locked-down systems
        logger.warning("Could not persist the bridge token file", exc_info=True)
    return token


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #
def _iso(value) -> str | None:
    parsed = parse_datetime(value)
    return parsed.isoformat() if parsed else None


def capsule_summary(capsule) -> dict[str, Any]:
    payload = capsule.payload()
    return {
        "id": capsule.id,
        "title": capsule.title,
        "platform": capsule.source_platform,
        "mode": capsule.compression_mode,
        "summary": capsule.summary,
        "next_action": capsule.next_action,
        "tokens": capsule.token_estimate,
        "draft": bool(payload.get("draft")),
        "created_at": _iso(capsule.created_at),
        "updated_at": _iso(capsule.updated_at),
    }


def bootstrap_document(document: Mapping[str, Any]) -> dict[str, Any]:
    """Backward-compatible view of a draft payload that has no document yet."""
    payload = dict(document)
    if "project" not in payload:
        capture = payload.get("capture") or {}
        payload.setdefault(
            "project",
            {
                "name": capture.get("title") or "Untitled capture",
                "objective": "",
                "description": "",
                "stage": "capture only",
                "technologies": [],
                "constraints": [],
            },
        )
        payload.setdefault("summary", "")
        payload.setdefault("progress", {"next_action": "", "pending": [], "completed": [], "errors": []})
        payload.setdefault("compression", {"mode": "balanced", "capsule_tokens": 0, "token_method": "n/a"})
        payload.setdefault("source", {"platform": capture.get("platform") or "Other"})
    return payload


# --------------------------------------------------------------------------- #
# Route handlers
# --------------------------------------------------------------------------- #
def api_status(_db, _body: Mapping[str, Any], _query: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    from ai.gpu_manager import GpuManager

    db = get_database()
    stats = db.stats()
    report = GpuManager().report
    return 200, {
        "app": APP_NAME,
        "version": VERSION,
        "stage": BUILD_STAGE,
        "format_version": CAPSULE_FORMAT_VERSION,
        "capsules": stats.total_capsules,
        "projects": stats.total_projects,
        "platforms": stats.platforms,
        "storage_bytes": db.storage_usage_bytes(),
        "hardware": {
            "device": report.status_line,
            "has_gpu": report.has_gpu,
            "neural": report.torch_installed,
            "notes": list(report.notes)[:4],
        },
        "destinations": list(DESTINATIONS),
        "data_dir": str(data_dir()),
    }


def api_preview(_db, body: Mapping[str, Any], _query: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    text = str(body.get("text") or "")
    platform = body.get("platform") or None
    if not text.strip():
        raise ApiError(400, "Paste a conversation first.")
    try:
        result = parse_text(text, platform_hint=platform)
    except ParseError as exc:
        raise ApiError(400, str(exc)) from exc
    return 200, {
        "title": result.title,
        "platform": result.platform,
        "confidence": result.platform_confidence,
        "reason": result.platform_reason,
        "messages": result.message_count,
        "code_blocks": len(result.code_blocks),
        "characters": result.character_count,
        "tokens": result.token_estimate,
        "token_method": "characters/4 heuristic",
        "roles": result.roles,
        "warnings": result.warnings,
    }


def api_create_capsule(_db, body: Mapping[str, Any], _query: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    db = get_database()
    text = str(body.get("text") or "")
    if not text.strip():
        raise ApiError(400, "Nothing to capture: the text is empty.")

    platform = body.get("platform") or None
    mode = str(body.get("mode") or db.get_setting("default_compression", "balanced"))
    if mode not in {"balanced", "high", "full"}:
        raise ApiError(400, f"Unknown compression mode: {mode}")

    engine = CaptureEngine(db)
    try:
        result = engine.analyze_text(text, platform_hint=platform)
    except ParseError as exc:
        raise ApiError(400, str(exc)) from exc

    draft_id = engine.save_draft(result)
    try:
        payload = db.get_capsule(draft_id).payload()
        conversation_id = (payload.get("capture") or {}).get("conversation_id")
        overrides = {
            "name": body.get("name"),
            "objective": body.get("objective"),
            "next_action": body.get("next_action"),
        }
        capsule_id, document = generate_capsule(
            db,
            result,
            capsule_id=draft_id,
            mode=mode,
            overrides={key: value for key, value in overrides.items() if value},
            conversation_id=conversation_id,
        )
    except Exception:
        db.delete_capsule(draft_id)
        raise

    capsule = db.get_capsule(capsule_id)
    return 201, {
        "capsule": capsule_summary(capsule) if capsule else {"id": capsule_id},
        "document": document,
        "prompt": continuation_prompt(document, "Other"),
        "preview": {
            "messages": result.message_count,
            "code_blocks": len(result.code_blocks),
            "platform": result.platform,
            "confidence": result.platform_confidence,
            "warnings": result.warnings,
        },
    }


def api_list_capsules(_db, _body, query: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    db = get_database()
    term = (query.get("q") or "").strip()
    hits = search(db, term, limit=100)
    return 200, {
        "query": term,
        "count": len(hits),
        "capsules": [
            {**capsule_summary(hit.capsule), "snippet": hit.snippet, "matched": hit.where} for hit in hits
        ],
    }


def _resolve_capsule(capsule_id: str):
    db = get_database()
    capsule = db.get_capsule(capsule_id)
    if capsule is None:
        raise ApiError(404, "Capsule not found.")
    return db, capsule


def api_get_capsule(_db, _body, _query, capsule_id: str) -> tuple[int, dict[str, Any]]:
    db, capsule = _resolve_capsule(capsule_id)
    document = bootstrap_document(capsule.payload())
    versions = db.query(
        "SELECT version_number, note, created_at FROM capsule_versions WHERE capsule_id = ? "
        "ORDER BY version_number DESC",
        (capsule_id,),
    )
    return 200, {
        "capsule": capsule_summary(capsule),
        "document": document,
        "prompt": continuation_prompt(document, "Other"),
        "brief": context_brief(document),
        "urls": DESTINATION_URLS,
        "versions": [
            {
                "version": row["version_number"],
                "note": row["note"],
                "created_at": _iso(row["created_at"]),
            }
            for row in versions
        ],
    }


def api_update_capsule(_db, body: Mapping[str, Any], _query, capsule_id: str) -> tuple[int, dict[str, Any]]:
    db, capsule = _resolve_capsule(capsule_id)
    document = bootstrap_document(capsule.payload())

    project = document.setdefault("project", {})
    progress = document.setdefault("progress", {})
    changed = False
    if str(body.get("name") or "").strip():
        project["name"] = str(body["name"]).strip()[:160]
        changed = True
    if str(body.get("objective") or "").strip():
        project["objective"] = str(body["objective"]).strip()[:600]
        changed = True
    if str(body.get("next_action") or "").strip():
        progress["next_action"] = str(body["next_action"]).strip()[:600]
        changed = True
    if not changed:
        raise ApiError(400, "Nothing to update.")

    if project.get("name"):
        document["summary"] = str(document.get("summary") or "").replace(
            capsule.title, str(project["name"])
        )
    save_document(db, document, capsule_id=capsule_id, note="Edited capsule fields")
    updated = db.get_capsule(capsule_id)
    return 200, {"capsule": capsule_summary(updated), "document": bootstrap_document(updated.payload())}


def api_delete_capsule(_db, _body, _query, capsule_id: str) -> tuple[int, dict[str, Any]]:
    db, _capsule = _resolve_capsule(capsule_id)
    db.delete_capsule(capsule_id)
    return 200, {"deleted": capsule_id}


def api_export(_db, _body, query: Mapping[str, str], capsule_id: str) -> tuple[int, bytes, dict[str, str]]:
    db, capsule = _resolve_capsule(capsule_id)
    fmt = (query.get("format") or "scapsule").lower()
    if fmt == "md":
        fmt = "markdown"
    if fmt not in EXPORT_MEDIA:
        raise ApiError(400, f"Unsupported export format: {fmt}")

    document = bootstrap_document(capsule.payload())
    if fmt in {"zip", "scapsule"}:
        validation = validate_document(document)
        validation.raise_if_invalid()

    from tempfile import TemporaryDirectory

    safe_title = "".join(ch for ch in capsule.title if ch.isalnum() or ch in " -_")[:60].strip() or "capsule"
    with TemporaryDirectory() as folder:
        target = Path(folder) / f"{safe_title}{SUFFIXES[fmt]}"
        try:
            written = export_document(document, target, fmt)
        except ValueError as exc:
            raise ApiError(400, str(exc)) from exc
        data = written.read_bytes()

    filename = f"{safe_title}{SUFFIXES[fmt]}"
    return 200, data, {
        "Content-Type": EXPORT_MEDIA[fmt],
        "Content-Disposition": f'attachment; filename="{filename}"',
    }


def api_prompt(_db, _body, query: Mapping[str, str], capsule_id: str) -> tuple[int, dict[str, Any]]:
    _db, capsule = _resolve_capsule(capsule_id)
    destination = query.get("destination") or "Other"
    if destination not in DESTINATIONS:
        raise ApiError(400, f"Unknown destination: {destination}")
    document = bootstrap_document(capsule.payload())
    return 200, {
        "destination": destination,
        "prompt": continuation_prompt(document, destination),
        "brief": context_brief(document),
        "url": DESTINATION_URLS.get(destination, ""),
    }


def api_import(_db, body: bytes, query: Mapping[str, str]) -> tuple[int, dict[str, Any]]:
    db = get_database()
    filename = (query.get("filename") or "capsule.scapsule").replace("/", "_").replace("\\", "_")
    if not body:
        raise ApiError(400, "Empty upload.")

    from tempfile import TemporaryDirectory

    suffix = Path(filename).suffix.lower()
    if suffix not in {".scapsule", ".zip", ".json"}:
        raise ApiError(400, "Upload a .scapsule, .zip or .json capsule file.")

    with TemporaryDirectory() as folder:
        path = Path(folder) / f"upload{suffix}"
        path.write_bytes(body)
        try:
            result = import_capsule(db, path)
        except ImportError_ as exc:
            raise ApiError(400, str(exc)) from exc
        except ValueError as exc:
            raise ApiError(400, f"Invalid capsule: {exc}") from exc

    capsule = db.get_capsule(result.capsule_id)
    return 201, {
        "capsule": capsule_summary(capsule) if capsule else {"id": result.capsule_id},
        "warnings": result.warnings,
        "attachments": result.attachments,
    }


def api_bridge_capture(_db, body: Mapping[str, Any], _query) -> tuple[int, dict[str, Any]]:
    """Endpoint used by the Chrome extension (token-authenticated)."""
    db = get_database()
    text = str(body.get("text") or "")
    if not text.strip():
        raise ApiError(400, "No conversation text received from the extension.")

    engine = CaptureEngine(db)
    try:
        result = engine.analyze_text(text, platform_hint=body.get("platform"))
    except ParseError as exc:
        raise ApiError(400, str(exc)) from exc

    draft_id = engine.save_draft(result)
    try:
        payload = db.get_capsule(draft_id).payload()
        capsule_id, document = generate_capsule(
            db,
            result,
            capsule_id=draft_id,
            mode=str(body.get("mode") or db.get_setting("default_compression", "balanced")),
            conversation_id=(payload.get("capture") or {}).get("conversation_id"),
        )
    except Exception:
        db.delete_capsule(draft_id)
        raise

    capsule = db.get_capsule(capsule_id)
    return 201, {
        "id": capsule_id,
        "title": capsule.title if capsule else result.title,
        "messages": result.message_count,
        "platform": result.platform,
        "summary": capsule.summary if capsule else "",
    }


JSON_ROUTES: list[tuple[str, str, Callable]] = [
    ("GET", r"^/api/status$", api_status),
    ("POST", r"^/api/preview$", api_preview),
    ("POST", r"^/api/capsules$", api_create_capsule),
    ("GET", r"^/api/capsules$", api_list_capsules),
    ("GET", r"^/api/capsules/([0-9a-f]{6,64})$", api_get_capsule),
    ("PATCH", r"^/api/capsules/([0-9a-f]{6,64})$", api_update_capsule),
    ("DELETE", r"^/api/capsules/([0-9a-f]{6,64})$", api_delete_capsule),
    ("GET", r"^/api/capsules/([0-9a-f]{6,64})/prompt$", api_prompt),
    ("POST", r"^/api/bridge/capture$", api_bridge_capture),
]


# --------------------------------------------------------------------------- #
# HTTP handler
# --------------------------------------------------------------------------- #
class SmartCapsuleHandler(BaseHTTPRequestHandler):
    server_version = f"SmartCapsule/{VERSION}"
    protocol_version = "HTTP/1.1"

    # -- guards ------------------------------------------------------------
    def _guard(self) -> bool:
        """Reject non-loopback traffic, DNS-rebinding Host headers and, on a
        public deployment, requests without the shared password."""
        if not getattr(self.server, "allow_remote", False):
            client = self.client_address[0]
            if client not in {"127.0.0.1", "::1", "localhost"}:
                self._json(403, {"error": "This server only accepts local connections."})
                return False

            host_header = (self.headers.get("Host") or "").strip().lower()
            if host_header:
                if host_header.startswith("["):
                    hostname = host_header.split("]")[0] + "]"
                else:
                    hostname = host_header.rsplit(":", 1)[0]
                if hostname not in LOOPBACK_HOSTS:
                    self._json(403, {"error": "Unexpected Host header."})
                    return False

        if not self._basic_auth_ok():
            self._send(
                401,
                b'{"error": "Authentication required."}',
                {
                    "Content-Type": "application/json; charset=utf-8",
                    "WWW-Authenticate": 'Basic realm="Smart Capsule", charset="UTF-8"',
                    "Cache-Control": "no-store",
                },
            )
            return False
        return True

    def _basic_auth_ok(self) -> bool:
        """Optional single-password gate (``SMART_CAPSULE_PASSWORD``).

        Local runs have no password and stay open; a hosted copy sets the
        variable so the URL alone does not expose the capsule library.
        """
        expected = os.environ.get("SMART_CAPSULE_PASSWORD", "")
        if not expected:
            return True
        if urllib.parse.urlsplit(self.path).path == "/healthz":
            return True
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Basic "):
            return False
        try:
            decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        _username, _, supplied = decoded.partition(":")
        return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))

    # -- helpers -----------------------------------------------------------
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - stdlib signature
        logger.debug("%s - %s", self.address_string(), fmt % args)

    def _cors(self) -> dict[str, str]:
        origin = self.headers.get("Origin") or ""
        if origin.startswith(("chrome-extension://", "moz-extension://")) or origin.startswith(
            ("http://127.0.0.1", "http://localhost")
        ):
            return {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-SmartCapsule-Token",
                "Vary": "Origin",
            }
        return {}

    def _send(self, status: int, body: bytes, headers: Mapping[str, str]) -> None:
        self.send_response(status)
        for key, value in {**self._cors(), **headers}.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"})

    def _read_body(self, limit: int = MAX_BODY) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError(400, "Invalid Content-Length header.")
        if length < 0 or length > limit:
            raise ApiError(413, "Request body too large.")
        return self.rfile.read(length) if length else b""

    def _json_body(self) -> dict[str, Any]:
        raw = self._read_body(8 * 1024 * 1024)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(400, f"Invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise ApiError(400, "The JSON body must be an object.")
        return data

    # -- verbs -------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802 - stdlib naming
        self._send(HTTPStatus.NO_CONTENT, b"", {})

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        if not self._guard():
            return
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}

        if path == "/healthz":
            self._json(200, {"ok": True, "version": VERSION})
            return

        if path.startswith("/api/"):
            self._dispatch("GET", path, query, b"")
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        if not self._guard():
            return
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = {key: values[-1] for key, values in urllib.parse.parse_qs(parsed.query).items()}

        if path == "/api/import":
            try:
                status, payload = api_import(get_database(), self._read_body(), query)
            except ApiError as exc:
                self._json(exc.status, {"error": exc.message})
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("Import failed")
                self._json(500, {"error": f"Import failed: {exc}"})
                return
            self._json(status, payload)
            return

        self._dispatch("POST", path, query, self._read_body(8 * 1024 * 1024))

    def do_PATCH(self) -> None:  # noqa: N802
        if not self._guard():
            return
        parsed = urllib.parse.urlsplit(self.path)
        self._dispatch("PATCH", urllib.parse.unquote(parsed.path), {}, self._read_body(1024 * 1024))

    def do_DELETE(self) -> None:  # noqa: N802
        if not self._guard():
            return
        parsed = urllib.parse.urlsplit(self.path)
        self._dispatch("DELETE", urllib.parse.unquote(parsed.path), {}, b"")

    # -- dispatch ----------------------------------------------------------
    def _dispatch(self, method: str, path: str, query: Mapping[str, str], raw: bytes) -> None:
        import re

        try:
            if path.startswith("/api/bridge/") and not self._bridge_authorized():
                raise ApiError(401, "Missing or invalid bridge token.")

            if path.endswith("/export"):
                match = re.match(r"^/api/capsules/([0-9a-f]{6,64})/export$", path)
                if match and method == "GET":
                    status, data, headers = api_export(get_database(), {}, query, match.group(1))
                    self._send(status, data, headers)
                    return

            for route_method, pattern, handler in JSON_ROUTES:
                if route_method != method:
                    continue
                match = re.match(pattern, path)
                if not match:
                    continue
                if handler is api_bridge_capture:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                    status, result = handler(get_database(), payload, query)
                elif method in {"POST", "PATCH"}:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                    if match.groups():
                        status, result = handler(get_database(), payload, query, *match.groups())
                    else:
                        status, result = handler(get_database(), payload, query)
                else:
                    if match.groups():
                        status, result = handler(get_database(), {}, query, *match.groups())
                    else:
                        status, result = handler(get_database(), {}, query)
                self._json(status, result)
                return

            raise ApiError(404, f"Unknown API route: {method} {path}")
        except ApiError as exc:
            self._json(exc.status, {"error": exc.message})
        except ParseError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - never leak a traceback to the client
            logger.exception("Unhandled API error on %s %s", method, path)
            self._json(500, {"error": f"Internal error: {exc}"})

    def _bridge_authorized(self) -> bool:
        provided = self.headers.get("X-SmartCapsule-Token") or ""
        expected = bridge_token()
        return bool(provided) and hmac.compare_digest(provided, expected)

    # -- static ------------------------------------------------------------
    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._json(403, {"error": "Forbidden path."})
            return

        if not candidate.is_file():
            if "." not in Path(relative).name:
                candidate = STATIC_DIR / "index.html"
            else:
                self._json(404, {"error": "Not found."})
                return

        content_type = STATIC_MEDIA.get(candidate.suffix.lower())
        if content_type is None:
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            if content_type.startswith("text/"):
                content_type += "; charset=utf-8"
        data = candidate.read_bytes()
        self._send(200, data, {"Content-Type": content_type, "Cache-Control": "no-cache"})


class SmartCapsuleServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    allow_remote = False


def create_server(host: str = "127.0.0.1", port: int = 8765, allow_remote: bool = False) -> SmartCapsuleServer:
    server = SmartCapsuleServer((host, port), SmartCapsuleHandler)
    server.allow_remote = allow_remote
    return server


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smart-capsule-web", description="Smart Capsule web interface")
    parser.add_argument("--host", default=os.environ.get("SMART_CAPSULE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--open", action="store_true", help="open the browser after start")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        default=_env_flag("SMART_CAPSULE_ALLOW_REMOTE"),
        help="allow binding to a non-loopback host (SMART_CAPSULE_ALLOW_REMOTE=1)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
    )

    if args.host not in {"127.0.0.1", "localhost", "::1"} and not args.allow_remote:
        print("Refusing to bind to a non-loopback host without --allow-remote.", file=sys.stderr)
        return 2

    get_database()
    token = bridge_token()
    server = create_server(args.host, args.port, allow_remote=args.allow_remote)
    url = f"http://{args.host}:{server.server_address[1]}/"
    print(f"{APP_NAME} web interface v{VERSION} ({BUILD_STAGE})")
    print(f"  URL:        {url}")
    print(f"  Data:       {data_dir()}")
    print(f"  Bridge:     {data_dir() / 'bridge_token.txt'} (paste into the extension options)")
    print(f"  Password:   {'set' if os.environ.get('SMART_CAPSULE_PASSWORD') else 'none (open)'}")
    print("  Press Ctrl+C to stop.")

    if args.allow_remote and not os.environ.get("SMART_CAPSULE_PASSWORD"):
        print(
            "WARNING: serving on a public interface without SMART_CAPSULE_PASSWORD. "
            "Anyone who knows the URL can read and delete your capsules.",
            file=sys.stderr,
        )

    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
