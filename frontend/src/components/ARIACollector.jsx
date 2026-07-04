import { useState, useEffect, useRef } from "react";

import "../styles/aria.css";
import { useTypewriter } from "../lib/hooks";
import { generateMockProfile } from "../lib/mockData";

import Blink        from "./Blink";
import LogLine      from "./LogLine";
import ProfileCard  from "./ProfileCard";
import PostRow      from "./PostRow";

const STATUSES = ["idle", "collecting", "done", "error"];

export default function ARIACollector() {
  const [platform,     setPlatform]     = useState("reddit");
  const [username,     setUsername]     = useState("");
  const [limit,        setLimit]        = useState(50);
  const [status,       setStatus]       = useState("idle");
  const [logs,         setLogs]         = useState([]);
  const [profile,      setProfile]      = useState(null);
  const [visiblePosts, setVisiblePosts] = useState(0);
  const [filterType,   setFilterType]   = useState("all");

  const logsRef = useRef(null);
  const headline = useTypewriter("ARIA — LAYER 1: DATA COLLECTION", 28);

  const addLog = line => setLogs(p => [...p, line]);

  // Auto-scroll log
  useEffect(() => {
    if (logsRef.current)
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
  }, [logs]);

  // Animate posts in one-by-one
  useEffect(() => {
    if (!profile?.posts?.length) return;
    setVisiblePosts(0);
    const step = () => setVisiblePosts(p => {
      if (p < profile.posts.length) { setTimeout(step, 40); return p + 1; }
      return p;
    });
    setTimeout(step, 300);
  }, [profile]);

  const handleCollect = async () => {
    if (!username.trim()) return;
    setStatus("collecting");
    setProfile(null);
    setLogs([]);
    setVisiblePosts(0);

    const u = username.trim().replace(/^[@u/]+/, "");
    addLog(`[>] ARIA Layer 1 — initiating collection`);
    addLog(`[>] Platform : ${platform.toUpperCase()}`);
    addLog(`[>] Target   : ${u}`);
    addLog(`[>] Limit    : ${limit} posts`);
    addLog(`[>] Resolving user profile...`);

    try {
      const res = await fetch(
        `http://localhost:8000/collect/${platform}/${encodeURIComponent(u)}?limit=${limit}`,
        { credentials: 'include' }
      );
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(`HTTP ${res.status}: ${detail}`);
      }
      const data = await res.json();
      addLog(`[OK] Profile resolved — ${data.display_name}`);
      addLog(`[OK] Collected ${data.posts?.length ?? 0} posts${data.subreddits?.length ? ` from ${data.subreddits.length} communities` : ""}`);
      addLog(`[OK] Collection complete.`);
      setProfile(data);
      setStatus("done");
    } catch (e) {
      if (e instanceof TypeError && e.message.includes("fetch")) {
        addLog(`[ERR] Backend unreachable (is uvicorn running?)`);
        addLog(`[>]   Falling back to mock data...`);
        const mock = generateMockProfile(platform, u, limit);
        addLog(`[OK] Mock: ${mock.posts.length} posts loaded`);
        setProfile(mock);
        setStatus("done");
      } else {
        addLog(`[ERR] ${e.message}`);
        setStatus("error");
      }
    }
  };

  const postTypes = profile
    ? [...new Set(profile.posts.map(p => p.metadata?.type).filter(Boolean))]
    : [];

  const filteredPosts = profile?.posts?.filter(p =>
    filterType === "all" || p.metadata?.type === filterType
  ) ?? [];

  return (
    <div className="aria-app">

      {/* ── Top bar ── */}
      <header className="aria-topbar">
        <div className="aria-topbar__brand">
          <span className="aria-topbar__name">ARIA</span>
          <span className="aria-topbar__tagline">SOCMINT IDENTITY RESOLUTION</span>
        </div>
        <div className="aria-topbar__status">
          {STATUSES.map(s => (
            <span key={s} className={`status-badge${s === status ? " status-badge--active" : ""}`}>
              {s.toUpperCase()}
            </span>
          ))}
        </div>
      </header>

      <main className="aria-main">

        {/* ── Hero ── */}
        <div className="aria-hero">
          <h1 className="aria-hero__title">{headline}<Blink /></h1>
          <p className="aria-hero__sub">SEED ACCOUNT → RAW SCRAPED DATA → ACCOUNTPROFILE</p>
        </div>

        {/* ── Seed account input ── */}
        <div className="aria-card" style={{ marginBottom: 24 }}>
          <p className="aria-card__label">Seed Account</p>
          <div className="seed-row">

            <div className="platform-toggle">
              {["reddit", "twitter"].map(p => (
                <button
                  key={p}
                  onClick={() => setPlatform(p)}
                  className={`platform-btn${platform === p ? ` platform-btn--${p}` : ""}`}
                >
                  {p === "reddit" ? "r/ REDDIT" : "@ TWITTER"}
                </button>
              ))}
            </div>

            <div className="username-wrap">
              <span className="username-prefix">{platform === "reddit" ? "u/" : "@"}</span>
              <input
                className="username-input"
                value={username}
                onChange={e => setUsername(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleCollect()}
                placeholder="username"
              />
            </div>

            <div className="limit-wrap">
              <span className="limit-label">LIMIT</span>
              <select
                className="limit-select"
                value={limit}
                onChange={e => setLimit(Number(e.target.value))}
              >
                {[10, 25, 50, 100, 250, 500].map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <button
              className={`collect-btn${status === "collecting" ? " collect-btn--collecting" : ""}`}
              onClick={handleCollect}
              disabled={!username.trim() || status === "collecting"}
            >
              {status === "collecting" ? "COLLECTING..." : "COLLECT ▶"}
            </button>
          </div>
        </div>

        {/* ── Collection log ── */}
        {logs.length > 0 && (
          <div className="aria-log">
            <p className="aria-log__label">Collection Log</p>
            <div className="aria-log__body" ref={logsRef}>
              {logs.map((l, i) => <LogLine key={i} line={l} />)}
              {status === "collecting" && <Blink />}
            </div>
          </div>
        )}

        {/* ── Profile + posts ── */}
        {profile && (
          <>
            <ProfileCard profile={profile} />

            <div style={{ marginTop: 24 }}>
              <div className="post-feed__header">
                <span className="post-feed__title">POST FEED</span>
                <span className="post-feed__count">{filteredPosts.length} records</span>
                <div className="post-feed__filters">
                  {["all", ...postTypes].map(t => (
                    <button
                      key={t}
                      onClick={() => setFilterType(t)}
                      className={`filter-btn${filterType === t ? " filter-btn--active" : ""}`}
                    >
                      {t.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              {filteredPosts.map((post, i) => (
                <PostRow key={i} post={post} index={i} visible={i < visiblePosts} />
              ))}

              {filteredPosts.length === 0 && (
                <p className="no-records">NO RECORDS MATCH FILTER</p>
              )}
            </div>
          </>
        )}

        {/* ── Empty state ── */}
        {status === "idle" && !profile && (
          <div className="empty-state">
            <p className="empty-state__title">AWAITING SEED ACCOUNT</p>
            <p className="empty-state__sub">enter a username and press COLLECT</p>
          </div>
        )}

      </main>
    </div>
  );
}
