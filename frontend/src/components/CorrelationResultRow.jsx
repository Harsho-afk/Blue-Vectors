import { useState } from "react";

export default function CorrelationResultRow({ result }) {
  const [expanded, setExpanded] = useState(false);

  const shap = result.shap_json || {};
  const band = shap.band || "Low";
  const confidence = shap.confidence_pct ?? result.confidence ?? 0;

  const bandColor =
    band === "High" ? "#4FFFB0" : band === "Medium" ? "#F6C90E" : "#FF4444";

  return (
    <div className="correlation-row">
      <div
        className="correlation-row__main"
        onClick={() => setExpanded((e) => !e)}
      >
        <div className="correlation-row__accounts">
          <span className="correlation-row__account">
            <span className="correlation-row__platform">
              {(result.a_platform || "").toUpperCase()}
            </span>
            <span className="correlation-row__username">
              {result.a_display_name || result.a_username}
            </span>
          </span>

          <span className="correlation-row__vs">&harr;</span>

          <span className="correlation-row__account">
            <span className="correlation-row__platform">
              {(result.b_platform || "").toUpperCase()}
            </span>
            <span className="correlation-row__username">
              {result.b_display_name || result.b_username}
            </span>
          </span>
        </div>

        <div className="correlation-row__score">
          <div className="correlation-row__bar-bg">
            <div
              className="correlation-row__bar-fill"
              style={{ width: `${confidence}%`, backgroundColor: bandColor }}
            />
          </div>
          <span
            className="correlation-row__pct"
            style={{ color: bandColor }}
          >
            {confidence}%
          </span>
          <span
            className="correlation-row__band"
            style={{
              color: bandColor,
              borderColor: bandColor + "40",
              background: bandColor + "15",
            }}
          >
            {band.toUpperCase()}
          </span>
        </div>

        <span className="correlation-row__chevron">
          {expanded ? "▼" : "▶"}
        </span>
      </div>

      {expanded && (
        <div className="correlation-row__evidence">
          <p className="correlation-row__evidence-title">SIGNAL BREAKDOWN</p>

          <SignalBar
            label="Username Match"
            score={shap.username_score}
          />
          <SignalBar
            label="Bio Similarity"
            score={shap.bio_score}
          />
          <SignalBar
            label="Temporal Pattern"
            score={shap.temporal_score}
          />

          {shap.notes && shap.notes.length > 0 && (
            <div className="evidence-notes">
              {shap.notes.map((note, i) => (
                <p key={i} className="evidence-notes__item">
                  {note}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SignalBar({ label, score }) {
  return (
    <div className="evidence-signal">
      <span className="evidence-signal__label">{label}</span>
      {score != null ? (
        <>
          <div className="evidence-signal__bar-bg">
            <div
              className="evidence-signal__bar-fill"
              style={{ width: `${score * 100}%` }}
            />
          </div>
          <span className="evidence-signal__value">
            {(score * 100).toFixed(0)}%
          </span>
        </>
      ) : (
        <span className="evidence-signal__na">unavailable</span>
      )}
    </div>
  );
}
