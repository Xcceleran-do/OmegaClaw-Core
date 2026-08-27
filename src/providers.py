import logging
import json

import evidence
from context import (
    ContextBudgetError,
    ContextCompiler,
    ContextInput,
    estimate_tokens,
    loop_context_records,
    validate_context_budget,
)
from model import ModelRequest, ModelResponse

logger = logging.getLogger(__name__)

_llmProviderRegistry = {}

class LLMProvider:
    """LLM provider implementation"""

    def start(self) -> None:
        """Configure and start LLM provider"""
        pass

    def stop(self) -> None:
        """Stop and LLM provider and free resources"""
        pass

    def chat(self, prompt: str, max_tokens: int = 6000, reasoning_mode: str = "medium") -> str:
        """Legacy string adapter retained for third-party plugins."""
        raise NotImplementedError()

    def complete(self, request: ModelRequest) -> ModelResponse:
        """Complete a typed request, adapting old plugins at this seam."""
        return ModelResponse(
            text=self.chat(
                request.to_legacy_prompt(),
                request.max_output_tokens,
                request.reasoning_mode,
            )
        )

    def count_tokens(self, text: str) -> int:
        """Estimate input tokens; providers may override with their tokenizer."""
        return estimate_tokens(text)

def registerLLMProvider(id: str, provider: LLMProvider) -> None:
    """
    Register LLM provider in the registry.

    Arguments:
    id: the identifier of the plugin which is used to load it
    provider: the implementation of the provider
    """
    global _llmProviderRegistry
    logger.info(f"registerLLMProvider: registering LLM provider {id}")
    _llmProviderRegistry[id] = provider

_llmprovider: LLMProvider = None
_last_request: ModelRequest | None = None
_last_response: ModelResponse | None = None
_last_manifest: dict[str, object] | None = None
_last_task_telemetry: dict[str, object] | None = None
_task_generation: int | None = None
_task_interaction = 0


def llmProviderValidateContextBudget(
    context_window_tokens, max_output_tokens, max_new_input_loops=None
):
    """Validate and log the model's configured input/output allocation."""
    window = int(context_window_tokens)
    output = int(max_output_tokens)
    budget = validate_context_budget(window, output)
    allocation = {
        "context_window_tokens": window,
        "max_output_tokens": output,
        "input_token_budget": budget,
    }
    if max_new_input_loops is not None:
        allocation["max_new_input_loops"] = int(max_new_input_loops)
    logger.info("[CONTEXT_BUDGET] %s", json.dumps(allocation, separators=(",", ":")))
    if budget < output:
        logger.warning(
            "[CONTEXT_BUDGET_WARNING] input reserve is smaller than output reserve: %s",
            json.dumps(allocation, separators=(",", ":")),
        )
    return budget


def _next_task_interaction(task_generation: int) -> int:
    global _task_generation, _task_interaction
    if task_generation != _task_generation:
        _task_generation = task_generation
        _task_interaction = 0
    _task_interaction += 1
    return _task_interaction

def llmProviderStart(provider):
    """Select and start one of the LLM providers registered by plugins"""
    global _llmprovider
    _llmprovider = _llmProviderRegistry.get(provider, None)
    if _llmprovider is None:
        error = f"llmProviderStart: LLM provider plugin {provider} is not registered"
        logger.error(error)
        raise RuntimeError(error)
    _llmprovider.start()

def llmProviderChat(prompt, max_tokens, reasoning_mode):
    """Compatibility entry point for the current MeTTa loop."""
    request = ModelRequest.from_legacy_prompt(prompt, max_tokens, reasoning_mode)
    return llmProviderComplete(request).text

def llmProviderComplete(request: ModelRequest) -> ModelResponse:
    """Complete a typed request via the selected provider adapter."""
    global _llmprovider, _last_response
    if _llmprovider is None:
        raise RuntimeError("llmProviderComplete: no LLM provider has been started")
    response = _llmprovider.complete(request)
    if not isinstance(response, ModelResponse):
        raise TypeError("LLM provider complete() must return ModelResponse")
    _last_response = response
    if response.usage is not None:
        logger.info(
            "[LLM_USAGE] input_tokens=%s output_tokens=%s total_tokens=%s cached_input_tokens=%s",
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.usage.total_tokens,
            response.usage.cached_input_tokens,
        )
    if response.finish_reason is not None:
        logger.info(
            "[LLM_FINISH] reason=%s tool_calls=%s",
            response.finish_reason,
            len(response.tool_calls),
        )
    return response

def llmProviderContextChat(
    prompt,
    skills,
    prompt_extensions,
    output_format,
    memory_directory,
    task_message,
    user_message,
    current_time,
    history,
    context_window_tokens,
    max_output_tokens,
    reasoning_mode,
):
    """Compile ranked loop records and complete one typed model request."""
    global _last_request, _last_manifest, _last_task_telemetry, _llmprovider
    if _llmprovider is None:
        raise RuntimeError("llmProviderContextChat: no LLM provider has been started")

    evidence_stats = evidence.stats()
    interaction = _next_task_interaction(evidence_stats.task_generation)
    records = loop_context_records(
        prompt=str(prompt),
        skills=str(skills),
        prompt_extensions=str(prompt_extensions),
        output_format=str(output_format),
        memory_directory=str(memory_directory),
        current_time=str(current_time),
        evidence_records=evidence.records(),
        history=str(history),
    )
    try:
        compiled = ContextCompiler(_llmprovider.count_tokens).compile(
            ContextInput(
                records=records,
                task_message=str(task_message),
                turn_message=str(user_message),
                context_window_tokens=int(context_window_tokens),
                max_output_tokens=int(max_output_tokens),
                reasoning_mode=str(reasoning_mode),
            )
        )
    except ContextBudgetError:
        logger.exception(
            "[CONTEXT_BUDGET_FAILURE] task_generation=%s interaction=%s "
            "context_window_tokens=%s max_output_tokens=%s evidence=%s",
            evidence_stats.task_generation,
            interaction,
            context_window_tokens,
            max_output_tokens,
            json.dumps(evidence_stats.as_dict(), separators=(",", ":")),
        )
        raise
    _last_request = compiled.request
    _last_manifest = compiled.manifest.as_dict()
    _last_task_telemetry = {
        "task_generation": evidence_stats.task_generation,
        "interaction": interaction,
        "evidence": evidence_stats.as_dict(),
        "context": _last_manifest,
    }
    logger.info("[CONTEXT_MANIFEST] %s", json.dumps(_last_manifest, separators=(",", ":")))
    logger.info(
        "[TASK_TELEMETRY] %s",
        json.dumps(_last_task_telemetry, separators=(",", ":")),
    )
    if compiled.manifest.estimated_input_tokens * 10 >= compiled.manifest.input_token_budget * 9:
        logger.warning(
            "[CONTEXT_BUDGET_PRESSURE] task_generation=%s interaction=%s "
            "estimated_input_tokens=%s input_token_budget=%s omitted_records=%s",
            evidence_stats.task_generation,
            interaction,
            compiled.manifest.estimated_input_tokens,
            compiled.manifest.input_token_budget,
            len(compiled.manifest.omitted_record_ids),
        )
    debug = compiled.request.to_legacy_prompt()
    logger.info("CHARS_SENT: %s %s", len(debug), json.dumps(debug, ensure_ascii=False))
    return llmProviderComplete(compiled.request).text

def llmProviderLastRequestChars():
    """Compatibility metric for existing loop logs and tests."""
    return len(_last_request.to_legacy_prompt()) if _last_request else 0

def llmProviderLastRequestDebug():
    """Compatibility rendering for the existing debug-level prompt trace."""
    return _last_request.to_legacy_prompt() if _last_request else ""

def llmProviderLastContextManifest():
    return json.dumps(_last_manifest or {}, separators=(",", ":"))


def llmProviderLastTaskTelemetry():
    return json.dumps(_last_task_telemetry or {}, separators=(",", ":"))
