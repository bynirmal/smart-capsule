# SMART CAPSULE

**One click. Complete context. Continue anywhere.**

Smart Capsule captures the working state of an AI conversation — requirements, decisions, code,
tasks, errors and the next action — compresses it into a portable capsule, and restores that
context on another AI platform.

It is not a chat archive. It is an AI working-memory portability system.

```
CAPTURE  →  ORGANIZE  →  COMPRESS  →  EXPORT (.scapsule)  →  IMPORT  →  CONTINUE
```

---

## Two ways to use it

### 1. Web app (primary)

```bash
python -m webapp            # http://127.0.0.1:8765
python -m webapp --open     # start and open the browser
```

The browser client shares the same SQLite database and engines as the desktop app: capture,
generate, review, edit, export, import and resume — all local.

| Screen | What it does |
| --- | --- |
| Capture | Paste a transcript, choose platform + compression, preview counts, create the capsule |
| Library | Search, open, export (.scapsule / JSON / Markdown / TXT / ZIP) or delete |
| Capsule | Full structured state, editable project/objective/next action, versioned saves |
| Resume | Destination-specific continuation prompt: copy, download or open the AI site |
| Import | Drop a `.scapsule`, `.zip` or `.json`; checksums and format are validated first |

The server binds to loopback only, rejects unexpected `Host` headers (DNS-rebinding guard), and
exposes the extension bridge behind a per-install token.

#### Deploy it

```bash
docker build -t smart-capsule .
docker run -d -p 8765:8765 \
  -e SMART_CAPSULE_PASSWORD='choose-a-long-one' \
  -v smart-capsule-data:/data smart-capsule
```

`render.yaml` deploys the same image to Render with a persistent disk. A hosted copy **must** set
`SMART_CAPSULE_PASSWORD` — otherwise anyone with the URL can read your capsules. Full steps and the
free-plan trade-off are in [docs/deploy.md](docs/deploy.md).

### 2. Desktop app (CustomTkinter)

```bash
python main.py            # main window
python main.py --smoke    # build + route all 13 screens, then exit
python main.py --debug    # verbose logging
```

Dashboard, capture, capsule generation/review, library, import, resume, GPU monitor, AI settings,
sidekick settings, platforms, version history and storage — plus a floating **Sidekick**
(`Ctrl+Shift+Space`) with `Ctrl+Shift+S` quick save and `Ctrl+Shift+C` clipboard capture.

---

## Install

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Python 3.11+ with Tk 8.6. No GPU required; CUDA / ROCm / Apple MPS are used when present.

| Check | Command |
| --- | --- |
| Tests (70) | `python -m pytest -q` |
| Desktop screens | `python main.py --smoke` |
| Web API | `python -m pytest tests/test_webapp.py -q` |

## Data

| Platform | Location |
| --- | --- |
| Windows | `%APPDATA%\SmartCapsule` |
| macOS | `~/Library/Application Support/SmartCapsule` |
| Linux | `~/.local/share/smart-capsule` |

Override with `SMART_CAPSULE_HOME`. The folder holds `smart_capsule.db` (WAL), `attachments/`,
`backups/`, `logs/` and `bridge_token.txt` for the browser extension.

## Browser extension

`browser_extension/` is a Manifest V3 extension with a popup and side panel, versioned adapters for
ChatGPT / Claude / Gemini (plus a generic fallback), and a token-authenticated bridge to the local
server. Load it unpacked after starting the web app; see
[`browser_extension/README.md`](browser_extension/README.md).

## Optional AI stack

```bash
python -m pip install -r requirements-ai.txt
```

Without it, the deterministic rule-based extractor does all the work and GPU detection falls back
to the driver/CPU. PyTorch supports a limited range of Python versions; if `pip` has no wheel, use
a supported interpreter for that environment — every non-neural feature keeps working.

### Why `sqlite3` instead of SQLAlchemy / Pydantic

Both were evaluated and dropped: this machine's Application Control policy blocks third-party
compiled extensions (`_pydantic_core.dll`, `sqlalchemy/**/_*_cy.pyd`), so the app could not import
them. Storage uses the standard-library `sqlite3` module with explicit SQL migrations, and the data
model uses dataclasses. The schema and the portable capsule document are unchanged by that choice.

---

## Architecture

```
gui/          CustomTkinter screens (13), widgets, theme, background workers
sidekick/     floating widget, global hotkeys, autostart
core/         parser · context · compression · capsule generator/importer · resume · search · validator
exporters/    JSON · Markdown · TXT · ZIP · .scapsule (hash manifest)
ai/           GPU detection (torch → nvidia-smi → CPU), model registry
database/     SQL schema, migrations, sqlite3 repository, dataclass models
storage/      attachments, online backups
webapp/       stdlib HTTP server + single-page browser client
browser_extension/  MV3 extension, adapters, bridge client
packaging/    PyInstaller spec
tests/        70 pytest cases across storage, GPU, capture, context, compression, capsule, sidekick, web API
```

* **Local first** — everything on disk; nothing transmitted implicitly.
* **Never blocks** — all slow work runs on worker threads and returns to the UI thread.
* **One engine** — desktop, web and extension share `core/`; there is no second implementation.
* **Honest extraction** — every inferred field is labelled, and missing information is reported
  instead of invented.

Full details: [`docs/architecture.md`](docs/architecture.md) ·
[`docs/capsule_format.md`](docs/capsule_format.md) ·
[`docs/api_reference.md`](docs/api_reference.md) ·
[`DEVELOPMENT_STATE.md`](DEVELOPMENT_STATE.md)

## Privacy

* Capture only ever happens from an explicit click, shortcut or extension button.
* No screenshots, no reading other windows, no background clipboard polling.
* No passwords, cookies or session tokens; imported text is treated as data, never instructions.
* Local-only AI processing by default; external providers require explicit configuration.
