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

    def test_oversized_result_is_explicitly_truncated(self):
        rendered = evidence.append("abcdefghijklmnopqrstuvwxyz", 24)

        self.assertEqual(len(rendered), 24)
        self.assertTrue(rendered.startswith("[TOOL_RESULT_TRUNCATED"))


if __name__ == "__main__":
    unittest.main()
