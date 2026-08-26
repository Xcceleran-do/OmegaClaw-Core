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

        evidence.append("next-result", 200)
        self.assertIn("TOOL_RESULT_TRUNCATED", evidence.render())
        self.assertTrue(evidence.render().endswith("next-result"))


if __name__ == "__main__":
    unittest.main()
