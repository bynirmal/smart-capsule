"""Embedded copy of the initial schema.

Used as a fallback when the ``database/migrations`` folder is not available
(for example inside a frozen PyInstaller build).  Keep this in sync with
``database/migrations/001_initial.sql``.
"""

from __future__ import annotations

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
    id          VARCHAR(32) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    description TEXT DEFAULT '',
    status      VARCHAR(32) DEFAULT 'active',
    created_at  DATETIME NOT NULL,
    updated_at  DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS capsules (
    id               VARCHAR(32) PRIMARY KEY,
    project_id       VARCHAR(32) REFERENCES projects(id) ON DELETE SET NULL,
    title            VARCHAR(300) NOT NULL,
    source_platform  VARCHAR(64) DEFAULT 'Other',
    format_version   INTEGER DEFAULT 1,
    summary          TEXT DEFAULT '',
    next_action      TEXT DEFAULT '',
    compression_mode VARCHAR(24) DEFAULT 'balanced',
    token_estimate   INTEGER DEFAULT 0,
    payload_json     TEXT DEFAULT '{}',
    is_archived      BOOLEAN DEFAULT 0,
    created_at       DATETIME NOT NULL,
    updated_at       DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_capsules_created_at ON capsules(created_at);

CREATE TABLE IF NOT EXISTS conversations (
    id            VARCHAR(32) PRIMARY KEY,
    capsule_id    VARCHAR(32) NOT NULL REFERENCES capsules(id) ON DELETE CASCADE,
    platform      VARCHAR(64) DEFAULT 'Other',
    title         VARCHAR(300) DEFAULT '',
    started_at    DATETIME,
    message_count INTEGER DEFAULT 0,
    raw_text      TEXT DEFAULT '',
    created_at    DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id              VARCHAR(32) PRIMARY KEY,
    conversation_id VARCHAR(32) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(24) DEFAULT 'user',
    content         TEXT DEFAULT '',
    sequence        INTEGER DEFAULT 0,
    contains_code   BOOLEAN DEFAULT 0,
    created_at      DATETIME NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_conversation_seq ON messages(conversation_id, sequence);

CREATE TABLE IF NOT EXISTS attachments (
    id          VARCHAR(32) PRIMARY KEY,
    capsule_id  VARCHAR(32) NOT NULL REFERENCES capsules(id) ON DELETE CASCADE,
    filename    VARCHAR(400) NOT NULL,
    mime_type   VARCHAR(120) DEFAULT 'application/octet-stream',
    size_bytes  INTEGER DEFAULT 0,
    sha256      VARCHAR(64) DEFAULT '',
    stored_path TEXT DEFAULT '',
    created_at  DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS capsule_versions (
    id             VARCHAR(32) PRIMARY KEY,
    capsule_id     VARCHAR(32) NOT NULL REFERENCES capsules(id) ON DELETE CASCADE,
    version_number INTEGER DEFAULT 1,
    note           VARCHAR(400) DEFAULT '',
    payload_json   TEXT DEFAULT '{}',
    created_at     DATETIME NOT NULL,
    CONSTRAINT uq_capsule_version UNIQUE (capsule_id, version_number)
);

CREATE TABLE IF NOT EXISTS ai_models (
    id           VARCHAR(32) PRIMARY KEY,
    name         VARCHAR(200) UNIQUE NOT NULL,
    backend      VARCHAR(40) DEFAULT 'transformers',
    size_mb      INTEGER DEFAULT 0,
    path         TEXT DEFAULT '',
    is_loaded    BOOLEAN DEFAULT 0,
    is_default   BOOLEAN DEFAULT 0,
    last_used_at DATETIME
);

CREATE TABLE IF NOT EXISTS processing_history (
    id         VARCHAR(32) PRIMARY KEY,
    capsule_id VARCHAR(32) REFERENCES capsules(id) ON DELETE SET NULL,
    stage      VARCHAR(60) DEFAULT 'extract',
    engine     VARCHAR(60) DEFAULT 'rule-based',
    model_name VARCHAR(200) DEFAULT '',
    device     VARCHAR(60) DEFAULT 'cpu',
    status     VARCHAR(24) DEFAULT 'ok',
    detail     TEXT DEFAULT '',
    started_at DATETIME NOT NULL,
    finished_at DATETIME
);

CREATE TABLE IF NOT EXISTS settings (
    key        VARCHAR(120) PRIMARY KEY,
    value      TEXT DEFAULT '',
    updated_at DATETIME NOT NULL
);
"""
