# The `.scapsule` format

Status: **contract defined, implementation in Phase 4.** This document is the specification the
generator, validator, exporter and importer must all satisfy; it is deliberately written before
the code so no two components invent different shapes.

## Package layout

A `.scapsule` file is a ZIP archive:

```
capsule.json          the document below (UTF-8, no BOM)
attachments/<id>_<filename>   binary attachments, referenced from the document
manifest.json         format version, file list, SHA-256 of every file, created_at
```

A reader must verify `manifest.json` hashes before trusting any content.

## Document

```jsonc
{
  "capsule_id": "9f2c…",            // UUIDv4 hex, unique per capsule
  "format_version": 1,              // must be understood by the reader
  "created_at": "2026-11-22T10:31:00Z",
  "app_version": "0.1.0",

  "source": {
    "platform": "ChatGPT",          // ChatGPT | Claude | Gemini | Cursor | Copilot | …
    "platform_confidence": "high",  // high | medium | low — never presented as certainty
    "conversation_title": "…",
    "conversation_date": "2026-11-20T18:02:00Z",
    "message_count": 42
  },

  "project": {
    "name": "…",
    "objective": "…",
    "description": "…",
    "stage": "…",                   // e.g. "implementation", "debugging"
    "technologies": ["Python", "CustomTkinter"],
    "constraints": ["offline first", "no GPU required"]
  },

  "instructions": [                 // explicit user requirements, quoted where possible
    { "text": "…", "kind": "format|technical|restriction|preference", "certainty": "stated|inferred" }
  ],

  "technical": {
    "languages": [], "frameworks": [], "libraries": [], "dependencies": [],
    "architecture_decisions": [ { "decision": "…", "rationale": "…" } ],
    "api_configurations": [],
    "database_structure": []
  },

  "code": [
    { "language": "python", "purpose": "…", "content": "…", "source_message": 17 }
  ],

  "progress": {
    "completed": [ { "task": "…", "evidence": "…" } ],
    "pending":   [ { "task": "…", "evidence": "…" } ],
    "current_task": "…",
    "errors":    [ { "error": "…", "solution": "…", "resolved": true } ],
    "next_action": "…"
  },

  "decisions": [ { "text": "…", "certainty": "stated|inferred" } ],

  "summary": "…",                   // compressed narrative of the working state
  "attachments": [
    { "id": "…", "filename": "…", "mime_type": "…", "size_bytes": 1234, "sha256": "…" }
  ],

  "original": {                     // present only in "full preservation" mode
    "messages": [ { "role": "user", "content": "…", "sequence": 0 } ]
  },

  "compression": {
    "mode": "balanced",             // balanced | high | full
    "original_tokens": 0,
    "capsule_tokens": 0,
    "token_method": "chars/4 estimate",  // literal method, never a fake exact count
    "preserved_sections": ["project", "instructions", "code", "progress"]
  }
}
```

## Rules

1. **Nothing invented.** Every field carries either a quote/evidence reference or a
   `certainty: "inferred"` marker. Empty lists are preferred to guesses.
2. **Never silently drop content.** Messages and code removed by compression are counted in
   `compression` metadata, and remain available in `original` when full preservation is used.
3. **Versioned.** A reader rejects `format_version` newer than it understands and reports the
   version instead of failing opaquely.
4. **Deterministic.** Two generations from the same input and settings produce the same document
   (ordering stable, no timestamps inside the body beyond `created_at`).
5. **No secrets.** Credentials, cookies, session tokens and API keys are never captured.

## Companion formats

| Format | Purpose |
| --- | --- |
| `.json` | the document above, without attachments |
| `.md` | human-readable brief + continuation prompt |
| `.txt` | plain-text summary for any chat box |
| `.zip` | archive of the document and attachments, without the `.scapsule` wrapper rules |

## Token estimates

Estimates are always labelled: a real tokenizer is used only when the selected model provides
one; otherwise the documented `chars/4` heuristic is reported as an estimate. The UI must never
print an unlabelled exact token count.
