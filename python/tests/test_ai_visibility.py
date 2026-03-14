from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from agentic_readiness.ai_visibility import (
    _analyze_response,
    _score_visibility,
    build_probe_prompts,
    run_ai_visibility_scan,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


class AiVisibilityTests(unittest.TestCase):
    def test_probe_set_is_deterministic(self) -> None:
        a = build_probe_prompts("example.com", "BrandX", "BrandX Inc")
        b = build_probe_prompts("example.com", "BrandX", "BrandX Inc")
        self.assertEqual(a, b)
        self.assertGreaterEqual(len(a), 8)

    def test_benchmark_precision_recall(self) -> None:
        rows = json.loads((FIXTURES / "visibility_benchmark_cases.json").read_text(encoding="utf-8"))
        tp_m = fp_m = fn_m = 0
        tp_c = fp_c = fn_c = 0
        for row in rows:
            analysis = _analyze_response(
                row["response_text"],
                aliases=[row["alias"]],
                domain=row["domain"],
            )
            exp = row["expected"]
            if analysis["mentioned"] and exp["mentioned"]:
                tp_m += 1
            elif analysis["mentioned"] and not exp["mentioned"]:
                fp_m += 1
            elif (not analysis["mentioned"]) and exp["mentioned"]:
                fn_m += 1

            if analysis["cited"] and exp["cited"]:
                tp_c += 1
            elif analysis["cited"] and not exp["cited"]:
                fp_c += 1
            elif (not analysis["cited"]) and exp["cited"]:
                fn_c += 1

        mention_precision = tp_m / max(1, tp_m + fp_m)
        mention_recall = tp_m / max(1, tp_m + fn_m)
        citation_precision = tp_c / max(1, tp_c + fp_c)
        citation_recall = tp_c / max(1, tp_c + fn_c)
        self.assertGreaterEqual(mention_precision, 0.75)
        self.assertGreaterEqual(mention_recall, 0.66)
        self.assertGreaterEqual(citation_precision, 0.75)
        self.assertGreaterEqual(citation_recall, 0.75)

    def test_score_drift_snapshot(self) -> None:
        provider_metrics = {
            "chatgpt": {"mention_rate": 0.75, "citation_rate": 0.5, "sentiment_avg": 0.4},
            "gemini": {"mention_rate": 0.5, "citation_rate": 0.4, "sentiment_avg": 0.2},
            "claude": {"mention_rate": 0.75, "citation_rate": 0.6, "sentiment_avg": 0.3},
        }
        topics = [
            {"visibility": 100},
            {"visibility": 50},
            {"visibility": 30},
            {"visibility": 90},
        ]
        score = _score_visibility(provider_metrics, topics)
        self.assertEqual(score["overall_score"], 63)
        self.assertEqual(score["overall_label"], "Medium")

    @patch("agentic_readiness.ai_visibility._provider_call")
    @patch("agentic_readiness.ai_visibility._extract_brand_info")
    def test_run_scan_with_mocked_providers(self, mock_extract, mock_provider_call) -> None:
        mock_extract.return_value = {
            "domain": "example.com",
            "title": "Example",
            "brand_name": "BrandX",
            "company_name": "BrandX Inc",
        }

        def fake_call(provider: str, prompt: str, cfg) -> str:
            if provider == "chatgpt":
                return "BrandX is trusted. Official site is https://example.com"
            if provider == "gemini":
                return "I recommend BrandX for this category."
            return "No clear recommendation."

        mock_provider_call.side_effect = fake_call
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "x",
                "GEMINI_API_KEY": "x",
                "ANTHROPIC_API_KEY": "x",
                "AI_VIS_MAX_PROMPTS": "3",
            },
            clear=False,
        ):
            result = run_ai_visibility_scan("https://example.com")
        self.assertIn("overall_score", result)
        self.assertEqual(result["prompt_set_version"], "v1")
        self.assertEqual(result["scoring_version"], "v1")
        self.assertEqual(len(result["topics"]), 3)

    @patch("agentic_readiness.ai_visibility._provider_call")
    @patch("agentic_readiness.ai_visibility._extract_brand_info")
    def test_selected_provider_only_gemini(self, mock_extract, mock_provider_call) -> None:
        mock_extract.return_value = {
            "domain": "example.com",
            "title": "Example",
            "brand_name": "BrandX",
            "company_name": "BrandX Inc",
        }

        def fake_call(provider: str, prompt: str, cfg) -> str:
            return f"{provider} says BrandX on https://example.com"

        mock_provider_call.side_effect = fake_call
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "x",
                "GEMINI_API_KEY": "x",
                "ANTHROPIC_API_KEY": "x",
                "AI_VIS_MAX_PROMPTS": "2",
            },
            clear=False,
        ):
            result = run_ai_visibility_scan(
                "https://example.com",
                selected_providers=["gemini"],
            )

        self.assertEqual(result["provider_status"]["chatgpt"]["status"], "skipped_by_user")
        self.assertEqual(result["provider_status"]["claude"]["status"], "skipped_by_user")
        self.assertEqual(result["provider_status"]["gemini"]["status"], "available")
        self.assertEqual(result["totals"]["probes_sent"], 2)
        self.assertEqual(result["by_llm"]["chatgpt"]["calls"], 0)
        self.assertEqual(result["by_llm"]["claude"]["calls"], 0)
        self.assertEqual(result["by_llm"]["gemini"]["calls"], 2)

    @patch("agentic_readiness.ai_visibility._provider_call")
    @patch("agentic_readiness.ai_visibility._extract_brand_info")
    def test_selected_provider_chatgpt_and_claude(self, mock_extract, mock_provider_call) -> None:
        mock_extract.return_value = {
            "domain": "example.com",
            "title": "Example",
            "brand_name": "BrandX",
            "company_name": "BrandX Inc",
        }

        def fake_call(provider: str, prompt: str, cfg) -> str:
            return f"{provider} mentions BrandX on https://example.com"

        mock_provider_call.side_effect = fake_call
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "x",
                "GEMINI_API_KEY": "x",
                "ANTHROPIC_API_KEY": "x",
                "AI_VIS_MAX_PROMPTS": "2",
            },
            clear=False,
        ):
            result = run_ai_visibility_scan(
                "https://example.com",
                selected_providers=["chatgpt", "claude"],
            )

        self.assertEqual(result["provider_status"]["gemini"]["status"], "skipped_by_user")
        self.assertEqual(result["by_llm"]["gemini"]["calls"], 0)
        self.assertEqual(result["by_llm"]["chatgpt"]["calls"], 2)
        self.assertEqual(result["by_llm"]["claude"]["calls"], 2)
        self.assertEqual(result["totals"]["probes_sent"], 4)


if __name__ == "__main__":
    unittest.main()
