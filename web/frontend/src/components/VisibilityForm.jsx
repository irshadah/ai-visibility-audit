import { useState, useEffect } from "react";

function isLikelyUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function getInitialFormState(initialValues) {
  if (!initialValues) return null;
  return {
    url: initialValues.url ?? "",
    countryCode: initialValues.country_code ?? "US",
    brandName: initialValues.brandName ?? "",
    companyName: initialValues.companyName ?? "",
    competitorUrl1: initialValues.competitor_urls?.[0] ?? "",
    competitorUrl2: initialValues.competitor_urls?.[1] ?? "",
    aliasesRaw: Array.isArray(initialValues.aliases) ? initialValues.aliases.join(", ") : "",
    llms: Array.isArray(initialValues.llms)?.length ? initialValues.llms : ["gemini"],
    scanMode: initialValues.query_text ? "query" : "topic",
    category: initialValues.category ?? "generic",
    customQuery: initialValues.query_text ?? "",
    selectedQuery: initialValues.query_text ?? ""
  };
}

export default function VisibilityForm({ onAnalyze, isLoading, useCache = false, initialValues = null }) {
  const ALL_LLM_OPTIONS = ["chatgpt", "gemini", "claude"];
  const seed = getInitialFormState(initialValues);
  const [url, setUrl] = useState(seed?.url ?? "");
  const [countryCode, setCountryCode] = useState(seed?.countryCode ?? "US");
  const [brandName, setBrandName] = useState(seed?.brandName ?? "");
  const [companyName, setCompanyName] = useState(seed?.companyName ?? "");
  const [competitorUrl1, setCompetitorUrl1] = useState(seed?.competitorUrl1 ?? "");
  const [competitorUrl2, setCompetitorUrl2] = useState(seed?.competitorUrl2 ?? "");
  const [aliasesRaw, setAliasesRaw] = useState(seed?.aliasesRaw ?? "");
  const [llms, setLlms] = useState(seed?.llms ?? ["gemini"]);
  const [localError, setLocalError] = useState("");
  const [scanMode, setScanMode] = useState(seed?.scanMode ?? "topic");
  const [category, setCategory] = useState(seed?.category ?? "generic");
  const [selectedQuery, setSelectedQuery] = useState(seed?.selectedQuery ?? "");
  const [customQuery, setCustomQuery] = useState(seed?.customQuery ?? "");
  const [queryTemplates, setQueryTemplates] = useState({ categories: [], queries: {} });
  const [countries, setCountries] = useState([]);
  const [advanceExpanded, setAdvanceExpanded] = useState(false);

  useEffect(() => {
    fetch("/api/visibility/query-templates")
      .then((r) => r.json())
      .then((d) => {
        if (d.categories?.length) setQueryTemplates({ categories: d.categories, queries: d.queries || {} });
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/visibility/countries")
      .then((r) => r.json())
      .then((d) => {
        if (d.countries?.length) {
          setCountries(d.countries);
        }
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    const q = queryTemplates.queries[category] || [];
    if (q.length && !q.includes(selectedQuery)) setSelectedQuery(q[0] || "");
    else if (!q.length) setSelectedQuery("");
  }, [category, queryTemplates.queries]);

  function toggleLlm(llm) {
    setLlms((prev) => {
      if (prev.includes(llm)) return prev.filter((v) => v !== llm);
      return [...prev, llm];
    });
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!isLikelyUrl(url)) {
      setLocalError("Please enter a valid http(s) URL.");
      return;
    }
    if (!countryCode) {
      setLocalError("Please select a country.");
      return;
    }
    if (llms.length === 0) {
      setLocalError("Select at least one LLM provider.");
      return;
    }
    if (scanMode === "query") {
      const q = customQuery.trim() || selectedQuery;
      if (!q) {
        setLocalError("Select or enter a query for query-driven scan.");
        return;
      }
      if (q.length > 200) {
        setLocalError("Query must be at most 200 characters.");
        return;
      }
    }
    setLocalError("");
    const aliases = aliasesRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const competitor_urls =
      scanMode === "topic" ? [competitorUrl1.trim(), competitorUrl2.trim()].filter(Boolean) : [];
    if (competitor_urls.some((u) => !isLikelyUrl(u))) {
      setLocalError("Competitor URLs must be valid http(s) URLs.");
      return;
    }
    if (competitor_urls.length > 2) {
      setLocalError("At most 2 competitor URLs.");
      return;
    }
    const query_text = scanMode === "query" ? (customQuery.trim() || selectedQuery) : "";
    onAnalyze({
      url,
      country_code: countryCode,
      brandName,
      companyName,
      aliases,
      llms,
      competitor_urls,
      query_text,
      category: scanMode === "query" ? category : undefined,
      use_cache: useCache
    });
  }

  const queries = queryTemplates.queries[category] || [];
  const showCompetitors = scanMode === "topic";
  const showQueryFields = scanMode === "query";

  function toggleAdvance(e) {
    if (e.key && e.key !== "Enter" && e.key !== " ") return;
    if (e.key) e.preventDefault();
    setAdvanceExpanded((prev) => !prev);
  }

  const advanceContentId = "advance-audit-config-content";

  return (
    <form className="card visibility-form" onSubmit={handleSubmit}>
      <div className="form-section">
        <div className="form-section-title">Audit Configuration</div>
        <div className="form-row">
          <label className="field" style={{ flex: 2 }}>
            <span>Scan Mode</span>
            <div className="mode-row">
              <button
                type="button"
                className={`mode-pill ${scanMode === "topic" ? "mode-pill--active" : ""}`}
                onClick={() => setScanMode("topic")}
              >
                Topic-based
              </button>
              <button
                type="button"
                className={`mode-pill ${scanMode === "query" ? "mode-pill--active" : ""}`}
                onClick={() => setScanMode("query")}
              >
                Query-driven
              </button>
            </div>
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            <span>LLM Providers</span>
            <div className="mode-row">
              {ALL_LLM_OPTIONS.map((llm) => (
                <button
                  type="button"
                  key={llm}
                  className={`mode-pill ${llms.includes(llm) ? "mode-pill--active" : ""}`}
                  onClick={() => toggleLlm(llm)}
                >
                  {llm}
                </button>
              ))}
            </div>
          </label>
        </div>
        <div className="form-row">
          <label className="field" style={{ flex: 2 }}>
            <span>URL</span>
            <input
              type="text"
              placeholder="https://www.example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Country (required)</span>
            <select
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value)}
              required
            >
              <option value="">Select country</option>
              {countries.map((c) => (
                <option key={c.code} value={c.code}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <button className="btn" disabled={isLoading} style={{ alignSelf: "flex-end" }}>
            {isLoading ? "Analyzing..." : "Analyze AI Visibility"}
          </button>
        </div>
        {showQueryFields && (
          <div className="form-row">
            <label className="field">
              <span>Category</span>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                {queryTemplates.categories.map((c) => (
                  <option key={c} value={c}>
                    {c.charAt(0).toUpperCase() + c.slice(1)}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Predefined Query</span>
              <select
                value={selectedQuery}
                onChange={(e) => setSelectedQuery(e.target.value)}
                disabled={!queries.length}
              >
                <option value="">-- Select --</option>
                {queries.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Custom Query (optional override)</span>
              <input
                type="text"
                placeholder="e.g. waterproof jacket"
                value={customQuery}
                onChange={(e) => setCustomQuery(e.target.value)}
                maxLength={200}
              />
            </label>
          </div>
        )}
      </div>

      <div className="form-section advance-config-section">
        <button
          type="button"
          className="advance-config-header"
          onClick={toggleAdvance}
          onKeyDown={toggleAdvance}
          aria-expanded={advanceExpanded}
          aria-controls={advanceContentId}
        >
          <span>Advance Audit Configuration</span>
          <span className={`advance-config-chevron ${advanceExpanded ? "advance-config-chevron--expanded" : ""}`} aria-hidden>
            ▼
          </span>
        </button>
        {advanceExpanded && (
          <div id={advanceContentId} className="advance-config-content" role="region" aria-label="Advance Audit Configuration">
            <div className="form-section-title">Brand overrides (optional)</div>
            <div className="form-row">
              <label className="field">
                <span>Brand Name</span>
                <input
                  type="text"
                  placeholder="What is your brand name?"
                  value={brandName}
                  onChange={(e) => setBrandName(e.target.value)}
                />
              </label>
              <label className="field">
                <span>Company Name</span>
                <input
                  type="text"
                  placeholder="Company Name"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                />
              </label>
            </div>
            {showCompetitors && (
              <>
                <div className="form-section-title">Competitor configuration</div>
                <div className="form-row">
                <label className="field">
                  <span>Competitor URL 1 (optional)</span>
                  <input
                    type="text"
                    placeholder="https://competitor.com"
                    value={competitorUrl1}
                    onChange={(e) => setCompetitorUrl1(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Competitor URL 2 (optional)</span>
                  <input
                    type="text"
                    placeholder="https://competitor2.com"
                    value={competitorUrl2}
                    onChange={(e) => setCompetitorUrl2(e.target.value)}
                  />
                </label>
              </div>
              </>
            )}
            <div className="form-section-title">Aliases (optional)</div>
            <div className="form-row">
              <label className="field">
                <span>Comma-separated</span>
                <input
                  type="text"
                  placeholder="Boss, HugoBoss, H.B."
                  value={aliasesRaw}
                  onChange={(e) => setAliasesRaw(e.target.value)}
                />
              </label>
            </div>
          </div>
        )}
      </div>

      {localError ? <div className="error-box">{localError}</div> : null}
    </form>
  );
}
