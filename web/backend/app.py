from __future__ import annotations

from pathlib import Path
import json
import logging
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Flask, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
PY_SRC = ROOT / "python" / "src"
if str(PY_SRC) not in sys.path:
    sys.path.insert(0, str(PY_SRC))

from agentic_readiness.engine import ScoringEngine
from agentic_readiness.formatter import CATEGORY_LABELS, FIX_HINTS, MODE_TITLES, RULE_LABELS
from agentic_readiness.ai_visibility import (
    PROMPT_SET_VERSION,
    SUPPORTED_PROVIDERS,
    VisibilityConfig,
    run_ai_visibility_scan,
    run_query_driven_scan,
    QUERY_PROBE_N_RUNS,
)
from agentic_readiness.url_input import load_single_url_product, validate_url
from agentic_readiness.visibility_store import (
    VisibilityStore,
    build_run_cache_key,
    compute_recommendations,
)

VALID_MODES = {"GEO", "AEO", "SEO"}
DEFAULT_MODES = ["SEO"]

FRONTEND_DIST = ROOT / "web" / "frontend" / "dist"
load_dotenv(ROOT / ".env")

app = Flask(__name__, static_folder=str(FRONTEND_DIST), static_url_path="/")
CORS(app)
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_visibility_jobs: dict[str, dict] = {}
_visibility_jobs_lock = threading.Lock()
_visibility_store = VisibilityStore(os.getenv("DATABASE_URL", ""))
_job_store_root = Path(os.getenv("JOB_STORE_DIR", "/tmp/geo-audit-jobs"))
_readiness_store = _job_store_root / "readiness"
_visibility_store_dir = _job_store_root / "visibility"
_readiness_store.mkdir(parents=True, exist_ok=True)
_visibility_store_dir.mkdir(parents=True, exist_ok=True)

# Rate limits (TASK 2b.2): in-memory concurrent jobs; daily count and spend from DB
def _get_rate_limit_config() -> tuple[int, int, float]:
    try:
        concurrent = int(os.getenv("MAX_CONCURRENT_SCANS", "3"))
    except (TypeError, ValueError):
        concurrent = 3
    try:
        per_day = int(os.getenv("MAX_SCANS_PER_DAY", "20"))
    except (TypeError, ValueError):
        per_day = 20
    try:
        spend = float(os.getenv("MAX_DAILY_SPEND_USD", "20.0"))
    except (TypeError, ValueError):
        spend = 20.0
    return concurrent, per_day, spend


def _visibility_running_or_queued_count() -> int:
    with _visibility_jobs_lock:
        return sum(
            1 for j in _visibility_jobs.values()
            if (j.get("state") or "").lower() in ("running", "queued")
        )


def _validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_modes(raw_modes: list[str] | None) -> list[str]:
    if not raw_modes:
        return DEFAULT_MODES[:]
    modes = []
    for mode in raw_modes:
        normalized = str(mode).upper().strip()
        if normalized not in VALID_MODES:
            raise ValueError(f"Invalid mode: {mode}. Allowed: GEO, AEO, SEO.")
        if normalized not in modes:
            modes.append(normalized)
    if not modes:
        return DEFAULT_MODES[:]
    return modes


@app.get("/api/health")
def health() -> tuple[dict, int]:
    return {"status": "ok"}, 200


@app.get("/api/visibility/providers")
def visibility_providers() -> tuple[dict, int]:
    cfg = VisibilityConfig.from_env()
    return {
        "providers": _provider_availability_from_env(),
        "config": {
            "timeout_sec": cfg.timeout_sec,
            "max_prompts": cfg.max_prompts,
            "models": {
                "chatgpt": cfg.openai_model,
                "gemini": cfg.gemini_model,
                "claude": cfg.anthropic_model,
            },
        },
    }, 200


def _set_job(job_id: str, **updates) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id, {})
        job.update(updates)
        _jobs[job_id] = job
    _persist_job_snapshot(job_id, job, visibility=False)


def _set_visibility_job(job_id: str, **updates) -> None:
    with _visibility_jobs_lock:
        job = _visibility_jobs.get(job_id, {})
        job.update(updates)
        _visibility_jobs[job_id] = job
    _persist_job_snapshot(job_id, job, visibility=True)


def _job_file(job_id: str, visibility: bool = False) -> Path:
    base = _visibility_store_dir if visibility else _readiness_store
    return base / f"{job_id}.json"


def _persist_job_snapshot(job_id: str, payload: dict, visibility: bool = False) -> None:
    path = _job_file(job_id, visibility=visibility)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception as exc:
        app.logger.warning("Could not persist job snapshot (%s): %s", job_id, exc)


def _load_job_snapshot(job_id: str, visibility: bool = False) -> dict | None:
    path = _job_file(job_id, visibility=visibility)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        app.logger.warning("Could not load job snapshot (%s): %s", job_id, exc)
        return None


def _get_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job:
        return job
    snapshot = _load_job_snapshot(job_id, visibility=False)
    if snapshot:
        with _jobs_lock:
            _jobs[job_id] = snapshot
    return snapshot


def _get_visibility_job(job_id: str) -> dict | None:
    with _visibility_jobs_lock:
        job = _visibility_jobs.get(job_id)
    if job:
        return job
    snapshot = _load_job_snapshot(job_id, visibility=True)
    if snapshot:
        with _visibility_jobs_lock:
            _visibility_jobs[job_id] = snapshot
    return snapshot


def _run_score_job(job_id: str, url: str, modes: list[str], timeout_sec: int) -> None:
    try:
        _set_job(job_id, state="running", stage="Fetching page content...", progress=20)

        def progress_hook(stage: str, progress: int) -> None:
            _set_job(job_id, state="running", stage=stage, progress=progress)

        product = load_single_url_product(url, timeout_sec=timeout_sec, progress_hook=progress_hook)

        assessments: dict[str, dict] = {}
        total_modes = max(1, len(modes))
        for idx, mode in enumerate(modes):
            _set_job(
                job_id,
                state="running",
                stage=f"Scoring {mode} readiness...",
                progress=min(90, 30 + int(((idx + 1) / total_modes) * 55)),
            )
            engine = ScoringEngine.from_mode(mode)
            assessments[mode] = engine.score_batch([product], previous_report=None)

        _set_job(job_id, state="running", stage="Compiling report...", progress=95)
        _set_job(
            job_id,
            state="done",
            stage="Completed",
            progress=100,
            result={
                "assessments": assessments,
                "meta": {
                    "mode_titles": MODE_TITLES,
                    "category_labels": CATEGORY_LABELS,
                    "rule_labels": RULE_LABELS,
                    "fix_hints": FIX_HINTS,
                },
            },
        )
    except RuntimeError as exc:
        _set_job(job_id, state="error", stage="Failed", progress=100, error=str(exc))
    except Exception as exc:  # pragma: no cover
        _set_job(job_id, state="error", stage="Failed", progress=100, error=f"Unexpected server error: {exc}")


def _provider_availability_from_env() -> dict[str, dict]:
    cfg = VisibilityConfig.from_env()
    out: dict[str, dict] = {}
    for provider in SUPPORTED_PROVIDERS:
        if provider == "chatgpt":
            available = bool(cfg.openai_api_key)
        elif provider == "gemini":
            available = bool(cfg.gemini_api_key)
        elif provider == "claude":
            available = bool(cfg.anthropic_api_key)
        else:
            available = False
        out[provider] = {"available": available}
    return out


def _run_visibility_query_job(
    job_id: str,
    url: str,
    query_text: str,
    category: str,
    brand_name: str | None,
    company_name: str | None,
    aliases: list[str] | None,
    llms: list[str] | None,
    use_cache: bool = False,
    country_code: str | None = None,
) -> None:
    """Phase 4: Query-driven scan. No competitors."""
    started_at = datetime.now(timezone.utc)
    try:
        _set_visibility_job(job_id, state="running", stage="Preparing query probe...", progress=10)

        def progress_hook(stage: str, progress: int) -> None:
            _set_visibility_job(job_id, state="running", stage=stage, progress=progress)

        result = run_query_driven_scan(
            url,
            query_text,
            category,
            brand_name=brand_name,
            company_name=company_name,
            aliases=aliases,
            selected_providers=llms,
            progress_hook=progress_hook,
            use_cache=use_cache,
            country_code=country_code,
        )
        _set_visibility_job(job_id, state="running", stage="Persisting...", progress=95)
        by_provider = result.get("by_provider") or {}
        rows = []
        for provider, agg in by_provider.items():
            rows.append({
                "provider": provider,
                "run_count": agg.get("run_count", QUERY_PROBE_N_RUNS),
                "mentioned": agg.get("mentioned", False),
                "in_top_5": agg.get("in_top_5", False),
                "in_top_10": agg.get("in_top_10", False),
                "appearance_rate_pct": agg.get("appearance_rate_pct", 0),
                "avg_position": agg.get("avg_position"),
                "evidence_text": agg.get("evidence_text"),
                "cost_estimate_usd": QUERY_PROBE_N_RUNS * 0.002,
                "latency_ms": agg.get("latency_ms", 0),
            })
        query_run_id = None
        if rows:
            query_run_id = _visibility_store.insert_query_run_rows(
                job_id=job_id,
                url=url,
                domain=result.get("domain", ""),
                brand_name=result.get("brand", ""),
                company_name=result.get("company_name", ""),
                aliases=result.get("aliases") or [],
                query_text=query_text,
                category=category,
                rows=rows,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
            )
        result["job_id"] = job_id
        result["query_run_id"] = query_run_id
        result["run_id"] = query_run_id  # for compatibility
        result["status"] = "complete"
        _set_visibility_job(job_id, state="done", stage="Completed", progress=100, result=result)
    except Exception as exc:  # pragma: no cover
        _set_visibility_job(job_id, state="error", stage="Failed", progress=100, error=str(exc))


def _run_visibility_job(
    job_id: str,
    url: str,
    brand_name: str | None,
    company_name: str | None,
    aliases: list[str] | None,
    llms: list[str] | None,
    competitor_urls: list[str] | None = None,
    query_text: str | None = None,
    category: str | None = None,
    use_cache: bool = False,
    country_code: str | None = None,
) -> None:
    competitor_urls = competitor_urls or []
    if query_text and query_text.strip():
        _run_visibility_query_job(
            job_id, url, query_text.strip(), (category or "generic").strip().lower(),
            brand_name, company_name, aliases, llms, use_cache=use_cache, country_code=country_code,
        )
        return
    started_at = datetime.now(timezone.utc)
    try:
        _set_visibility_job(job_id, state="running", stage="Preparing probe set...", progress=10)

        def progress_hook(stage: str, progress: int) -> None:
            _set_visibility_job(job_id, state="running", stage=stage, progress=progress)

        # 1. Primary scan
        result = run_ai_visibility_scan(
            url,
            brand_name=brand_name,
            company_name=company_name,
            aliases=aliases,
            selected_providers=llms,
            progress_hook=progress_hook,
            use_cache=use_cache,
            country_code=country_code,
        )
        _set_visibility_job(job_id, state="running", stage="Persisting run...", progress=97)
        skipped_codes = {"skipped_by_user", "missing_api_key"}
        total_probes = sum(
            len(p.get("responses") or {}) for p in result.get("probes") or []
        )
        failed_probes = sum(
            1
            for p in result.get("probes") or []
            for r in (p.get("responses") or {}).values()
            if r.get("error_code") and r.get("error_code") not in skipped_codes
        )
        run_status = "complete"
        if total_probes > 0 and (failed_probes / total_probes) > 0.3:
            run_status = "partial"
        run_payload = {
            "job_id": job_id,
            "url": url,
            "domain": result.get("domain"),
            "brand_name": result.get("brand"),
            "company_name": result.get("company_name"),
            "aliases": result.get("aliases") or [],
            "prompt_set_version": result.get("prompt_set_version", "v1"),
            "scoring_version": result.get("scoring_version", "v1"),
            "overall_score": result.get("overall_score"),
            "overall_label": result.get("overall_label"),
            "status": run_status,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc),
            "provider_status": result.get("provider_status") or {},
            "cost_estimate_usd": result.get("cost_estimate_usd", 0.0),
            "latency_ms": result.get("latency_ms", 0),
        }
        run_id = _visibility_store.insert_run(run_payload)
        if run_id:
            _visibility_store.insert_provider_metrics(run_id, result.get("by_llm") or {})
            _visibility_store.insert_topics(run_id, result.get("topics") or [])
            _visibility_store.insert_probes(run_id, result.get("probes") or [])
        result["job_id"] = job_id
        if run_id:
            result["run_id"] = run_id
        result["status"] = run_status

        # 2. Competitor scans (sequential)
        competitors = []
        for idx, comp_url in enumerate(competitor_urls):
            _set_visibility_job(
                job_id,
                state="running",
                stage=f"Checking competitor {idx + 1}/{len(competitor_urls)}...",
                progress=min(90, 70 + (idx + 1) * 8),
            )
            cache_key = build_run_cache_key(comp_url, PROMPT_SET_VERSION, "us", "en")
            cached_run_id = _visibility_store.cache_get_run_id(cache_key)
            if cached_run_id:
                detail = _visibility_store.get_run_detail(cached_run_id)
                if detail:
                    totals = {"mentions": 0, "citations": 0}
                    for m in detail.get("provider_metrics") or []:
                        totals["mentions"] += int(m.get("mentions") or 0)
                        totals["citations"] += int(m.get("citations") or 0)
                    competitors.append({
                        "url": comp_url,
                        "domain": detail.get("domain"),
                        "overall_score": detail.get("overall_score"),
                        "totals": totals,
                        "run_id": cached_run_id,
                    })
                    continue
            _set_visibility_job(
                job_id, state="running",
                stage=f"Scanning competitor {idx + 1}...",
                progress=min(92, 75 + (idx + 1) * 8),
            )
            comp_result = run_ai_visibility_scan(
                comp_url,
                selected_providers=llms,
                progress_hook=progress_hook,
                use_cache=use_cache,
                country_code=country_code,
            )
            comp_run_payload = {
                "job_id": job_id,
                "url": comp_url,
                "domain": comp_result.get("domain"),
                "brand_name": comp_result.get("brand"),
                "company_name": comp_result.get("company_name"),
                "aliases": comp_result.get("aliases") or [],
                "prompt_set_version": comp_result.get("prompt_set_version", "v1"),
                "scoring_version": comp_result.get("scoring_version", "v1"),
                "overall_score": comp_result.get("overall_score"),
                "overall_label": comp_result.get("overall_label"),
                "status": "complete",
                "started_at": datetime.now(timezone.utc),
                "completed_at": datetime.now(timezone.utc),
                "provider_status": comp_result.get("provider_status") or {},
                "cost_estimate_usd": comp_result.get("cost_estimate_usd", 0.0),
                "latency_ms": comp_result.get("latency_ms", 0),
            }
            comp_run_id = _visibility_store.insert_run(comp_run_payload)
            if comp_run_id:
                _visibility_store.insert_provider_metrics(comp_run_id, comp_result.get("by_llm") or {})
                _visibility_store.insert_topics(comp_run_id, comp_result.get("topics") or [])
                _visibility_store.insert_probes(comp_run_id, comp_result.get("probes") or [])
                _visibility_store.cache_set(cache_key, comp_run_id)
            totals = comp_result.get("totals") or {}
            competitors.append({
                "url": comp_url,
                "domain": comp_result.get("domain"),
                "overall_score": comp_result.get("overall_score"),
                "totals": {
                    "mentions": totals.get("mentions", 0),
                    "citations": totals.get("citations", 0),
                },
                "run_id": comp_run_id,
            })

        if competitors:
            result = {
                **result,
                "primary": result,
                "competitors": competitors,
            }
        result["recommendations"] = compute_recommendations(
            result.get("topics") or [], result.get("by_llm") or {}
        )
        _set_visibility_job(job_id, state="done", stage="Completed", progress=100, result=result)
    except Exception as exc:  # pragma: no cover
        _set_visibility_job(job_id, state="error", stage="Failed", progress=100, error=str(exc))


@app.post("/api/score/start")
def score_start() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    url = str(body.get("url", "")).strip()
    try:
        timeout_sec = int(body.get("timeout_sec", 60))
    except (TypeError, ValueError):
        return {"error": "timeout_sec must be an integer"}, 400

    if not url:
        return {"error": "url is required"}, 400
    if not _validate_url(url):
        return {"error": "Invalid URL. Use full http(s) URL."}, 400

    try:
        modes = _normalize_modes(body.get("modes"))
    except ValueError as exc:
        return {"error": str(exc)}, 400

    job_id = uuid.uuid4().hex
    _set_job(job_id, state="queued", stage="Queued", progress=5, result=None, error=None)

    worker = threading.Thread(target=_run_score_job, args=(job_id, url, modes, timeout_sec), daemon=True)
    worker.start()
    return {"job_id": job_id}, 202


@app.get("/api/score/status/<job_id>")
def score_status(job_id: str) -> tuple[dict, int]:
    job = _get_job(job_id)
    if not job:
        return {"error": "Job not found"}, 404
    return job, 200


@app.post("/api/visibility/start")
def visibility_start() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    url = str(body.get("url", "")).strip()
    brand_name = str(body.get("brand_name", "")).strip() or None
    company_name = str(body.get("company_name", "")).strip() or None
    aliases_raw = body.get("aliases", [])
    aliases = [str(x).strip() for x in aliases_raw if str(x).strip()] if isinstance(aliases_raw, list) else []
    llms_raw = body.get("llms", [])
    if llms_raw is None:
        llms_raw = []
    if not isinstance(llms_raw, list):
        return {"error": "llms must be an array."}, 400
    llms = [str(x).strip().lower() for x in llms_raw if str(x).strip()]
    if not llms:
        llms = ["gemini"]
    invalid_llms = [x for x in llms if x not in SUPPORTED_PROVIDERS]
    if invalid_llms:
        return {"error": f"Invalid llms: {', '.join(invalid_llms)}. Allowed: chatgpt, gemini, claude."}, 400

    # Only run providers that have an API key configured; skip others so progress never shows them
    availability = _provider_availability_from_env()
    llms_available = [p for p in llms if availability.get(p, {}).get("available")]
    if not llms_available:
        missing = [p for p in llms if p in SUPPORTED_PROVIDERS]
        return {
            "error": f"No API key configured for selected provider(s): {', '.join(missing)}. Add the corresponding env var (e.g. OPENAI_API_KEY for chatgpt) or choose another provider."
        }, 400
    llms = llms_available

    if not url:
        return {"error": "url is required"}, 400
    if not _validate_url(url):
        return {"error": "Invalid URL. Use full http(s) URL."}, 400

    country_code = str(body.get("country_code", "")).strip().upper() or None
    if not country_code:
        return {"error": "country_code is required. Select a country from the dropdown."}, 400
    from agentic_readiness.query_templates import COUNTRY_CODES
    if country_code not in COUNTRY_CODES:
        return {"error": f"Invalid country_code: {country_code}. Must be one of the supported countries."}, 400

    query_text = str(body.get("query_text", "")).strip()
    category = str(body.get("category", "generic")).strip().lower() or "generic"
    use_cache = bool(body.get("use_cache", False))
    if query_text:
        from agentic_readiness.query_templates import CATEGORIES, validate_query_text
        err = validate_query_text(query_text)
        if err:
            return {"error": err}, 400
        if category not in CATEGORIES:
            return {"error": f"category must be one of {list(CATEGORIES)}"}, 400

    competitor_urls_raw = body.get("competitor_urls", [])
    if not isinstance(competitor_urls_raw, list):
        return {"error": "competitor_urls must be an array."}, 400
    competitor_urls = [str(u).strip() for u in competitor_urls_raw if str(u).strip()][:2]
    if len(competitor_urls_raw) > 2:
        return {"error": "At most 2 competitor URLs allowed."}, 400
    if query_text and competitor_urls:
        return {"error": "Competitor URLs are not supported in query-driven mode."}, 400
    try:
        validate_url(url, timeout_sec=60)
        for u in competitor_urls:
            validate_url(u, timeout_sec=60)
    except ValueError as e:
        msg = str(e)
        if "timeout" in msg.lower():
            logging.warning("URL pre-check timed out for %s (or competitor); starting job anyway. %s", url, msg)
        else:
            return {"error": msg}, 400

    max_concurrent, max_per_day, max_spend = _get_rate_limit_config()
    running = _visibility_running_or_queued_count()
    if running >= max_concurrent:
        return (
            {"error": "Rate limit exceeded", "retry_after": 60},
            429,
            {"Retry-After": "60"},
        )
    try:
        today = _visibility_store.get_today_completed_count_and_spend()
    except Exception as exc:
        app.logger.exception("Visibility preflight failed before queueing job: %s", exc)
        return {
            "error": (
                "Visibility preflight failed. Ensure DATABASE_URL is valid and DB migrations are applied "
                "(run: python scripts/run_migrations.py)."
            )
        }, 500
    if today["runs_count"] >= max_per_day:
        return (
            {"error": "Daily scan limit reached", "retry_after": 3600},
            429,
            {"Retry-After": "3600"},
        )
    if today["total_usd"] >= max_spend:
        return (
            {"error": "Daily budget exceeded", "retry_after": 3600},
            429,
            {"Retry-After": "3600"},
        )

    job_id = uuid.uuid4().hex
    _set_visibility_job(
        job_id,
        state="queued",
        stage="Queued",
        progress=5,
        result=None,
        error=None,
    )
    worker = threading.Thread(
        target=_run_visibility_job,
        args=(job_id, url, brand_name, company_name, aliases, llms, competitor_urls, query_text or None, category if query_text else None, use_cache, country_code),
        daemon=True,
    )
    worker.start()
    return {"job_id": job_id}, 202


@app.get("/api/visibility/countries")
def visibility_countries() -> tuple[dict, int]:
    """Return curated country list for location dropdown."""
    from agentic_readiness.query_templates import COUNTRIES
    return {"countries": [{"code": c[0], "name": c[1]} for c in COUNTRIES]}, 200


@app.get("/api/visibility/query-templates")
def visibility_query_templates() -> tuple[dict, int]:
    """Phase 4: Return categories and predefined queries for query-driven mode."""
    from agentic_readiness.query_templates import (
        CATEGORIES,
        get_queries_for_category,
    )
    queries = {cat: get_queries_for_category(cat) for cat in CATEGORIES}
    return {"categories": list(CATEGORIES), "queries": queries}, 200


@app.get("/api/visibility/query-runs")
def visibility_query_runs_list() -> tuple[dict, int]:
    """Phase 4: List recent query runs. Query param: url (optional), limit (default 10)."""
    url = request.args.get("url", "").strip() or None
    try:
        limit = int(request.args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    runs = _visibility_store.list_query_runs(url=url, limit=limit)
    return {"runs": runs}, 200


@app.get("/api/visibility/query-runs/<int:run_id>")
def visibility_query_run_detail(run_id: int) -> tuple[dict, int]:
    """Phase 4: Full detail for a query-driven run."""
    detail = _visibility_store.get_query_run_detail(run_id)
    if not detail:
        return {"error": "Query run not found"}, 404
    return detail, 200


@app.get("/api/visibility/status/<job_id>")
def visibility_status(job_id: str) -> tuple[dict, int]:
    job = _get_visibility_job(job_id)
    if not job:
        return {"error": "Job not found"}, 404
    return job, 200


@app.get("/api/admin/costs")
def admin_costs() -> tuple[dict, int]:
    """Return total cost and run count for a date range. Query params: from=YYYY-MM-DD, to=YYYY-MM-DD (UTC)."""
    from_str = (request.args.get("from") or "").strip()
    to_str = (request.args.get("to") or "").strip()
    from_ts = None
    to_ts = None
    try:
        if from_str:
            from_ts = datetime.strptime(from_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if to_str:
            d = datetime.strptime(to_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            to_ts = d.replace(hour=23, minute=59, second=59, microsecond=999999)
    except ValueError:
        return {"error": "from and to must be YYYY-MM-DD"}, 400
    summary = _visibility_store.get_cost_summary(from_ts=from_ts, to_ts=to_ts)
    return {"total_usd": round(summary["total_usd"], 4), "runs_count": summary["runs_count"]}, 200


@app.get("/api/visibility/runs/<int:run_id>")
def visibility_run_by_id(run_id: int) -> tuple[dict, int]:
    detail = _visibility_store.get_run_detail(run_id)
    if detail is None:
        return {"error": "Run not found"}, 404
    return detail, 200


@app.get("/api/visibility/runs")
def visibility_runs() -> tuple[dict, int]:
    url = str(request.args.get("url", "")).strip() or None
    try:
        limit = int(request.args.get("limit", "20"))
    except ValueError:
        return {"error": "limit must be an integer"}, 400
    limit = max(1, min(100, limit))
    runs = _visibility_store.list_runs(url=url, limit=limit)
    return {"runs": runs}, 200


@app.post("/api/score")
def score_url() -> tuple[dict, int]:
    body = request.get_json(silent=True) or {}
    url = str(body.get("url", "")).strip()
    try:
        timeout_sec = int(body.get("timeout_sec", 60))
    except (TypeError, ValueError):
        return {"error": "timeout_sec must be an integer"}, 400

    if not url:
        return {"error": "url is required"}, 400
    if not _validate_url(url):
        return {"error": "Invalid URL. Use full http(s) URL."}, 400

    try:
        modes = _normalize_modes(body.get("modes"))
    except ValueError as exc:
        return {"error": str(exc)}, 400

    try:
        product = load_single_url_product(url, timeout_sec=timeout_sec)
        assessments: dict[str, dict] = {}
        for mode in modes:
            engine = ScoringEngine.from_mode(mode)
            assessments[mode] = engine.score_batch([product], previous_report=None)

        return {
            "assessments": assessments,
            "meta": {
                "mode_titles": MODE_TITLES,
                "category_labels": CATEGORY_LABELS,
                "rule_labels": RULE_LABELS,
                "fix_hints": FIX_HINTS,
            },
        }, 200
    except RuntimeError as exc:
        app.logger.warning("Score URL failed: %s", exc)
        return {"error": str(exc)}, 422
    except Exception as exc:  # pragma: no cover
        return {"error": f"Unexpected server error: {exc}"}, 500


@app.get("/")
def serve_index():
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return send_from_directory(str(FRONTEND_DIST), "index.html")
    return (
        "Frontend is not built yet. Run Vite dev server in web/frontend or build frontend assets.",
        200,
    )


@app.get("/<path:path>")
def serve_static(path: str):
    target = FRONTEND_DIST / path
    if target.exists():
        return send_from_directory(str(FRONTEND_DIST), path)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return send_from_directory(str(FRONTEND_DIST), "index.html")
    return "Not Found", 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5001"))
    debug = os.getenv("FLASK_ENV", "").lower() != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
