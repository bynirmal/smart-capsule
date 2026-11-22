# Architecture

## 1. Goals that shape the design

1. **Local first.** Every capsule, conversation and attachment lives on the user's machine.
   Nothing leaves it without an explicit, per-action decision.
2. **Runs anywhere.** A GPU and a neural model are optimisations. A CPU-only laptop with a
   standard Python install must get the full application.
3. **Never blocks.** Tkinter has one thread for the UI; anything slower than a frame runs in a
   worker and delivers its result back through `widget.after`.
4. **One engine, many clients.** Desktop, floating Sidekick and browser extension will share the
   same core modules and the same database — not copies of the logic.

## 2. Layers

```
┌─────────────────────────────────────────────────────────────┐
│ gui/            CustomTkinter window, pages, widgets, theme │
│ sidekick/       floating widget (Phase 6)                    │
├─────────────────────────────────────────────────────────────┤
│ core/           capture, parsing, context, compression,      │
│                 capsule generation/import, resume, search    │
├─────────────────────────────────────────────────────────────┤
│ ai/             GPU manager, model manager, extractor,       │
│                 embeddings, provider adapters                │
├─────────────────────────────────────────────────────────────┤
│ database/       schema + migrations + repository (sqlite3)   │
│ storage/        attachments, backups                         │
│ exporters/      JSON / Markdown / TXT / ZIP / .scapsule      │
└─────────────────────────────────────────────────────────────┘
```

Dependencies point downwards only: `gui → core → ai → database/storage`. The UI never executes
SQL of its own beyond the repository's typed helpers, and core modules never import Tk.

## 3. Threading model

* **UI thread** — the only thread allowed to touch widgets.
* **Worker threads** — daemon threads started by `gui/workers.run_in_background` (GPU probing,
  statistics, AI/compression work). They return a plain result object; the callback runs on the
  UI thread.
* **SQLite** — one connection per unit of work (`Database.connection()`), WAL mode enabled.
  A worker can therefore never interleave with the UI's transaction.

Long AI jobs (Phase 3) will report progress through a thread-safe callback that is also scheduled
with `after`, so a model download or a summarisation pass can show a percentage without freezing.

## 4. Persistence

`database/migrations/NNN_*.sql` are applied in filename order and tracked by
`PRAGMA user_version`. `database/schema.py` carries an embedded copy of the initial schema as a
fallback for frozen builds. The relational schema is normalised (capsules → conversations →
messages, attachments, versions) while the **portable document** is additionally stored verbatim
in `capsules.payload_json`, because that JSON is exactly what gets exported and re-imported.

## 5. Hardware detection

`ai/gpu_manager.detect()` probes layers in order and records a note for each fallback:

1. PyTorch → CUDA / ROCm device count, names, VRAM, current allocation; Apple MPS on macOS.
2. `nvidia-smi` → GPU name and VRAM without any Python package.
3. CPU → always appended, always usable.

The report is cached in `GpuManager` and refreshed only on demand (button or startup), so the UI
never pays for repeated driver queries.

## 6. Web client and extension bridge

`webapp/server.py` is a standard-library `ThreadingHTTPServer` that imports `core/` directly, so the
browser and the desktop app cannot drift apart. It binds to loopback, rejects non-loopback clients
and unexpected `Host` headers (DNS-rebinding guard), serves static assets from a resolved directory
(with explicit JS/CSS MIME types because Windows' registry can mislabel them), and exposes JSON
routes only. Exports stream from a temporary directory; imports are written to a temp file and
validated by the same importer the desktop uses.

The Chrome extension talks to `/api/bridge/capture` with an `X-SmartCapsule-Token` header compared
using `hmac.compare_digest`. The token lives in the app's data folder, is created on first server
start, and is never embedded in the extension package.

## 7. Floating Sidekick

A single `CTkToplevel` owned by `SidekickWindowManager`. It polls status every five seconds, keeps
no state of its own beyond window geometry, and delegates every action to `sidekick.quick_actions`,
which reads the clipboard only inside an explicit button handler. Global hotkeys use Win32
`RegisterHotKey` and a WM_HOTKEY-filtered `PeekMessageW` loop, so Tk's own message queue is never
drained; when registration fails the conflict is surfaced and in-app bindings remain.

## 8. Navigation and page lifecycle

`gui/navigation.py` is the single registry (key, label, group, module, class). The sidebar and the
router both read it, so a page cannot exist in one and be missing from the other.

Pages are created on first visit and cached. `BasePage` supplies the title block, the header
action slot and the scrolling body; subclasses implement `build()` (once) and optionally
`on_show()` / `refresh()` (every visit). If a page raises during construction, the shell shows an
inline error instead of crashing — the rest of the application stays usable.

## 9. Security posture

* No screen capture, no reading other applications' windows, no silent clipboard access.
* Attachments stored by content hash; imports validated before any write (Phase 4).
* Imported conversation content is treated as untrusted data — it is never interpreted as
  instructions to the application or as SQL.
* API keys, when providers are added, live in the OS user profile and are never logged or
  rendered in the UI.
