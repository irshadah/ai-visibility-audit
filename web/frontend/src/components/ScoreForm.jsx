import { useState } from "react";

const ALL_MODES = ["GEO", "AEO", "SEO"];

function isLikelyUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

export default function ScoreForm({ defaultModes, onAnalyze, isLoading }) {
  const [url, setUrl] = useState("");
  const [modes, setModes] = useState(defaultModes);
  const [localError, setLocalError] = useState("");

  function toggleMode(mode) {
    setModes((prev) => {
      if (prev.includes(mode)) return prev.filter((m) => m !== mode);
      return [...prev, mode];
    });
  }

  function handleSubmit(e) {
    e.preventDefault();
    if (!isLikelyUrl(url)) {
      setLocalError("Please enter a valid http(s) URL.");
      return;
    }
    if (modes.length === 0) {
      setLocalError("Select at least one assessment mode.");
      return;
    }
    setLocalError("");
    onAnalyze({ url, modes });
  }

  return (
    <form className="card" onSubmit={handleSubmit}>
      <div className="form-row">
        <label className="field">
          <span>URL</span>
          <input
            type="text"
            placeholder="https://www.example.com/product"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <button className="btn" disabled={isLoading}>
          {isLoading ? "Analyzing..." : "Analyze"}
        </button>
      </div>
      <div className="mode-row">
        {ALL_MODES.map((mode) => (
          <button
            type="button"
            key={mode}
            className={`mode-pill ${modes.includes(mode) ? "mode-pill--active" : ""}`}
            onClick={() => toggleMode(mode)}
          >
            {mode}
          </button>
        ))}
      </div>
      {localError ? <div className="error-box">{localError}</div> : null}
    </form>
  );
}
