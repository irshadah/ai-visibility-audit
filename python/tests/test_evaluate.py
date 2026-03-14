from __future__ import annotations

import json
from pathlib import Path
import unittest

from agentic_readiness.evaluate import evaluate_benchmark

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


class EvaluateBenchmarkTests(unittest.TestCase):
    def test_benchmark_summary_shape(self) -> None:
        cases = json.loads((FIXTURES / "benchmark_cases.json").read_text(encoding="utf-8"))
        summary = evaluate_benchmark(cases)
        self.assertGreaterEqual(summary["case_count"], 10)
        self.assertIn("page_type_accuracy", summary)
        self.assertIn("rules", summary)
        self.assertIn("S6", summary["rules"])

    def test_rule_metrics_include_precision_and_recall(self) -> None:
        cases = json.loads((FIXTURES / "benchmark_cases.json").read_text(encoding="utf-8"))
        summary = evaluate_benchmark(cases)
        s10 = summary["rules"]["S10"]
        self.assertIn("precision", s10)
        self.assertIn("recall", s10)


if __name__ == "__main__":
    unittest.main()
