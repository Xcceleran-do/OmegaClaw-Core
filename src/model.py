"""Provider-neutral model request and response values.

The agent loop and provider plugins meet at these values.  The legacy
``system :-:-:-: user`` string remains available only as a compatibility
adapter for plugins that have not implemented ``complete`` yet.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping


PROMPT_DELIMITER = ":-:-:-:"
ModelRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ModelContentBlock:
    """Provider-neutral envelope for non-scalar message content."""

    type: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type:
            raise ValueError("Model content block type must not be empty")

    @classmethod
    def text(cls, value: str) -> "ModelContentBlock":
        return cls("text", {"text": value})

    @classmethod
    def image_url(cls, url: str, detail: str | None = None) -> "ModelContentBlock":
        image: dict[str, str] = {"url": url}
        if detail is not None:
            image["detail"] = detail
        return cls("image_url", {"image_url": image})

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, **dict(self.data)}


ModelContent = str | tuple[ModelContentBlock, ...]


@dataclass(frozen=True)
class ModelMessage:
    role: ModelRole
    content: ModelContent
    name: str | None = None
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Unsupported model message role: {self.role}")
        if not isinstance(self.content, str):
            if not isinstance(self.content, tuple) or not all(
                isinstance(block, ModelContentBlock) for block in self.content
            ):
                raise TypeError(
                    "Model message content must be a string or tuple of ModelContentBlock values"
                )

    def as_dict(self) -> dict[str, Any]:
        content: str | list[dict[str, Any]]
        if isinstance(self.content, str):
            content = self.content
        else:
            content = [block.as_dict() for block in self.content]
        value: dict[str, Any] = {"role": self.role, "content": content}
        if self.name is not None:
            value["name"] = self.name
        if self.tool_call_id is not None:
            value["tool_call_id"] = self.tool_call_id
        return value

    def text_content(self, *, strict: bool = False) -> str:
        if isinstance(self.content, str):
            return self.content
        text = []
        for block in self.content:
            if block.type == "text" and isinstance(block.data.get("text"), str):
                text.append(block.data["text"])
            elif strict:
                raise TypeError(
                    f"Message role {self.role} contains non-text block {block.type!r}"
                )
        return "\n".join(text)


@dataclass(frozen=True)
class ModelToolCall:
    id: str
    name: str
    arguments: Any


@dataclass(frozen=True)
class ModelUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None


@dataclass(frozen=True)
class ModelRequest:
    messages: tuple[ModelMessage, ...]
    max_output_tokens: int = 6000
    reasoning_mode: str = "medium"
    tools: tuple[Mapping[str, Any], ...] = ()
    response_schema: Mapping[str, Any] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("Model request must contain at least one message")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")

    @classmethod
    def from_legacy_prompt(
        cls,
        prompt: str,
        max_output_tokens: int = 6000,
        reasoning_mode: str = "medium",
    ) -> "ModelRequest":
        if PROMPT_DELIMITER not in prompt:
            messages = (ModelMessage("user", prompt.strip()),)
        else:
            system, _, user = prompt.partition(PROMPT_DELIMITER)
            user = user.strip() or "EMPTY / NO NEW USER INPUT."
            messages = (
                ModelMessage("system", system.strip()),
                ModelMessage("user", user),
            )
        return cls(
            messages=messages,
            max_output_tokens=int(max_output_tokens),
            reasoning_mode=str(reasoning_mode),
        )

    def to_legacy_prompt(self) -> str:
        system = "\n\n".join(
            message.text_content(strict=True) for message in self.messages if message.role == "system"
        ).strip()
        conversation = [message for message in self.messages if message.role != "system"]
        if len(conversation) == 1 and conversation[0].role == "user":
            user = conversation[0].text_content(strict=True).strip()
        else:
            user = "\n\n".join(
                f"[{message.role.upper()}]\n{message.text_content(strict=True)}"
                for message in conversation
            ).strip()
        if not system:
            return user
        return f"{system} {PROMPT_DELIMITER} {user or 'EMPTY / NO NEW USER INPUT.'}"


@dataclass(frozen=True)
class ModelResponse:
    text: str = ""
    tool_calls: tuple[ModelToolCall, ...] = ()
    usage: ModelUsage | None = None
    finish_reason: str | None = None
    reasoning_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("Model response text must be a string")
