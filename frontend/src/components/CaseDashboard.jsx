import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";

const API = "http://localhost:8000";

export default function CaseDashboard() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    fetch(`${API}/api/cases`, { credentials: "include" })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => setCases(data.cases || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="aria-main">
        <div className="aria-loading">Initializing dashboard...</div>
      </div>
    );
  }

  const openCount = cases.filter(c => c.status === "open").length;
  const closedCount = cases.filter(c => c.status === "closed").length;

  return (
    <div className="aria-main">
      <div className="dash-header">
        <div>
          <h1 className="dash-header__title">Investigations</h1>
          {cases.length > 0 && (
            <div className="dash-header__stats">
              <span className="dash-stat dash-stat--open">{openCount} active</span>
              <span className="dash-stat__sep">/</span>
              <span className="dash-stat">{closedCount} closed</span>
            </div>
          )}
        </div>
        <button className="dash-header__new" onClick={() => navigate("/cases/new")}>
          + NEW CASE
        </button>
      </div>

      {error && <div className="aria-auth-error">{error}</div>}

      {cases.length === 0 && !error ? (
        <div className="empty-state">
          <div className="empty-state__icon">
            <span className="empty-state__crosshair" />
          </div>
          <p className="empty-state__title">No active investigations</p>
          <p className="empty-state__sub">Create a case, add seed identifiers, and start collecting</p>
        </div>
      ) : (
        <div className="case-list">
          {cases.map(c => (
            <div
              key={c.id}
              className={`case-row case-row--${c.status}`}
              onClick={() => navigate(`/cases/${c.id}`)}
            >
              <div className="case-row__top">
                <span className="case-row__title">{c.title}</span>
                <span className={`case-row__status case-row__status--${c.status}`}>
                  {c.status.toUpperCase()}
                </span>
              </div>
              <div className="case-row__bottom">
                <span className="case-row__id">CASE-{String(c.id).padStart(4, "0")}</span>
                <span className="case-row__date">
                  {new Date(c.created_at).toLocaleDateString("en-US", {
                    year: "numeric", month: "short", day: "numeric",
                  })}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
