import unittest

import evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        evidence.reset()

    def test_accumulates_results_and_resets_for_new_task(self):
        evidence.append("result-a", 100)
        evidence.append("result-b", 100)

        self.assertEqual(evidence.render(), "result-a\nresult-b")

        evidence.reset()
        self.assertEqual(evidence.render(), "")

    def test_budget_evicts_whole_old_records(self):
        evidence.append("aaaa", 9)
        evidence.append("bbbb", 9)
        evidence.append("cccc", 9)

        self.assertEqual(evidence.render(), "bbbb\ncccc")
        stats = evidence.stats()
        self.assertEqual(stats.appended_records, 3)
        self.assertEqual(stats.appended_chars, 12)
        self.assertEqual(stats.retained_records, 2)
        self.assertEqual(stats.retained_chars, 8)
        self.assertEqual(stats.evicted_records, 1)
        self.assertEqual(stats.evicted_chars, 4)

    def test_tiny_budget_truncates_the_marker_to_reserved_space(self):
        rendered = evidence.append("abcdefghijklmnopqrstuvwxyz", 24)

        self.assertEqual(len(rendered), 12)
        self.assertTrue("[TOOL_RESULT_TRUNCATED".startswith(rendered))

    def test_oversized_result_reserves_room_for_later_evidence(self):
        oversized = "source-url:" + "a" * 380 + ":article-tail"
        rendered = evidence.append(oversized, 200)

        self.assertEqual(len(rendered), 100)
        self.assertTrue(rendered.startswith("[TOOL_RESULT_TRUNCATED"))
        self.assertIn("source", rendered)
        self.assertTrue(rendered.endswith("tail"))
        stats = evidence.stats()
        self.assertEqual(stats.truncated_records, 1)
        self.assertEqual(stats.truncated_chars, len(oversized) - len(rendered))

        evidence.append("next-result", 200)
        self.assertIn("TOOL_RESULT_TRUNCATED", evidence.render())
        self.assertTrue(evidence.render().endswith("next-result"))

    def test_reset_starts_new_telemetry_generation(self):
        first_generation = evidence.stats().task_generation
        evidence.append("old", 100)

        evidence.reset()

        stats = evidence.stats()
        self.assertEqual(stats.task_generation, first_generation + 1)
        self.assertEqual(stats.appended_records, 0)
        self.assertEqual(stats.retained_records, 0)


if __name__ == "__main__":
    unittest.main()
