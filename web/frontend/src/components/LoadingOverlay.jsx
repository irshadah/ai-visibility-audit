export default function LoadingOverlay({ isLoading, progress = 0, stage = "Processing..." }) {
  if (!isLoading) return null;

  return (
    <section className="card loading-card" role="status" aria-live="polite" aria-busy="true">
      <div className="loading-title">Analyzing URL</div>
      <div className="loading-subtitle">
        <span className="loading-dot" />
        {stage || "Processing..."}
      </div>
      <div className="loading-progress-track" aria-hidden="true">
        <span className="loading-progress-bar" style={{ width: `${Math.max(4, Math.min(100, Number(progress) || 0))}%` }} />
      </div>
      <div className="muted loading-footnote">{Math.round(progress || 0)}% complete</div>
    </section>
  );
}
