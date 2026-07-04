import { useState } from "react";
import { useNavigate } from "react-router-dom";

const API = "http://localhost:8000";

const EMPTY_ID = { identifier_type: "username", value: "", platform_hint: "" };

export default function NewCase() {
  const [title, setTitle] = useState("");
  const [identifiers, setIdentifiers] = useState([{ ...EMPTY_ID }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  const updateId = (i, field, val) => {
    setIdentifiers(prev => prev.map((row, j) => (j === i ? { ...row, [field]: val } : row)));
  };

  const addRow = () => setIdentifiers(prev => [...prev, { ...EMPTY_ID }]);

  const removeRow = (i) => {
    if (identifiers.length <= 1) return;
    setIdentifiers(prev => prev.filter((_, j) => j !== i));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;

    const cleaned = identifiers
      .filter(r => r.value.trim())
      .map(r => ({
        identifier_type: r.identifier_type,
        value: r.value.trim(),
        platform_hint: r.platform_hint || null,
      }));

    if (cleaned.length === 0) {
      setError("Add at least one identifier");
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch(`${API}/api/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ title: title.trim(), identifiers: cleaned }),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      const data = await res.json();
      navigate(`/cases/${data.case_id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="aria-main">
      <h1 className="dash-header__title" style={{ marginBottom: 24 }}>NEW INVESTIGATION</h1>

      <form className="aria-card" onSubmit={handleSubmit}>
        {error && <div className="aria-auth-error">{error}</div>}

        <div className="aria-form-group" style={{ marginBottom: 20 }}>
          <label className="aria-form-label">Case Title</label>
          <input
            className="aria-form-input"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="e.g. Cross-platform identity analysis — johndoe"
            required
            disabled={submitting}
          />
        </div>

        <div style={{ marginBottom: 20 }}>
          <label className="aria-form-label" style={{ marginBottom: 10, display: "block" }}>
            Seed Identifiers
          </label>

          {identifiers.map((row, i) => (
            <div key={i} className="id-row">
              <select
                className="id-row__select"
                value={row.identifier_type}
                onChange={e => updateId(i, "identifier_type", e.target.value)}
                disabled={submitting}
              >
                <option value="username">USERNAME</option>
                <option value="email">EMAIL</option>
                <option value="phone">PHONE</option>
                <option value="profile_url">PROFILE URL</option>
              </select>

              <input
                className="aria-form-input id-row__value"
                value={row.value}
                onChange={e => updateId(i, "value", e.target.value)}
                placeholder="value"
                disabled={submitting}
              />

              <select
                className="id-row__select id-row__platform"
                value={row.platform_hint}
                onChange={e => updateId(i, "platform_hint", e.target.value)}
                disabled={submitting}
              >
                <option value="">NO PLATFORM</option>
                <option value="reddit">REDDIT</option>
                <option value="twitter">TWITTER</option>
              </select>

              {identifiers.length > 1 && (
                <button
                  type="button"
                  className="id-row__remove"
                  onClick={() => removeRow(i)}
                  disabled={submitting}
                  title="Remove"
                >
                  x
                </button>
              )}
            </div>
          ))}

          <button
            type="button"
            className="id-row__add"
            onClick={addRow}
            disabled={submitting}
          >
            + ADD IDENTIFIER
          </button>
        </div>

        <button
          type="submit"
          className="aria-auth-button"
          disabled={submitting || !title.trim()}
        >
          {submitting ? "CREATING..." : "CREATE CASE"}
        </button>
      </form>
    </div>
  );
}
