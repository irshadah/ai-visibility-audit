from __future__ import annotations

from typing import Any, Dict, Optional


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def resolve_field(data: Dict[str, Any], dotted_path: str) -> Any:
    value: Any = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def rule_applies(rule: Dict[str, Any], product: Dict[str, Any]) -> bool:
    applies_to = rule.get("applies_to_page_types")
    if not applies_to:
        return True
    if not isinstance(applies_to, list):
        return True
    page_type = resolve_field(product, "page.page_type")
    if not page_type:
        return False
    return str(page_type) in {str(v) for v in applies_to}


def evaluate_rule(rule: Dict[str, Any], product: Dict[str, Any]) -> Optional[float]:
    value = resolve_field(product, rule["field"])
    rule_type = rule["type"]

    if value is None:
        missing_behavior = str(rule.get("missing_behavior", "skip")).lower()
        if missing_behavior == "zero":
            return 0.0
        return None

    if rule_type == "binary":
        return 1.0 if bool(value) else 0.0

    if rule_type == "ratio":
        return _clamp(float(value))

    if rule_type == "threshold":
        minimum = float(rule["min"])
        return _clamp(float(value) / minimum) if minimum > 0 else 0.0

    if rule_type == "inverse_threshold":
        maximum = float(rule["max"])
        if maximum <= 0:
            return 0.0
        return _clamp(1.0 - (float(value) / maximum))

    if rule_type == "range":
        minimum = float(rule["min"])
        maximum = float(rule["max"])
        v = float(value)
        if minimum <= v <= maximum:
            return 1.0
        if v < minimum:
            return _clamp(v / minimum) if minimum > 0 else 0.0
        if v > maximum:
            # Soft penalty for too-long titles.
            return _clamp(maximum / v) if v > 0 else 0.0

    return 0.0
