import { useMemo, useState } from "react";
import ScoreForm from "./components/ScoreForm";
import ResultsDashboard from "./components/ResultsDashboard";
import LoadingOverlay from "./components/LoadingOverlay";
import VisibilityForm from "./components/VisibilityForm";
import VisibilityDashboard from "./components/VisibilityDashboard";

const DEFAULT_MODES = ["SEO"];

export default function App() {
  const [view, setView] = useState("audit");
  const [useCache, setUseCache] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [visibilityResult, setVisibilityResult] = useState(null);
  const [lastVisibilityFormValues, setLastVisibilityFormValues] = useState(null);

  const modeOrder = useMemo(() => ["GEO", "AEO", "SEO"], []);

  async function handleAnalyze({ url, modes }) {
    const overallTimeoutMs = 240000;
    const startedAt = Date.now();
    let lastProgress = -1;
    let lastUpdateAt = Date.now();
    setIsLoading(true);
    setLoadingProgress(5);
    setLoadingStage("Queued");
    setError("");
    try {
      const startRes = await fetch("/api/score/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, modes, timeout_sec: 120 })
      });
      const startData = await startRes.json();
      if (!startRes.ok) {
        throw new Error(startData?.error || `Failed to start analysis (${startRes.status})`);
      }

      const jobId = startData?.job_id;
      if (!jobId) throw new Error("Backend did not return job_id.");

      let finalResult = null;
      while (Date.now() - startedAt < overallTimeoutMs) {
        await new Promise((r) => setTimeout(r, 1200));
        const statusRes = await fetch(`/api/score/status/${jobId}`);
        const statusData = await statusRes.json();
        if (!statusRes.ok) {
          throw new Error(statusData?.error || `Failed to read job status (${statusRes.status})`);
        }
        setLoadingProgress(Number(statusData.progress || 0));
        setLoadingStage(statusData.stage || "Processing...");
        if (Number(statusData.progress || 0) !== lastProgress) {
          lastProgress = Number(statusData.progress || 0);
          lastUpdateAt = Date.now();
        }
        if (Date.now() - lastUpdateAt > 120000) {
          throw new Error("Analysis appears stuck while fetching content. Please retry.");
        }

        if (statusData.state === "done") {
          finalResult = statusData.result;
          break;
        }
        if (statusData.state === "error") {
          throw new Error(statusData.error || "Analysis failed.");
        }
      }

      if (!finalResult) {
        throw new Error("Analysis timed out after 4 minutes. Please retry.");
      }

      setResult(finalResult);
    } catch (err) {
      setError(err.message || "Unexpected error.");
    } finally {
      setLoadingProgress(0);
      setLoadingStage("");
      setIsLoading(false);
    }
  }

  async function handleVisibilityAnalyze({
    url,
    country_code,
    brandName,
    companyName,
    aliases,
    llms,
    competitor_urls,
    query_text,
    category,
    use_cache
  }) {
    const overallTimeoutMs = 300000;
    const startedAt = Date.now();
    setIsLoading(true);
    setLoadingProgress(5);
    setLoadingStage("Queued");
    setError("");
    try {
      const startRes = await fetch("/api/visibility/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url,
          country_code: country_code || "",
          brand_name: brandName || "",
          company_name: companyName || "",
          aliases: aliases || [],
          llms: llms || ["gemini"],
          competitor_urls: competitor_urls || [],
          query_text: query_text || "",
          category: category || "generic",
          use_cache: use_cache || false
        })
      });

      const startContentType = startRes.headers.get("content-type") || "";
      const startIsJson = startContentType.includes("application/json");
      let startData = null;
      let startRawText = "";
      if (startIsJson) {
        startData = await startRes.json();
      } else {
        startRawText = await startRes.text();
      }

      if (!startRes.ok) {
        const backendMsg = startData?.error || startRawText?.trim();
        if (startRes.status === 429) {
          throw new Error(backendMsg || "Rate limit exceeded. Try again later.");
        }
        throw new Error(backendMsg || `Failed to start visibility scan (${startRes.status})`);
      }
      const jobId = startData?.job_id;
      if (!jobId) throw new Error("Backend did not return visibility job_id.");

      setLastVisibilityFormValues({
        url,
        country_code: country_code || "",
        brandName: brandName || "",
        companyName: companyName || "",
        aliases: aliases || [],
        llms: llms || ["gemini"],
        competitor_urls: competitor_urls || [],
        query_text: query_text || "",
        category: category || "generic"
      });

      let finalResult = null;
      while (Date.now() - startedAt < overallTimeoutMs) {
        await new Promise((r) => setTimeout(r, 1300));
        const statusRes = await fetch(`/api/visibility/status/${jobId}`);

        const statusContentType = statusRes.headers.get("content-type") || "";
        const statusIsJson = statusContentType.includes("application/json");
        let statusData = null;
        let statusRawText = "";
        if (statusIsJson) {
          statusData = await statusRes.json();
        } else {
          statusRawText = await statusRes.text();
        }

        if (!statusRes.ok) {
          throw new Error(statusData?.error || statusRawText?.trim() || `Failed to read visibility status (${statusRes.status})`);
        }
        setLoadingProgress(Number(statusData.progress || 0));
        setLoadingStage(statusData.stage || "Processing visibility...");
        if (statusData.state === "done") {
          finalResult = statusData.result;
          break;
        }
        if (statusData.state === "error") {
          throw new Error(statusData.error || "Visibility analysis failed.");
        }
      }
      if (!finalResult) {
        throw new Error("Visibility analysis timed out after 5 minutes. Please retry.");
      }
      setVisibilityResult(finalResult);
    } catch (err) {
      setError(err.message || "Unexpected error.");
    } finally {
      setLoadingProgress(0);
      setLoadingStage("");
      setIsLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="page-header">
        <div className="page-header-left">
          <h1>Agentic Readiness Audit</h1>
          <p>Analyze URLs for readiness and AI visibility quality.</p>
        </div>
        {view === "visibility" && (
          <div className="cache-toggle-wrap">
            <span className="cache-toggle-label">Cache</span>
            <button
              type="button"
              className={`cache-toggle-btn ${useCache ? "cache-toggle-btn--on" : ""}`}
              onClick={() => setUseCache((v) => !v)}
              title={useCache ? "Cache on – reusing stored responses" : "Cache off – calling LLM API"}
            >
              <span className="cache-toggle-off">Off</span>
              <span className="cache-toggle-on">On</span>
            </button>
          </div>
        )}
      </header>

      <div className="view-switcher">
        <button
          type="button"
          className={`tab-btn ${view === "audit" ? "active" : ""}`}
          onClick={() => setView("audit")}
        >
          Readiness Audit
        </button>
        <button
          type="button"
          className={`tab-btn ${view === "visibility" ? "active" : ""}`}
          onClick={() => setView("visibility")}
        >
          AI Visibility
        </button>
      </div>

      {view === "audit" ? (
        <ScoreForm defaultModes={DEFAULT_MODES} onAnalyze={handleAnalyze} isLoading={isLoading} />
      ) : (
        <VisibilityForm
          onAnalyze={handleVisibilityAnalyze}
          isLoading={isLoading}
          useCache={useCache}
          initialValues={lastVisibilityFormValues}
        />
      )}

      {error ? <div className="error-box">{error}</div> : null}

      <LoadingOverlay isLoading={isLoading} progress={loadingProgress} stage={loadingStage} />

      {view === "audit" && result ? <ResultsDashboard result={result} modeOrder={modeOrder} /> : null}
      {view === "visibility" && visibilityResult ? (
        <VisibilityDashboard
          result={visibilityResult}
          onSelectRunId={async (runId, isQueryRun) => {
            try {
              const path = isQueryRun
                ? `/api/visibility/query-runs/${runId}`
                : `/api/visibility/runs/${runId}`;
              const res = await fetch(path);
              const data = await res.json();
              if (res.ok) setVisibilityResult(data);
              else setError(data?.error || "Failed to load run");
            } catch (e) {
              setError(e.message || "Failed to load run");
            }
          }}
        />
      ) : null}
    </div>
  );
}
