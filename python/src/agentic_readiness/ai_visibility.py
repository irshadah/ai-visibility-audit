from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .url_input import build_product_from_url_html, fetch_html

PROMPT_SET_VERSION = "v1"
SCORING_VERSION = "v1"
DEFAULT_TIMEOUT_SEC = 30
DEFAULT_MAX_PROMPTS = 12
SUPPORTED_PROVIDERS = ("chatgpt", "gemini", "claude")


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc or "").lower().split(":")[0]


def _tokenize(text: str) -> List[str]:
    clean = re.sub(r"[^a-z0-9äöüß\s.-]", " ", (text or "").lower())
    return [t for t in clean.split() if t]


def _normalize_aliases(brand_name: str, company_name: str, aliases: List[str]) -> List[str]:
    out: List[str] = []
    for candidate in [brand_name, company_name] + list(aliases or []):
        value = (candidate or "").strip()
        if not value:
            continue
        if value.lower() not in {x.lower() for x in out}:
            out.append(value)
    return out


def _contains_alias(text: str, aliases: List[str]) -> Optional[str]:
    text_l = (text or "").lower()
    text_compact = text_l.replace(" ", "")
    for alias in aliases:
        a = (alias or "").lower()
        if not a:
            continue
        a_compact = a.replace(" ", "")
        # Match either the spaced form or a compacted form so that
        # host-derived aliases like "hugoboss" still match "hugo boss".
        if a in text_l or a_compact in text_compact:
            return alias
    return None


def _extract_brand_info(url: str) -> Dict[str, Any]:
    fetched = fetch_html(url, timeout_sec=DEFAULT_TIMEOUT_SEC, progress_hook=None)
    product = build_product_from_url_html(url, fetched.html)
    evidence = product.get("evidence") or {}
    entities = evidence.get("entities") or {}
    title = str(entities.get("title") or "").strip()
    schema_brand = str(entities.get("schema_brand") or "").strip()

    host = _domain_from_url(url)
    host_tokens = [t for t in host.replace("-", " ").split(".") if t and t not in {"www", "com", "de", "net", "org"}]
    guessed_brand = schema_brand or (host_tokens[0].replace("-", " ").title() if host_tokens else "")
    if not guessed_brand and title:
        guessed_brand = title.split("|")[0].strip()

    return {
        "domain": host,
        "title": title,
        "brand_name": guessed_brand or "Unknown Brand",
        "company_name": schema_brand or guessed_brand or "Unknown Company",
    }


@dataclass
class VisibilityConfig:
    openai_api_key: str
    gemini_api_key: str
    anthropic_api_key: str
    timeout_sec: int
    max_prompts: int
    openai_model: str
    gemini_model: str
    anthropic_model: str

    @classmethod
    def from_env(cls) -> "VisibilityConfig":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            timeout_sec=int(os.getenv("AI_VIS_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SEC))),
            max_prompts=int(os.getenv("AI_VIS_MAX_PROMPTS", str(DEFAULT_MAX_PROMPTS))),
            openai_model=os.getenv("AI_VIS_OPENAI_MODEL", "gpt-4o-mini").strip(),
            gemini_model=os.getenv("AI_VIS_GEMINI_MODEL", "gemini-2.0-flash").strip(),
            anthropic_model=os.getenv("AI_VIS_ANTHROPIC_MODEL", "claude-3-5-haiku-latest").strip(),
        )


def build_probe_prompts(domain: str, brand_name: str, company_name: str) -> List[Dict[str, str]]:
    topics = [
        ("brand_overview", f"What is {brand_name} known for?"),
        ("brand_company", f"Tell me about the company behind {brand_name}."),
        ("best_brands", f"What are the best brands in this category similar to {brand_name}?"),
        ("product_recommendation", f"Which products from {brand_name} should I consider buying?"),
        ("comparison", f"Compare {brand_name} with two competitors and explain key differences."),
        ("trust_signal", f"Is {brand_name} a trustworthy brand? Why?"),
        ("official_site", f"What is the official website for {brand_name}?"),
        ("brand_recall", f"Name top companies similar to {company_name}."),
        ("purchase_intent", f"Where can I buy products from {brand_name}?"),
        ("brand_relevance", f"Is {brand_name} relevant for premium customers?"),
        ("seo_like_query", f"{brand_name} reviews and ratings summary."),
        ("domain_specific", f"What does {domain} offer to customers?"),
    ]
    return [{"topic_key": t[0], "topic": t[0].replace("_", " ").title(), "prompt": t[1]} for t in topics]


def _call_openai(prompt: str, cfg: VisibilityConfig) -> str:
    # Use chat completions API for broad model compatibility.
    from openai import OpenAI

    client = OpenAI(api_key=cfg.openai_api_key)
    resp = client.chat.completions.create(
        model=cfg.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=400,
    )
    try:
        content = resp.choices[0].message.content or ""
    except Exception:
        content = ""
    if isinstance(content, str):
        return content.strip()
    # Newer SDKs may return a list of content parts.
    if isinstance(content, list) and content:
        texts = [getattr(part, "text", None) or getattr(part, "content", None) for part in content]
        return " ".join([t for t in texts if t]).strip()
    return ""


def _call_gemini(prompt: str, cfg: VisibilityConfig) -> str:
    # Uses the new google-genai SDK as per
    # https://ai.google.dev/gemini-api/docs/quickstart#python_1
    from google import genai

    if not cfg.gemini_api_key:
        # Client can also pick up GEMINI_API_KEY from env automatically,
        # but we keep it explicit to align with the other providers.
        client = genai.Client()
    else:
        client = genai.Client(api_key=cfg.gemini_api_key)

    resp = client.models.generate_content(
        model=cfg.gemini_model,
        contents=prompt,
        config={"temperature": 0, "max_output_tokens": 400},
    )
    return (resp.text or "").strip()


def _call_claude(prompt: str, cfg: VisibilityConfig) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=cfg.anthropic_api_key)
    resp = client.messages.create(
        model=cfg.anthropic_model,
        max_tokens=400,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    chunks = []
    for item in getattr(resp, "content", []):
        text = getattr(item, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


def _provider_available(provider: str, cfg: VisibilityConfig) -> bool:
    if provider == "chatgpt":
        return bool(cfg.openai_api_key)
    if provider == "gemini":
        return bool(cfg.gemini_api_key)
    if provider == "claude":
        return bool(cfg.anthropic_api_key)
    return False


def _provider_call(provider: str, prompt: str, cfg: VisibilityConfig) -> str:
    if provider == "chatgpt":
        return _call_openai(prompt, cfg)
    if provider == "gemini":
        return _call_gemini(prompt, cfg)
    if provider == "claude":
        return _call_claude(prompt, cfg)
    raise RuntimeError(f"Unsupported provider: {provider}")


def _provider_call_with_retry(
    provider: str, prompt: str, cfg: VisibilityConfig, max_attempts: int = 3
) -> tuple[str, str]:
    """Returns (response_text, probe_status). probe_status is 'success', 'timeout', or 'failed'."""
    backoff = [1.0, 3.0]
    last_exc = None
    for attempt in range(max_attempts):
        try:
            if attempt > 0:
                time.sleep(backoff[attempt - 1])
            text = _provider_call(provider, prompt, cfg)
            return (text, "success")
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            if "timeout" in msg or "timed out" in msg:
                return ("", "timeout")
    return ("", "failed")


def _analyze_response(
    response_text: str,
    aliases: List[str],
    domain: str,
) -> Dict[str, Any]:
    text = response_text or ""
    alias_hit = _contains_alias(text, aliases)
    tokens = _tokenize(text)
    domain_hits = any(domain in t for t in tokens) or (domain in text.lower())
    positive_terms = ["best", "strong", "trusted", "quality", "premium", "recommended", "reliable"]
    negative_terms = ["bad", "poor", "avoid", "weak", "scam"]
    pos = sum(text.lower().count(term) for term in positive_terms)
    neg = sum(text.lower().count(term) for term in negative_terms)
    sentiment = 0.0
    if pos or neg:
        sentiment = (pos - neg) / max(1, pos + neg)
    return {
        "mentioned": bool(alias_hit),
        "cited": bool(domain_hits),
        "brand_context": alias_hit,
        "sentiment": round(float(sentiment), 4),
    }


def _score_visibility(
    provider_metrics: Dict[str, Dict[str, Any]],
    topic_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    providers = [p for p in provider_metrics.values()]
    if not providers:
        return {"overall_score": 0, "overall_label": "Low"}

    mention_rate = sum(float(p.get("mention_rate", 0)) for p in providers) / len(providers)
    citation_rate = sum(float(p.get("citation_rate", 0)) for p in providers) / len(providers)
    avg_sentiment = sum(float(p.get("sentiment_avg", 0)) for p in providers) / len(providers)
    topic_cov = (
        sum(1 for row in topic_rows if float(row.get("visibility", 0)) >= 50) / max(1, len(topic_rows))
    )
    sentiment_norm = max(0.0, min(1.0, (avg_sentiment + 1.0) / 2.0))
    score = (
        mention_rate * 45.0
        + citation_rate * 30.0
        + topic_cov * 20.0
        + sentiment_norm * 5.0
    )
    rounded = int(round(score))
    if rounded >= 75:
        label = "High"
    elif rounded >= 45:
        label = "Medium"
    else:
        label = "Low"
    return {"overall_score": rounded, "overall_label": label}


def run_ai_visibility_scan(
    url: str,
    *,
    brand_name: Optional[str] = None,
    company_name: Optional[str] = None,
    aliases: Optional[List[str]] = None,
    selected_providers: Optional[List[str]] = None,
    progress_hook=None,
) -> Dict[str, Any]:
    cfg = VisibilityConfig.from_env()
    extracted = _extract_brand_info(url)
    domain = extracted["domain"]
    brand = (brand_name or extracted["brand_name"]).strip()
    company = (company_name or extracted["company_name"]).strip()
    all_aliases = _normalize_aliases(brand, company, aliases or [])
    prompts = build_probe_prompts(domain, brand, company)[: max(1, cfg.max_prompts)]
    provider_status: Dict[str, Dict[str, Any]] = {}
    provider_counts: Dict[str, Dict[str, Any]] = {}
    probe_rows: List[Dict[str, Any]] = []
    started = time.time()
    total_api_calls = 0

    if selected_providers:
        allowed = {p for p in selected_providers if p in SUPPORTED_PROVIDERS}
        providers_for_run = [p for p in SUPPORTED_PROVIDERS if p in allowed]
    else:
        providers_for_run = list(SUPPORTED_PROVIDERS)

    probed_providers: List[str] = []

    for provider in SUPPORTED_PROVIDERS:
        if provider not in providers_for_run:
            provider_status[provider] = {"status": "skipped_by_user"}
        elif _provider_available(provider, cfg):
            provider_status[provider] = {"status": "available"}
            probed_providers.append(provider)
        else:
            provider_status[provider] = {"status": "missing_api_key"}

    for idx, probe in enumerate(prompts):
        topic = probe["topic"]
        prompt = probe["prompt"]
        row = {"topic": topic, "topic_key": probe["topic_key"], "prompt": prompt, "responses": {}}
        for provider in SUPPORTED_PROVIDERS:
            status = provider_status[provider]["status"]
            if status != "available":
                error_code = "missing_api_key" if status == "missing_api_key" else "skipped_by_user"
                row["responses"][provider] = {
                    "mentioned": False,
                    "cited": False,
                    "sentiment": 0.0,
                    "response_text": "",
                    "error_code": error_code,
                    "response_latency_ms": 0,
                }
                continue
            if progress_hook:
                progress_hook(
                    f"Probing {provider} ({idx + 1}/{len(prompts)})...",
                    min(92, 15 + int(((idx + 1) / max(1, len(prompts))) * 72)),
                )
            t0 = time.time()
            response_text, probe_status = _provider_call_with_retry(provider, prompt, cfg)
            latency_ms = int((time.time() - t0) * 1000)
            if probe_status == "success":
                analysis = _analyze_response(response_text, all_aliases, domain)
                row["responses"][provider] = {
                    **analysis,
                    "response_text": response_text,
                    "error_code": None,
                    "response_latency_ms": latency_ms,
                }
                bucket = provider_counts.setdefault(
                    provider,
                    {"mentions": 0, "citations": 0, "sentiment_sum": 0.0, "calls": 0},
                )
                bucket["mentions"] += int(analysis["mentioned"])
                bucket["citations"] += int(analysis["cited"])
                bucket["sentiment_sum"] += float(analysis["sentiment"])
                bucket["calls"] += 1
                total_api_calls += 1
            else:
                if probe_status == "failed":
                    logging.getLogger(__name__).warning("Provider %s call failed after retries", provider)
                    provider_status[provider] = {"status": "error", "error": "failed after retries"}
                row["responses"][provider] = {
                    "mentioned": False,
                    "cited": False,
                    "sentiment": 0.0,
                    "response_text": "",
                    "error_code": probe_status,
                    "response_latency_ms": latency_ms,
                }
        probe_rows.append(row)

    provider_metrics: Dict[str, Dict[str, Any]] = {}
    for provider in SUPPORTED_PROVIDERS:
        counts = provider_counts.get(provider, {"mentions": 0, "citations": 0, "sentiment_sum": 0.0, "calls": 0})
        calls = int(counts["calls"])
        safe_calls = max(1, calls)
        provider_metrics[provider] = {
            "mentions": int(counts["mentions"]),
            "citations": int(counts["citations"]),
            "mention_rate": round(float(counts["mentions"]) / safe_calls, 4),
            "citation_rate": round(float(counts["citations"]) / safe_calls, 4),
            "sentiment_avg": round(float(counts["sentiment_sum"]) / safe_calls, 4),
            "calls": calls,
        }

    topics_out: List[Dict[str, Any]] = []
    by_topic: Dict[str, Dict[str, Any]] = {}
    for probe in probe_rows:
        key = probe["topic_key"]
        node = by_topic.setdefault(
            key,
            {
                "topic": probe["topic"],
                "topic_key": key,
                "mentions_by_llm": {p: False for p in SUPPORTED_PROVIDERS},
                "hits": 0,
                "total": 0,
            },
        )
        for provider in providers_for_run:
            item = (probe.get("responses") or {}).get(provider) or {}
            mention = bool(item.get("mentioned", False))
            node["mentions_by_llm"][provider] = node["mentions_by_llm"][provider] or mention
            node["hits"] += int(mention)
            node["total"] += 1

    for _, node in by_topic.items():
        visibility = int(round(100.0 * (node["hits"] / max(1, node["total"]))))
        volume = "high" if visibility >= 70 else "medium" if visibility >= 40 else "low"
        topics_out.append(
            {
                "topic": node["topic"],
                "topic_key": node["topic_key"],
                "visibility": visibility,
                "mentions_by_llm": node["mentions_by_llm"],
                "ai_volume_estimate": volume,
            }
        )
    topics_out.sort(key=lambda x: x["visibility"], reverse=True)

    score_metrics = {k: provider_metrics[k] for k in providers_for_run}
    score = _score_visibility(score_metrics, topics_out)
    elapsed_ms = int((time.time() - started) * 1000)
    total_mentions = sum(int(m.get("mentions") or 0) for m in provider_metrics.values())
    total_citations = sum(int(m.get("citations") or 0) for m in provider_metrics.values())

    return {
        "url": url,
        "domain": domain,
        "brand": brand,
        "company_name": company,
        "aliases": all_aliases,
        "prompt_set_version": PROMPT_SET_VERSION,
        "scoring_version": SCORING_VERSION,
        "overall_score": score["overall_score"],
        "overall_label": score["overall_label"],
        "totals": {
            "mentions": total_mentions,
            "citations": total_citations,
            "probes_sent": len(prompts) * len(probed_providers),
            "provider_calls_successful": total_api_calls,
        },
        "provider_status": provider_status,
        "by_llm": provider_metrics,
        "topics": topics_out,
        "probes": probe_rows,
        "cost_estimate_usd": round(total_api_calls * 0.002, 4),
        "latency_ms": elapsed_ms,
    }

