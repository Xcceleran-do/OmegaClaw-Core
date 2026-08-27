"""Interface tests for the typed model/provider seam."""

import unittest
from unittest.mock import patch

import evidence
import providers
from model import ModelContentBlock, ModelMessage, ModelRequest, ModelResponse


class ModelContractTests(unittest.TestCase):
    def tearDown(self):
        evidence.reset()

    def test_legacy_prompt_becomes_role_preserving_request(self):
        request = ModelRequest.from_legacy_prompt("stable system :-:-:-: active task", 8000, "high")

        self.assertEqual(
            request.messages,
            (ModelMessage("system", "stable system"), ModelMessage("user", "active task")),
        )
        self.assertEqual(request.max_output_tokens, 8000)
        self.assertEqual(request.reasoning_mode, "high")

    def test_empty_legacy_user_message_gets_explicit_wakeup_text(self):
        request = ModelRequest.from_legacy_prompt("stable system :-:-:-:   ")

        self.assertEqual(request.messages[-1], ModelMessage("user", "EMPTY / NO NEW USER INPUT."))

    def test_legacy_provider_is_adapted_only_at_provider_seam(self):
        class LegacyProvider(providers.LLMProvider):
            def __init__(self):
                self.received = None

            def chat(self, prompt, max_tokens=6000, reasoning_mode="medium"):
                self.received = (prompt, max_tokens, reasoning_mode)
                return "legacy reply"

        provider = LegacyProvider()
        request = ModelRequest(
            messages=(ModelMessage("system", "rules"), ModelMessage("user", "task")),
            max_output_tokens=321,
            reasoning_mode="low",
        )

        with patch.object(providers, "_llmprovider", provider):
            response = providers.llmProviderComplete(request)

        self.assertEqual(response, ModelResponse(text="legacy reply"))
        self.assertEqual(provider.received, ("rules :-:-:-: task", 321, "low"))

    def test_typed_provider_response_metadata_survives_registry(self):
        expected = ModelResponse(text="done", finish_reason="stop", reasoning_metadata={"effort": "medium"})

        class TypedProvider(providers.LLMProvider):
            def complete(self, request):
                if request.messages[-1].content != "task":
                    raise AssertionError("task message was not preserved")
                return expected

        with patch.object(providers, "_llmprovider", TypedProvider()):
            actual = providers.llmProviderComplete(ModelRequest(messages=(ModelMessage("user", "task"),)))

        self.assertIs(actual, expected)

    def test_content_blocks_reach_typed_provider_without_flattening(self):
        blocks = (
            ModelContentBlock.text("inspect this"),
            ModelContentBlock.image_url("https://example.test/source.png", "high"),
        )

        class TypedProvider(providers.LLMProvider):
            def complete(self, request):
                self.request = request
                return ModelResponse(text="seen")

        provider = TypedProvider()
        request = ModelRequest(messages=(ModelMessage("user", blocks),))
        with patch.object(providers, "_llmprovider", provider):
            providers.llmProviderComplete(request)

        self.assertIs(provider.request, request)
        self.assertEqual(provider.request.messages[0].content, blocks)
        with self.assertRaisesRegex(TypeError, "non-text block"):
            request.to_legacy_prompt()

    def test_legacy_loop_entry_still_returns_plain_text(self):
        class TypedProvider(providers.LLMProvider):
            def complete(self, request):
                if request.messages[0].role != "system":
                    raise AssertionError("system role was not preserved")
                return ModelResponse(text="plain loop reply", finish_reason="stop")

        with patch.object(providers, "_llmprovider", TypedProvider()):
            actual = providers.llmProviderChat("rules :-:-:-: task", 99, "medium")

        self.assertEqual(actual, "plain loop reply")

    def test_loop_context_compiles_records_before_calling_provider(self):
        class CapturingProvider(providers.LLMProvider):
            def __init__(self):
                self.request = None

            def count_tokens(self, text):
                return len(text.split())

            def complete(self, request):
                self.request = request
                return ModelResponse(text="compiled reply", finish_reason="stop")

        provider = CapturingProvider()
        evidence.append("source A", 1000)
        evidence.append("source B", 1000)

        with patch.object(providers, "_llmprovider", provider):
            result = providers.llmProviderContextChat(
                "system rules",
                "send and search",
                "task extension",
                "one command",
                "/tmp",
                "write the article",
                "HUMAN-MSG: write the article",
                "2026-08-26 12:00:00",
                "",
                200,
                50,
                "medium",
            )

        self.assertEqual(result, "compiled reply")
        self.assertEqual(
            provider.request.messages[-1].role,
            "user",
        )
        self.assertIn("HUMAN-MSG: write the article", provider.request.messages[-1].content)
        self.assertIn("source A", provider.request.messages[-1].content)
        self.assertIn("source B", provider.request.messages[-1].content)
        self.assertNotIn("source A", provider.request.messages[0].content)
        manifest = provider.request.metadata["context_manifest"]
        self.assertIn("tool-result-1", manifest["included_record_ids"])
        self.assertIn("tool-result-2", manifest["included_record_ids"])

    def test_continuation_keeps_current_task_in_required_user_message(self):
        class CapturingProvider(providers.LLMProvider):
            def complete(self, request):
                self.request = request
                return ModelResponse(text="continue")

        provider = CapturingProvider()
        with patch.object(providers, "_llmprovider", provider):
            providers.llmProviderContextChat(
                "rules",
                "skills",
                "",
                "one command",
                "/tmp",
                "write the article from source A",
                "",
                "2026-08-26 12:00:00",
                "",
                400,
                50,
                "medium",
            )

        self.assertIn("write the article from source A", provider.request.messages[-1].content)


if __name__ == "__main__":
    unittest.main()
