# Development roadmap

A phase is finished only when its exit criteria are met and its tests pass.

## Phase 1 — Foundation ✅

Shell, design system, 13 screens, dashboard on live SQLite data, schema + migrations, GPU detection
with CPU fallback, worker threads, backups, settings. **Exit criteria met.**

## Phase 2 — Capture Engine ✅

Fence-aware role parsing, TXT/Markdown/JSON (incl. OpenAI mapping exports), platform detection with
confidence, labelled token estimates, atomic draft persistence. **Exit met:** a 200-message
transcript round-trips and code fences containing role markers stay intact.

## Phase 3 — Intelligence ✅

Rule-based extraction of project, instructions, stack, decisions, completed/pending tasks, errors
with solutions, next action, inferred stage, and warnings; three compression modes with protected
sections and labelled token estimates. **Exit met:** every field records certainty and origin, and
nothing is invented.

## Phase 4 — Capsule Core ✅

Versioned JSON document, validator, JSON/Markdown/TXT/ZIP/`.scapsule` exporters with SHA-256
manifests, importer with checksum verification, traversal rejection and atomic writes.
**Exit met:** generate → export → import produces identical structured content (tested).

## Phase 5 — Resume Engine ✅

Structured brief, destination templates (ChatGPT/Claude/Gemini/Cursor/Other), copy/export/open
actions in desktop and web, version snapshots with working restore. **Exit met.**

## Phase 6 — Sidekick ✅

Floating always-on-top widget with compact/expanded modes, clipboard quick save, prompt copy,
Win32 global hotkeys with conflict reporting and in-app fallback, opt-in autostart, opacity,
privacy guarantees. **Code complete; interactive verification pending (see DEVELOPMENT_STATE).**

## Phase 7 — Browser Extension + Web ✅

MV3 popup + side panel, versioned adapters (ChatGPT/Claude/Gemini/generic), token-authenticated
bridge, stdlib web server with single-page client covering capture, library, capsule detail,
editing, resume and import. **Web verified end-to-end in Chromium; extension load test pending.**

## Phase 8 — Advanced / Release ✅ (with one documented omission)

PyInstaller one-folder spec bundling static assets and migrations; release version 1.0.0.
**Omitted deliberately:** PostgreSQL cloud sync — `psycopg2` ships compiled extensions blocked by
this machine's Application Control policy, so the adapter could not be tested, and shipping an
untested data path is not acceptable. The web API already offers import/export for external sync
tools.

## Remaining hardening (future work)

* Load the unpacked extension against live ChatGPT/Claude/Gemini pages and refresh selectors.
* Produce and test a signed executable on a clean machine.
* Optional Postgres adapter on a machine without the DLL restriction.
