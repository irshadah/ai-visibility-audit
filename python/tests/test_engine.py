from __future__ import annotations

import json
from pathlib import Path
import unittest

from agentic_readiness.engine import ScoringEngine

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


class ScoringEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.products = json.loads((FIXTURES / "products.json").read_text(encoding="utf-8"))["products"]
        self.previous = json.loads((FIXTURES / "previous_report.json").read_text(encoding="utf-8"))

    def test_global_rubric_fallback_is_used(self) -> None:
        engine = ScoringEngine.from_rubric_file()
        report = engine.score_batch(self.products)
        self.assertEqual(report["scoring_meta"]["rubric_source"], "global_fallback")

    def test_custom_rubric_is_used(self) -> None:
        engine = ScoringEngine.from_rubric_file(str(FIXTURES / "custom_rubric.json"))
        engine.rubric["is_custom"] = True
        report = engine.score_batch(self.products)
        self.assertEqual(report["scoring_meta"]["rubric_source"], "custom")

    def test_confidence_gate_blocks_low_confidence_product(self) -> None:
        engine = ScoringEngine.from_rubric_file()
        report = engine.score_batch(self.products)
        low = next(p for p in report["products"] if p["product_id"] == "SKU-LOWCONF")
        self.assertTrue(low["blocked"])
        self.assertIsNone(low["overall_score"])
        self.assertLess(low["confidence"], 70)

    def test_regression_delta_available_when_previous_exists(self) -> None:
        engine = ScoringEngine.from_rubric_file()
        report = engine.score_batch(self.products, previous_report=self.previous)
        current = next(p for p in report["products"] if p["product_id"] == "SKU-123")
        self.assertTrue(current["regression"]["has_previous"])
        self.assertIn("overall_delta", current["regression"])

    def test_rule_skipped_for_non_matching_page_type(self) -> None:
        engine = ScoringEngine.from_mode("GEO")
        product = {
            "product_id": "url::https://example.com/category/ski",
            "url": "https://example.com/category/ski",
            "prevalence": 1.0,
            "has_feed": False,
            "schema": {"product_present": False, "required_field_coverage": 0.0},
            "page": {
                "page_type": "plp_category",
                "indexable": True,
                "og_coverage": 1.0,
                "url_hygiene": True,
                "price_availability_machine_readable": True,
                "variant_clarity": True,
            },
            "content": {
                "title_length": 55,
                "description_length": 320,
                "attribute_completeness": 0.9,
                "pricing_clarity": True,
                "policy_clarity": True,
                "review_presence": False,
                "support_trust_info": True,
            },
            "semantic": {
                "ambiguity_count": 0,
                "entity_consistency": 0.9,
                "query_answerability": 0.9,
                "factual_grounding": 0.9,
                "llm_variance": 0,
            },
            "ux": {
                "render_accessibility": True,
                "core_discoverability": True,
                "media_quality": 1.0,
                "mobile_readability": True,
            },
        }
        report = engine.score_batch([product])
        rationale = report["products"][0]["rationale"]
        c6 = next(r for r in rationale if r["rule_id"] == "C6")
        self.assertEqual(c6["status"], "not_applicable_page_type")


if __name__ == "__main__":
    unittest.main()
