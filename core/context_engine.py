"""Rule-based context extraction.

Turns a parsed conversation into a structured project state: objective, explicit
instructions, technology stack, decisions, completed / pending tasks, errors with
solutions and the next action.

Every extracted item records its origin message and a certainty marker. Anything
that is guessed (current stage, missing next action) is marked ``inferred`` — the
brief forbids presenting uncertain information as fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from core.parser_engine import ParseResult

MAX_ITEMS = 12

TECHNOLOGIES: tuple[tuple[str, str], ...] = (
    # (canonical name, pattern)
    ("Python", r"\bpython\b"),
    ("FastAPI", r"\bfastapi\b"),
    ("Flask", r"\bflask\b"),
    ("Django", r"\bdjango\b"),
    ("React", r"\breact(?:\.js|js)?\b"),
    ("Next.js", r"\bnext\.?js\b"),
    ("Vue", r"\bvue(?:\.js)?\b"),
    ("Svelte", r"\bsvelte\b"),
    ("TypeScript", r"\btypescript\b"),
    ("JavaScript", r"\bjavascript\b"),
    ("Node.js", r"\bnode\.?js\b"),
    ("CustomTkinter", r"\bcustomtkinter\b"),
    ("Tkinter", r"\btkinter\b"),
    ("PyTorch", r"\bpytorch\b|\btorch\b"),
    ("TensorFlow", r"\btensorflow\b"),
    ("Transformers", r"\btransformers\b"),
    ("SQLite", r"\bsqlite3?\b"),
    ("PostgreSQL", r"\bpostgres(?:ql)?\b"),
    ("MySQL", r"\bmysql\b"),
    ("MongoDB", r"\bmongodb\b"),
    ("Redis", r"\bredis\b"),
    ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
    ("Cloudflare", r"\bcloudflare\b|\bworkers\b"),
    ("Tailwind CSS", r"\btailwind\b"),
    ("Pandas", r"\bpandas\b"),
    ("NumPy", r"\bnumpy\b"),
    ("Pydantic", r"\bpydantic\b"),
    ("SQLAlchemy", r"\bsqlalchemy\b"),
    ("Ollama", r"\bollama\b"),
    ("OpenAI API", r"\bopenai\b"),
    ("Chrome Extension", r"\bchrome extension\b|\bmanifest v3\b"),
    ("Electron", r"\belectron\b"),
    ("Tauri", r"\btauri\b"),
)

LANGUAGES = {
    "Python",
    "TypeScript",
    "JavaScript",
    "SQLite",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
}
FRAMEWORKS = {
    "FastAPI",
    "Flask",
    "Django",
    "React",
    "Next.js",
    "Vue",
    "Svelte",
    "CustomTkinter",
    "Tkinter",
    "PyTorch",
    "TensorFlow",
    "Electron",
    "Tauri",
}

INSTRUCTION_MARKERS = (
    "must",
    "should",
    "need to",
    "needs to",
    "have to",
    "always",
    "never",
    "only",
    "don't",
    "do not",
    "avoid",
    "prefer",
    "require",
    "make sure",
    "ensure",
    "keep ",
    "use ",
    "remember",
)
CONSTRAINT_MARKERS = (
    "must not",
    "no external",
    "without",
    "offline",
    "never",
    "cannot",
    "can't",
    "only",
    "limit",
    "restrict",
)
PENDING_MARKERS = (
    "todo",
    "to do",
    "next step",
    "pending",
    "still need",
    "remaining",
    "not yet",
    "need to add",
    "need to implement",
    "need to fix",
    "haven't",
    "have not",
    "will add",
    "should add",
    "should implement",
)
COMPLETED_MARKERS = (
    "done",
    "completed",
    "finished",
    "implemented",
    "fixed",
    "works now",
    "working now",
    "resolved",
    "added",
    "created",
    "built",
)
DECISION_MARKERS = (
    "decided",
    "let's use",
    "we will use",
    "we'll use",
    "i'll use",
    "go with",
    "instead of",
    "approach",
    "chose",
    "choose",
    "settled on",
)
ERROR_MARKERS = (
    "traceback",
    "error",
    "exception",
    "failed",
    "failure",
    "crash",
    "doesn't work",
    "does not work",
    "not working",
    "broken",
    "bug",
)
SOLUTION_MARKERS = (
    "fix",
    "solution",
    "because",
    "try",
    "change",
    "replace",
    "update",
    "wrap",
    "remove",
    "instead",
    "should work",
    "root cause",
)
FORMAT_MARKERS = ("format", "json", "markdown", "bullet", "style", "tone", "word", "table")

_FENCE_BLOCK = re.compile(r"```.*?```", re.S)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Evidence:
    text: str
    certainty: str = "stated"  # stated | inferred
    message_index: int = -1
    kind: str = "requirement"


@dataclass(slots=True)
class TaskItem:
    task: str
    certainty: str = "stated"
    message_index: int = -1


@dataclass(slots=True)
class ErrorItem:
    error: str
    solution: str = ""
    resolved: bool = False
    certainty: str = "stated"
    message_index: int = -1


@dataclass(slots=True)
class TechnicalInfo:
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    decisions: list[Evidence] = field(default_factory=list)
    apis: list[Evidence] = field(default_factory=list)
    databases: list[Evidence] = field(default_factory=list)


@dataclass(slots=True)
class ProjectContext:
    name: str = "Untitled project"
    objective: str = ""
    description: str = ""
    stage: str = "unknown"
    stage_certainty: str = "inferred"
    technologies: list[str] = field(default_factory=list)
    instructions: list[Evidence] = field(default_factory=list)
    constraints: list[Evidence] = field(default_factory=list)
    decisions: list[Evidence] = field(default_factory=list)
    technical: TechnicalInfo = field(default_factory=TechnicalInfo)
    completed: list[TaskItem] = field(default_factory=list)
    pending: list[TaskItem] = field(default_factory=list)
    errors: list[ErrorItem] = field(default_factory=list)
    next_action: str = ""
    next_action_certainty: str = "inferred"
    summary: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def current_task(self) -> str:
        if self.pending:
            return self.pending[0].task
        return self.next_action


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _plain(text: str) -> str:
    return _FENCE_BLOCK.sub(" ", text)


def _clip(text: str, limit: int = 240) -> str:
    collapsed = _WHITESPACE.sub(" ", text).strip(" -•*\t")
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def _sentences(text: str) -> list[str]:
    """Split a message into candidate statements, ignoring code blocks."""
    plain = _plain(text)
    candidates: list[str] = []
    for line in plain.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        bullet = re.match(r"^(?:[-*•]|\d+[.)])\s+(.*)$", stripped)
        if bullet:
            candidates.append(bullet.group(1))
            continue
        candidates.extend(part for part in _SENTENCE_SPLIT.split(stripped) if part.strip())
    return [candidate.strip() for candidate in candidates if len(candidate.strip()) > 3]


def _contains(sentence: str, markers: Iterable[str]) -> bool:
    lowered = sentence.lower()
    return any(marker in lowered for marker in markers)


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())[:90]


class _Deduper:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def add(self, text: str) -> bool:
        key = _key(text)
        if not key or key in self._seen:
            return False
        self._seen.add(key)
        return True


def detect_technologies(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for name, pattern in TECHNOLOGIES:
        if re.search(pattern, lowered):
            found.append(name)
    return found


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def extract(result: ParseResult) -> ProjectContext:
    """Build a :class:`ProjectContext` from a parsed conversation."""
    context = ProjectContext()
    texts = [_plain(message.content) for message in result.messages]
    combined = "\n".join(texts)

    context.name = _clip(result.title or "Untitled project", 80) or "Untitled project"
    context.technologies = detect_technologies(combined)

    first_user = next((message for message in result.messages if message.role == "user"), None)
    if first_user is not None:
        first_sentences = _sentences(first_user.content)[:3]
        context.objective = _clip(first_sentences[0], 220) if first_sentences else ""
        context.description = _clip(" ".join(first_sentences)[:400], 400)
    if not context.objective:
        context.objective = "Objective not stated explicitly in the captured conversation."

    instruction_dedup, constraint_dedup = _Deduper(), _Deduper()
    pending_dedup, completed_dedup, decision_dedup = _Deduper(), _Deduper(), _Deduper()
    api_dedup, db_dedup = _Deduper(), _Deduper()

    for index, message in enumerate(result.messages):
        sentences = _sentences(message.content)
        if not sentences:
            continue

        for sentence in sentences:
            lowered = sentence.lower()

            is_constraint = _contains(sentence, CONSTRAINT_MARKERS)

            if message.role == "user" and _contains(sentence, INSTRUCTION_MARKERS):
                # Constraints are also user instructions: keep them in both views so
                # no explicit requirement can disappear from the capsule.
                if is_constraint and len(context.constraints) < MAX_ITEMS and constraint_dedup.add(sentence):
                    context.constraints.append(
                        Evidence(_clip(sentence), "stated", index, kind="constraint")
                    )
                if len(context.instructions) < MAX_ITEMS and instruction_dedup.add(sentence):
                    if is_constraint:
                        kind = "constraint"
                    elif _contains(sentence, FORMAT_MARKERS):
                        kind = "preference"
                    else:
                        kind = "requirement"
                    context.instructions.append(Evidence(_clip(sentence), "stated", index, kind=kind))

            if _contains(sentence, DECISION_MARKERS) and len(context.decisions) < MAX_ITEMS:
                if decision_dedup.add(sentence):
                    context.decisions.append(Evidence(_clip(sentence), "stated", index, kind="decision"))
                    context.technical.decisions = list(context.decisions)

            if _contains(sentence, PENDING_MARKERS) and len(context.pending) < MAX_ITEMS:
                if not sentence.rstrip().endswith("?") and pending_dedup.add(sentence):
                    context.pending.append(TaskItem(_clip(sentence), "stated", index))

            if _contains(sentence, COMPLETED_MARKERS) and not _contains(sentence, PENDING_MARKERS):
                if len(context.completed) < MAX_ITEMS and completed_dedup.add(sentence):
                    context.completed.append(TaskItem(_clip(sentence), "stated", index))

            if ("api" in lowered or "endpoint" in lowered) and len(context.technical.apis) < 8:
                if api_dedup.add(sentence):
                    context.technical.apis.append(Evidence(_clip(sentence), "stated", index, kind="api"))

            if any(word in lowered for word in ("schema", "database table", "migration", "table ")):
                if len(context.technical.databases) < 8 and db_dedup.add(sentence):
                    context.technical.databases.append(
                        Evidence(_clip(sentence), "stated", index, kind="database")
                    )

    # -- errors with solutions ------------------------------------------------
    error_dedup = _Deduper()
    for index, message in enumerate(result.messages):
        for sentence in _sentences(message.content):
            if not _contains(sentence, ERROR_MARKERS):
                continue
            # "never expose raw SQL errors" is a requirement, not an incident.
            if _contains(sentence, INSTRUCTION_MARKERS) or _contains(sentence, CONSTRAINT_MARKERS):
                continue
            if len(context.errors) >= 8 or not error_dedup.add(sentence):
                continue
            solution = ""
            for lookahead in range(index + 1, min(index + 4, len(result.messages))):
                candidate = next(
                    (
                        item
                        for item in _sentences(result.messages[lookahead].content)
                        if _contains(item, SOLUTION_MARKERS)
                    ),
                    "",
                )
                if candidate:
                    solution = _clip(candidate)
                    break
            context.errors.append(
                ErrorItem(
                    error=_clip(sentence),
                    solution=solution,
                    resolved=bool(solution),
                    certainty="stated",
                    message_index=index,
                )
            )

    # -- technical classification -------------------------------------------
    context.technical.languages = [tech for tech in context.technologies if tech in LANGUAGES]
    context.technical.frameworks = [tech for tech in context.technologies if tech in FRAMEWORKS]
    context.technical.libraries = [
        tech
        for tech in context.technologies
        if tech not in LANGUAGES and tech not in FRAMEWORKS
    ]

    # -- next action ---------------------------------------------------------
    explicit = next(
        (
            sentence
            for sentence in reversed([s for text in texts for s in _sentences(text)])
            if sentence.lower().startswith(("next step", "next,", "now let's", "next i", "next we"))
        ),
        "",
    )
    if explicit:
        context.next_action = _clip(explicit)
        context.next_action_certainty = "stated"
    elif context.pending:
        context.next_action = context.pending[0].task
        context.next_action_certainty = "stated"
    else:
        context.next_action = "Review this capsule and continue the pending work."
        context.next_action_certainty = "inferred"

    # -- stage ---------------------------------------------------------------
    lowered_combined = combined.lower()
    if context.errors and not any(error.resolved for error in context.errors):
        context.stage = "debugging (unresolved errors)"
    elif _contains(lowered_combined, ("design", "architecture", "plan", "requirements")):
        context.stage = "planning / design"
    elif context.pending:
        context.stage = "implementation"
    elif context.completed:
        context.stage = "maintenance"
    else:
        context.stage = "unknown"
    context.stage_certainty = "inferred"

    # -- warnings ------------------------------------------------------------
    if not context.instructions:
        context.warnings.append("No explicit user instructions were detected in this capture.")
    if not context.pending:
        context.warnings.append("No pending tasks were detected; confirm the next action manually.")
    if not context.decisions:
        context.warnings.append("No explicit technical decisions were found.")
    if len(result.messages) < 3:
        context.warnings.append("Very short capture: the extracted state may be incomplete.")

    context.summary = build_summary(context)
    return context


def build_summary(context: ProjectContext) -> str:
    """Deterministic narrative summary of the project state."""
    lines = [f"Project: {context.name}"]
    if context.objective:
        lines.append(f"Objective: {context.objective}")
    if context.technologies:
        lines.append(f"Stack: {', '.join(context.technologies[:8])}")
    lines.append(f"Stage: {context.stage} (inferred)")
    lines.append(
        f"Progress: {len(context.completed)} completed task(s), {len(context.pending)} pending, "
        f"{len(context.errors)} error(s) recorded"
    )
    if context.pending:
        lines.append("Next up: " + context.pending[0].task)
    elif context.next_action:
        lines.append("Next action: " + context.next_action)
    return "\n".join(lines)
