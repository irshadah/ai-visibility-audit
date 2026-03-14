from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    score: float
    weight: float
    impact: int
    confidence: float
    message: str
    evidence: str
    category: str


@dataclass
class ProductResult:
    product_id: str
    url: str
    category_scores: Dict[str, float]
    overall_score: Optional[int]
    confidence: float
    blocked: bool
    issues: Dict[str, List[Dict[str, Any]]]
    rationale: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    ai_optimization_suggestions: List[str]
    regression: Dict[str, Any]
    evidence: Dict[str, Any]

