"""Rich terminal report formatter for GEO Agentic Readiness scores."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# ANSI
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"

CATEGORY_LABELS: Dict[str, str] = {
    "geo_structure": "GEO Structure",
    "content_quality": "Content Quality",
    "semantic_quality": "Semantic Quality",
    "ux_signals": "UX Signals",
    "feed_quality": "Feed Quality",
    "answer_structure": "Answer Structure",
    "snippet_readiness": "Snippet Readiness",
    "entity_clarity": "Entity Clarity",
    "voice_readiness": "Voice Readiness",
    "technical_seo": "Technical SEO",
    "on_page_seo": "On-Page SEO",
    "content_seo": "Content SEO",
    "link_and_media": "Link & Media",
}

RULE_LABELS: Dict[str, str] = {
    "G1": "Product Schema Present",
    "G2": "Required Schema Fields",
    "G3": "Page Indexable",
    "G4": "Open Graph Coverage",
    "G5": "URL Hygiene",
    "G6": "Machine-Readable Pricing",
    "G7": "Variant Clarity",
    "C1": "Title Length",
    "C2": "Description Length",
    "C3": "Attribute Completeness",
    "C4": "Pricing Clarity",
    "C5": "Policy Clarity",
    "C6": "Review Presence",
    "C7": "Support & Trust Info",
    "L1": "Ambiguity (low)",
    "L2": "Entity Consistency",
    "L3": "Query Answerability",
    "L4": "Factual Grounding",
    "U1": "Render & Accessibility",
    "U2": "Core Discoverability",
    "U3": "Media Quality",
    "U4": "Mobile Readability",
    "F1": "Feed Required Coverage",
    "F2": "Feed Attribute Completeness",
    "F3": "Feed Validity",
    "F4": "Feed–Page Consistency",
    "F5": "Feed Freshness",
    "A1": "FAQ Schema Present",
    "A2": "HowTo Schema Present",
    "A3": "Direct Answer Patterns",
    "A4": "List Structure Ratio",
    "A5": "Table Presence",
    "A6": "Concise Paragraph Ratio",
    "A7": "Heading Hierarchy Valid",
    "A8": "Title Length (snippet)",
    "A9": "Description Length (snippet)",
    "A10": "Entity Consistency",
    "A11": "Ambiguity (low)",
    "A12": "Factual Grounding",
    "A13": "Question Coverage",
    "A14": "Mobile Readability",
    "A15": "Query Answerability",
    "S1": "Page Indexable",
    "S2": "Canonical Present",
    "S3": "Canonical Self-Ref",
    "S4": "Hreflang Present",
    "S5": "Robots Valid",
    "S6": "H1 Present",
    "S7": "H1 Count (one)",
    "S8": "Title Length (50-60)",
    "S9": "Meta Desc Length",
    "S10": "Meta Desc Present",
    "S11": "Word Count",
    "S12": "Attribute Completeness",
    "S13": "Query Answerability",
    "S14": "Internal Links",
    "S15": "External Links",
    "S16": "Image Alt Ratio",
}

FIX_HINTS: Dict[str, str] = {
    "G1": "Add Product or Offer schema (JSON-LD) to the page.",
    "G2": "Add missing required Product/Offer schema fields.",
    "G3": "Ensure the page is indexable (no noindex, allow crawlers).",
    "G4": "Add all Open Graph tags (og:title, og:image, og:description, og:price:amount).",
    "G5": "Fix URL hygiene: use clean, canonical URLs without session/tracking params.",
    "G6": "Expose price and availability in machine-readable form (schema or meta).",
    "G7": "Clarify variant selection (size, color) in schema or structured data.",
    "C1": "Adjust the title to be between 40 and 140 characters for optimal AI discoverability.",
    "C2": "Add a product description of at least 300 characters with specs, use-cases, and benefits.",
    "C3": "Complete required and recommended product attributes (material, size, color, etc.).",
    "C4": "Show clear pricing (price, currency, availability) on the page.",
    "C5": "Add shipping, returns, or policy information.",
    "C6": "Add customer reviews or a review widget to the page.",
    "C7": "Add support or trust signals (contact, guarantees, certifications).",
    "L1": "Remove or clarify ambiguous terms that could confuse AI entity extraction.",
    "L2": "Align brand/model/price entities between schema and visible content.",
    "L3": "Add explicit Q&A content for compatibility, fit, and use-case queries.",
    "L4": "Add verifiable specs and factual claims backed by structured data.",
    "U1": "Ensure images have alt text and content is accessible to assistive tech.",
    "U2": "Improve core discoverability (headings, breadcrumbs, clear structure).",
    "U3": "Use higher-quality or properly sized images and media.",
    "U4": "Ensure layout and text are readable on mobile (viewport, font size).",
    "F1": "Populate all required Merchant feed fields.",
    "F2": "Complete feed attribute coverage for required and recommended fields.",
    "F3": "Fix feed validity (format, encoding, required fields).",
    "F4": "Align feed data with page content (titles, prices, availability).",
    "F5": "Keep feed updated (fresh availability and pricing).",
    "A1": "Add FAQPage schema (JSON-LD) for Q&A content.",
    "A2": "Add HowTo schema for step-by-step or instructional content.",
    "A3": "Use direct-answer phrasing (e.g. \"The X is Y\", \"You can...\") in key paragraphs.",
    "A4": "Add bullet or numbered lists for scannable answers.",
    "A5": "Add tables for comparative or factual data.",
    "A6": "Break content into concise paragraphs (under 50 words) for snippet extraction.",
    "A7": "Use exactly one H1 and logical heading hierarchy (H2, H3).",
    "A8": "Keep title between 40 and 60 characters for answer snippets.",
    "A9": "Provide a meta description of at least 150 characters.",
    "A10": "Align entity names (brand, product) across schema and visible content.",
    "A11": "Reduce ambiguous or vague terms for clearer entity extraction.",
    "A12": "Back factual claims with structured data or clear specs.",
    "A13": "Include question-and-answer style content for voice and featured snippets.",
    "A14": "Ensure mobile-friendly layout and viewport for voice assistants.",
    "A15": "Add explicit Q&A or specs that answer common queries.",
    "S1": "Allow indexing; remove noindex from robots meta if appropriate.",
    "S2": "Add a canonical link tag pointing to the preferred URL.",
    "S3": "Set canonical URL to this page's URL (self-referencing canonical).",
    "S4": "Add hreflang tags for multi-language or regional variants.",
    "S5": "Ensure robots meta does not block indexing (no noindex).",
    "S6": "Add at least one H1 heading to the page.",
    "S7": "Use exactly one H1 per page for clear topical focus.",
    "S8": "Keep title tag between 50 and 60 characters for search snippets.",
    "S9": "Keep meta description between 120 and 160 characters.",
    "S10": "Add a unique meta description for the page.",
    "S11": "Increase word count to at least 300 words of substantive content.",
    "S12": "Complete product attributes (material, size, brand, etc.) for relevance.",
    "S13": "Add content that answers common search queries (Q&A, specs).",
    "S14": "Add internal links to related pages (at least 3).",
    "S15": "Add at least one relevant external link to authoritative sources.",
    "S16": "Add descriptive alt text to all images.",
}

# For contextual inline hints (rule_id -> optional dict with min, max, type)
RULE_PARAMS: Dict[str, Dict[str, Any]] = {
    "C1": {"type": "range", "min": 40, "max": 140},
    "C2": {"type": "threshold", "min": 300},
    "C3": {"type": "ratio"},
    "L1": {"type": "inverse_threshold", "max": 3},
    "G2": {"type": "ratio"},
    "G4": {"type": "ratio"},
    "S7": {"type": "range", "min": 1, "max": 1},
    "S9": {"type": "range", "min": 120, "max": 160},
    "S11": {"type": "threshold", "min": 300},
    "S14": {"type": "threshold", "min": 3},
    "S15": {"type": "threshold", "min": 1},
}

MODE_TITLES: Dict[str, str] = {
    "GEO": "GEO Readiness",
    "AEO": "AEO Readiness",
    "SEO": "SEO Readiness",
    "custom": "Custom Rubric",
}


def score_bar(pct: Optional[float], width: int = 20) -> str:
    """Render a Unicode block progress bar with color. pct in 0..1 or None."""
    if pct is None:
        return DIM + "░" * width + RESET
    pct = max(0.0, min(1.0, float(pct)))
    filled = round(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    if pct >= 0.8:
        return GREEN + bar + RESET
    if pct >= 0.5:
        return YELLOW + bar + RESET
    return RED + bar + RESET


def _inline_hint(rule_id: str, raw_value: Any, normalized_score: Optional[float]) -> str:
    """Build a short contextual hint for a rule line."""
    if normalized_score is None or normalized_score >= 1.0:
        return ""
    hint = ""
    if rule_id == "C1" and raw_value is not None:
        hint = f"title is {raw_value} chars; ideal range is 40–140"
    elif rule_id == "C2":
        if raw_value == 0 or raw_value is None:
            hint = "no description found; need >= 300 chars"
        else:
            hint = f"description {raw_value} chars; need >= 300"
    elif rule_id == "C3" and raw_value is not None:
        hint = f"only {int(raw_value * 100)}% of key attributes present"
    elif rule_id == "G2" and raw_value is not None:
        hint = f"missing {int((1 - raw_value) * 100)}% of required Product/Offer fields"
    elif rule_id == "G4" and raw_value is not None:
        hint = f"only {raw_value:.0%} OG tags present"
    elif rule_id == "L1" and raw_value is not None:
        hint = f"ambiguity count {raw_value} (lower is better, max 3)"
    elif rule_id == "L2" and raw_value is not None:
        hint = f"entity consistency {raw_value:.0%}"
    elif rule_id == "L4" and raw_value is not None:
        hint = f"factual grounding {raw_value:.0%}"
    elif rule_id == "C6":
        hint = "no customer reviews detected"
    elif rule_id == "U3" and raw_value is not None:
        hint = f"media quality {raw_value:.0%}"
    elif rule_id == "A1":
        hint = "no FAQPage schema found" if not raw_value else ""
    elif rule_id == "S7" and raw_value is not None:
        hint = f"H1 count is {raw_value}; use exactly one"
    elif rule_id == "S11" and raw_value is not None:
        hint = f"word count {raw_value}; need >= 300" if raw_value < 300 else ""
    elif rule_id == "S14" and raw_value is not None:
        hint = f"internal links {raw_value}; need >= 3" if raw_value < 3 else ""
    elif rule_id == "S15" and raw_value is not None:
        hint = f"external links {raw_value}; need >= 1" if raw_value < 1 else ""
    else:
        hint = FIX_HINTS.get(rule_id, "")
        if len(hint) > 60:
            hint = hint[:57] + "..."
    if not hint:
        return ""
    return "  " + DIM + "← " + hint + RESET


def _rule_status(normalized_score: Optional[float], status: str) -> tuple[str, str]:
    """Return (status_label, color_code)."""
    if status == "not_applicable_page_type":
        return "SKIP", CYAN
    if status == "not_applicable_missing_input":
        return "N/A ", DIM
    if normalized_score is None:
        return "N/A ", DIM
    if normalized_score >= 1.0:
        return "PASS", GREEN
    if normalized_score <= 0.0:
        return "FAIL", RED
    return "WARN", YELLOW


def _format_category_block(
    category: str,
    category_score: float,
    rationale_entries: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    rec_by_rule: Dict[str, Dict[str, Any]],
) -> str:
    """Format one category section with rule rows and How to improve."""
    lines: List[str] = []
    label = CATEGORY_LABELS.get(category, category.replace("_", " ").title())
    cat_rationale = [r for r in rationale_entries if r["category"] == category]
    all_na = all(r.get("status") == "not_applicable_missing_input" for r in cat_rationale)
    if category == "feed_quality" and all_na:
        header = f"── {label} ── N/A (no feed data provided) ─────────────"
    elif category_score >= 0 and not (category == "feed_quality" and all_na):
        pct = category_score / 100.0
        bar = score_bar(pct, 20)
        header = f"── {label} ── {category_score:.2f} / 100 {bar}"
    else:
        header = f"── {label} ── N/A (no feed data provided) ─────────────"
    lines.append(header)
    for r in rationale_entries:
        if r["category"] != category:
            continue
        rid = r["rule_id"]
        raw = r.get("raw_value")
        norm = r.get("normalized_score")
        status = r.get("status", "evaluated")
        rule_label = RULE_LABELS.get(rid, rid)
        status_label, color = _rule_status(norm, status)
        pct_str = f"{norm * 100:.1f}%" if norm is not None else "N/A"
        hint = _inline_hint(rid, raw, norm)
        line = f"  {color}{status_label}{RESET}  {rid}  {rule_label:<28} {pct_str:>6}{hint}"
        lines.append(line)
    recs_for_cat = [rec for rec in recommendations if rec_by_rule.get(rec["rule_id"], {}).get("category") == category]
    if recs_for_cat:
        lines.append("")
        lines.append("  How to improve:")
        for rec in recs_for_cat:
            action = rec.get("action", "")
            lift = rec.get("estimated_lift", "")
            lines.append(f"    → {rec['rule_id']}: {action} (est. {lift} pts)")
    lines.append("")
    return "\n".join(lines)


def _format_single_report(
    report: Dict[str, Any],
    mode_name: Optional[str] = None,
) -> List[str]:
    """Format one assessment report; returns list of lines."""
    products = report.get("products", [])
    if not products:
        return ["No products in report."]
    prod = products[0]
    rationale = prod.get("rationale", [])
    recommendations = prod.get("recommendations", [])
    category_scores = prod.get("category_scores", {})
    overall = prod.get("overall_score")
    evidence = prod.get("evidence", {}) or {}

    rec_by_rule: Dict[str, Dict[str, Any]] = {}
    for r in rationale:
        rec_by_rule[r["rule_id"]] = r

    def lift_key(rec: Dict[str, Any]) -> int:
        est = rec.get("estimated_lift", "") or ""
        m = re.search(r"\+(\d+)", est)
        return int(m.group(1)) if m else 0

    top_recs = sorted(recommendations, key=lift_key, reverse=True)

    lines: List[str] = []
    title = MODE_TITLES.get(mode_name or "", mode_name or "Report")
    overall_pct = (overall / 100.0) if isinstance(overall, int) else None
    overall_str = f"{overall} / 100" if isinstance(overall, int) else "N/A"
    bar = score_bar(overall_pct, 20)
    lines.append(f"  {title}  {overall_str}  {bar}")
    lines.append("")

    category_order = list(category_scores.keys())
    for cat in category_order:
        score = category_scores.get(cat, 0.0)
        block = _format_category_block(cat, score, rationale, recommendations, rec_by_rule)
        lines.append(block)

    lines.append("  Top Recommendations (by estimated impact):")
    for i, rec in enumerate(top_recs[:6], 1):
        action = rec.get("action", "")
        lift = rec.get("estimated_lift", "")
        lines.append(f"    {i}. {rec['rule_id']}: {action}  ({lift})")
    ai_suggestions = prod.get("ai_optimization_suggestions") or []
    if ai_suggestions:
        lines.append("")
        lines.append("  AI Optimization:")
        for s in ai_suggestions:
            lines.append(f"    • {s}")
    if evidence:
        lines.append("")
        lines.append("  Extraction Evidence:")
        page_type = evidence.get("page_type")
        if page_type:
            lines.append(f"    • page_type: {page_type}")
        schema_types = evidence.get("schema_types") or []
        if schema_types:
            lines.append(f"    • schema_types: {', '.join(schema_types[:8])}")
        entities = evidence.get("entities") or {}
        if entities:
            lines.append(
                f"    • title: {entities.get('title', '')[:80]} | schema_brand: {entities.get('schema_brand', '')[:40]}"
            )
            lines.append(
                f"    • meta_description_length: {entities.get('meta_description_length', 0)}"
            )
        segmentation = evidence.get("segmentation") or {}
        if segmentation:
            lines.append(
                f"    • words(main/total): {segmentation.get('main_word_count', 0)}/{segmentation.get('total_word_count', 0)}"
            )
    return lines


def format_report(report: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """Build the full rich terminal report string. Handles both flat and assessments dict."""
    sep = "══════════════════════════════════════════════════════════════"
    out: List[str] = []

    if "assessments" in report:
        assessments = report["assessments"]
        if not assessments:
            return "No assessments in report."

        first_report = next(iter(assessments.values()))
        products = first_report.get("products", [])
        url = products[0].get("url", "") if products else ""

        out.append(sep)
        out.append("  Readiness Assessment Report")
        out.append(f"  URL: {url}")
        out.append("")
        for mode_name, single_report in assessments.items():
            out.append(sep)
            out.extend(_format_single_report(single_report, mode_name=mode_name))
            out.append("")

        out.append(sep)
        out.append("  Summary by mode:")
        for mode_name, single_report in assessments.items():
            prods = single_report.get("products", [])
            overall = prods[0].get("overall_score") if prods else None
            overall_str = f"{overall} / 100" if isinstance(overall, int) else "N/A"
            out.append(f"    {mode_name}: {overall_str}")
        if output_path:
            out.append("")
            out.append(f"  Full report saved to: {output_path}")
        out.append(sep)
        return "\n".join(out)

    products = report.get("products", [])
    if not products:
        return "No products in report."
    url = products[0].get("url", "")
    out.append(sep)
    out.append("  GEO Agentic Readiness Report")
    out.append(f"  URL: {url}")
    out.append("")
    out.append(sep)
    out.extend(_format_single_report(report, mode_name="GEO"))
    if output_path:
        out.append("")
        out.append(f"  Full report saved to: {output_path}")
    out.append(sep)
    return "\n".join(out)
