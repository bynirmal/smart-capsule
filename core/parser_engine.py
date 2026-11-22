"""Conversation parsing.

Turns raw pasted text, or a TXT / Markdown / JSON export, into ordered messages
with roles, while preserving code blocks byte-for-byte.

Design rules
------------
* Never silently drop content: anything that cannot be attributed is kept and a
  warning explains the assumption.
* Never fabricate certainty: platform detection returns an explicit confidence.
* Code fences are tracked before role detection, so a line such as
  ``Assistant:`` inside a code block never splits a message.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from config import SUPPORTED_AI_PLATFORMS

MAX_CHARS = 4_000_000
MAX_FILE_BYTES = 32 * 1024 * 1024

TOKEN_METHOD = "characters/4 heuristic (not an exact tokenizer count)"


class ParseError(ValueError):
    """Raised when the input cannot be interpreted as a conversation."""


# --------------------------------------------------------------------------- #
# Result objects
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class ParsedMessage:
    role: str
    content: str
    sequence: int
    contains_code: bool = False


@dataclass(slots=True)
class CodeBlock:
    language: str
    content: str
    message_index: int


@dataclass(slots=True)
class ParseResult:
    text: str
    messages: list[ParsedMessage]
    code_blocks: list[CodeBlock]
    platform: str = "Other"
    platform_confidence: str = "low"
    platform_reason: str = ""
    title: str = "Untitled capture"
    warnings: list[str] = field(default_factory=list)
    source_kind: str = "paste"
    source_name: str = ""

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def character_count(self) -> int:
        return len(self.text)

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.text)

    @property
    def roles(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for message in self.messages:
            counts[message.role] = counts.get(message.role, 0) + 1
        return counts

    @property
    def summary_line(self) -> str:
        return (
            f"{self.message_count} message(s) · {self.character_count:,} characters · "
            f"~{self.token_estimate:,} tokens ({TOKEN_METHOD})"
        )


def estimate_tokens(text: str) -> int:
    """Labelled estimate used everywhere until a real tokenizer is selected."""
    if not text:
        return 0
    return max(1, len(text) // 4)


# --------------------------------------------------------------------------- #
# Role markers
# --------------------------------------------------------------------------- #
_ROLE_LABELS: dict[str, set[str]] = {
    "user": {"user", "you", "human", "me", "prompt", "question", "q"},
    "assistant": {
        "assistant",
        "chatgpt",
        "claude",
        "gemini",
        "ai",
        "bot",
        "copilot",
        "cursor",
        "perplexity",
        "model",
        "answer",
        "response",
        "a",
    },
    "system": {"system", "instructions", "developer"},
}

_LABEL_TO_ROLE: dict[str, str] = {
    label: role for role, labels in _ROLE_LABELS.items() for label in labels
}

_SUFFIXES = (" said", " says", " wrote", " replied", " answered", " responds")

_HEADING_RE = re.compile(r"^#{1,6}\s*([A-Za-z][A-Za-z ._\-]{0,24}?)\s*$")
_INLINE_RE = re.compile(r"^\*{0,2}([A-Za-z][A-Za-z ._\-]{0,24}?)\*{0,2}\s*:\s*(.*)$", re.S)

_FENCE_RE = re.compile(r"^(```|~~~)")


def _normalise_label(label: str) -> str:
    value = " ".join(label.strip().lower().split())
    for suffix in _SUFFIXES:
        if value.endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value


def _role_for_label(label: str) -> str | None:
    return _LABEL_TO_ROLE.get(_normalise_label(label))


def _match_role_line(line: str) -> tuple[str, str] | None:
    """Return ``(role, inline_text)`` when the line introduces a message."""
    raw = line.strip()
    if not raw or len(raw) > 240:
        return None

    heading = _HEADING_RE.match(raw)
    if heading:
        role = _role_for_label(heading.group(1))
        if role:
            return role, ""

    inline = _INLINE_RE.match(raw)
    if inline:
        role = _role_for_label(inline.group(1))
        if role:
            return role, inline.group(2).strip()
    return None


# --------------------------------------------------------------------------- #
# Code extraction
# --------------------------------------------------------------------------- #
_CODE_FENCE_RE = re.compile(r"(```|~~~)([A-Za-z0-9_+.\-]*)[ \t]*\r?\n(.*?)(?:\1)", re.S)


def extract_code_blocks(messages: Iterable[ParsedMessage]) -> tuple[list[CodeBlock], list[ParsedMessage]]:
    """Collect fenced code blocks and flag every message that contains one."""
    blocks: list[CodeBlock] = []
    updated: list[ParsedMessage] = []
    for index, message in enumerate(messages):
        found = False
        for match in _CODE_FENCE_RE.finditer(message.content):
            language = (match.group(2) or "").strip() or "text"
            blocks.append(CodeBlock(language=language, content=match.group(3), message_index=index))
            found = True
        message.contains_code = found or message.contains_code
        updated.append(message)
    return blocks, updated


# --------------------------------------------------------------------------- #
# Transcript parsing
# --------------------------------------------------------------------------- #
def _split_transcript(text: str) -> tuple[list[ParsedMessage], list[str]]:
    warnings: list[str] = []
    messages: list[ParsedMessage] = []
    current_role: str | None = None
    buffer: list[str] = []
    fence: str | None = None
    preamble: list[str] = []

    def flush() -> None:
        nonlocal buffer
        content = "\n".join(buffer).strip("\n")
        if content.strip():
            messages.append(
                ParsedMessage(role=current_role or "user", content=content.strip(), sequence=len(messages))
            )
        buffer = []

    for line in text.splitlines():
        stripped = line.strip()
        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None

        if fence is None:
            marker = _match_role_line(line)
            if marker is not None:
                role, inline = marker
                flush()
                current_role = role
                if inline:
                    buffer.append(inline)
                continue

        if current_role is None:
            if stripped:
                preamble.append(line)
            continue
        buffer.append(line)

    flush()

    if not messages:
        stripped = text.strip()
        if not stripped:
            raise ParseError("The capture is empty.")
        warnings.append(
            "No role markers were detected, so the whole capture is stored as a single user message."
        )
        return [ParsedMessage(role="user", content=stripped, sequence=0)], warnings

    if preamble:
        warnings.append(
            "Text before the first role marker was kept as a leading user message."
        )
        messages.insert(
            0,
            ParsedMessage(role="user", content="\n".join(preamble).strip(), sequence=0),
        )
        for index, message in enumerate(messages):
            message.sequence = index

    return messages, warnings


# --------------------------------------------------------------------------- #
# JSON parsing
# --------------------------------------------------------------------------- #
def _stringify_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_stringify_content(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, Mapping):
        for key in ("text", "content", "parts", "value", "message"):
            if key in value:
                return _stringify_content(value[key])
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _messages_from_items(items: list[Any]) -> list[ParsedMessage]:
    messages: list[ParsedMessage] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or item.get("from") or item.get("author") or "user").lower()
        if role in {"human", "user", "prompt"}:
            role = "user"
        elif role in {"gpt", "assistant", "ai", "model", "bot"}:
            role = "assistant"
        elif role not in {"system", "tool"}:
            role = "user"
        content = _stringify_content(
            item.get("content", item.get("text", item.get("message", item.get("parts"))))
        )
        if not content.strip():
            continue
        messages.append(ParsedMessage(role=role, content=content.strip(), sequence=len(messages)))
    return messages


def _messages_from_chatgpt_mapping(mapping: Mapping[str, Any]) -> list[ParsedMessage]:
    """Read the node mapping used by OpenAI's data export."""
    messages: list[ParsedMessage] = []
    for node in mapping.values():
        if not isinstance(node, Mapping):
            continue
        message = node.get("message")
        if not isinstance(message, Mapping):
            continue
        author = message.get("author") or {}
        role = str(author.get("role") or "user")
        content = message.get("content") or {}
        parts = content.get("parts") if isinstance(content, Mapping) else None
        text = _stringify_content(parts if parts is not None else content)
        if not text.strip():
            continue
        messages.append(
            ParsedMessage(
                role="assistant" if role == "assistant" else ("system" if role == "system" else "user"),
                content=text.strip(),
                sequence=len(messages),
            )
        )
    return messages


def _parse_json_document(data: Any) -> tuple[list[ParsedMessage], dict[str, str]]:
    meta: dict[str, str] = {}

    if isinstance(data, Mapping):
        for key in ("platform", "source", "provider"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                meta["platform"] = value.strip()
        for key in ("title", "name", "conversation_title", "summary"):
            value = data.get(key)
            if isinstance(value, str) and value.strip() and len(value) < 300:
                meta["title"] = value.strip()
                break

    if isinstance(data, list):
        messages = _messages_from_items(data)
    elif isinstance(data, Mapping):
        if isinstance(data.get("messages"), list):
            messages = _messages_from_items(data["messages"])
        elif isinstance(data.get("mapping"), Mapping):
            messages = _messages_from_chatgpt_mapping(data["mapping"])
        elif isinstance(data.get("conversations"), list) and data["conversations"]:
            first = data["conversations"][0]
            messages = _parse_json_document(first)[0]
            if isinstance(first, Mapping):
                for key in ("platform", "title", "name"):
                    value = first.get(key)
                    if isinstance(value, str) and value.strip():
                        meta.setdefault(key if key != "name" else "title", value.strip())
        elif isinstance(data.get("conversation"), Mapping):
            messages = _parse_json_document(data["conversation"])[0]
        else:
            raise ParseError(
                "The JSON file does not contain a recognised conversation. Expected a list of messages, "
                "'messages', 'mapping' or 'conversations'."
            )
    else:
        raise ParseError("The JSON root must be an object or an array.")

    if not messages:
        raise ParseError("The JSON file contained no readable messages.")
    return messages, meta


# --------------------------------------------------------------------------- #
# Platform detection
# --------------------------------------------------------------------------- #
_PLATFORM_SIGNATURES: dict[str, tuple[str, ...]] = {
    "ChatGPT": (r"\bchatgpt\b", r"you said:", r"\bopenai\b", r"\bgpt-[345]\b"),
    "Claude": (r"\bclaude\b", r"\banthropic\b", r"claude said"),
    "Gemini": (r"\bgemini\b", r"\bbard\b", r"google ai studio"),
    "Cursor": (r"\bcursor\b", r"\.cursor(?:rules|ignore)"),
    "Copilot": (r"\bgithub copilot\b", r"\bcopilot\b"),
    "Perplexity": (r"\bperplexity\b",),
}


def _normalise_platform(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lower()
    for platform in SUPPORTED_AI_PLATFORMS:
        if platform.lower() == candidate:
            return platform
    aliases = {
        "openai": "ChatGPT",
        "gpt": "ChatGPT",
        "anthropic": "Claude",
        "google": "Gemini",
        "bard": "Gemini",
        "github": "Copilot",
    }
    return aliases.get(candidate)


def detect_platform(text: str, hint: str | None = None) -> tuple[str, str, str]:
    """Return ``(platform, confidence, reason)``."""
    explicit = _normalise_platform(hint)
    if explicit:
        return explicit, "high", f"Selected explicitly by the user ({explicit})."

    haystack = text.lower()
    scores: dict[str, int] = {}
    for platform, patterns in _PLATFORM_SIGNATURES.items():
        score = 0
        for pattern in patterns:
            score += len(re.findall(pattern, haystack))
        if score:
            scores[platform] = score

    if not scores:
        return "Other", "low", "No platform-specific markers found."

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    if best_score >= 2 and best_score > runner_up:
        return best, "medium", f"Detected from {best_score} signature(s); confirm before saving."
    return best, "low", f"Only weak {best} markers were found; confirm before saving."


# --------------------------------------------------------------------------- #
# Titles
# --------------------------------------------------------------------------- #
def derive_title(messages: list[ParsedMessage], fallback: str = "") -> str:
    for message in messages:
        if message.role != "user":
            continue
        for line in message.content.splitlines():
            candidate = line.strip().lstrip("#>*-• ").strip()
            if candidate and not candidate.startswith("```"):
                return candidate[:80]
    if fallback:
        return Path(fallback).stem[:80] or "Untitled capture"
    return "Untitled capture"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def parse_text(
    text: str,
    *,
    platform_hint: str | None = None,
    title_hint: str = "",
    source_kind: str = "paste",
    source_name: str = "",
) -> ParseResult:
    """Parse a pasted transcript."""
    if not text or not text.strip():
        raise ParseError("Nothing to parse: the capture is empty.")
    if len(text) > MAX_CHARS:
        raise ParseError(
            f"The capture is too large ({len(text):,} characters). The limit is {MAX_CHARS:,}."
        )

    messages, warnings = _split_transcript(text)
    blocks, messages = extract_code_blocks(messages)
    platform, confidence, reason = detect_platform(text, platform_hint)

    return ParseResult(
        text=text,
        messages=messages,
        code_blocks=blocks,
        platform=platform,
        platform_confidence=confidence,
        platform_reason=reason,
        title=derive_title(messages, title_hint or source_name),
        warnings=warnings,
        source_kind=source_kind,
        source_name=source_name,
    )


def _decode(raw: bytes, path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ParseError(f"The file {path.name} could not be decoded as text.")


def parse_file(path: str | Path, *, platform_hint: str | None = None) -> ParseResult:
    """Parse a TXT, Markdown or JSON export from disk."""
    file_path = Path(path)
    if not file_path.exists():
        raise ParseError(f"File not found: {file_path}")
    if not file_path.is_file():
        raise ParseError(f"Not a file: {file_path}")

    size = file_path.stat().st_size
    if size == 0:
        raise ParseError(f"{file_path.name} is empty.")
    if size > MAX_FILE_BYTES:
        raise ParseError(
            f"{file_path.name} is {size / 1_048_576:.1f} MB; the limit is {MAX_FILE_BYTES / 1_048_576:.0f} MB."
        )

    suffix = file_path.suffix.lower()
    raw = file_path.read_bytes()
    text = _decode(raw, file_path)

    if suffix == ".json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ParseError(f"{file_path.name} is not valid JSON (line {exc.lineno}, column {exc.colno}).") from exc

        messages, meta = _parse_json_document(data)
        blocks, messages = extract_code_blocks(messages)
        platform, confidence, reason = detect_platform(text, platform_hint or meta.get("platform"))
        warnings: list[str] = []
        if not any(message.contains_code for message in messages) and "```" in text:
            warnings.append("Code fences were found in the JSON payload but not inside message content.")
        return ParseResult(
            text=text,
            messages=messages,
            code_blocks=blocks,
            platform=platform,
            platform_confidence=confidence,
            platform_reason=reason,
            title=(meta.get("title") or derive_title(messages, file_path.name))[:80],
            warnings=warnings,
            source_kind="json",
            source_name=file_path.name,
        )

    if suffix in {".md", ".markdown"}:
        source_kind = "markdown"
    elif suffix in {".txt", ".text", ""}:
        source_kind = "txt"
    else:
        raise ParseError(f"Unsupported file type '{suffix or 'unknown'}'. Use TXT, Markdown or JSON.")

    result = parse_text(
        text,
        platform_hint=platform_hint,
        title_hint=file_path.stem,
        source_kind=source_kind,
        source_name=file_path.name,
    )
    return result
