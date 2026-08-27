import os
import json
import lib_llm_ext as llm
import providers
from src.logger import get_logger
from config import config_get_by_key
from model import ModelMessage, ModelRequest, ModelResponse, ModelToolCall

logger = get_logger(__name__)

class OpenAIProvider(providers.LLMProvider):

    def __init__(self):
        super().__init__()

    def start(self) -> None:
        openai_model = config_get_by_key("openai_model", "gpt-5.5")
        model = config_get_by_key("model", openai_model)
        self.delegate = OpenAIProviderImpl("OpenAI", "OPENAI_API_KEY",
                                           model, "https://api.openai.com/v1")

    def stop(self) -> None:
        self.delegate.stop()

    def chat(self, prompt: str, max_tokens: int = 6000, reasoning_mode: str = "medium") -> str:
        return self.delegate.chat(prompt, max_tokens, reasoning_mode)

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.delegate.complete(request)

def loadOmegaClawPlugin():
    providers.registerLLMProvider("OpenAI", OpenAIProvider())

class OpenAIProviderImpl(llm.AIProvider):
    """OpenAI provider using the Responses API (reasoning models)."""

    def chat(self, content: str, max_tokens: int = 6000, reasoning: str = "medium", **kwargs) -> str:
        """Legacy string adapter."""
        return self.complete(ModelRequest.from_legacy_prompt(content, max_tokens, reasoning), **kwargs).text

    def complete(self, request: ModelRequest, **kwargs) -> ModelResponse:
        """Send a typed request via the Responses API."""
        self._ensure_client()

        if self._client is None:
            raise RuntimeError(f"{self.name} not configured (set {self._var_name})")

        sysmsg = "\n\n".join(
            message.text_content(strict=True)
            for message in request.messages
            if message.role == "system"
        )
        non_system = [_responses_message(message) for message in request.messages if message.role != "system"]
        if len(non_system) == 1 and non_system[0]["role"] == "user":
            model_input = non_system[0]["content"]
        else:
            model_input = non_system

        try:
            create_kwargs = {
                "instructions": sysmsg,
                "model": self._model_name,
                "input": model_input,
                "max_output_tokens": request.max_output_tokens,
                "reasoning": {"effort": request.reasoning_mode},
                "prompt_cache_key": config_get_by_key("OPENAI_PROMPT_CACHE_KEY", llm._stable_cache_key("openai", self._model_name, sysmsg)),
            }
            # GPT-5.5 supports only 24h; GPT-5.4 also supports extended retention.
            if self._model_name.startswith(("gpt-5.5", "gpt-5.4")):
                create_kwargs["prompt_cache_retention"] = "24h"

            if request.tools:
                create_kwargs["tools"] = [_responses_tool(tool) for tool in request.tools]

            if request.response_schema:
                create_kwargs["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "response",
                        "schema": dict(request.response_schema),
                        "strict": True,
                    }
                }

            create_kwargs.update(kwargs)

            response = self._client.responses.create(**create_kwargs)

            usage = llm._model_usage(getattr(response, "usage", None))
            if usage:
                logger.info(
                    f"[LLM_USAGE] provider={self._name} model={self._model_name} "
                    f"input_tokens={usage.input_tokens} output_tokens={usage.output_tokens} "
                    f"total_tokens={usage.total_tokens} cached_tokens={usage.cached_input_tokens}"
                )

            raw = response.output_text or ""
            llm._log_raw(self._name, self._model_name, raw)
            reasoning_metadata = {}
            reasoning = getattr(response, "reasoning", None)
            if reasoning is not None:
                reasoning_metadata["reasoning"] = reasoning
            return ModelResponse(
                text=self._clean_text(raw),
                tool_calls=_response_tool_calls(response),
                usage=usage,
                finish_reason=llm._string_or_none(getattr(response, "status", None)),
                reasoning_metadata=reasoning_metadata,
            )
        except Exception as e:
            logger.exception(f"[OpenAIProviderImpl.chat]: Exception while communicating with LLM: {e}")
            return ModelResponse()


def _response_tool_calls(response) -> tuple[ModelToolCall, ...]:
    parsed = []
    for item in getattr(response, "output", None) or ():
        if getattr(item, "type", None) not in {"function_call", "custom_tool_call"}:
            continue
        arguments = getattr(item, "arguments", {})
        try:
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError:
            pass
        parsed.append(
            ModelToolCall(
                id=str(getattr(item, "call_id", getattr(item, "id", ""))),
                name=str(getattr(item, "name", "")),
                arguments=arguments,
            )
        )
    return tuple(parsed)


def _responses_message(message: ModelMessage) -> dict:
    if isinstance(message.content, str):
        return message.as_dict()

    content = []
    for block in message.content:
        if block.type == "text":
            content.append({"type": "input_text", "text": block.data.get("text", "")})
        elif block.type == "image_url":
            image = block.data.get("image_url", {})
            content.append({"type": "input_image", "image_url": image.get("url", "")})
        else:
            raise TypeError(f"OpenAI Responses does not support content block {block.type!r}")
    value = message.as_dict()
    value["content"] = content
    return value


def _responses_tool(tool) -> dict:
    value = dict(tool)
    if value.get("type") == "function" and isinstance(value.get("function"), dict):
        function = dict(value.pop("function"))
        value.update(function)
    return value
