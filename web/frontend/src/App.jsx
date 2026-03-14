import { useMemo, useState } from "react";
import ScoreForm from "./components/ScoreForm";
import ResultsDashboard from "./components/ResultsDashboard";
import LoadingOverlay from "./components/LoadingOverlay";
import VisibilityForm from "./components/VisibilityForm";
import VisibilityDashboard from "./components/VisibilityDashboard";

const DEFAULT_MODES = ["SEO"];

export default function App() {
  const [view, setView] = useState("audit");
  const [isLoading, setIsLoading] = useState(false);
  const [loadingProgress, setLoadingProgress] = useState(0);
  const [loadingStage, setLoadingStage] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [visibilityResult, setVisibilityResult] = useState(null);

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

  async function handleVisibilityAnalyze({ url, brandName, companyName, aliases, llms, competitor_urls }) {
    const overallTimeoutMs = 150000;
    const startedAt = Date.now();
    let lastProgress = -1;
    let lastUpdateAt = Date.now();
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
          brand_name: brandName || "",
          company_name: companyName || "",
          aliases: aliases || [],
          llms: llms || ["gemini"],
          competitor_urls: competitor_urls || []
        })
      });
      const startData = await startRes.json();
      if (!startRes.ok) {
        if (startRes.status === 429) {
          throw new Error(startData?.error || "Rate limit exceeded. Try again later.");
        }
        throw new Error(startData?.error || `Failed to start visibility scan (${startRes.status})`);
      }
      const jobId = startData?.job_id;
      if (!jobId) throw new Error("Backend did not return visibility job_id.");

      let finalResult = null;
      while (Date.now() - startedAt < overallTimeoutMs) {
        await new Promise((r) => setTimeout(r, 1300));
        const statusRes = await fetch(`/api/visibility/status/${jobId}`);
        const statusData = await statusRes.json();
        if (!statusRes.ok) {
          throw new Error(statusData?.error || `Failed to read visibility status (${statusRes.status})`);
        }
        setLoadingProgress(Number(statusData.progress || 0));
        setLoadingStage(statusData.stage || "Processing visibility...");
        if (Number(statusData.progress || 0) !== lastProgress) {
          lastProgress = Number(statusData.progress || 0);
          lastUpdateAt = Date.now();
        }
        if (Date.now() - lastUpdateAt > 80000) {
          throw new Error("Visibility analysis appears stuck. Please retry.");
        }
        if (statusData.state === "done") {
          finalResult = statusData.result;
          break;
        }
        if (statusData.state === "error") {
          throw new Error(statusData.error || "Visibility analysis failed.");
        }
      }
      if (!finalResult) {
        throw new Error("Visibility analysis timed out after 150s. Please retry.");
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
        <h1>Agentic Readiness Audit</h1>
        <p>Analyze URLs for readiness and AI visibility quality.</p>
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
        <VisibilityForm onAnalyze={handleVisibilityAnalyze} isLoading={isLoading} />
      )}

      {error ? <div className="error-box">{error}</div> : null}

      <LoadingOverlay isLoading={isLoading} progress={loadingProgress} stage={loadingStage} />

      {view === "audit" && result ? <ResultsDashboard result={result} modeOrder={modeOrder} /> : null}
      {view === "visibility" && visibilityResult ? (
        <VisibilityDashboard
          result={visibilityResult}
          onSelectRunId={async (runId) => {
            try {
              const res = await fetch(`/api/visibility/runs/${runId}`);
              const data = await res.json();
              if (res.ok) setVisibilityResult(data);
              else setError(data?.error || "Failed to load run");
            } catch (e) {
              setError(e.message || "Failed to load run");
            }
          }}
        />
      ) : null}

      <footer className="app-footer">Powered by Agentic Readiness Engine</footer>
    </div>
  );
}
