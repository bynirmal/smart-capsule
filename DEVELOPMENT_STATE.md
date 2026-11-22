# SMART CAPSULE — DEVELOPMENT STATE

> Hand-off document. Keep it current after every change.

**Last updated:** 2026-11-22
**Current phase:** all eight phases implemented — release 1.0.0
**Build stage string:** `Phase 8 - Release`
**Version:** 1.0.0

---

## 1. Environment facts

| Fact | Value |
| --- | --- |
| Workspace | `C:\25KD1A05S1\mini` (project root == workspace root) |
| Interpreter | `py -3.14` → `.venv\Scripts\python.exe` (Python 3.14.6, Tk 8.6) |
| OS | Windows 64-bit, NVIDIA RTX 4050 (driver detected, no PyTorch) |
| Blocked by policy | third-party compiled `.pyd` extensions (`pydantic_core`, SQLAlchemy Cython) |
| Consequence | stdlib `sqlite3` + SQL migrations + dataclasses; no ORM/pydantic |
| Dev data folder | `.devdata/` (git-ignored) via `SMART_CAPSULE_HOME` |

## 2. Completed features

### Phase 1 — Foundation
CustomTkinter shell, 13-screen sidebar, design system + widget library, dashboard on live data,
SQLite schema (9 tables) with migrations/WAL/FK, GPU detection (torch → nvidia-smi → CPU), worker
threads, backups, persisted settings.

### Phase 2 — Capture
`core/parser_engine.py`: fence-aware role splitting, TXT/MD/JSON (incl. OpenAI `mapping` exports),
platform detection with confidence + reason, labelled token estimate, encoding/size guards.
`core/capture_engine.py`: write-free analysis, atomic draft save, rollback cleanup, draft
reconstruction.

### Phase 3 — Intelligence
`core/context_engine.py`: objective/description, instructions (requirement/preference/constraint
with certainty), technology classification, decisions, completed/pending tasks, errors paired with
solutions, explicit next action, inferred stage, warnings — all with message indices.
`core/compression_engine.py`: balanced / high / full, fixed priority order, protected sections,
per-mode budgets, labelled token estimates, markdown + plain rendering.

### Phase 4 — Capsule core
`core/capsule_generator.py` (document assembly, overrides, versioned persistence),
`core/validator.py` (structure/format/type checks), `exporters/` (JSON, Markdown, TXT, ZIP,
`.scapsule` with SHA-256 manifest), `core/capsule_importer.py` (manifest verification, traversal
rejection, atomic writes, attachment storage), `core/search_engine.py` (payload search + snippets).

### Phase 5 — Resume
`core/resume_engine.py`: structured brief + destination-specific continuation prompt
(ChatGPT/Claude/Gemini/Cursor/Other), explicit "no hidden memory" statement. Desktop resume screen:
copy prompt, copy brief, export prompt, open destination, library hand-off. Version history with
working restore (restores are recorded as new revisions).

### Phase 6 — Sidekick
`sidekick/floating_widget.py` (compact/expanded, draggable, always-on-top, opacity, status polling,
quick actions), `window_manager.py` (single instance), `keyboard_shortcuts.py` (Win32
`RegisterHotKey` + WM_HOTKEY polling with in-app fallback and conflict reporting),
`startup_manager.py` (HKCU Run key, opt-in), `quick_actions.py` (explicit clipboard quick save).
Sidebar button + `Ctrl+Shift+Space` toggle; settings page controls all of it for real.

### Phase 7 — Browser extension + web client
`browser_extension/`: MV3 manifest, popup, side panel, content script, versioned adapters
(chatgpt 1.1.0, claude 1.0.0, gemini 1.0.0, generic), background worker posting to the token-guarded
bridge. `webapp/`: stdlib `ThreadingHTTPServer` + single-page client (capture/library/capsule/
import/about), 11 API routes, loopback + Host guards, MIME overrides, attachment downloads.

### Phase 8 — Packaging / release
`packaging/smart_capsule.spec` (one-folder PyInstaller build, static assets + migrations bundled,
neural deps excluded), `docs/packaging.md`. Web mode available via `python -m webapp` and
`python main.py --web`.

## 3. Files created (by area)

```
main.py config.py requirements.txt requirements-ai.txt README.md DEVELOPMENT_STATE.md .gitignore
gui/     16 modules (shell, sidebar, navigation, theme, widgets, workers, 13 pages, base_page)
core/    parser_engine capture_engine context_engine compression_engine capsule_generator
         capsule_importer validator resume_engine search_engine __init__
exporters/ __init__ json markdown text zip capsule
ai/      gpu_manager __init__
database/ db models schema migrations/001_initial.sql __init__
storage/ backup __init__
sidekick/ floating_widget window_manager keyboard_shortcuts startup_manager quick_actions __init__
webapp/  server __init__ __main__ static/{index.html,styles.css,app.js}
browser_extension/ manifest.json background.js content.js popup.{html,js,css}
                   sidepanel.{html,js} adapters/adapters.js README.md
packaging/ smart_capsule.spec
tests/   conftest test_database test_gpu test_capture test_context test_compression
         test_capsule test_webapp
docs/    architecture capsule_format api_reference development_roadmap packaging
```

## 4. Architecture decisions (cumulative)

| # | Decision | Reason |
| --- | --- | --- |
| D1 | stdlib `sqlite3` + SQL migrations | ORM Cython extensions blocked by policy |
| D2 | dataclasses instead of pydantic | `pydantic_core` DLL blocked |
| D3 | one connection per unit of work | thread safety between UI and workers |
| D4 | lazy pages via module path | fast startup, no circular imports |
| D5 | layered GPU detection | GPU optional; human-readable fallback |
| D6 | no controls for unbuilt features | no fake buttons (all are now real) |
| D7 | `run_in_background` for slow work | Tk loop must never block |
| D8 | parser is pure and write-free | analysis testable without a DB |
| D9 | draft flagged in payload, not a new table | one capsule row per capture |
| D10 | messages stored relationally **and** in payload | search + export both work |
| D11 | platform confidence never `high` unless chosen | no invented certainty |
| D12 | document is JSON validated before every write | exporter/importer share one contract |
| D13 | web server stdlib-only, loopback + Host guard, token bridge | no dependencies, no rebinding |
| D14 | web API reuses `core/` directly | one engine for desktop, web, extension |
| D15 | hotkeys via Win32 with in-app fallback | global keys without extra packages |
| D16 | PostgreSQL sync omitted | `psycopg2` binaries blocked here; untested adapter would violate the rules |

## 5. Verification

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 70 passed |
| `python main.py --smoke` | 13 pages built and routed |
| Web API tests (`tests/test_webapp.py`) | 11 passed (CRUD, exports, round-trip import, bridge auth, traversal/Host guards) |
| Sidekick GUI probe | created → hidden → re-shown → destroyed; close button clears visibility |
| Browser run | capture → capsule → library → capsule detail → prompt verified in Chromium; no console errors |
| GPU probe | RTX 4050 reported via driver; CPU fallback notes present |

Known limitations (honest):
* The Chrome extension is code-complete and its manifest/JS parse cleanly, but it was **not**
  loaded unpacked against live ChatGPT/Claude/Gemini pages here, so adapter selectors are unverified.
* The PyInstaller build was not executed (PyInstaller is not installed in this venv).
* Native desktop window was never visually inspected; its construction and Sidekick lifecycle are
  verified programmatically.
* Cloud sync is intentionally out of scope for this release (blocked dependency + untestable here).

## 6. Next steps

1. Load the extension unpacked and verify capture on each adapter (markup may have changed).
2. Install PyInstaller and run the spec; verify `--smoke` and `--web` from the frozen build.
3. Optional: postgres sync adapter once a machine without the DLL policy is available.
