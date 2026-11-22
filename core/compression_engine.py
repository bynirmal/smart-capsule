"""Context compression.

Reduces a conversation to the smallest text that still lets another AI continue
the work. The priority order is fixed by the product specification:

requirements → user instructions → decisions → technical details → code →
errors/solutions → completed → pending → dependencies → next action.

Three modes are available. Token figures are always produced by the same labelled
heuristic as the parser — never presented as exact tokenizer counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.context_engine import ProjectContext
from core.parser_engine import ParseResult, estimate_tokens

TOKEN_METHOD = "characters/4 heuristic"

MODES: tuple[str, ...] = ("balanced", "high", "full")

# Character budgets for the structured sections (excluding full-preservation text).
BUDGETS = {"balanced": 14000, "high": 6000, "full": 24000}
SECTION_LIMITS = {
    "balanced": {"bullets": 10, "code_blocks": 2, "code_chars": 900},
    "high": {"bullets": 6, "code_blocks": 1, "code_chars": 400},
    "full": {"bullets": 40, "code_blocks": 20, "code_chars": 6000},
}

# Sections that must never be dropped, even when the budget is exhausted.
PROTECTED = {"Project requirements", "User instructions", "Next action"}


@dataclass(slots=True)
class CompressionResult:
    mode: str
    summary: str
    sections: list[tuple[str, list[str]]] = field(default_factory=list)
    original_tokens: int = 0
    capsule_tokens: int = 0
    token_method: str = TOKEN_METHOD
    preserved_sections: list[str] = field(default_factory=list)
    omitted_sections: list[str] = field(default_factory=list)
    omitted_messages: int = 0
    original_text_included: bool = False

    @property
    def markdown(self) -> str:
        return self.render_markdown()

    @property
    def plain_text(self) -> str:
        blocks: list[str] = [self.summary, ""]
        for title, items in self.sections:
            if not items:
                continue
            blocks.append(title.upper())
            blocks.extend(f"- {item}" for item in items)
            blocks.append("")
        return "\n".join(blocks).strip() + "\n"

    def render_markdown(self) -> str:
        lines: list[str] = [self.summary, ""]
        for title, items in self.sections:
            if not items:
                continue
            lines.append(f"## {title}")
            lines.extend(f"- {item}" for item in items)
            lines.append("")
        if self.original_text_included:
            lines.append("## Original conversation")
            lines.append("")
            lines.append("_Full original data is stored in this capsule document._")
        return "\n".join(lines).strip() + "\n"

    def as_metadata(self) -> dict:
        return {
            "mode": self.mode,
            "original_tokens": self.original_tokens,
            "capsule_tokens": self.capsule_tokens,
            "token_method": self.token_method,
            "preserved_sections": self.preserved_sections,
            "omitted_sections": self.omitted_sections,
            "omitted_messages": self.omitted_messages,
            "original_included": self.original_text_included,
        }


def _build_sections(context: ProjectContext, result: ParseResult, mode: str) -> list[tuple[str, list[str]]]:
    limits = SECTION_LIMITS[mode]

    requirements: list[str] = []
    if context.objective:
        requirements.append(f"Objective: {context.objective}")
    requirements.extend(f"Constraint: {item.text}" for item in context.constraints[: limits["bullets"]])

    # Constraints are rendered under "Project requirements" (protected), so they
    # are not repeated here; every other instruction keeps its priority slot.
    instructions = [
        f"[{item.kind}] {item.text}" if item.kind not in {"requirement", "constraint"} else item.text
        for item in context.instructions[: limits["bullets"]]
        if item.kind != "constraint"
    ]

    decisions = [item.text for item in context.decisions[: limits["bullets"]]]

    technical: list[str] = []
    if context.technical.languages:
        technical.append("Languages: " + ", ".join(context.technical.languages))
    if context.technical.frameworks:
        technical.append("Frameworks: " + ", ".join(context.technical.frameworks))
    if context.technical.libraries:
        technical.append("Libraries/tools: " + ", ".join(context.technical.libraries))
    technical.extend(f"API: {item.text}" for item in context.technical.apis[:4])
    technical.extend(f"Data: {item.text}" for item in context.technical.databases[:4])

    code: list[str] = []
    for block in result.code_blocks[: limits["code_blocks"]]:
        snippet = block.content.strip()
        if len(snippet) > limits["code_chars"]:
            snippet = snippet[: limits["code_chars"]].rstrip() + "\n… (truncated)"
        code.append(f"{block.language}:\n{snippet}")

    errors = [
        f"{item.error}" + (f" → {item.solution}" if item.solution else " (no solution recorded)")
        for item in context.errors[: limits["bullets"]]
    ]

    completed = [item.task for item in context.completed[: limits["bullets"]]]
    pending = [item.task for item in context.pending[: limits["bullets"]]]
    dependencies = [
        tech
        for tech in context.technologies
        if tech not in context.technical.languages and tech not in context.technical.frameworks
    ][:10]
    next_action = [context.next_action] if context.next_action else []

    sections = [
        ("Project requirements", requirements),
        ("User instructions", instructions),
        ("Decisions", decisions),
        ("Technical context", technical),
        ("Code", code),
        ("Errors and solutions", errors),
        ("Completed tasks", completed),
        ("Pending tasks", pending),
        ("Dependencies", dependencies),
        ("Next action", next_action),
    ]
    return sections


def compress(context: ProjectContext, result: ParseResult, mode: str = "balanced") -> CompressionResult:
    """Compress ``result`` into a :class:`CompressionResult` for ``mode``."""
    if mode not in MODES:
        raise ValueError(f"Unknown compression mode: {mode}")

    budget = BUDGETS[mode]
    sections = _build_sections(context, result, mode)

    kept: list[tuple[str, list[str]]] = []
    preserved: list[str] = []
    omitted: list[str] = []
    used = len(context.summary)

    for title, items in sections:
        if not items:
            continue
        accepted: list[str] = []
        for item in items:
            cost = len(item) + 4
            if used + cost > budget and title not in PROTECTED:
                break
            accepted.append(item)
            used += cost
        if accepted:
            kept.append((title, accepted))
            preserved.append(title)
        else:
            omitted.append(title)

    original_included = mode == "full"
    rendered = _render(context.summary, kept)
    if original_included:
        rendered += "\n" + result.text

    omitted_messages = 0 if mode == "full" else max(
        0, result.message_count - sum(len(items) for _, items in kept)
    )

    return CompressionResult(
        mode=mode,
        summary=context.summary,
        sections=kept,
        original_tokens=estimate_tokens(result.text),
        capsule_tokens=estimate_tokens(rendered),
        preserved_sections=preserved,
        omitted_sections=omitted,
        omitted_messages=omitted_messages,
        original_text_included=original_included,
    )


def _render(summary: str, sections: list[tuple[str, list[str]]]) -> str:
    parts = [summary, ""]
    for title, items in sections:
        parts.append(f"## {title}")
        parts.extend(f"- {item}" for item in items)
        parts.append("")
    return "\n".join(parts)
