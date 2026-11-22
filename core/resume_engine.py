"""Resume engine: turn a capsule document into context a new AI can continue from.

Two artifacts are produced:

* a **context brief** — structured state (objective, stack, instructions, tasks,
  errors, next action), and
* a **continuation prompt** — destination-specific instructions telling the new
  assistant how to pick up the work.

Nothing here claims to move hidden model memory; the prompt states that explicitly.
"""

from __future__ import annotations

from typing import Any, Mapping

DESTINATIONS: tuple[str, ...] = ("ChatGPT", "Claude", "Gemini", "Cursor", "Other")

DESTINATION_URLS = {
    "ChatGPT": "https://chatgpt.com/",
    "Claude": "https://claude.ai/new",
    "Gemini": "https://gemini.google.com/app",
    "Cursor": "https://cursor.com/",
    "Other": "",
}

_STYLE = {
    "ChatGPT": "Use short paragraphs and a numbered plan before any code.",
    "Claude": "Be concise; call out assumptions and unresolved risks explicitly.",
    "Gemini": "Structure the answer with clear headings and a short checklist.",
    "Cursor": "Focus on the repository: files to change, exact edits, and commands to run.",
    "Other": "Ask one clarifying question if any requirement is ambiguous.",
}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _bullets(items: list[Any], empty: str = "None recorded.") -> str:
    lines = [f"- {_text(item)}" for item in items if _text(item)]
    return "\n".join(lines) if lines else f"- {empty}"


def context_brief(document: Mapping[str, Any]) -> str:
    """Plain-text structured brief of the capsule."""
    project = document.get("project") or {}
    source = document.get("source") or {}
    progress = document.get("progress") or {}
    technical = document.get("technical") or {}
    compression = document.get("compression") or {}

    instructions = [
        item.get("text", "") if isinstance(item, Mapping) else str(item)
        for item in document.get("instructions", [])
    ]
    decisions = [
        item.get("text", "") if isinstance(item, Mapping) else str(item)
        for item in document.get("decisions", [])
    ]
    completed = [
        item.get("task", "") if isinstance(item, Mapping) else str(item)
        for item in progress.get("completed", [])
    ]
    pending = [
        item.get("task", "") if isinstance(item, Mapping) else str(item)
        for item in progress.get("pending", [])
    ]
    errors = []
    for item in progress.get("errors", []):
        if isinstance(item, Mapping):
            errors.append(
                f"{item.get('error', '')}"
                + (f" → {item.get('solution', '')}" if item.get("solution") else " (unresolved)")
            )
        else:
            errors.append(str(item))

    stack_parts: list[str] = []
    for key, label in (
        ("languages", "Languages"),
        ("frameworks", "Frameworks"),
        ("libraries", "Libraries"),
    ):
        values = technical.get(key) or []
        if values:
            stack_parts.append(f"{label}: {', '.join(_text(value) for value in values)}")

    constraints = [
        _text(item) for item in (project.get("constraints") or [])
    ]

    lines = [
        f"# PROJECT HANDOFF — {_text(project.get('name')) or 'Untitled project'}",
        "",
        f"Source platform: {_text(source.get('platform')) or 'unknown'}",
        f"Captured: {_text(document.get('created_at'))}",
        f"Compression: {_text(compression.get('mode'))} "
        f"(~{compression.get('capsule_tokens', 0)} tokens, {compression.get('token_method', 'estimate')})",
        "",
        "## Objective",
        _text(project.get("objective")) or "Not stated.",
        "",
        "## Description",
        _text(project.get("description")) or "Not recorded.",
        "",
        "## Current stage",
        f"{_text(project.get('stage')) or 'unknown'} (inferred from the conversation)",
        "",
        "## Stack",
        "\n".join(stack_parts) if stack_parts else "Not identified.",
        "",
        "## Requirements and constraints",
        _bullets(constraints),
        "",
        "## Explicit instructions",
        _bullets(instructions),
        "",
        "## Technical decisions",
        _bullets(decisions),
        "",
        "## Completed",
        _bullets(completed),
        "",
        "## Pending",
        _bullets(pending),
        "",
        "## Errors and solutions",
        _bullets(errors),
        "",
        "## Next action",
        _text(progress.get("next_action")) or "Not recorded.",
        "",
        "## Summary",
        _text(document.get("summary")) or "Not recorded.",
    ]

    code = document.get("code") or []
    if code:
        lines.extend(["", "## Relevant code"])
        for item in code[:4]:
            if not isinstance(item, Mapping):
                continue
            language = _text(item.get("language")) or "text"
            lines.extend(["", f"```{language}", _text(item.get("content")), "```"])

    return "\n".join(lines).strip() + "\n"


def continuation_prompt(document: Mapping[str, Any], destination: str = "Other") -> str:
    """Destination-specific prompt that continues the project."""
    project = document.get("project") or {}
    progress = document.get("progress") or {}
    target = destination if destination in DESTINATIONS else "Other"

    header = (
        f"You are continuing an in-progress project called "
        f"“{_text(project.get('name')) or 'Untitled project'}”. "
        "The structured handoff below is the complete working context available to you. "
        "It was produced by Smart Capsule; it does not contain hidden model memory, "
        "account state or any credentials."
    )
    brief = context_brief(document)
    next_action = _text(progress.get("next_action")) or "Confirm the priorities with me before starting."

    return (
        f"{header}\n\n"
        f"{brief}\n"
        "## Your task\n"
        f"1. Read the handoff and restate the project state in at most five bullets.\n"
        f"2. Flag anything ambiguous or missing instead of inventing details.\n"
        f"3. Continue from the next action: {next_action}\n"
        f"4. {_STYLE.get(target, _STYLE['Other'])}\n"
        "5. Keep every existing constraint and decision above; do not silently change the stack.\n"
    ).strip() + "\n"
