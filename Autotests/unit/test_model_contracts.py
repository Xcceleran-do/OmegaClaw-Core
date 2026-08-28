"""Interface tests for the typed model/provider seam."""

import unittest
from unittest.mock import patch
from pathlib import Path
import importlib.util
import json
import sys
import types

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
        telemetry = json.loads(providers.llmProviderLastTaskTelemetry())
        self.assertEqual(telemetry["interaction"], 1)
        self.assertEqual(telemetry["evidence"]["retained_records"], 2)
        self.assertEqual(telemetry["evidence"]["source_marker_mismatches"], 0)
        self.assertEqual(telemetry["context"]["tool_results"]["candidate"]["count"], 2)

    def test_task_interaction_counter_resets_with_evidence(self):
        class CapturingProvider(providers.LLMProvider):
            def complete(self, _request):
                return ModelResponse(text="done")

        def run_once():
            with patch.object(providers, "_llmprovider", CapturingProvider()):
                providers.llmProviderContextChat(
                    "rules", "skills", "", "one command", "/tmp", "task", "task",
                    "2026-08-27 00:00:00", "", 400, 50, "medium",
                )
            return json.loads(providers.llmProviderLastTaskTelemetry())

        first = run_once()
        second = run_once()
        evidence.reset()
        after_reset = run_once()

        self.assertEqual(first["interaction"], 1)
        self.assertEqual(second["interaction"], 2)
        self.assertEqual(after_reset["interaction"], 1)
        self.assertNotEqual(first["task_generation"], after_reset["task_generation"])

    def test_startup_budget_validation_logs_resolved_allocation(self):
        with patch.object(providers.logger, "info") as info:
            budget = providers.llmProviderValidateContextBudget(32768, 6000, 50)

        self.assertEqual(budget, 26768)
        self.assertIn("[CONTEXT_BUDGET]", info.call_args.args[0])
        self.assertIn('"max_new_input_loops":50', info.call_args.args[1])

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

    def test_loop_has_no_dead_context_assembler_and_clears_finished_task_on_wake(self):
        loop = (Path(__file__).parents[2] / "src" / "loop.metta").read_text()

        self.assertNotIn("(= (getContext)", loop)
        self.assertIn(
            '(progn (py-call (evidence.reset))\n'
            '                                           (change-state! &prevmsg "")',
            loop,
        )
        self.assertIn("($respi (catch (llmProviderContextChat", loop)
        self.assertLess(
            loop.index("(initLogger)"),
            loop.index("providers.llmProviderValidateContextBudget"),
        )

    def test_chars_sent_trace_is_single_line_and_precedes_provider_call(self):
        events = []

        class CapturingProvider(providers.LLMProvider):
            def complete(self, _request):
                events.append("provider-call")
                return ModelResponse(text="done")

        def capture_log(template, *args):
            rendered = template % args
            if "CHARS_SENT:" in rendered:
                events.append(rendered)

        with (
            patch.object(providers, "_llmprovider", CapturingProvider()),
            patch.object(providers.logger, "info", side_effect=capture_log),
        ):
            providers.llmProviderContextChat(
                "rules",
                "skills",
                "",
                "one command",
                "/tmp",
                "write",
                "write",
                "2026-08-27 00:00:00",
                "",
                400,
                50,
                "medium",
            )

        self.assertTrue(events[0].startswith("CHARS_SENT:"))
        self.assertEqual(len(events[0].splitlines()), 1)
        self.assertIn("LAST_SKILL_USE_RESULTS:", events[0])
        self.assertEqual(events[1], "provider-call")

    def test_prompt_cache_key_ignores_per_turn_context(self):
        openai_stub = types.ModuleType("openai")
        openai_stub.OpenAI = object
        config_stub = types.ModuleType("config")
        config_stub.config_get_by_key = lambda _key, default=None: default
        path = Path(__file__).parents[2] / "providers" / "lib_llm_ext.py"
        spec = importlib.util.spec_from_file_location("lib_llm_ext_cache_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"openai": openai_stub, "config": config_stub}):
            spec.loader.exec_module(module)

        first = "PROMPT: rules\n\nLAST_SKILL_USE_RESULTS: [id=evidence-header]\nTIME: one"
        second = "PROMPT: rules\n\nLAST_SKILL_USE_RESULTS: [id=evidence-header]\nTIME: two"
        self.assertEqual(
            module._stable_cache_key("openai", "model", first),
            module._stable_cache_key("openai", "model", second),
        )


if __name__ == "__main__":
    unittest.main()
