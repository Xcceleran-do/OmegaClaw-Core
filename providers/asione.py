import lib_llm_ext as llm
import providers
from src.logger import get_logger
from config import config_get_by_key
from model import ModelRequest, ModelResponse

logger = get_logger(__name__)

class ASIOneProvider(providers.LLMProvider):

    def __init__(self):
        super().__init__()

    def start(self) -> None:
        asione_model = config_get_by_key("asione_model", "asi1-ultra")
        model = config_get_by_key("model", asione_model)
        self.delegate = ASIOneProviderImpl("ASIOne", "ASIONE_API_KEY",
                                           model, "https://api.asi1.ai/v1")

    def stop(self) -> None:
        self.delegate.stop()

    def chat(self, prompt: str, max_tokens: int = 6000, reasoning_mode: str = "medium") -> str:
        return self.delegate.chat(prompt, max_tokens, reasoning_mode)

    def complete(self, request: ModelRequest) -> ModelResponse:
        return self.delegate.complete(request)

def loadOmegaClawPlugin():
    providers.registerLLMProvider("ASIOne", ASIOneProvider())

class ASIOneProviderImpl(llm.AIProvider):
    """Lazy AI provider with on-demand initialization."""

    def __init__(self, name: str, var_name: str, model_name: str, base_url: str):
        super().__init__(name, var_name, model_name, base_url)

    def complete(self, request: ModelRequest, **kwargs) -> ModelResponse:
        extra_body = llm._merge_dicts(
            {
                "enable_thinking": True,
                "thinking_budget": min(6000, request.max_output_tokens),
            },
            kwargs.pop("extra_body", None),
        )
        return super().complete(request, extra_body=extra_body, **kwargs)
