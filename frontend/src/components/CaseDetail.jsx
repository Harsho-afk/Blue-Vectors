import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import ProfileCard from "./ProfileCard";
import PostRow from "./PostRow";
import { API } from "../lib/api";

const EMPTY_ID = { identifier_type: "username", value: "", platform_hint: "" };

export default function CaseDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [caseData, setCaseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [collecting, setCollecting] = useState({});

  // Add-identifier form state
  const [newIds, setNewIds] = useState([{ ...EMPTY_ID }]);
  const [addingIds, setAddingIds] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);

  // Per-account post visibility: { accountId: { filter, expanded } }
  const [postView, setPostView] = useState({});

  const fetchCase = () => {
    fetch(`${API}/api/cases/${id}`, { credentials: "include" })
      .then(r => {
        if (!r.ok) throw new Error(r.status === 404 ? "Case not found" : `HTTP ${r.status}`);
        return r.json();
      })
      .then(data => setCaseData(data))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchCase(); }, [id]);

  const handleCollect = async (identifier) => {
    if (identifier.identifier_type !== "username") return;
    const platform = identifier.platform_hint || "reddit";
    const key = identifier.id;
    setCollecting(prev => ({ ...prev, [key]: true }));
    setError(null);

    try {
      const res = await fetch(`${API}/api/cases/${id}/collect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ platform, username: identifier.value }),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      fetchCase();
    } catch (e) {
      setError(e.message);
    } finally {
      setCollecting(prev => ({ ...prev, [key]: false }));
    }
  };

  // ── Add identifiers ──
  const updateNewId = (i, field, val) => {
    setNewIds(prev => prev.map((row, j) => (j === i ? { ...row, [field]: val } : row)));
  };

  const handleAddIdentifiers = async () => {
    const cleaned = newIds
      .filter(r => r.value.trim())
      .map(r => ({
        identifier_type: r.identifier_type,
        value: r.value.trim(),
        platform_hint: r.platform_hint || null,
      }));
    if (cleaned.length === 0) return;

    setAddingIds(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/cases/${id}/identifiers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(cleaned),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      setNewIds([{ ...EMPTY_ID }]);
      setShowAddForm(false);
      fetchCase();
    } catch (e) {
      setError(e.message);
    } finally {
      setAddingIds(false);
    }
  };

  // ── Post filter helpers ──
  const getPostView = (accId) => postView[accId] || { filter: "all", expanded: false };

  const setFilter = (accId, filter) => {
    setPostView(prev => ({ ...prev, [accId]: { ...getPostView(accId), filter } }));
  };

  const toggleExpanded = (accId) => {
    setPostView(prev => ({
      ...prev,
      [accId]: { ...getPostView(accId), expanded: !getPostView(accId).expanded },
    }));
  };

  if (loading) {
    return <div className="aria-main"><div className="aria-loading">Loading case...</div></div>;
  }

  if (error && !caseData) {
    return (
      <div className="aria-main">
        <div className="aria-auth-error">{error}</div>
        <button className="back-link" onClick={() => navigate("/")}>BACK TO CASES</button>
      </div>
    );
  }

  const { case: c, identifiers, accounts } = caseData;

  return (
    <div className="aria-main">
      <button className="back-link" onClick={() => navigate("/")}>
        &larr; ALL CASES
      </button>

      {/* ── Case header ── */}
      <div className="case-header">
        <div className="case-header__top">
          <h1 className="case-header__title">{c.title}</h1>
          <span className={`case-row__status case-row__status--${c.status}`}>
            {c.status.toUpperCase()}
          </span>
        </div>
        <div className="case-header__meta">
          <span>CASE-{String(c.id).padStart(4, "0")}</span>
          <span>Created {new Date(c.created_at).toLocaleDateString("en-US", {
            year: "numeric", month: "short", day: "numeric",
          })}</span>
        </div>
      </div>

      {error && <div className="aria-auth-error" style={{ marginBottom: 16 }}>{error}</div>}

      {/* ── Seed identifiers ── */}
      <div className="aria-card">
        <div className="section-header">
          <p className="aria-card__label" style={{ marginBottom: 0 }}>SEED IDENTIFIERS</p>
          {!showAddForm && (
            <button className="id-row__add" onClick={() => setShowAddForm(true)}>
              + ADD IDENTIFIER
            </button>
          )}
        </div>

        {identifiers.length === 0 && !showAddForm ? (
          <p className="no-records">No identifiers</p>
        ) : (
          <div className="id-list">
            {identifiers.map(ident => (
              <div key={ident.id} className="id-list__row">
                <span className="id-list__type">{ident.identifier_type.toUpperCase()}</span>
                <span className="id-list__value">{ident.value}</span>
                {ident.platform_hint && (
                  <span className={`platform-badge platform-badge--${ident.platform_hint}`}>
                    {ident.platform_hint.toUpperCase()}
                  </span>
                )}
                {ident.identifier_type === "username" && (
                  <button
                    className={`collect-btn${collecting[ident.id] ? " collect-btn--collecting" : ""}`}
                    onClick={() => handleCollect(ident)}
                    disabled={collecting[ident.id]}
                  >
                    {collecting[ident.id] ? "COLLECTING..." : "COLLECT"}
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* ── Add identifier form (inline) ── */}
        {showAddForm && (
          <div className="add-id-form">
            {newIds.map((row, i) => (
              <div key={i} className="id-row">
                <select
                  className="id-row__select"
                  value={row.identifier_type}
                  onChange={e => updateNewId(i, "identifier_type", e.target.value)}
                  disabled={addingIds}
                >
                  <option value="username">USERNAME</option>
                  <option value="email">EMAIL</option>
                  <option value="phone">PHONE</option>
                  <option value="profile_url">PROFILE URL</option>
                </select>
                <input
                  className="aria-form-input id-row__value"
                  value={row.value}
                  onChange={e => updateNewId(i, "value", e.target.value)}
                  placeholder="value"
                  disabled={addingIds}
                />
                <select
                  className="id-row__select id-row__platform"
                  value={row.platform_hint}
                  onChange={e => updateNewId(i, "platform_hint", e.target.value)}
                  disabled={addingIds}
                >
                  <option value="">NO PLATFORM</option>
                  <option value="reddit">REDDIT</option>
                  <option value="twitter">TWITTER</option>
                </select>
                {newIds.length > 1 && (
                  <button
                    type="button"
                    className="id-row__remove"
                    onClick={() => setNewIds(prev => prev.filter((_, j) => j !== i))}
                    disabled={addingIds}
                  >
                    x
                  </button>
                )}
              </div>
            ))}
            <div className="add-id-form__actions">
              <button
                className="id-row__add"
                onClick={() => setNewIds(prev => [...prev, { ...EMPTY_ID }])}
                disabled={addingIds}
              >
                + MORE
              </button>
              <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
                <button
                  className="cancel-btn"
                  onClick={() => { setShowAddForm(false); setNewIds([{ ...EMPTY_ID }]); }}
                  disabled={addingIds}
                >
                  CANCEL
                </button>
                <button
                  className="collect-btn"
                  onClick={handleAddIdentifiers}
                  disabled={addingIds || newIds.every(r => !r.value.trim())}
                >
                  {addingIds ? "SAVING..." : "SAVE"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Collected accounts + posts ── */}
      {accounts.length > 0 && (
        <div style={{ marginTop: 24 }}>
          {accounts.map(acc => {
            const pv = getPostView(acc.id);
            const posts = acc.posts || [];
            const postTypes = [...new Set(posts.map(p => p.metadata?.type).filter(Boolean))];
            const filtered = posts.filter(p =>
              pv.filter === "all" || p.metadata?.type === pv.filter
            );
            const visiblePosts = pv.expanded ? filtered : filtered.slice(0, 5);

            return (
              <div key={acc.id} className="account-section">
                <ProfileCard
                  profile={{
                    platform: acc.platform,
                    username: acc.username,
                    display_name: acc.display_name || acc.username,
                    bio: acc.bio || "",
                    location: acc.location || "",
                    profile_image_url: acc.profile_image_url || "",
                    created_utc: acc.created_at ? new Date(acc.created_at).getTime() / 1000 : null,
                    karma: acc.karma,
                    follower_count: acc.follower_count,
                    following_count: acc.following_count,
                    posts: posts,
                    subreddits: [...new Set(
                      posts
                        .map(p => p.metadata?.subreddit)
                        .filter(Boolean)
                    )],
                  }}
                />

                {posts.length > 0 && (
                  <div className="aria-card" style={{ marginTop: 8 }}>
                    <div className="post-feed__header">
                      <span className="post-feed__title">
                        {acc.platform.toUpperCase()} ACTIVITY
                      </span>
                      <span className="post-feed__count">{filtered.length} records</span>
                      <div className="post-feed__filters">
                        {["all", ...postTypes].map(t => (
                          <button
                            key={t}
                            onClick={() => setFilter(acc.id, t)}
                            className={`filter-btn${pv.filter === t ? " filter-btn--active" : ""}`}
                          >
                            {t.toUpperCase()}
                          </button>
                        ))}
                      </div>
                    </div>

                    {visiblePosts.map((post, i) => (
                      <PostRow key={post.id || i} post={post} index={i} visible={true} />
                    ))}

                    {filtered.length === 0 && (
                      <p className="no-records">NO RECORDS MATCH FILTER</p>
                    )}

                    {filtered.length > 5 && (
                      <button
                        className="show-more-btn"
                        onClick={() => toggleExpanded(acc.id)}
                      >
                        {pv.expanded
                          ? "SHOW LESS"
                          : `SHOW ALL ${filtered.length} RECORDS`}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {accounts.length === 0 && (
        <div className="empty-state" style={{ marginTop: 24 }}>
          <p className="empty-state__title">NO ACCOUNTS COLLECTED</p>
          <p className="empty-state__sub">use the COLLECT button above to gather data</p>
        </div>
      )}
    </div>
  );
}
