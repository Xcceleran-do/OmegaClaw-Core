"""Interface-level tests for token-budgeted context compilation."""

import unittest

import evidence
from context import ContextBudgetError, ContextCompiler, ContextInput, ContextRecord, history_records


def words(text):
    return len(text.split())


def record(record_id, text, priority, required=False, message_role="system"):
    return ContextRecord(record_id, "TEST", text, priority, required, message_role)


class ContextCompilerTests(unittest.TestCase):
    def tearDown(self):
        evidence.reset()

    def test_reserves_output_tokens_and_keeps_whole_records(self):
        compiler = ContextCompiler(count_tokens=words)
        context = ContextInput(
            records=(
                record("task-facts", "required facts", 100, required=True),
                record("evidence-a", "alpha evidence complete", 80, message_role="user"),
                record("evidence-b", "beta evidence complete", 80, message_role="user"),
                record("history-a", "old conversation record", 20, message_role="user"),
            ),
            task_message="write now",
            turn_message="write now",
            context_window_tokens=31,
            max_output_tokens=8,
        )

        compiled = compiler.compile(context)

        self.assertEqual(compiled.manifest.input_token_budget, 23)
        self.assertEqual(compiled.manifest.included_record_ids, ("task-facts", "evidence-b"))
        self.assertEqual(compiled.manifest.omitted_record_ids, ("evidence-a", "history-a"))
        system = compiled.request.messages[0].content
        user = compiled.request.messages[1].content
        self.assertNotIn("beta evidence complete", system)
        self.assertIn("beta evidence complete", user)
        self.assertNotIn("alpha evidence complete", user)
        self.assertNotIn("old conversation record", user)

    def test_evidence_outranks_history_even_when_history_is_newer(self):
        compiler = ContextCompiler(count_tokens=words)
        context = ContextInput(
            records=(
                record("required", "rules", 100, required=True),
                record("evidence", "source body", 80),
                record("history", "recent chatter", 20),
            ),
            task_message="compose",
            turn_message="compose",
            context_window_tokens=23,
            max_output_tokens=4,
        )

        compiled = compiler.compile(context)

        self.assertIn("evidence", compiled.manifest.included_record_ids)
        self.assertIn("history", compiled.manifest.omitted_record_ids)

    def test_required_context_fails_closed_instead_of_being_sliced(self):
        compiler = ContextCompiler(count_tokens=words)
        context = ContextInput(
            records=(record("oversized-task", "one two three four five six", 100, required=True),),
            task_message="one two three four five six",
            turn_message="",
            context_window_tokens=10,
            max_output_tokens=2,
        )

        with self.assertRaisesRegex(ContextBudgetError, "oversized-task"):
            compiler.compile(context)

    def test_history_reader_returns_complete_stable_records(self):
        content = (
            '("2026-08-26 10:00:00" "HUMAN_MESSAGE: A")\n'
            '("2026-08-26 10:01:00" "HUMAN_MESSAGE: B")\n'
        )
        first = history_records(content)
        second = history_records(content)

        self.assertEqual(
            [item.text for item in first],
            [
                '("2026-08-26 10:00:00" "HUMAN_MESSAGE: A")',
                '("2026-08-26 10:01:00" "HUMAN_MESSAGE: B")',
            ],
        )
        self.assertEqual([item.id for item in first], [item.id for item in second])

    def test_history_reader_ignores_parentheses_and_record_like_text_inside_strings(self):
        records = history_records(
            '("2026-08-26 10:00:00" "line one\\n(\\\"2026-08-27 fake\\\" nested)")\n'
            '("2026-08-26 10:01:00" (send "done"))\n'
        )

        self.assertEqual(len(records), 2)
        self.assertTrue(records[0].text.endswith('nested)\")'))
        self.assertEqual(records[1].text, '("2026-08-26 10:01:00" (send "done"))')

    def test_history_reader_discards_a_leading_partial_record(self):
        records = history_records(
            'truncated text (send "not a record"))\n'
            '("2026-08-26 10:01:00" (send "complete"))\n'
        )

        self.assertEqual(
            [item.text for item in records],
            ['("2026-08-26 10:01:00" (send "complete"))'],
        )

    def test_evidence_records_have_task_local_stable_ids(self):
        evidence.append("first", 100)
        evidence.append("second", 100)

        self.assertEqual(
            [(item.id, item.text) for item in evidence.records()],
            [("tool-result-1", "first"), ("tool-result-2", "second")],
        )

        evidence.reset()
        evidence.append("new task", 100)
        self.assertEqual(
            [(item.id, item.text) for item in evidence.records()],
            [("tool-result-1", "new task")],
        )


if __name__ == "__main__":
    unittest.main()
