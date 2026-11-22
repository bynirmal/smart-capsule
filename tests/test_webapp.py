"""Web interface tests: every API route, security guards and round-trip import."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

TRANSCRIPT = """User: Build a FastAPI invoicing service. You must use PostgreSQL.

Assistant: Done: schema and models are implemented.

User: We decided to use SQLAlchemy for the ORM.

Assistant: The list endpoint returned a 500 error about a missing column.

User: The fix is to run the migration that adds total_amount.

User: Next step is adding pagination tests.
"""


@pytest.fixture()
def base_url(home):
    from database.db import reset_database_singleton
    from webapp.server import create_server

    reset_database_singleton()
    server = create_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        reset_database_singleton()


def call(base, method, path, payload=None, raw=None, headers=None):
    data = raw
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(base + path, data=data, method=method, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def test_status_endpoint(base_url) -> None:
    status, headers, body = call(base_url, "GET", "/api/status")
    assert status == 200
    assert headers["Content-Type"].startswith("application/json")
    payload = json.loads(body)
    assert payload["app"] == "Smart Capsule"
    assert payload["capsules"] == 0
    assert "hardware" in payload
    assert payload["format_version"] == 1


def test_static_client_is_served_with_executable_mime(base_url) -> None:
    status, headers, body = call(base_url, "GET", "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"SMART" in body

    status, headers, _ = call(base_url, "GET", "/app.js")
    assert status == 200
    assert "javascript" in headers["Content-Type"]

    status, _, _ = call(base_url, "GET", "/styles.css")
    assert status == 200


def test_static_traversal_is_blocked(base_url) -> None:
    status, _, _ = call(base_url, "GET", "/../config.py")
    assert status in {403, 404}


def test_preview_does_not_persist(base_url) -> None:
    status, _, body = call(base_url, "POST", "/api/preview", {"text": TRANSCRIPT, "platform": "Claude"})
    assert status == 200
    preview = json.loads(body)
    assert preview["messages"] >= 5
    assert preview["platform"] == "Claude"
    assert preview["confidence"] == "high"
    assert preview["code_blocks"] == 0

    _, _, body = call(base_url, "GET", "/api/status")
    assert json.loads(body)["capsules"] == 0


def test_create_list_detail_prompt_and_export(base_url, tmp_path) -> None:
    status, _, body = call(
        base_url, "POST", "/api/capsules", {"text": TRANSCRIPT, "platform": "Claude", "mode": "balanced"}
    )
    assert status == 201, body
    payload = json.loads(body)
    capsule_id = payload["capsule"]["id"]
    assert payload["document"]["project"]["name"]
    assert payload["document"]["progress"]["next_action"]
    assert "hidden model memory" in payload["prompt"]

    status, _, body = call(base_url, "GET", "/api/capsules")
    listing = json.loads(body)
    assert listing["count"] == 1
    assert listing["capsules"][0]["id"] == capsule_id
    assert listing["capsules"][0]["draft"] is False

    status, _, body = call(base_url, "GET", f"/api/capsules/{capsule_id}")
    assert status == 200
    detail = json.loads(body)
    assert detail["document"]["capsule_id"] == capsule_id
    assert len(detail["versions"]) == 1
    assert detail["brief"].startswith("# PROJECT HANDOFF")

    status, _, body = call(base_url, "GET", f"/api/capsules/{capsule_id}/prompt?destination=Cursor")
    assert status == 200
    assert json.loads(body)["url"].startswith("https://cursor")

    for fmt, expected in (
        ("scapsule", b"PK"),
        ("json", b"{"),
        ("markdown", b"#"),
        ("txt", b"You are continuing"),
        ("zip", b"PK"),
    ):
        status, headers, data = call(base_url, "GET", f"/api/capsules/{capsule_id}/export?format={fmt}")
        assert status == 200, (fmt, data[:200])
        assert data.startswith(expected)
        assert "Content-Disposition" in headers


def test_export_roundtrip_through_web_import(base_url) -> None:
    _, _, body = call(base_url, "POST", "/api/capsules", {"text": TRANSCRIPT, "mode": "full"})
    original = json.loads(body)["capsule"]["id"]

    status, _, data = call(base_url, "GET", f"/api/capsules/{original}/export?format=scapsule")
    assert status == 200

    status, _, body = call(
        base_url,
        "POST",
        "/api/import?filename=handoff.scapsule",
        raw=data,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert status == 201, body
    imported = json.loads(body)
    assert imported["capsule"]["id"] != original
    assert imported["capsule"]["title"]

    _, _, body = call(base_url, "GET", "/api/status")
    assert json.loads(body)["capsules"] == 2


def test_update_creates_new_version(base_url) -> None:
    _, _, body = call(base_url, "POST", "/api/capsules", {"text": TRANSCRIPT})
    capsule_id = json.loads(body)["capsule"]["id"]

    status, _, body = call(
        base_url,
        "PATCH",
        f"/api/capsules/{capsule_id}",
        {"next_action": "Ship pagination today", "name": "Invoice API"},
    )
    assert status == 200, body
    updated = json.loads(body)
    assert updated["document"]["progress"]["next_action"] == "Ship pagination today"
    assert updated["capsule"]["title"] == "Invoice API"

    _, _, body = call(base_url, "GET", f"/api/capsules/{capsule_id}")
    assert len(json.loads(body)["versions"]) == 2

    status, _, _ = call(base_url, "PATCH", f"/api/capsules/{capsule_id}", {})
    assert status == 400


def test_delete_capsule(base_url) -> None:
    _, _, body = call(base_url, "POST", "/api/capsules", {"text": TRANSCRIPT})
    capsule_id = json.loads(body)["capsule"]["id"]

    status, _, _ = call(base_url, "DELETE", f"/api/capsules/{capsule_id}")
    assert status == 200
    status, _, _ = call(base_url, "GET", f"/api/capsules/{capsule_id}")
    assert status == 404


def test_unknown_routes_and_bad_payloads(base_url) -> None:
    status, _, _ = call(base_url, "GET", "/api/nope")
    assert status == 404

    status, _, body = call(base_url, "POST", "/api/capsules", {"text": "   "})
    assert status == 400
    assert "error" in json.loads(body)

    status, _, body = call(base_url, "GET", "/api/capsules/deadbeef/export?format=pdf")
    assert status == 404  # capsule does not exist


def test_bridge_requires_token(base_url, home) -> None:
    status, _, _ = call(base_url, "POST", "/api/bridge/capture", {"text": TRANSCRIPT})
    assert status == 401

    from webapp.server import bridge_token

    token = bridge_token()
    status, _, body = call(
        base_url,
        "POST",
        "/api/bridge/capture",
        {"text": TRANSCRIPT, "platform": "Gemini"},
        headers={"X-SmartCapsule-Token": token},
    )
    assert status == 201, body
    payload = json.loads(body)
    assert payload["id"]
    assert payload["messages"] >= 5

    status, _, _ = call(
        base_url, "POST", "/api/bridge/capture", {"text": TRANSCRIPT}, headers={"X-SmartCapsule-Token": "wrong"}
    )
    assert status == 401


def test_bridge_token_file_written(base_url) -> None:
    from webapp.server import bridge_token

    token = bridge_token()
    path = bridge_token_path = __import__("config").data_dir() / "bridge_token.txt"
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip() == token
    assert bridge_token_path == path


def test_health_endpoint_is_public(base_url, monkeypatch) -> None:
    monkeypatch.setenv("SMART_CAPSULE_PASSWORD", "s3cret")
    status, _, body = call(base_url, "GET", "/healthz")
    assert status == 200
    assert json.loads(body)["ok"] is True


def test_password_gate_protects_api_and_static(base_url, monkeypatch) -> None:
    import base64

    monkeypatch.setenv("SMART_CAPSULE_PASSWORD", "s3cret")

    status, headers, _ = call(base_url, "GET", "/api/status")
    assert status == 401
    assert headers["WWW-Authenticate"].startswith("Basic")

    status, _, _ = call(base_url, "GET", "/")
    assert status == 401

    good = base64.b64encode(b"capsule:s3cret").decode("ascii")
    status, _, _ = call(base_url, "GET", "/api/status", headers={"Authorization": f"Basic {good}"})
    assert status == 200

    wrong = base64.b64encode(b"capsule:nope").decode("ascii")
    status, _, _ = call(base_url, "GET", "/api/status", headers={"Authorization": f"Basic {wrong}"})
    assert status == 401


def test_no_password_gate_when_variable_unset(base_url, monkeypatch) -> None:
    monkeypatch.delenv("SMART_CAPSULE_PASSWORD", raising=False)
    status, _, _ = call(base_url, "GET", "/api/status")
    assert status == 200
