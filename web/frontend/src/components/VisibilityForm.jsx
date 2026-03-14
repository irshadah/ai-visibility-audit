import { useState } from "react";

function isLikelyUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export default function VisibilityForm({ onAnalyze, isLoading }) {
  const ALL_LLM_OPTIONS = ["chatgpt", "gemini", "claude"];
  const [url, setUrl] = useState("");
  const [brandName, setBrandName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [competitorUrl1, setCompetitorUrl1] = useState("");
  const [competitorUrl2, setCompetitorUrl2] = useState("");
  const [aliasesRaw, setAliasesRaw] = useState("");
  const [llms, setLlms] = useState(["gemini"]);
  const [localError, setLocalError] = useState("");

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
    if (llms.length === 0) {
      setLocalError("Select at least one LLM provider.");
      return;
    }
    setLocalError("");
    const aliases = aliasesRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const competitor_urls = [competitorUrl1.trim(), competitorUrl2.trim()].filter(Boolean);
    if (competitor_urls.some((u) => !isLikelyUrl(u))) {
      setLocalError("Competitor URLs must be valid http(s) URLs.");
      return;
    }
    if (competitor_urls.length > 2) {
      setLocalError("At most 2 competitor URLs.");
      return;
    }
    onAnalyze({ url, brandName, companyName, aliases, llms, competitor_urls });
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="form-row">
        <label className="field">
          <span>URL</span>
          <input
            type="text"
            placeholder="https://www.example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <button className="btn" disabled={isLoading}>
          {isLoading ? "Analyzing..." : "Analyze AI Visibility"}
        </button>
      </div>
      <div className="form-row" style={{ marginTop: 10 }}>
        <label className="field">
          <span>Brand Name (optional override)</span>
          <input
            type="text"
            placeholder="HUGO BOSS"
            value={brandName}
            onChange={(e) => setBrandName(e.target.value)}
          />
        </label>
        <label className="field">
          <span>Company Name (optional override)</span>
          <input
            type="text"
            placeholder="HUGO BOSS AG"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
          />
        </label>
      </div>
      <div className="form-row" style={{ marginTop: 10 }}>
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
      <div className="form-row" style={{ marginTop: 10 }}>
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
      <div className="form-row" style={{ marginTop: 10 }}>
        <label className="field">
          <span>Aliases (comma-separated, optional)</span>
          <input
            type="text"
            placeholder="Boss, HugoBoss, H.B."
            value={aliasesRaw}
            onChange={(e) => setAliasesRaw(e.target.value)}
          />
        </label>
      </div>
      {localError ? <div className="error-box">{localError}</div> : null}
    </form>
  );
}
