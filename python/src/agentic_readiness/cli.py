from __future__ import annotations

import argparse
import json
from typing import List, Optional

from .engine import ScoringEngine
from .evaluate import evaluate_benchmark
from .formatter import format_report
from .io import load_previous, load_products, write_json
from .url_input import load_single_url_product

VALID_MODES = ["GEO", "AEO", "SEO"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agentic Readiness Assessment scorer")
    sub = parser.add_subparsers(dest="command", required=True)

    score = sub.add_parser("score", help="Score products from JSON input")
    score.add_argument("--input", required=True, help="Input JSON path")
    score.add_argument(
        "--input-type",
        default="auto",
        choices=["auto", "normalized_json", "merchant_json", "merchant_csv", "merchant_xml"],
        help="Input payload type",
    )
    score.add_argument("--output", required=True, help="Output report path")
    score.add_argument("--rubric", help="Custom rubric JSON path")
    score.add_argument("--previous", help="Previous report JSON path for regression")
    score.add_argument("--json-summary", action="store_true", help="Print minimal JSON summary instead of rich report")
    score.add_argument(
        "modes",
        nargs="*",
        choices=VALID_MODES,
        metavar="MODE",
        help="Assessment modes to run (default: GEO if none given)",
    )

    score_url = sub.add_parser("score-url", help="Fetch and score a single live URL")
    score_url.add_argument("--url", required=True, help="Customer URL")
    score_url.add_argument("--output", required=True, help="Output report path")
    score_url.add_argument("--rubric", help="Custom rubric JSON path")
    score_url.add_argument("--previous", help="Previous report JSON path for regression")
    score_url.add_argument("--timeout-sec", type=int, default=30, help="HTTP fetch timeout in seconds")
    score_url.add_argument("--json-summary", action="store_true", help="Print minimal JSON summary instead of rich report")
    score_url.add_argument(
        "modes",
        nargs="*",
        choices=VALID_MODES,
        metavar="MODE",
        help="Assessment modes to run: GEO, AEO, SEO (default: GEO if none given)",
    )

    evaluate = sub.add_parser("evaluate-benchmark", help="Evaluate extraction accuracy on benchmark fixtures")
    evaluate.add_argument("--fixtures", required=True, help="Path to benchmark fixtures JSON")
    evaluate.add_argument("--output", help="Optional output summary path")

    return parser.parse_args()


def run_score(
    input_path: str,
    input_type: str,
    output_path: str,
    rubric_path: Optional[str],
    previous_path: Optional[str],
    json_summary: bool = False,
    modes: Optional[List[str]] = None,
) -> int:
    modes = modes or ["GEO"]
    previous = load_previous(previous_path)
    products = load_products(input_path, input_type=input_type)

    if rubric_path:
        engine = ScoringEngine.from_rubric_file(rubric_path)
        engine.rubric["is_custom"] = True
        report = engine.score_batch(products, previous_report=previous)
        combined = {"assessments": {"custom": report}}
    else:
        combined = {"assessments": {}}
        for mode in modes:
            engine = ScoringEngine.from_mode(mode)
            prev_for_mode = (previous.get("assessments") or {}).get(mode) if previous else None
            report = engine.score_batch(products, previous_report=prev_for_mode)
            combined["assessments"][mode] = report

    write_json(output_path, combined)

    if json_summary:
        first = next(iter(combined["assessments"].values()))
        summary = first["summary"]
        print(
            json.dumps(
                {
                    "output": output_path,
                    "product_count": summary["product_count"],
                    "scored_count": summary["scored_count"],
                    "blocked_count": summary["blocked_count"],
                    "average_score": summary["average_score"],
                    "rubric_source": first["scoring_meta"]["rubric_source"],
                    "modes": list(combined["assessments"].keys()),
                },
                indent=2,
            )
        )
    else:
        print(format_report(combined, output_path))
    return 0


def run_score_url(
    url: str,
    output_path: str,
    rubric_path: Optional[str],
    previous_path: Optional[str],
    timeout_sec: int,
    json_summary: bool = False,
    modes: Optional[List[str]] = None,
) -> int:
    modes = modes or ["GEO"]
    product = load_single_url_product(url, timeout_sec=timeout_sec)
    previous = load_previous(previous_path)

    if rubric_path:
        engine = ScoringEngine.from_rubric_file(rubric_path)
        engine.rubric["is_custom"] = True
        report = engine.score_batch([product], previous_report=previous)
        combined = {"assessments": {"custom": report}}
    else:
        combined = {"assessments": {}}
        for mode in modes:
            engine = ScoringEngine.from_mode(mode)
            prev_for_mode = (previous.get("assessments") or {}).get(mode) if previous else None
            report = engine.score_batch([product], previous_report=prev_for_mode)
            combined["assessments"][mode] = report

    write_json(output_path, combined)

    if json_summary:
        first = next(iter(combined["assessments"].values()))
        summary = first["summary"]
        print(
            json.dumps(
                {
                    "output": output_path,
                    "product_count": summary["product_count"],
                    "scored_count": summary["scored_count"],
                    "blocked_count": summary["blocked_count"],
                    "average_score": summary["average_score"],
                    "rubric_source": first["scoring_meta"]["rubric_source"],
                    "mode": "score-url",
                    "modes": list(combined["assessments"].keys()),
                },
                indent=2,
            )
        )
    else:
        print(format_report(combined, output_path))
    return 0


def main() -> int:
    args = parse_args()
    json_summary = getattr(args, "json_summary", False)
    modes = getattr(args, "modes", None) or ["GEO"]
    if args.command == "score":
        return run_score(args.input, args.input_type, args.output, args.rubric, args.previous, json_summary, modes)
    if args.command == "score-url":
        return run_score_url(args.url, args.output, args.rubric, args.previous, args.timeout_sec, json_summary, modes)
    if args.command == "evaluate-benchmark":
        import pathlib

        cases = json.loads(pathlib.Path(args.fixtures).read_text(encoding="utf-8"))
        summary = evaluate_benchmark(cases)
        if args.output:
            pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(args.output).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
