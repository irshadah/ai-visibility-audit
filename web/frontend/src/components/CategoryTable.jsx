function statusFromRationale(item) {
  if (item.status === "not_applicable_missing_input" || item.normalized_score == null) {
    return "N/A";
  }
  if (item.normalized_score >= 1) return "PASS";
  if (item.normalized_score <= 0) return "FAIL";
  return "WARN";
}

function statusClass(status) {
  if (status === "PASS") return "badge pass";
  if (status === "WARN") return "badge warn";
  if (status === "FAIL") return "badge fail";
  return "badge na";
}

export default function CategoryTable({ category, score, rows, labels, fixHints, recommendationByRule }) {
  const isFeedNa =
    category === "feed_quality" && rows.length > 0 && rows.every((r) => r.status === "not_applicable_missing_input");
  if (isFeedNa) return null;

  return (
    <div className="card">
      <div className="category-header">
        <strong>{labels.categoryLabels[category] || category}</strong>
        <span className="category-score">{Number.isFinite(score) ? `${score.toFixed(2)} / 100` : "N/A"}</span>
      </div>
      <div className="progress category-progress">
        <span style={{ width: `${Math.max(0, Math.min(100, score || 0))}%` }} />
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Rule</th>
              <th>Rule Name</th>
              <th>Score %</th>
              <th>What to fix</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const status = statusFromRationale(row);
              const fix = recommendationByRule[row.rule_id] || fixHints[row.rule_id] || "-";
              const pct =
                row.normalized_score == null ? "N/A" : `${(Number(row.normalized_score) * 100).toFixed(1)}%`;
              return (
                <tr key={`${category}-${row.rule_id}`}>
                  <td>
                    <span className={statusClass(status)}>{status}</span>
                  </td>
                  <td>{row.rule_id}</td>
                  <td>{labels.ruleLabels[row.rule_id] || row.rule_id}</td>
                  <td>{pct}</td>
                  <td>{fix}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
