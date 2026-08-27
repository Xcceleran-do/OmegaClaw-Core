"""Token-budgeted, whole-record model context compilation."""

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Callable, Iterable

from model import ModelMessage, ModelRequest, ModelRole


TokenCounter = Callable[[str], int]
_HISTORY_RECORD = re.compile(r'^\("\d{4}-\d{2}-\d{2} ')


class ContextBudgetError(ValueError):
    """Required context does not fit after reserving model output tokens."""


@dataclass(frozen=True)
class ContextRecord:
    id: str
    kind: str
    text: str
    priority: int
    required: bool = False
    message_role: ModelRole = "system"

    def render(self) -> str:
        return f"[{self.kind} id={self.id}]\n{self.text.strip()}"


@dataclass(frozen=True)
class ContextInput:
    records: tuple[ContextRecord, ...]
    task_message: str
    turn_message: str
    context_window_tokens: int
    max_output_tokens: int
    reasoning_mode: str = "medium"


@dataclass(frozen=True)
class ContextManifest:
    input_token_budget: int
    estimated_input_tokens: int
    included_record_ids: tuple[str, ...]
    omitted_record_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "input_token_budget": self.input_token_budget,
            "estimated_input_tokens": self.estimated_input_tokens,
            "included_record_ids": list(self.included_record_ids),
            "omitted_record_ids": list(self.omitted_record_ids),
        }


@dataclass(frozen=True)
class CompiledContext:
    request: ModelRequest
    manifest: ContextManifest


class ContextCompiler:
    """Select complete records and produce one provider-neutral request."""

    def __init__(self, count_tokens: TokenCounter | None = None):
        self._count_tokens = count_tokens or estimate_tokens

    def compile(self, context: ContextInput) -> CompiledContext:
        budget = int(context.context_window_tokens) - int(context.max_output_tokens)
        if budget <= 0:
            raise ContextBudgetError(
                "context_window_tokens must be greater than max_output_tokens"
            )

        indexed = list(enumerate(context.records))
        selected = {index for index, record in indexed if record.required}
        required_messages = self._messages(context, selected)
        required_tokens = self._count_messages(required_messages)
        if required_tokens > budget:
            required_ids = [record.id for record in context.records if record.required]
            raise ContextBudgetError(
                f"Required context needs {required_tokens} tokens but budget is {budget}; "
                f"record_ids={required_ids}"
            )

        optional = sorted(
            ((index, record) for index, record in indexed if not record.required),
            key=lambda item: (item[1].priority, item[0]),
            reverse=True,
        )
        for index, _record in optional:
            candidate = selected | {index}
            if self._count_messages(self._messages(context, candidate)) <= budget:
                selected = candidate

        messages = self._messages(context, selected)
        estimated_tokens = self._count_messages(messages)
        included = tuple(record.id for index, record in indexed if index in selected)
        omitted = tuple(record.id for index, record in indexed if index not in selected)
        manifest = ContextManifest(
            input_token_budget=budget,
            estimated_input_tokens=estimated_tokens,
            included_record_ids=included,
            omitted_record_ids=omitted,
        )
        request = ModelRequest(
            messages=messages,
            max_output_tokens=int(context.max_output_tokens),
            reasoning_mode=context.reasoning_mode,
            metadata={"context_manifest": manifest.as_dict()},
        )
        return CompiledContext(request=request, manifest=manifest)

    def _messages(self, context: ContextInput, selected: set[int]) -> tuple[ModelMessage, ...]:
        system = "\n\n".join(
            record.render()
            for index, record in enumerate(context.records)
            if index in selected and record.message_role == "system"
        )
        user_context = "\n\n".join(
            record.render()
            for index, record in enumerate(context.records)
            if index in selected and record.message_role == "user"
        )
        active_task = _active_user_message(context.task_message, context.turn_message)
        user = f"{user_context}\n\n[ACTIVE_TASK]\n{active_task}" if user_context else active_task
        return (
            ModelMessage("system", system),
            ModelMessage("user", user),
        )

    def _count_messages(self, messages: tuple[ModelMessage, ...]) -> int:
        # Four tokens per message and two for assistant priming are the common
        # chat framing estimate. Provider adapters can inject an exact counter.
        return 2 + sum(4 + max(0, int(self._count_tokens(message.content))) for message in messages)


def estimate_tokens(text: str) -> int:
    """Portable fallback when a provider has no tokenizer implementation."""
    if not text:
        return 0
    return max(1, math.ceil(len(text.encode("utf-8")) / 3))


def history_records(content: str) -> tuple[ContextRecord, ...]:
    """Parse complete records from the bounded history text supplied by MeTTa."""
    records = []
    complete = (text for text in _top_level_expressions(content) if _HISTORY_RECORD.match(text))
    for index, text in enumerate(complete, start=1):
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        records.append(
            ContextRecord(
                id=f"history-{index}-{digest}",
                kind="HISTORY_RECORD",
                text=text,
                priority=20,
                message_role="user",
            )
        )
    return tuple(records)


def _active_user_message(task_message: str, turn_message: str) -> str:
    """Keep the active task in the user role on every continuation turn."""
    task = task_message.strip()
    turn = turn_message.strip()
    if turn and task and task in turn:
        return turn
    if task and turn:
        return f"CURRENT_TASK:\n{task}\n\nTURN_SIGNAL:\n{turn}"
    if task:
        return f"CURRENT_TASK:\n{task}\n\nContinue the current task using the available evidence."
    return turn or "EMPTY / NO NEW USER INPUT."


def _top_level_expressions(content: str) -> tuple[str, ...]:
    """Split MeTTa history into complete top-level expressions."""
    records = []
    start = None
    depth = 0
    in_string = False
    escaped = False

    for index, char in enumerate(content):
        if start is None:
            if char == "(":
                start = index
                depth = 1
            continue

        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                records.append(content[start:index + 1].strip())
                start = None

    return tuple(records)


def loop_context_records(
    *,
    prompt: str,
    skills: str,
    prompt_extensions: str,
    output_format: str,
    memory_directory: str,
    current_time: str,
    evidence_records: Iterable[object],
    history: str,
) -> tuple[ContextRecord, ...]:
    """Adapt existing loop inputs into ranked records for the compiler."""
    records = [
        ContextRecord("system-prompt", "PROMPT", prompt, 100, required=True),
        ContextRecord("skills", "SKILLS", skills, 95, required=True),
        ContextRecord("prompt-extensions", "PROMPT_EXTENSIONS", prompt_extensions, 95, required=True),
        ContextRecord("output-format", "OUTPUT_FORMAT", output_format, 100, required=True),
        ContextRecord("memory-directory", "SAVE_PERMANENT_FILES_DIR", memory_directory, 90, required=True),
        ContextRecord("evidence-header", "LAST_SKILL_USE_RESULTS", "Tool evidence follows.", 90, required=True),
    ]
    records.extend(
        ContextRecord(
            id=str(getattr(record, "id")),
            kind="TOOL_RESULT",
            text=str(getattr(record, "text")),
            priority=80,
            message_role="user",
        )
        for record in evidence_records
    )
    records.append(
        ContextRecord(
            "history-header",
            "HISTORY",
            "Conversation records follow.",
            30,
            required=True,
            message_role="user",
        )
    )
    records.extend(history_records(history))
    records.append(ContextRecord("current-time", "TIME", current_time, 90, required=True))
    return tuple(records)
