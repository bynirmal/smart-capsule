# API reference (implemented modules)

Only what exists today is documented here; later phases append to this file.

## `config`

| Symbol | Description |
| --- | --- |
| `APP_NAME`, `VERSION`, `BUILD_STAGE`, `TAGLINE`, `SLOGAN` | identity strings |
| `CAPSULE_EXTENSION`, `CAPSULE_FORMAT_VERSION` | `.scapsule`, `1` |
| `data_dir()` | writable per-user folder (honours `SMART_CAPSULE_HOME`) |
| `database_path()`, `exports_dir()`, `attachments_dir()`, `backups_dir()`, `logs_dir()` | derived paths |
| `SUPPORTED_AI_PLATFORMS`, `COMPRESSION_MODES` | canonical option lists |

## `database.db.Database`

```python
Database(path: Path | str | None = None)
```

| Method | Returns | Notes |
| --- | --- | --- |
| `initialize()` | `None` | applies pending migrations; safe to call repeatedly |
| `schema_version()` | `int` | `PRAGMA user_version` |
| `connection()` | context manager → `sqlite3.Connection` | WAL + foreign keys; commit/rollback automatic |
| `query(sql, params)`, `query_one`, `scalar`, `execute` | rows / value / lastrowid | explicit SQL for advanced queries |
| `get_setting(key, default)`, `set_setting(key, value)`, `get_bool_setting(key, default)` | | key/value preferences |
| `create_capsule(...)`, `get_capsule(id)`, `list_capsules(...)`, `count_capsules(...)` | `Capsule` / list / int | search matches title, summary, next action |
| `update_capsule(id, **fields)` | `None` | whitelisted columns only |
| `delete_capsule(id)` | `None` | cascades conversations, messages, attachments, versions |
| `create_project(name, description)`, `list_projects()`, `ensure_project(name)` | `Project` / list | |
| `stats()` | `AppStats` | dashboard counters incl. per-platform map |
| `storage_usage_bytes()` | `int` | database + WAL + attachment folder |
| `recent_capsules(limit)` | `list[Capsule]` | |

`get_database()` returns the process-wide singleton (migrated on first use);
`reset_database_singleton()` exists for tests.

## `database.models`

Dataclasses `Project`, `Capsule`, `Conversation`, `Message`, `Attachment`, `CapsuleVersion`,
`AIModel`, `ProcessingRun`, `AppStats`. Each has `from_row(mapping)`; `Capsule.payload()` decodes
the stored JSON document and returns `{}` on corruption.

## `ai.gpu_manager`

| Symbol | Description |
| --- | --- |
| `detect()` | full probe; never raises; returns `GpuReport` |
| `GpuReport` | `devices`, `cuda_available`, `torch_installed`, `torch_version`, `cuda_version`, `accelerator_count`, `notes`, `platform_label`, `probed_at`, `extras`; properties `recommended`, `has_gpu`, `status_line`, `summary` |
| `Device` | `name`, `backend`, `index`, `is_gpu`, `total_memory_mb`, `used_memory_mb`; properties `vram_label`, `backend_label` |
| `GpuManager()` | `.report` (cached), `.refresh()`, `.recommended_device()` |

## `core.parser_engine`

| Symbol | Description |
| --- | --- |
| `parse_text(text, *, platform_hint=None, title_hint='', source_kind='paste', source_name='')` | parse a pasted transcript; raises `ParseError` |
| `parse_file(path, *, platform_hint=None)` | TXT / MD / JSON (incl. OpenAI `mapping` exports) |
| `detect_platform(text, hint=None)` | `(platform, confidence, reason)` — `high` only when the user chose it |
| `estimate_tokens(text)` | `characters/4` heuristic, always labelled as such |
| `ParseResult` | `text`, `messages`, `code_blocks`, `platform`, `platform_confidence`, `platform_reason`, `title`, `warnings`, `source_kind`, `source_name`; properties `message_count`, `character_count`, `token_estimate`, `roles`, `summary_line` |
| `ParsedMessage` / `CodeBlock` | `role`, `content`, `sequence`, `contains_code` / `language`, `content`, `message_index` |
| `ParseError` | subclass of `ValueError` with a user-presentable message |

Role markers understood: `User:`, `You said:`, `Human:`, `Assistant:`, `ChatGPT said:`, `Claude:`,
`## User`, `**Assistant:**`, plus a single-message fallback with a warning when no marker exists.

## `core.capture_engine.CaptureEngine`

| Method | Description |
| --- | --- |
| `analyze_text(text, *, platform_hint=None)` | parse only; writes nothing |
| `analyze_file(path, *, platform_hint=None)` | parse a file; writes nothing |
| `save_draft(result)` | atomically writes capsule + conversation + messages + processing run; returns capsule id; deletes the capsule if conversation persistence fails |

## `storage.backup`

| Function | Description |
| --- | --- |
| `create_backup(database, label="manual", keep=10)` | online backup via SQLite's backup API; prunes old snapshots; returns path |
| `list_backups()` | snapshots, oldest first |
| `restore_backup(database, path)` | replaces the live database (restart the UI afterwards) |

## `core.context_engine`

| Symbol | Description |
| --- | --- |
| `extract(ParseResult)` | builds `ProjectContext` (objective, instructions + constraints, technologies, decisions, completed/pending tasks, errors with solutions, next action, inferred stage, warnings) |
| `build_summary(context)` | deterministic narrative summary |
| `detect_technologies(text)` | word-bounded stack detection |
| `ProjectContext` | dataclass carrying `evidence.certainty` and `message_index` on every item |

## `core.compression_engine`

`compress(context, result, mode)` → `CompressionResult` with `sections`, `omitted_sections`,
`original_tokens`, `capsule_tokens`, `token_method`, `original_text_included`, `markdown`,
`plain_text`, `as_metadata()`. Modes: `balanced` (14k chars), `high` (6k), `full` (24k + original).
Sections that are never dropped: requirements, user instructions, next action.

## `core.capsule_generator`

| Symbol | Description |
| --- | --- |
| `build_document(result, context, compression, ...)` | assemble the portable document |
| `generate_document(result, mode, overrides, capsule_id, conversation_id)` | `(document, context, compression)` without writes |
| `save_document(db, document, capsule_id=None, note=...)` | validate → upsert capsule → append version |
| `generate_capsule(db, result, ..., mode, overrides)` | full pipeline → `(capsule_id, document)` |
| `apply_overrides(context, overrides)` | review-screen edits (name, objective, next action) |

## `core.validator`

`validate_document(document)` → `ValidationResult(ok, errors, warnings)`; `raise_if_invalid()`.
Checks required fields/types, format version support, compression mode and token-method labelling.

## `core.capsule_importer`

`import_capsule(db, path)` → `ImportResult(capsule_id, title, document, warnings, attachments)`.
Accepts `.scapsule`/`.zip`/`.json`; verifies manifest hashes, rejects traversal, validates before
writing, and deletes the capsule if any write fails. Raises `ImportError_` (a `ValueError`).

## `core.resume_engine`

`context_brief(document)`, `continuation_prompt(document, destination)`, `DESTINATIONS`,
`DESTINATION_URLS`. Prompts state explicitly that no hidden model memory or credentials are included.

## `core.search_engine`

`search(db, term, limit=50)` → `SearchHit(capsule, snippet, where)`; matches title, summary, next
action and payload, with snippet extraction.

## `exporters`

`FORMATS`, `SUFFIXES`, `export_document(document, target, fmt)` for `json`, `markdown`, `txt`,
`zip`, `scapsule`. Every writer validates first; archives include a SHA-256 manifest.

## `sidekick`

`SidekickWindowManager(app)` (`show/hide/toggle/destroy`), `FloatingSidekick(app)`,
`ShortcutManager(root, handlers)` (`start/stop/status`, Win32 `RegisterHotKey` + fallback),
`startup_manager.is_enabled()/set_enabled(bool)`, `quick_actions` (clipboard, quick save, latest prompt).

## `webapp`

`create_server(host, port, allow_remote=False)` → `ThreadingHTTPServer`; `main(argv)` CLI;
`bridge_token()` per-install token. API surface: `/api/status`, `/api/preview`,
`/api/capsules` (GET/POST), `/api/capsules/{id}` (GET/PATCH/DELETE),
`/api/capsules/{id}/prompt`, `/api/capsules/{id}/export`, `/api/import`,
`/api/bridge/capture`. Loopback-only, Host-header guard, JSON errors, no-store on JSON.

## `gui.workers`

| Symbol | Description |
| --- | --- |
| `run_in_background(widget, task, on_success, on_error, on_finally)` | runs `task` in a daemon thread, delivers the outcome on the UI thread |
| `Debouncer(widget, delay_ms)` | `.call(fn)` / `.cancel()` for search boxes |

## `gui.navigation`

`NavItem`, `NAV_ITEMS`, `get_item(key)`, `groups()`, `page_class(key)`, `DEFAULT_PAGE`.
