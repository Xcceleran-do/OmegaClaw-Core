import os, hashlib, json
import openai
from typing import Optional, Tuple, Dict, Any
from config import config_get_by_key
from model import ModelRequest, ModelResponse, ModelToolCall, ModelUsage, PROMPT_DELIMITER

from src.logger import get_logger


logger = get_logger(__name__)

def _log_raw(provider: str, model: str, raw: str) -> None:
    logger.debug(f"[LLM_RAW] provider={provider} model={model} chars={len(raw or '')} raw={raw!r}")

def _split_system_user(content: str) -> Tuple[str, str]:
    """
    MeTTa sends:
        <system/context> :-:-:-: <last human/wakeup message>

    Keep the split intact so providers receive a real system prompt.
    """
    request = ModelRequest.from_legacy_prompt(content)
    system = "\n\n".join(message.text_content(strict=True) for message in request.messages if message.role == "system")
    user = "\n\n".join(message.text_content(strict=True) for message in request.messages if message.role == "user")
    return system, user

def _stable_cache_key(provider: str, model: str, sysmsg: str) -> str:
    """
    Stable key for requests sharing the same system-prefix family.
    Do not include the user message here.
    """
    marker = " LAST_SKILL_USE_RESULTS: "
    stable = sysmsg.split(marker, 1)[0].strip()
    digest = hashlib.sha256(stable.encode("utf-8")).hexdigest()[:24]
    return f"{provider.lower()}:{model}:{digest}"


def _merge_dicts(base: Optional[Dict[str, Any]], extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(base or {})
    merged.update(extra or {})
    return merged

class AbstractAIProvider:
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def chat(self, content: str, max_tokens: int = 6000, reasoning: str = "medium", **kwargs) -> str:
        raise NotImplementedError

    def complete(self, request: ModelRequest, **kwargs) -> ModelResponse:
        raise NotImplementedError

    @property
    def is_available(self) -> bool:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

class AIProvider(AbstractAIProvider):
    """Lazy AI provider with on-demand initialization."""

    def __init__(self, name: str, var_name: str, model_name: str, base_url: str):
        super().__init__(name)
        self._var_name = var_name
        self._model_name = model_name
        self._base_url = base_url
        self._client = None  # lazy initialization

    def _ensure_client(self):
        """Initialize client on first use."""
        if self._client is None:
            self._client = self._create_client()

    def _create_client(self) -> Optional[openai.OpenAI]:
        """Create OpenAI client from environment."""
        proxy_url = config_get_by_key("GATEWAY_URL")
        if proxy_url:
            prefix = self._name.lower()
            base_url = f"{proxy_url.rstrip('/')}/{prefix}/"
            logger.info(f"[AIProvider._create_client]: Connecting via proxy: {base_url}")
            return openai.OpenAI(
                    api_key="proxy",
                    base_url=base_url,
                    )
        if self._var_name in os.environ:
            return openai.OpenAI(api_key=os.environ.get(self._var_name), base_url=self._base_url)

        return None

    @property
    def is_available(self) -> bool:
        """Check if provider is configured (without initializing)."""
        return bool(config_get_by_key("GATEWAY_URL")) or bool(os.environ.get(self._var_name))

    def _build_messages(self, content: str):
        return [message.as_dict() for message in ModelRequest.from_legacy_prompt(content).messages]

    def chat(self, content: str, max_tokens: int = 6000, reasoning: str = "medium", **kwargs) -> str:
        """Legacy string adapter."""
        request = ModelRequest.from_legacy_prompt(content, max_tokens, reasoning)
        return self.complete(request, **kwargs).text

    def complete(self, request: ModelRequest, **kwargs) -> ModelResponse:
        """Send a typed request via an OpenAI-compatible chat API."""
        self._ensure_client()

        if self._client is None:
            raise RuntimeError(f"{self.name} not configured (set {self._var_name})")

        try:
            create_kwargs = {
                "model": self._model_name,
                "messages": [message.as_dict() for message in request.messages],
                "max_tokens": request.max_output_tokens,
                **kwargs,
            }
            if request.tools:
                create_kwargs["tools"] = [dict(tool) for tool in request.tools]
            if request.response_schema:
                create_kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": dict(request.response_schema),
                        "strict": True,
                    },
                }
            response = self._client.chat.completions.create(**create_kwargs)

            choice = response.choices[0]
            message = choice.message
            raw = message.content or ""
            _log_raw(self._name, self._model_name, raw)
            reasoning_metadata = {}
            reasoning = getattr(message, "reasoning", None)
            if reasoning is not None:
                reasoning_metadata["reasoning"] = reasoning
            return ModelResponse(
                text=self._clean_text(raw),
                tool_calls=_chat_tool_calls(message),
                usage=_model_usage(getattr(response, "usage", None)),
                finish_reason=_string_or_none(getattr(choice, "finish_reason", None)),
                reasoning_metadata=reasoning_metadata,
            )
        except Exception as e:
            logger.exception(f"[AIProvider.chat]: Exception while communicating with LLM: {e}")
            return ModelResponse()

    def _clean_text(self, text: str) -> str:
        """Unescape special characters."""
        return text.replace("_quote_", '"').replace("_apostrophe_", "'").replace("</arg_value>", " ") \
                    .replace("</tool_call>", " ").replace("<arg_value>", " ").replace("<tool_call>", " ")

    def stop(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None


def _model_usage(usage) -> ModelUsage | None:
    if usage is None:
        return None
    input_tokens = getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", None))
    output_tokens = getattr(usage, "completion_tokens", getattr(usage, "output_tokens", None))
    total_tokens = getattr(usage, "total_tokens", None)
    details = getattr(usage, "prompt_tokens_details", getattr(usage, "input_tokens_details", None))
    cached_tokens = getattr(details, "cached_tokens", None) if details is not None else None
    return ModelUsage(input_tokens, output_tokens, total_tokens, cached_tokens)


def _chat_tool_calls(message) -> tuple[ModelToolCall, ...]:
    parsed = []
    for call in getattr(message, "tool_calls", None) or ():
        function = getattr(call, "function", None)
        name = getattr(function, "name", "")
        arguments = getattr(function, "arguments", {})
        try:
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            pass
        parsed.append(ModelToolCall(id=str(getattr(call, "id", "")), name=str(name), arguments=arguments))
    return tuple(parsed)


def _string_or_none(value) -> str | None:
    return None if value is None else str(value)


_embedding_model = None

def initLocalEmbedding():
    model_name="intfloat/e5-large-v2"
    global _embedding_model
    os.environ["HF_HUB_OFFLINE"] = "1"
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(model_name)
    return _embedding_model

def useLocalEmbedding(atom):
    global _embedding_model
    if _embedding_model is None:
        raise RuntimeError("Call initLocalEmbedding() first.")
    return _embedding_model.encode(
        atom,
        normalize_embeddings=True
    ).tolist()
