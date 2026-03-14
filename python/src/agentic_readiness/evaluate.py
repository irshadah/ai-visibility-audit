from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from .url_input import build_product_from_url_html


RULE_FIELD_MAP = {
    "A1": "aeo.faq_schema_present",
    "A2": "aeo.howto_schema_present",
    "S6": "seo.h1_present",
    "S10": "seo.meta_desc_present",
    "G1": "schema.product_present",
}


def _resolve_field(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def evaluate_benchmark(cases: list[Dict[str, Any]]) -> Dict[str, Any]:
    metrics: Dict[str, Dict[str, int]] = {}
    page_type_correct = 0

    for case in cases:
        product = build_product_from_url_html(case["url"], case["html"])
        expected = case.get("expected", {})

        if expected.get("page_type") and product.get("page", {}).get("page_type") == expected["page_type"]:
            page_type_correct += 1

        expected_rules = expected.get("rules", {})
        for rule_id, expected_val in expected_rules.items():
            field = RULE_FIELD_MAP.get(rule_id)
            if not field:
                continue
            actual = bool(_resolve_field(product, field))
            expected_bool = bool(expected_val)
            bucket = metrics.setdefault(rule_id, {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
            if actual and expected_bool:
                bucket["tp"] += 1
            elif actual and not expected_bool:
                bucket["fp"] += 1
            elif (not actual) and expected_bool:
                bucket["fn"] += 1
            else:
                bucket["tn"] += 1

    rule_summary: Dict[str, Dict[str, float | int]] = {}
    for rule_id, bucket in metrics.items():
        total = sum(bucket.values()) or 1
        precision = bucket["tp"] / max(1, bucket["tp"] + bucket["fp"])
        recall = bucket["tp"] / max(1, bucket["tp"] + bucket["fn"])
        rule_summary[rule_id] = {
            **bucket,
            "accuracy": round((bucket["tp"] + bucket["tn"]) / total, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }

    total_cases = len(cases) or 1
    return {
        "case_count": len(cases),
        "page_type_accuracy": round(page_type_correct / total_cases, 4),
        "rules": rule_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run benchmark evaluation for GEO/AEO/SEO feature extraction.")
    parser.add_argument("--fixtures", required=True, help="Path to benchmark fixtures JSON file")
    parser.add_argument("--output", help="Optional output JSON path for summary")
    args = parser.parse_args()

    cases = json.loads(Path(args.fixtures).read_text(encoding="utf-8"))
    summary = evaluate_benchmark(cases)

    payload = json.dumps(summary, indent=2)
    print(payload)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
