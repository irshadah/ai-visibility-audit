import React, { useEffect, useMemo, useState } from "react";

function ringStyle(score) {
  const safe = Math.max(0, Math.min(100, Number(score || 0)));
  const filledColor = "#38bdf8";
  const restColor = "#dbeafe";
  return {
    background: `conic-gradient(${filledColor} ${safe * 3.6}deg, ${restColor} 0deg)`
  };
}

function providerPercent(part, total) {
  if (!total) return 0;
  return Math.round((part / total) * 1000) / 10;
}

function statusClass(value) {
  if (value >= 75) return "pass";
  if (value >= 45) return "warn";
  return "fail";
}

// Normalize probes to flat list so one view works for job result (nested) and GET run detail (flat)
function normalizeProbes(result) {
  const probes = result?.probes || [];
  if (!probes.length) return [];
  const first = probes[0];
  if (first?.responses && typeof first.responses === "object") {
    const flat = [];
    const topicLabel = (p) => p.topic_label || p.topic || (p.topic_key || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    for (const p of probes) {
      const topic_key = p.topic_key || p.topic || "unknown";
      const topic_label = topicLabel(p);
      for (const [provider, row] of Object.entries(p.responses || {})) {
        const err = row?.error_code;
        let probe_status = "success";
        if (err != null && String(err).trim() !== "") probe_status = String(err).toLowerCase().includes("timeout") ? "timeout" : "failed";
        flat.push({
          topic_key,
          topic_label,
          provider,
          response_text: row?.response_text ?? "",
          mentioned: Boolean(row?.mentioned),
          cited: Boolean(row?.cited),
          probe_status,
          response_latency_ms: Number(row?.response_latency_ms) || 0,
          error_code: err ?? null
        });
      }
    }
    return flat;
  }
  return probes.map((p) => ({
    ...p,
    topic_label: p.topic_label || p.topic || (p.topic_key || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    probe_status: p.probe_status ?? "success"
  }));
}

const TOPIC_RECOMMENDATIONS = {
  best_brands: "Improve presence in competitive-list answers.",
  product_recommendation: "Strengthen product-level signals so AIs can recommend your products.",
  official_site: "Ensure brand and domain are clearly associated in structured data and authoritative sources.",
  brand_overview: "Improve visibility for this topic through content and technical SEO.",
  brand_company: "Improve visibility for this topic through content and technical SEO.",
  comparison: "Improve visibility for this topic through content and technical SEO.",
  trust_signal: "Improve visibility for this topic through content and technical SEO.",
  brand_recall: "Improve visibility for this topic through content and technical SEO.",
  purchase_intent: "Improve visibility for this topic through content and technical SEO.",
  brand_relevance: "Improve visibility for this topic through content and technical SEO.",
  seo_like_query: "Improve visibility for this topic through content and technical SEO.",
  domain_specific: "Improve visibility for this topic through content and technical SEO."
};

function detectSources(responseText, runUrl) {
  if (!responseText || typeof responseText !== "string") return [];
  const text = responseText.toLowerCase();
  const seen = new Set();
  const patterns = [
    { re: /wikipedia/gi, name: "Wikipedia" },
    { re: /according to\s+([^.,]+)/gi, name: (m) => m[1].trim() },
    { re: /source:\s*([^\n.,]+)/gi, name: (m) => m[1].trim() },
    { re: /reddit/gi, name: "Reddit" },
    { re: /([a-z0-9-]+\.(?:com|de|org|net))\b/gi, name: (m) => m[1].toLowerCase() }
  ];
  for (const { re, name } of patterns) {
    let m;
    re.lastIndex = 0;
    while ((m = re.exec(text)) !== null) {
      const n = typeof name === "function" ? name(m) : name;
      if (n && n.length < 80) seen.add(n);
    }
  }
  if (runUrl) {
    try {
      const domain = new URL(runUrl.startsWith("http") ? runUrl : `https://${runUrl}`).hostname.toLowerCase();
      if (domain && text.includes(domain)) seen.add(domain);
    } catch (_) {}
  }
  return [...seen];
}

export default function VisibilityDashboard({ result, onSelectRunId }) {
  const [history, setHistory] = useState([]);
  const [expandedTopicKey, setExpandedTopicKey] = useState(null);
  const byLlmRaw = result?.by_llm || result?.provider_metrics?.reduce((acc, m) => ({ ...acc, [m.provider]: m }), {}) || {};
  const providerStatus = result?.provider_status || {};
  const byLlm = useMemo(() => {
    const available = Object.entries(providerStatus).filter(([, s]) => s?.status === "available").map(([p]) => p);
    if (available.length === 0) return byLlmRaw;
    return Object.fromEntries(Object.entries(byLlmRaw).filter(([p]) => available.includes(p)));
  }, [byLlmRaw, providerStatus]);
  const topics = result?.topics || [];
  const totals = result?.totals || {};

  const flatProbes = useMemo(() => normalizeProbes(result), [result]);
  const probesByTopic = useMemo(() => {
    const byTopic = {};
    for (const p of flatProbes) {
      const k = p.topic_key || "unknown";
      if (!byTopic[k]) byTopic[k] = [];
      byTopic[k].push(p);
    }
    return byTopic;
  }, [flatProbes]);

  const mentionTotal = useMemo(() => {
    return Object.values(byLlm).reduce((sum, row) => sum + Number(row?.mentions || 0), 0);
  }, [byLlm]);

  const gapTopics = useMemo(() => {
    const zero = [];
    const low = [];
    for (const t of topics) {
      const vis = Number(t.visibility ?? t.visibility_score ?? 0);
      const label = t.topic_label || t.topic || (t.topic_key || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      const rec = TOPIC_RECOMMENDATIONS[t.topic_key] || "Improve visibility for this topic through content and technical SEO.";
      if (vis === 0) zero.push({ ...t, label, rec });
      else if (vis <= 33) low.push({ ...t, label, rec });
    }
    return { zero, low };
  }, [topics]);

  useEffect(() => {
    async function loadHistory() {
      if (!result?.url) return;
      try {
        const res = await fetch(`/api/visibility/runs?url=${encodeURIComponent(result.url)}&limit=5`);
        const data = await res.json();
        if (res.ok) setHistory(data?.runs || []);
      } catch {
        setHistory([]);
      }
    }
    loadHistory();
  }, [result?.url]);

  const isPartial = result?.status === "partial";

  return (
    <section className="card">
      <div className="results-header">
        <h2 style={{ margin: 0 }}>AI Visibility Report</h2>
        <div className="muted">{result?.domain}</div>
      </div>
      {isPartial && (
        <div className="warn" style={{ padding: "10px 14px", marginBottom: 12, borderRadius: 6, background: "var(--bg-warn-subtle, #fffbeb)" }}>
          This run had some failed probes; scores may be incomplete.
        </div>
      )}

      <div className="visibility-layout">
        <div className="visibility-score-card">
          <div className="muted">AI Visibility</div>
          <div className="score-circle" style={ringStyle(result?.overall_score)}>
            <div className="score-circle-inner">
              <span className="score-value">{result?.overall_score ?? 0}</span>
              <span className="score-denominator">/100</span>
            </div>
          </div>
          <div className={`badge ${statusClass(Number(result?.overall_score || 0))}`}>{result?.overall_label || "Low"}</div>
          {(result?.recommendations?.length > 0) && (
            <div style={{ marginTop: 12, padding: "8px 12px", background: "var(--bg-subtle, #f0fdf4)", borderRadius: 6 }}>
              <div className="muted" style={{ marginBottom: 6, fontWeight: 600 }}>Next actions</div>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {result.recommendations.map((rec, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>{rec}</li>
                ))}
              </ul>
            </div>
          )}
          {(!result?.recommendations?.length) && (
            <div className="muted" style={{ marginTop: 8 }}>No specific recommendations for this run.</div>
          )}
          <div className="muted" style={{ marginTop: 8 }}>
            Brand: <strong>{result?.brand || result?.brand_name || "-"}</strong>
          </div>
          <div className="muted">
            Company: <strong>{result?.company_name || "-"}</strong>
          </div>
        </div>

        <div className="visibility-main-card">
          <div className="summary-grid">
            <div className="summary-item">
              <div className="muted">Mentions</div>
              <div className="score-value">{totals?.mentions ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="muted">Citations</div>
              <div className="score-value">{totals?.citations ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="muted">Probes Sent</div>
              <div className="score-value">{totals?.probes_sent ?? 0}</div>
            </div>
            <div className="summary-item">
              <div className="muted">Provider Calls</div>
              <div className="score-value">{totals?.provider_calls_successful ?? 0}</div>
            </div>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Distribution by LLM</th>
                  <th>Mentions</th>
                  <th>Share</th>
                  <th title="% of probes where the AI mentioned your domain">Citation rate</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(byLlm).map(([provider, row]) => {
                  const share = providerPercent(Number(row?.mentions || 0), mentionTotal);
                  const citationRate = row?.citation_rate != null ? Math.round(Number(row.citation_rate) * 100) : null;
                  return (
                    <tr key={provider}>
                      <td style={{ width: "45%" }}>
                        <div style={{ marginBottom: 6 }}>{provider}</div>
                        <div className="progress">
                          <span style={{ width: `${share}%` }} />
                        </div>
                      </td>
                      <td>{row?.mentions ?? 0}</td>
                      <td>{share}%</td>
                      <td>{citationRate != null ? `${citationRate}%` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {Object.keys(byLlm).length > 0 && (
            <p style={{ marginTop: 8, fontSize: "0.95em" }} title="% of probes where the AI mentioned your domain (e.g. yoursite.com) in its response">
              Citation rate: {Object.entries(byLlm).map(([p, row]) => {
                const rate = row?.citation_rate != null ? Math.round(Number(row.citation_rate) * 100) : 0;
                return `${p} ${rate}%`;
              }).join(", ")}.
            </p>
          )}
        </div>
      </div>

      <div style={{ marginTop: 16 }}>
        <h3 style={{ marginBottom: 10 }}>Topics</h3>
        {topics.length === 0 && flatProbes.length === 0 ? (
          <div className="muted">No response data</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Topic</th>
                  <th>Visibility %</th>
                  <th>Mentioned (ChatGPT)</th>
                  <th>Mentioned (Gemini)</th>
                  <th>Mentioned (Claude)</th>
                  <th>AI Volume</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {topics.map((topic) => {
                  const mentions = topic?.mentions_by_llm || {};
                  const topicKey = topic.topic_key || topic.topic;
                  const topicLabel = topic.topic_label || topic.topic || (topicKey || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                  const isExpanded = expandedTopicKey === topicKey;
                  const topicProbes = probesByTopic[topicKey] || [];
                  return (
                    <React.Fragment key={topicKey}>
                      <tr>
                        <td>{topicLabel}</td>
                        <td>{topic.visibility ?? topic.visibility_score ?? "—"}</td>
                        <td>{mentions.chatgpt ? "Yes" : "No"}</td>
                        <td>{mentions.gemini ? "Yes" : "No"}</td>
                        <td>{mentions.claude ? "Yes" : "No"}</td>
                        <td>{topic.ai_volume_estimate ?? "—"}</td>
                        <td>
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => setExpandedTopicKey(isExpanded ? null : topicKey)}
                          >
                            {isExpanded ? "Hide" : "View LLM response"}
                          </button>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${topicKey}-expanded`}>
                          <td colSpan={7} style={{ padding: "12px 16px", background: "var(--bg-subtle, #f8fafc)", verticalAlign: "top" }}>
                            {topicProbes.length === 0 ? (
                              <div className="muted">No response data for this topic.</div>
                            ) : (
                              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                                {topicProbes.map((probe) => {
                                  const isFail = probe.probe_status === "failed" || probe.probe_status === "timeout";
                                  const sources = detectSources(probe.response_text, result?.url);
                                  return (
                                    <div key={`${topicKey}-${probe.provider}`} style={{ borderLeft: "3px solid #38bdf8", paddingLeft: 12 }}>
                                      <div style={{ fontWeight: 600, marginBottom: 6 }}>{probe.provider}</div>
                                      {isFail ? (
                                        <p className="muted">
                                          {probe.probe_status === "timeout" ? "This probe timed out." : "This probe failed."}
                                          {probe.response_text ? ` Partial: ${probe.response_text.slice(0, 200)}…` : ""}
                                        </p>
                                      ) : (
                                        <>
                                          <blockquote style={{ margin: "8px 0", fontStyle: "italic", opacity: 0.95 }}>
                                            {probe.response_text || "No response."}
                                          </blockquote>
                                          <div className="muted" style={{ fontSize: "0.9em" }}>
                                            Sources detected: {sources.length ? sources.join(", ") : "—"}
                                          </div>
                                        </>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {result?.competitors?.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ marginBottom: 10 }}>Competitor comparison</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>URL / Domain</th>
                  <th>Score</th>
                  <th>Mentions</th>
                  <th>Citations</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{result?.url || result?.domain || "—"}</td>
                  <td>{result?.overall_score ?? "—"}</td>
                  <td>{result?.totals?.mentions ?? "—"}</td>
                  <td>{result?.totals?.citations ?? "—"}</td>
                </tr>
                {result.competitors.map((c, i) => (
                  <tr key={i}>
                    <td>{c.url || c.domain || "—"}</td>
                    <td>{c.overall_score ?? "—"}</td>
                    <td>{c.totals?.mentions ?? "—"}</td>
                    <td>{c.totals?.citations ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(gapTopics.zero.length > 0 || gapTopics.low.length > 0) && (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ marginBottom: 6 }}>Improvement opportunities</h3>
          <p className="muted" style={{ marginBottom: 12, fontSize: "0.9em" }}>
            Topics where AI assistants rarely or never mention your brand. These are not errors—they are gaps you can address with content and technical SEO to improve AI visibility.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {gapTopics.zero.map((t) => (
              <div key={t.topic_key || t.label} style={{ padding: "10px 14px", background: "var(--bg-subtle, #fef2f2)", borderRadius: 6, borderLeft: "3px solid #f87171" }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{t.label}</div>
                <div style={{ fontSize: "0.9em" }}>0% visibility — {t.rec}</div>
              </div>
            ))}
            {gapTopics.low.map((t) => (
              <div key={t.topic_key || t.label} className="warn" style={{ padding: "10px 14px", background: "var(--bg-warn-subtle, #fffbeb)", borderRadius: 6, borderLeft: "3px solid #f59e0b" }}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{t.label}</div>
                <div style={{ fontSize: "0.9em" }}>Low visibility ({t.visibility ?? t.visibility_score}%) — {t.rec}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ marginTop: 16 }}>
        <h3 style={{ marginBottom: 10 }}>Provider Status</h3>
        <div className="mode-row">
          {Object.entries(providerStatus).map(([provider, state]) => {
            const status = state?.status || "unknown";
            const cls =
              status === "available"
                ? "pass"
                : status === "missing_api_key" || status === "skipped_by_user"
                  ? "warn"
                  : "fail";
            const label = status === "skipped_by_user" ? "skipped" : status;
            return (
              <span key={provider} className={`badge ${cls}`}>
                {provider}: {label}
              </span>
            );
          })}
        </div>
      </div>

      {history.length > 0 ? (
        <div style={{ marginTop: 16 }}>
          <h3 style={{ marginBottom: 10 }}>Recent Runs</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Started</th>
                  <th>Score</th>
                  <th>Label</th>
                  <th>Status</th>
                  <th>Prompt Set</th>
                  <th>Scoring Version</th>
                  {onSelectRunId ? <th></th> : null}
                </tr>
              </thead>
              <tbody>
                {history.map((run) => (
                  <tr key={run.id || run.job_id}>
                    <td>{run.started_at ? new Date(run.started_at).toLocaleString() : "-"}</td>
                    <td>{run.overall_score ?? "-"}</td>
                    <td>{run.overall_label ?? "-"}</td>
                    <td>{run.status ?? "-"}</td>
                    <td>{run.prompt_set_version ?? "-"}</td>
                    <td>{run.scoring_version ?? "-"}</td>
                    {onSelectRunId && run.id ? (
                      <td>
                        <button type="button" className="secondary" onClick={() => onSelectRunId(run.id)}>
                          View
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
