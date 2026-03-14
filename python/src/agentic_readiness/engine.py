from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

from .models import ProductResult
from .rules import evaluate_rule, resolve_field, rule_applies


class ScoringEngine:
    def __init__(self, rubric: Dict[str, Any]):
        self.rubric = rubric

    _MODE_RUBRIC = {"GEO": "geo_rubric.json", "AEO": "aeo_rubric.json", "SEO": "seo_rubric.json"}

    @classmethod
    def from_mode(cls, mode: str) -> "ScoringEngine":
        filename = cls._MODE_RUBRIC.get(mode.upper())
        if not filename:
            raise ValueError(f"Unknown mode: {mode}. Use GEO, AEO, or SEO.")
        path = Path(__file__).parent / "rubrics" / filename
        rubric = json.loads(path.read_text(encoding="utf-8"))
        return cls(rubric=rubric)

    @classmethod
    def from_rubric_file(cls, rubric_path: Optional[str] = None) -> "ScoringEngine":
        if rubric_path:
            path = Path(rubric_path)
        else:
            path = Path(__file__).parent / "rubrics" / "geo_rubric.json"
        rubric = json.loads(path.read_text(encoding="utf-8"))
        return cls(rubric=rubric)

    def score_batch(self, products: List[Dict[str, Any]], previous_report: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        by_key_previous = self._build_previous_index(previous_report)
        results = [self._score_product(product, by_key_previous) for product in products]

        report = {
            "scoring_meta": {
                "ruleset_version": self.rubric["version"],
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "rubric_source": "custom" if self.rubric.get("is_custom") else "global_fallback"
            },
            "summary": self._build_summary(results),
            "products": [asdict(r) for r in results],
        }
        return report

    def _score_product(self, product: Dict[str, Any], previous_map: Dict[str, Dict[str, Any]]) -> ProductResult:
        category_scores: Dict[str, float] = {}
        rationale: List[Dict[str, Any]] = []
        issues = {"high": [], "medium": [], "low": []}
        recommendations: List[Dict[str, Any]] = []

        for category, rules in self.rubric["rules"].items():
            weighted_sum = 0.0
            applied_weight = 0.0
            for rule in rules:
                if not rule_applies(rule, product):
                    rationale.append(
                        {
                            "rule_id": rule["id"],
                            "category": category,
                            "raw_value": None,
                            "normalized_score": None,
                            "score_impact": 0.0,
                            "status": "not_applicable_page_type",
                        }
                    )
                    continue
                rule_score = evaluate_rule(rule, product)
                if rule_score is None:
                    rationale.append(
                        {
                            "rule_id": rule["id"],
                            "category": category,
                            "raw_value": None,
                            "normalized_score": None,
                            "score_impact": 0.0,
                            "status": "not_applicable_missing_input",
                        }
                    )
                    continue

                weighted_sum += rule["weight"] * rule_score
                applied_weight += rule["weight"]
                delta = rule["weight"] * (1.0 - rule_score)
                rationale.append(
                    {
                        "rule_id": rule["id"],
                        "category": category,
                        "raw_value": resolve_field(product, rule["field"]),
                        "normalized_score": round(rule_score, 4),
                        "score_impact": round(-delta, 2),
                        "status": "evaluated",
                    }
                )

                if rule_score < 0.999:
                    issue = self._build_issue(rule, rule_score, product)
                    issues[issue["priority"]].append(issue)
                    if rule["id"] in self.rubric.get("recommendation_map", {}):
                        recommendations.append(
                            {
                                "rule_id": rule["id"],
                                "action": self.rubric["recommendation_map"][rule["id"]],
                                "estimated_lift": self._estimate_lift(rule, rule_score),
                            }
                        )
            if applied_weight == 0:
                category_scores[category] = 0.0
            else:
                category_scores[category] = round((weighted_sum / applied_weight) * 100.0, 2)

        confidence = self._compute_confidence(product)
        overall_score = self._compute_overall_score(category_scores, product)
        blocked = confidence < float(self.rubric.get("confidence_gate", 70))
        if blocked:
            overall_score = None

        product_id = str(product.get("product_id", ""))
        url = str(product.get("url", ""))
        regression = self._compute_regression(product_id, url, overall_score, category_scores, previous_map)

        return ProductResult(
            product_id=product_id,
            url=url,
            category_scores=category_scores,
            overall_score=overall_score,
            confidence=round(confidence, 2),
            blocked=blocked,
            issues=issues,
            rationale=rationale,
            recommendations=self._dedupe_recommendations(recommendations),
            ai_optimization_suggestions=self._build_ai_suggestions(product),
            regression=regression,
            evidence=product.get("evidence", {}),
        )

    def _compute_overall_score(self, category_scores: Dict[str, float], product: Dict[str, Any]) -> int:
        weights = dict(self.rubric["category_weights"])
        feed_weight = weights.pop("feed_quality", 0.0)
        has_feed = bool(product.get("has_feed", False))

        if feed_weight > 0 and not has_feed:
            remaining = sum(weights.values())
            if remaining > 0:
                for key in list(weights.keys()):
                    weights[key] = weights[key] + (weights[key] / remaining) * feed_weight

        total = 0.0
        for category, weight in weights.items():
            total += weight * category_scores.get(category, 0.0)
        return round(total)

    def _compute_confidence(self, product: Dict[str, Any]) -> float:
        confidence = 100.0
        required_paths = self.rubric.get(
            "confidence_paths",
            [
                "content.title_length",
                "content.description_length",
                "schema.required_field_coverage",
                "semantic.query_answerability",
                "semantic.factual_grounding",
            ],
        )
        missing = 0
        for path in required_paths:
            if resolve_field(product, path) is None:
                missing += 1
        confidence -= missing * 8.0

        llm_variance = float(resolve_field(product, "semantic.llm_variance") or 0)
        if llm_variance > 10:
            confidence -= min(20.0, llm_variance)

        return max(0.0, confidence)

    def _build_issue(self, rule: Dict[str, Any], rule_score: float, product: Dict[str, Any]) -> Dict[str, Any]:
        prevalence = float(product.get("prevalence", 1.0))
        prevalence_bucket = 1 + round(4 * max(0.0, min(1.0, prevalence)))
        priority_score = rule["impact"] * 1.0 * prevalence_bucket * (1.0 - rule_score)

        if rule["impact"] >= 5 and rule_score <= 0.0:
            priority = "high"
        elif priority_score >= 8:
            priority = "high"
        elif priority_score >= 4:
            priority = "medium"
        else:
            priority = "low"

        return {
            "rule_id": rule["id"],
            "message": f"Rule {rule['id']} failed or partially failed",
            "priority": priority,
            "priority_score": round(priority_score, 2),
            "evidence": f"field={rule['field']} value={resolve_field(product, rule['field'])}",
        }

    def _build_previous_index(self, previous_report: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not previous_report:
            return {}
        index: Dict[str, Dict[str, Any]] = {}
        for item in previous_report.get("products", []):
            pid = str(item.get("product_id", ""))
            url = str(item.get("url", ""))
            if pid:
                index[f"id:{pid}"] = item
            if url:
                index[f"url:{url}"] = item
        return index

    def _compute_regression(
        self,
        product_id: str,
        url: str,
        overall_score: Optional[int],
        category_scores: Dict[str, float],
        previous_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        prev = None
        if product_id and f"id:{product_id}" in previous_map:
            prev = previous_map[f"id:{product_id}"]
        elif url and f"url:{url}" in previous_map:
            prev = previous_map[f"url:{url}"]

        if not prev:
            return {"has_previous": False}

        prev_score = prev.get("overall_score")
        delta = None
        if isinstance(prev_score, int) and isinstance(overall_score, int):
            delta = overall_score - prev_score

        cat_delta: Dict[str, float] = {}
        prev_cats = prev.get("category_scores", {})
        for key, val in category_scores.items():
            old = float(prev_cats.get(key, 0.0))
            cat_delta[key] = round(val - old, 2)

        return {
            "has_previous": True,
            "previous_overall_score": prev_score,
            "overall_delta": delta,
            "category_deltas": cat_delta,
        }

    def _build_ai_suggestions(self, product: Dict[str, Any]) -> List[str]:
        suggestions: List[str] = []
        if float(resolve_field(product, "semantic.query_answerability") or 0.0) < 0.7:
            suggestions.append("Add explicit Q&A content for compatibility, fit, and use-case queries.")
        if float(resolve_field(product, "semantic.entity_consistency") or 0.0) < 0.7:
            suggestions.append("Normalize brand/model naming across title, schema, and feed.")
        if float(resolve_field(product, "content.attribute_completeness") or 0.0) < 0.8:
            suggestions.append("Increase attribute density for AI retrieval and ranking signals.")
        return suggestions

    def _estimate_lift(self, rule: Dict[str, Any], rule_score: float) -> str:
        potential = rule["weight"] * (1.0 - rule_score)
        lo = max(1, round(potential * 0.6))
        hi = max(lo, round(potential))
        return f"+{lo} to +{hi}"

    def _dedupe_recommendations(self, recs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        out = []
        for rec in recs:
            key = (rec["rule_id"], rec["action"])
            if key in seen:
                continue
            seen.add(key)
            out.append(rec)
        return out

    def _build_summary(self, results: List[ProductResult]) -> Dict[str, Any]:
        scores = [r.overall_score for r in results if isinstance(r.overall_score, int)]
        blocked = sum(1 for r in results if r.blocked)

        return {
            "product_count": len(results),
            "scored_count": len(scores),
            "blocked_count": blocked,
            "average_score": round(mean(scores), 2) if scores else None,
        }
