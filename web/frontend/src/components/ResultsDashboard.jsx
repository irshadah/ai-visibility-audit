import { useEffect, useMemo, useState } from "react";
import CategoryTable from "./CategoryTable";
import PdfExportButton from "./PdfExportButton";

function scoreColor(score) {
  if (score == null) return "#6b7280";
  return score >= 50 ? "#0f766e" : "#b91c1c";
}

function scoreRingStyle(score) {
  const safe = score == null ? 0 : Math.max(0, Math.min(100, Number(score)));
  const filledColor = "#34d399";
  const restColor = "#fca5a5";
  return {
    background: `conic-gradient(${filledColor} ${safe * 3.6}deg, ${restColor} 0deg)`
  };
}

function byCategory(rationale) {
  const out = {};
  for (const row of rationale || []) {
    out[row.category] ||= [];
    out[row.category].push(row);
  }
  return out;
}

function recommendationMap(recommendations) {
  const map = {};
  for (const r of recommendations || []) {
    map[r.rule_id] = r.action;
  }
  return map;
}

function ModeReport({ mode, report, labels, fixHints }) {
  const product = report?.products?.[0];
  if (!product) return null;
  const categories = product.category_scores || {};
  const rationaleByCategory = byCategory(product.rationale || []);
  const recMap = recommendationMap(product.recommendations || []);

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>
        {labels.modeTitles[mode] || mode} - {product.overall_score ?? "N/A"} / 100
      </h3>
      {Object.entries(categories).map(([category, score]) => (
        <CategoryTable
          key={`${mode}-${category}`}
          category={category}
          score={score}
          rows={rationaleByCategory[category] || []}
          labels={labels}
          fixHints={fixHints}
          recommendationByRule={recMap}
        />
      ))}
    </div>
  );
}

export default function ResultsDashboard({ result, modeOrder }) {
  const assessments = result.assessments || {};
  const modeTitles = result.meta?.mode_titles || {};
  const categoryLabels = result.meta?.category_labels || {};
  const ruleLabels = result.meta?.rule_labels || {};
  const fixHints = result.meta?.fix_hints || {};

  const modes = useMemo(
    () => modeOrder.filter((m) => assessments[m]).concat(Object.keys(assessments).filter((m) => !modeOrder.includes(m))),
    [assessments, modeOrder]
  );
  const [activeMode, setActiveMode] = useState(modes[0]);
  useEffect(() => {
    setActiveMode(modes[0]);
  }, [result, modes]);

  const labels = { modeTitles, categoryLabels, ruleLabels };

  return (
    <section className="card">
      <div className="results-header">
        <h2 style={{ margin: 0 }}>Assessment Results</h2>
        <PdfExportButton targetId="pdf-report-root" />
      </div>

      <div className="summary-grid">
        {modes.map((mode) => {
          const score = assessments[mode]?.products?.[0]?.overall_score;
          return (
            <div className="summary-item" key={`summary-${mode}`}>
              <div className="muted">{modeTitles[mode] || mode}</div>
              <div className="score-circle" style={scoreRingStyle(score)}>
                <div className="score-circle-inner" style={{ color: scoreColor(score) }}>
                  <span className="score-value">{score ?? "N/A"}</span>
                  <span className="score-denominator">/100</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="tabs">
        {modes.map((mode) => (
          <button
            type="button"
            key={mode}
            className={`tab-btn ${activeMode === mode ? "active" : ""}`}
            onClick={() => setActiveMode(mode)}
          >
            {mode}
          </button>
        ))}
      </div>

      {activeMode ? (
        <ModeReport mode={activeMode} report={assessments[activeMode]} labels={labels} fixHints={fixHints} />
      ) : null}

      <div id="pdf-report-root" className="pdf-print-root">
        <div style={{ padding: 24 }}>
          <h1>Agentic Readiness Report</h1>
          {modes.map((mode) => (
            <div key={`pdf-${mode}`} style={{ marginBottom: 24 }}>
              <ModeReport mode={mode} report={assessments[mode]} labels={labels} fixHints={fixHints} />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
