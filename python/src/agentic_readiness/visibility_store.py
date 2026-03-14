from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_url_for_cache(url: str) -> str:
    """Lowercase host, https, no fragment, no trailing slash."""
    parsed = urlparse(url.strip())
    scheme = "https" if parsed.scheme in ("https", "") else "https"
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "/").rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", "", ""))


# Single source of truth for topic_key -> display label (TASK 1.4; keep in sync with ai_visibility.build_probe_prompts)
TOPIC_LABELS: Dict[str, str] = {
    "brand_overview": "Brand Overview",
    "brand_company": "Brand & Company",
    "best_brands": "Best Brands",
    "product_recommendation": "Product Recommendation",
    "comparison": "Comparison",
    "trust_signal": "Trust Signal",
    "official_site": "Official Site",
    "brand_recall": "Brand Recall",
    "purchase_intent": "Purchase Intent",
    "brand_relevance": "Brand Relevance",
    "seo_like_query": "SEO-like Query",
    "domain_specific": "Domain Specific",
}


def _normalize_jsonb_list(val: Any) -> List[Any]:
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return []


def _normalize_jsonb_dict(val: Any) -> Dict[str, Any]:
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return {}
    return {}


def compute_recommendations(
    topics: List[Dict[str, Any]], by_llm: Dict[str, Dict[str, Any]]
) -> List[str]:
    """TASK 1.7: 0–5 recommendations from fixed rules, in order."""
    out: List[str] = []
    if not by_llm:
        return out
    # Overall citation rate (average across providers)
    citation_rates = [float(m.get("citation_rate") or 0) for m in by_llm.values()]
    avg_citation = sum(citation_rates) / len(citation_rates) if citation_rates else 0.0
    if avg_citation < 0.2:
        out.append(
            "Increase Schema.org Product/Offer coverage and align feed data with on-page content."
        )
    if len(out) >= 5:
        return out[:5]
    # Topic visibility 0%
    by_key = {t.get("topic_key", t.get("topic", "")): t for t in (topics or [])}
    for key, rec in (
        ("best_brands", "Improve presence in authoritative comparative-list content (reviews, guides, marketplaces)."),
        ("product_recommendation", "Strengthen product-level signals (titles, descriptions, structured data) so AIs can recommend your products."),
        ("official_site", "Ensure brand and domain are clearly associated in structured data and authoritative sources."),
    ):
        node = by_key.get(key, {})
        vis = node.get("visibility", node.get("visibility_score", -1))
        if vis is not None and int(vis) == 0:
            out.append(rec)
        if len(out) >= 5:
            return out[:5]
    # Overall mention rate
    mention_rates = [float(m.get("mention_rate") or 0) for m in by_llm.values()]
    avg_mention = sum(mention_rates) / len(mention_rates) if mention_rates else 0.0
    if avg_mention < 0.4:
        out.append(
            "Improve brand and product visibility across key topics; consider content and technical SEO for AI discoverability."
        )
    return out[:5]


CACHE_TTL_HOURS = 24


def build_run_cache_key(
    url: str, topic_set_version: str = "v1", region_code: str = "us", language_code: str = "en"
) -> str:
    """Cache key for competitor run lookup (TASK 1.6)."""
    normalized = normalize_url_for_cache(url)
    return f"visibility:run:{topic_set_version}:{normalized}:{region_code}:{language_code}"


class VisibilityStore:
    def __init__(self, database_url: Optional[str]) -> None:
        self.database_url = (database_url or "").strip()
        self.enabled = bool(self.database_url)

    def _connect(self):
        if not self.enabled:
            raise RuntimeError("VisibilityStore is disabled: DATABASE_URL is not set.")
        try:
            import psycopg
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("psycopg is not installed.") from exc
        return psycopg.connect(self.database_url)

    def insert_run(self, run: Dict[str, Any]) -> Optional[int]:
        if not self.enabled:
            return None
        query = """
            INSERT INTO visibility_runs (
                job_id, url, domain, brand_name, company_name, aliases_json,
                prompt_set_version, scoring_version, overall_score, overall_label,
                status, started_at, completed_at, error_message, provider_status_json,
                cost_estimate_usd, latency_ms
            ) VALUES (
                %(job_id)s, %(url)s, %(domain)s, %(brand_name)s, %(company_name)s, %(aliases_json)s::jsonb,
                %(prompt_set_version)s, %(scoring_version)s, %(overall_score)s, %(overall_label)s,
                %(status)s, %(started_at)s, %(completed_at)s, %(error_message)s, %(provider_status_json)s::jsonb,
                %(cost_estimate_usd)s, %(latency_ms)s
            )
            RETURNING id
        """
        payload = {
            "job_id": run.get("job_id"),
            "url": run.get("url"),
            "domain": run.get("domain"),
            "brand_name": run.get("brand_name"),
            "company_name": run.get("company_name"),
            "aliases_json": json.dumps(run.get("aliases") or []),
            "prompt_set_version": run.get("prompt_set_version", "v1"),
            "scoring_version": run.get("scoring_version", "v1"),
            "overall_score": run.get("overall_score"),
            "overall_label": run.get("overall_label"),
            "status": run.get("status", "complete"),
            "started_at": run.get("started_at") or _utc_now(),
            "completed_at": run.get("completed_at") or _utc_now(),
            "error_message": run.get("error_message"),
            "provider_status_json": json.dumps(run.get("provider_status") or {}),
            "cost_estimate_usd": float(run.get("cost_estimate_usd") or 0.0),
            "latency_ms": int(run.get("latency_ms") or 0),
        }
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, payload)
                row = cur.fetchone()
                conn.commit()
                return int(row[0]) if row else None

    def insert_provider_metrics(self, run_id: int, metrics: Dict[str, Dict[str, Any]]) -> None:
        if not self.enabled or not run_id:
            return
        query = """
            INSERT INTO visibility_provider_metrics (
                run_id, provider, mentions, citations, mention_rate, citation_rate
            ) VALUES (
                %(run_id)s, %(provider)s, %(mentions)s, %(citations)s, %(mention_rate)s, %(citation_rate)s
            )
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                for provider, row in (metrics or {}).items():
                    cur.execute(
                        query,
                        {
                            "run_id": run_id,
                            "provider": provider,
                            "mentions": int(row.get("mentions") or 0),
                            "citations": int(row.get("citations") or 0),
                            "mention_rate": float(row.get("mention_rate") or 0.0),
                            "citation_rate": float(row.get("citation_rate") or 0.0),
                        },
                    )
                conn.commit()

    def insert_topics(self, run_id: int, topics: List[Dict[str, Any]]) -> None:
        if not self.enabled or not run_id:
            return
        query = """
            INSERT INTO visibility_topics (
                run_id, topic_key, topic_label, visibility_score, ai_volume_bucket,
                chatgpt_mentioned, gemini_mentioned, claude_mentioned
            ) VALUES (
                %(run_id)s, %(topic_key)s, %(topic_label)s, %(visibility_score)s, %(ai_volume_bucket)s,
                %(chatgpt_mentioned)s, %(gemini_mentioned)s, %(claude_mentioned)s
            )
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                for topic in topics or []:
                    mentions_by_llm = topic.get("mentions_by_llm") or {}
                    cur.execute(
                        query,
                        {
                            "run_id": run_id,
                            "topic_key": topic.get("topic_key", topic.get("topic", "unknown")),
                            "topic_label": topic.get("topic", "Unknown"),
                            "visibility_score": int(topic.get("visibility") or 0),
                            "ai_volume_bucket": topic.get("ai_volume_estimate", "unknown"),
                            "chatgpt_mentioned": bool(mentions_by_llm.get("chatgpt", False)),
                            "gemini_mentioned": bool(mentions_by_llm.get("gemini", False)),
                            "claude_mentioned": bool(mentions_by_llm.get("claude", False)),
                        },
                    )
                conn.commit()

    def insert_probes(self, run_id: int, probes: List[Dict[str, Any]]) -> None:
        if not self.enabled or not run_id:
            return
        query = """
            INSERT INTO visibility_probes (
                run_id, topic_key, prompt_text, provider, response_text,
                mentioned, cited, brand_context, response_latency_ms, error_code, probe_status
            ) VALUES (
                %(run_id)s, %(topic_key)s, %(prompt_text)s, %(provider)s, %(response_text)s,
                %(mentioned)s, %(cited)s, %(brand_context)s, %(response_latency_ms)s, %(error_code)s, %(probe_status)s
            )
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                for probe in probes or []:
                    topic_key = probe.get("topic_key", probe.get("topic", "unknown"))
                    prompt_text = str(probe.get("prompt", ""))
                    responses = probe.get("responses") or {}
                    for provider, row in responses.items():
                        err = row.get("error_code")
                        if err is None or (isinstance(err, str) and err.strip() == ""):
                            probe_status = "success"
                        elif isinstance(err, str) and "timeout" in err.lower():
                            probe_status = "timeout"
                        else:
                            probe_status = "failed"
                        cur.execute(
                            query,
                            {
                                "run_id": run_id,
                                "topic_key": topic_key,
                                "prompt_text": prompt_text,
                                "provider": provider,
                                "response_text": str(row.get("response_text") or ""),
                                "mentioned": bool(row.get("mentioned", False)),
                                "cited": bool(row.get("cited", False)),
                                "brand_context": row.get("brand_context"),
                                "response_latency_ms": int(row.get("response_latency_ms") or 0),
                                "error_code": err,
                                "probe_status": probe_status,
                            },
                        )
                conn.commit()

    def list_runs(self, url: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []

        base_query = """
            SELECT id, job_id, url, domain, brand_name, company_name, aliases_json,
                   prompt_set_version, scoring_version, overall_score, overall_label,
                   status, started_at, completed_at, error_message, provider_status_json,
                   cost_estimate_usd, latency_ms
            FROM visibility_runs
        """
        params: Dict[str, Any] = {"limit": int(limit)}

        if url:
            query = base_query + " WHERE url = %(url)s ORDER BY started_at DESC LIMIT %(limit)s"
            params["url"] = url
        else:
            query = base_query + " ORDER BY started_at DESC LIMIT %(limit)s"

        out: List[Dict[str, Any]] = []
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                for row in cur.fetchall():
                    out.append(
                        {
                            "id": int(row[0]),
                            "job_id": row[1],
                            "url": row[2],
                            "domain": row[3],
                            "brand_name": row[4],
                            "company_name": row[5],
                            "aliases": row[6] if isinstance(row[6], list) else [],
                            "prompt_set_version": row[7],
                            "scoring_version": row[8],
                            "overall_score": row[9],
                            "overall_label": row[10],
                            "status": row[11],
                            "started_at": row[12].isoformat() if row[12] else None,
                            "completed_at": row[13].isoformat() if row[13] else None,
                            "error_message": row[14],
                            "provider_status": row[15] if isinstance(row[15], dict) else {},
                            "cost_estimate_usd": float(row[16] or 0.0),
                            "latency_ms": int(row[17] or 0),
                        }
                    )
        return out

    def get_cost_summary(
        self, from_ts: Optional[datetime] = None, to_ts: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Sum cost_estimate_usd and count runs with completed_at in [from_ts, to_ts] (inclusive)."""
        if not self.enabled:
            return {"total_usd": 0.0, "runs_count": 0}
        conditions = ["completed_at IS NOT NULL", "status IN ('complete', 'partial', 'done')"]
        params: Dict[str, Any] = {}
        if from_ts is not None:
            conditions.append("completed_at >= %(from_ts)s")
            params["from_ts"] = from_ts
        if to_ts is not None:
            conditions.append("completed_at <= %(to_ts)s")
            params["to_ts"] = to_ts
        query = f"""
            SELECT COALESCE(SUM(cost_estimate_usd), 0), COUNT(*)
            FROM visibility_runs
            WHERE {' AND '.join(conditions)}
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                row = cur.fetchone()
        if not row:
            return {"total_usd": 0.0, "runs_count": 0}
        return {"total_usd": float(row[0] or 0.0), "runs_count": int(row[1] or 0)}

    def get_today_completed_count_and_spend(self) -> Dict[str, Any]:
        """Count runs and sum cost for today (UTC). status IN ('complete','partial','done')."""
        if not self.enabled:
            return {"runs_count": 0, "total_usd": 0.0}
        today_start = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        query = """
            SELECT COUNT(*), COALESCE(SUM(cost_estimate_usd), 0)
            FROM visibility_runs
            WHERE completed_at >= %(today_start)s
              AND status IN ('complete', 'partial', 'done')
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, {"today_start": today_start})
                row = cur.fetchone()
        if not row:
            return {"runs_count": 0, "total_usd": 0.0}
        return {"runs_count": int(row[0] or 0), "total_usd": float(row[1] or 0.0)}

    def cache_get_run_id(self, cache_key: str) -> Optional[int]:
        """Return run_id if cache has a non-expired entry for cache_key."""
        if not self.enabled:
            return None
        cutoff = _utc_now() - timedelta(hours=CACHE_TTL_HOURS)
        query = """
            SELECT run_id FROM visibility_run_cache
            WHERE cache_key = %(cache_key)s AND created_at >= %(cutoff)s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, {"cache_key": cache_key, "cutoff": cutoff})
                row = cur.fetchone()
        return int(row[0]) if row else None

    def cache_set(self, cache_key: str, run_id: int) -> None:
        """Insert or update cache entry."""
        if not self.enabled:
            return
        query = """
            INSERT INTO visibility_run_cache (cache_key, run_id, created_at)
            VALUES (%(cache_key)s, %(run_id)s, %(now)s)
            ON CONFLICT (cache_key) DO UPDATE SET run_id = EXCLUDED.run_id, created_at = EXCLUDED.created_at
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, {"cache_key": cache_key, "run_id": run_id, "now": _utc_now()})
            conn.commit()

    def get_run_detail(self, run_id: int) -> Optional[Dict[str, Any]]:
        """Full run detail for GET /api/visibility/runs/<id>. Returns None if run does not exist."""
        if not self.enabled or not run_id:
            return None
        run_query = """
            SELECT id, job_id, url, domain, brand_name, company_name, aliases_json,
                   prompt_set_version, scoring_version, overall_score, overall_label,
                   status, started_at, completed_at, error_message, provider_status_json,
                   cost_estimate_usd, latency_ms
            FROM visibility_runs WHERE id = %(run_id)s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(run_query, {"run_id": run_id})
                run_row = cur.fetchone()
                if not run_row:
                    return None

                aliases = _normalize_jsonb_list(run_row[6])
                provider_status = _normalize_jsonb_dict(run_row[15])
                status = run_row[11]
                if status == "done":
                    status = "complete"

                run_detail = {
                    "id": int(run_row[0]),
                    "job_id": run_row[1],
                    "url": run_row[2],
                    "domain": run_row[3],
                    "brand_name": run_row[4],
                    "company_name": run_row[5],
                    "aliases": aliases,
                    "prompt_set_version": run_row[7],
                    "scoring_version": run_row[8],
                    "overall_score": run_row[9],
                    "overall_label": run_row[10],
                    "status": status,
                    "started_at": run_row[12].isoformat() if run_row[12] else None,
                    "completed_at": run_row[13].isoformat() if run_row[13] else None,
                    "error_message": run_row[14],
                    "provider_status": provider_status,
                    "cost_estimate_usd": float(run_row[16] or 0.0),
                    "latency_ms": int(run_row[17] or 0),
                }

                cur.execute(
                    """
                    SELECT topic_key, prompt_text, provider, response_text, mentioned, cited,
                           brand_context, response_latency_ms, error_code, probe_status
                    FROM visibility_probes WHERE run_id = %(run_id)s ORDER BY topic_key, provider
                    """,
                    {"run_id": run_id},
                )
                probes_raw = cur.fetchall()
                probes = []
                for r in probes_raw:
                    topic_key = r[0]
                    topic_label = TOPIC_LABELS.get(topic_key, topic_key.replace("_", " ").title())
                    probes.append({
                        "topic_key": topic_key,
                        "topic_label": topic_label,
                        "prompt_text": r[1],
                        "provider": r[2],
                        "response_text": r[3] or "",
                        "mentioned": bool(r[4]),
                        "cited": bool(r[5]),
                        "brand_context": r[6],
                        "response_latency_ms": int(r[7] or 0),
                        "error_code": r[8],
                        "probe_status": r[9] if len(r) > 9 else "success",
                    })

                cur.execute(
                    """
                    SELECT provider, mentions, citations, mention_rate, citation_rate
                    FROM visibility_provider_metrics WHERE run_id = %(run_id)s
                    """,
                    {"run_id": run_id},
                )
                provider_metrics = [
                    {
                        "provider": r[0],
                        "mentions": int(r[1]),
                        "citations": int(r[2]),
                        "mention_rate": float(r[3] or 0),
                        "citation_rate": float(r[4] or 0),
                    }
                    for r in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT topic_key, topic_label, visibility_score,
                           chatgpt_mentioned, gemini_mentioned, claude_mentioned
                    FROM visibility_topics WHERE run_id = %(run_id)s ORDER BY visibility_score DESC
                    """,
                    {"run_id": run_id},
                )
                topics = []
                for r in cur.fetchall():
                    topics.append({
                        "topic_key": r[0],
                        "topic_label": r[1] or TOPIC_LABELS.get(r[0], r[0].replace("_", " ").title()),
                        "visibility_score": int(r[2] or 0),
                        "mentions_by_llm": {
                            "chatgpt": bool(r[3]),
                            "gemini": bool(r[4]),
                            "claude": bool(r[5]),
                        },
                    })

                run_detail["probes"] = probes
                run_detail["provider_metrics"] = provider_metrics
                run_detail["topics"] = topics
                by_llm = {m["provider"]: m for m in provider_metrics}
                run_detail["recommendations"] = compute_recommendations(topics, by_llm)
                return run_detail

