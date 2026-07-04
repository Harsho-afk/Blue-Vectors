import { useState, useEffect, useRef } from "react";

const C = {
  bg:       "#0A0B0D",
  surface:  "#111318",
  surface2: "#161A22",
  border:   "#1E2229",
  border2:  "#2A3040",
  accent:   "#4FFFB0",
  accentDim:"#1A6644",
  text:     "#E2E8F0",
  muted:    "#4A5568",
  muted2:   "#6B7280",
  red:      "#FF4444",
  yellow:   "#F6C90E",
  blue:     "#5B8DEF",
  reddit:   "#FF4500",
  twitter:  "#1D9BF0",
};

const mono = "'JetBrains Mono', 'Fira Mono', 'Courier New', monospace";
const sans = "Inter, system-ui, sans-serif";

function useTypewriter(text, speed = 18) {
  const [displayed, setDisplayed] = useState("");
  useEffect(() => {
    setDisplayed("");
    if (!text) return;
    let i = 0;
    const iv = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) clearInterval(iv);
    }, speed);
    return () => clearInterval(iv);
  }, [text]);
  return displayed;
}

function Blink() {
  const [on, setOn] = useState(true);
  useEffect(() => {
    const iv = setInterval(() => setOn(p => !p), 530);
    return () => clearInterval(iv);
  }, []);
  return (
    <span style={{ color: C.accent, opacity: on ? 1 : 0, fontFamily: mono }}>█</span>
  );
}

function PlatformBadge({ platform }) {
  const color = platform === "reddit" ? C.reddit : C.twitter;
  const icon  = platform === "reddit" ? "r/" : "@";
  return (
    <span style={{
      fontFamily: mono, fontSize: 11, color, border: `1px solid ${color}33`,
      background: `${color}15`, borderRadius: 3, padding: "1px 6px", letterSpacing: 1,
    }}>
      {icon}{platform.toUpperCase()}
    </span>
  );
}

function StatPill({ label, value, color }) {
  return (
    <div style={{
      background: C.surface2, border: `1px solid ${C.border2}`,
      borderRadius: 4, padding: "8px 14px", display: "flex",
      flexDirection: "column", gap: 2, minWidth: 90,
    }}>
      <span style={{ fontFamily: mono, fontSize: 10, color: C.muted2, letterSpacing: 1, textTransform: "uppercase" }}>{label}</span>
      <span style={{ fontFamily: mono, fontSize: 18, fontWeight: 700, color: color || C.accent }}>{value ?? "—"}</span>
    </div>
  );
}

function PostRow({ post, index, visible }) {
  const ts = post.timestamp
    ? new Date(post.timestamp * 1000).toISOString().replace("T", " ").slice(0, 16) + "Z"
    : "—";
  const isComment = post.metadata?.type === "comment";
  const isTweet   = post.metadata?.type === "tweet";
  const sub       = post.metadata?.subreddit;
  const score     = post.metadata?.score;
  const rt        = post.metadata?.retweet_count;
  const fav       = post.metadata?.favorite_count;

  return (
    <div style={{
      opacity: visible ? 1 : 0,
      transform: visible ? "translateY(0)" : "translateY(6px)",
      transition: "opacity 0.25s ease, transform 0.25s ease",
      borderBottom: `1px solid ${C.border}`,
      padding: "10px 0",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 5 }}>
        <span style={{ fontFamily: mono, fontSize: 10, color: C.muted, minWidth: 26 }}>
          {String(index + 1).padStart(3, "0")}
        </span>
        <span style={{
          fontFamily: mono, fontSize: 10,
          color: isComment ? C.yellow : isTweet ? C.blue : C.accent,
          border: `1px solid ${isComment ? C.yellow : isTweet ? C.blue : C.accent}33`,
          background: `${isComment ? C.yellow : isTweet ? C.blue : C.accent}12`,
          borderRadius: 2, padding: "0 5px", letterSpacing: 0.5,
        }}>
          {post.metadata?.type?.toUpperCase() || "POST"}
        </span>
        {sub && (
          <span style={{ fontFamily: mono, fontSize: 10, color: C.muted2 }}>r/{sub}</span>
        )}
        <span style={{ fontFamily: mono, fontSize: 10, color: C.muted, marginLeft: "auto" }}>{ts}</span>
      </div>
      <p style={{
        fontFamily: mono, fontSize: 12, color: C.text, margin: "0 0 0 34px",
        lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word",
        display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
      }}>
        {post.text || "—"}
      </p>
      {(score != null || rt != null) && (
        <div style={{ display: "flex", gap: 12, marginTop: 5, marginLeft: 34 }}>
          {score != null && (
            <span style={{ fontFamily: mono, fontSize: 10, color: C.muted2 }}>▲ {score}</span>
          )}
          {rt != null && (
            <span style={{ fontFamily: mono, fontSize: 10, color: C.muted2 }}>⟳ {rt}</span>
          )}
          {fav != null && (
            <span style={{ fontFamily: mono, fontSize: 10, color: C.muted2 }}>♥ {fav}</span>
          )}
        </div>
      )}
    </div>
  );
}

function ProfileCard({ profile }) {
  const created = profile.created_utc
    ? new Date(profile.created_utc * 1000).toISOString().slice(0, 10)
    : null;

  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border2}`,
      borderRadius: 6, padding: "20px 20px 16px",
    }}>
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14, marginBottom: 16 }}>
        {profile.profile_image_url ? (
          <img
            src={profile.profile_image_url}
            alt=""
            style={{ width: 52, height: 52, borderRadius: "50%", border: `2px solid ${C.border2}`, objectFit: "cover", flexShrink: 0 }}
          />
        ) : (
          <div style={{
            width: 52, height: 52, borderRadius: "50%", background: C.surface2,
            border: `2px solid ${C.border2}`, display: "flex", alignItems: "center",
            justifyContent: "center", flexShrink: 0,
          }}>
            <span style={{ fontFamily: mono, fontSize: 18, color: C.accent }}>
              {(profile.display_name || profile.username || "?")[0].toUpperCase()}
            </span>
          </div>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontFamily: sans, fontWeight: 600, fontSize: 16, color: C.text }}>
              {profile.display_name || profile.username}
            </span>
            <PlatformBadge platform={profile.platform} />
          </div>
          <span style={{ fontFamily: mono, fontSize: 12, color: C.muted2 }}>
            u/{profile.username}
          </span>
          {profile.bio && (
            <p style={{
              fontFamily: sans, fontSize: 13, color: C.muted2,
              margin: "8px 0 0", lineHeight: 1.5,
              display: "-webkit-box", WebkitLineClamp: 3,
              WebkitBoxOrient: "vertical", overflow: "hidden",
            }}>
              {profile.bio}
            </p>
          )}
          {profile.location && (
            <p style={{ fontFamily: mono, fontSize: 11, color: C.muted, margin: "4px 0 0" }}>
              ◈ {profile.location}
            </p>
          )}
        </div>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {profile.karma != null && (
          <StatPill label="karma" value={profile.karma.toLocaleString()} />
        )}
        {profile.follower_count != null && (
          <StatPill label="followers" value={profile.follower_count.toLocaleString()} color={C.blue} />
        )}
        {profile.following_count != null && (
          <StatPill label="following" value={profile.following_count.toLocaleString()} color={C.muted2} />
        )}
        <StatPill label="posts" value={profile.posts?.length ?? 0} />
        {profile.subreddits?.length > 0 && (
          <StatPill label="subreddits" value={profile.subreddits.length} color={C.reddit} />
        )}
        {created && (
          <StatPill label="joined" value={created} color={C.muted2} />
        )}
      </div>

      {profile.subreddits?.length > 0 && (
        <div style={{ marginTop: 14, borderTop: `1px solid ${C.border}`, paddingTop: 12 }}>
          <p style={{ fontFamily: mono, fontSize: 10, color: C.muted, letterSpacing: 1, marginBottom: 6 }}>
            ACTIVE SUBREDDITS
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {profile.subreddits.slice(0, 20).map(s => (
              <span key={s} style={{
                fontFamily: mono, fontSize: 10, color: C.reddit,
                background: `${C.reddit}12`, border: `1px solid ${C.reddit}30`,
                borderRadius: 3, padding: "2px 7px",
              }}>
                r/{s}
              </span>
            ))}
            {profile.subreddits.length > 20 && (
              <span style={{ fontFamily: mono, fontSize: 10, color: C.muted }}>
                +{profile.subreddits.length - 20} more
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function LogLine({ line }) {
  const color = line.startsWith("[ERR]") ? C.red
    : line.startsWith("[OK]") ? C.accent
    : line.startsWith("[>]") ? C.yellow
    : C.muted2;
  return (
    <div style={{ fontFamily: mono, fontSize: 11, color, lineHeight: 1.7 }}>
      {line}
    </div>
  );
}

export default function ARIACollector() {
  const [platform, setPlatform] = useState("reddit");
  const [username, setUsername] = useState("");
  const [limit, setLimit] = useState(50);
  const [status, setStatus] = useState("idle");
  const [logs, setLogs] = useState([]);
  const [profile, setProfile] = useState(null);
  const [visiblePosts, setVisiblePosts] = useState(0);
  const [filterType, setFilterType] = useState("all");
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const logsRef  = useRef(null);
  const headline = useTypewriter("ARIA — LAYER 1: DATA COLLECTION", 28);

  const addLog = (line) => setLogs(p => [...p, line]);

  useEffect(() => {
    if (logsRef.current) {
      logsRef.current.scrollTop = logsRef.current.scrollHeight;
    }
  }, [logs]);

  useEffect(() => {
    if (!profile?.posts?.length) return;
    setVisiblePosts(0);
    const step = () => {
      setVisiblePosts(p => {
        if (p < profile.posts.length) {
          setTimeout(step, 40);
          return p + 1;
        }
        return p;
      });
    };
    setTimeout(step, 300);
  }, [profile]);

  const handleCollect = async () => {
    if (!username.trim()) return;
    setStatus("collecting");
    setProfile(null);
    setLogs([]);
    setError(null);
    setVisiblePosts(0);

    const u = username.trim().replace(/^[@u\/]+/, "");
    addLog(`[>] ARIA Layer 1 — initiating collection`);
    addLog(`[>] Platform : ${platform.toUpperCase()}`);
    addLog(`[>] Target   : ${u}`);
    addLog(`[>] Limit    : ${limit} posts`);
    addLog(`[>] Resolving user profile...`);

    try {
      await new Promise(r => setTimeout(r, 600));
      addLog(`[>] Profile resolved. Fetching posts...`);
      await new Promise(r => setTimeout(r, 800));
      addLog(`[>] Fetching comments/timeline...`);
      await new Promise(r => setTimeout(r, 600));

      const mockProfile = generateMockProfile(platform, u, limit);
      addLog(`[OK] Collected ${mockProfile.posts.length} posts from ${mockProfile.subreddits?.length || 0} communities`);
      addLog(`[OK] Profile saved. account_id=42`);
      setProfile(mockProfile);
      setStatus("done");
    } catch (e) {
      addLog(`[ERR] Collection failed: ${e.message}`);
      setError(e.message);
      setStatus("error");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleCollect();
  };

  const filteredPosts = profile?.posts?.filter(p => {
    if (filterType === "all") return true;
    return p.metadata?.type === filterType;
  }) ?? [];

  const postTypes = profile
    ? [...new Set(profile.posts.map(p => p.metadata?.type).filter(Boolean))]
    : [];

  return (
    <div style={{
      background: C.bg, minHeight: "100vh", fontFamily: sans,
      color: C.text, padding: "0 0 60px",
    }}>
      <div style={{
        borderBottom: `1px solid ${C.border}`,
        background: C.surface,
        padding: "14px 24px",
        display: "flex", alignItems: "center", gap: 16,
      }}>
        <div>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.accent, letterSpacing: 2 }}>
            ARIA
          </span>
          <span style={{ fontFamily: mono, fontSize: 11, color: C.muted, letterSpacing: 1, marginLeft: 8 }}>
            SOCMINT IDENTITY RESOLUTION
          </span>
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {["idle", "collecting", "done", "error"].map(s => (
            <span key={s} style={{
              fontFamily: mono, fontSize: 9, letterSpacing: 1,
              color: s === status ? C.accent : C.muted,
              opacity: s === status ? 1 : 0.3,
              padding: "2px 8px",
              border: `1px solid ${s === status ? C.accent : "transparent"}`,
              borderRadius: 2,
            }}>
              {s.toUpperCase()}
            </span>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 860, margin: "0 auto", padding: "32px 24px 0" }}>
        <div style={{ marginBottom: 32 }}>
          <h1 style={{
            fontFamily: mono, fontSize: 22, fontWeight: 700, color: C.accent,
            letterSpacing: 1, margin: 0, lineHeight: 1.2, minHeight: "1.4em",
          }}>
            {headline}<Blink />
          </h1>
          <p style={{ fontFamily: mono, fontSize: 12, color: C.muted2, margin: "6px 0 0", letterSpacing: 0.5 }}>
            SEED ACCOUNT → RAW SCRAPED DATA → ACCOUNTPROFILE
          </p>
        </div>

        <div style={{
          background: C.surface, border: `1px solid ${C.border2}`,
          borderRadius: 6, padding: "20px 20px 18px", marginBottom: 24,
        }}>
          <p style={{ fontFamily: mono, fontSize: 10, color: C.muted, letterSpacing: 1, margin: "0 0 14px" }}>
            SEED ACCOUNT
          </p>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <div style={{ display: "flex", gap: 0 }}>
              {["reddit", "twitter"].map(p => (
                <button
                  key={p}
                  onClick={() => setPlatform(p)}
                  style={{
                    fontFamily: mono, fontSize: 12, padding: "0 16px", height: 38,
                    background: platform === p ? (p === "reddit" ? `${C.reddit}22` : `${C.twitter}22`) : C.surface2,
                    color: platform === p ? (p === "reddit" ? C.reddit : C.twitter) : C.muted,
                    border: `1px solid ${platform === p ? (p === "reddit" ? C.reddit : C.twitter) : C.border2}`,
                    cursor: "pointer",
                    borderRadius: p === "reddit" ? "4px 0 0 4px" : "0 4px 4px 0",
                    letterSpacing: 0.5,
                    transition: "all 0.15s",
                  }}
                >
                  {p === "reddit" ? "r/ REDDIT" : "@ TWITTER"}
                </button>
              ))}
            </div>

            <div style={{ flex: 1, minWidth: 160, position: "relative" }}>
              <span style={{
                position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)",
                fontFamily: mono, fontSize: 13, color: C.muted,
                pointerEvents: "none",
              }}>
                {platform === "reddit" ? "u/" : "@"}
              </span>
              <input
                ref={inputRef}
                value={username}
                onChange={e => setUsername(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="username"
                style={{
                  width: "100%", height: 38, background: C.surface2,
                  border: `1px solid ${C.border2}`, borderRadius: 4,
                  fontFamily: mono, fontSize: 13, color: C.text,
                  padding: "0 12px 0 30px", outline: "none", boxSizing: "border-box",
                }}
              />
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: C.muted, whiteSpace: "nowrap" }}>LIMIT</span>
              <select
                value={limit}
                onChange={e => setLimit(Number(e.target.value))}
                style={{
                  height: 38, background: C.surface2, border: `1px solid ${C.border2}`,
                  borderRadius: 4, fontFamily: mono, fontSize: 12, color: C.text,
                  padding: "0 8px", outline: "none",
                }}
              >
                {[10, 25, 50, 100].map(n => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <button
              onClick={handleCollect}
              disabled={!username.trim() || status === "collecting"}
              style={{
                height: 38, padding: "0 20px",
                background: status === "collecting" ? C.accentDim : C.accent,
                color: "#0A0B0D", fontFamily: mono, fontSize: 12, fontWeight: 700,
                border: "none", borderRadius: 4, cursor: status === "collecting" ? "wait" : "pointer",
                letterSpacing: 1, transition: "background 0.2s",
                opacity: !username.trim() ? 0.5 : 1,
              }}
            >
              {status === "collecting" ? "COLLECTING..." : "COLLECT ▶"}
            </button>
          </div>
        </div>

        {logs.length > 0 && (
          <div style={{
            background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: 6, padding: "14px 16px", marginBottom: 24,
          }}>
            <p style={{ fontFamily: mono, fontSize: 10, color: C.muted, letterSpacing: 1, margin: "0 0 10px" }}>
              COLLECTION LOG
            </p>
            <div ref={logsRef} style={{ maxHeight: 140, overflowY: "auto" }}>
              {logs.map((l, i) => <LogLine key={i} line={l} />)}
              {status === "collecting" && <Blink />}
            </div>
          </div>
        )}

        {profile && (
          <>
            <ProfileCard profile={profile} />

            <div style={{ marginTop: 24 }}>
              <div style={{
                display: "flex", alignItems: "center", gap: 12,
                marginBottom: 14, paddingBottom: 10, borderBottom: `1px solid ${C.border}`,
              }}>
                <span style={{ fontFamily: mono, fontSize: 10, color: C.muted, letterSpacing: 1 }}>
                  POST FEED
                </span>
                <span style={{ fontFamily: mono, fontSize: 10, color: C.accent }}>
                  {filteredPosts.length} records
                </span>
                <div style={{ marginLeft: "auto", display: "flex", gap: 4 }}>
                  {["all", ...postTypes].map(t => (
                    <button
                      key={t}
                      onClick={() => setFilterType(t)}
                      style={{
                        fontFamily: mono, fontSize: 10, padding: "3px 10px",
                        background: filterType === t ? `${C.accent}22` : "transparent",
                        color: filterType === t ? C.accent : C.muted,
                        border: `1px solid ${filterType === t ? C.accent : C.border2}`,
                        borderRadius: 3, cursor: "pointer", letterSpacing: 0.5,
                      }}
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
                <p style={{ fontFamily: mono, fontSize: 12, color: C.muted, textAlign: "center", padding: "40px 0" }}>
                  NO RECORDS MATCH FILTER
                </p>
              )}
            </div>
          </>
        )}

        {status === "idle" && !profile && (
          <div style={{
            textAlign: "center", padding: "60px 0",
            borderTop: `1px solid ${C.border}`,
          }}>
            <p style={{ fontFamily: mono, fontSize: 11, color: C.muted, letterSpacing: 2 }}>
              AWAITING SEED ACCOUNT
            </p>
            <p style={{ fontFamily: mono, fontSize: 10, color: `${C.muted}88`, marginTop: 8 }}>
              enter a username and press COLLECT
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function generateMockProfile(platform, username, limit) {
  const now = Date.now() / 1000;
  const subs = ["programming", "technology", "MachineLearning", "Python", "webdev", "datascience", "cscareerquestions"];
  const posts = [];

  const sampleReddit = [
    "Just published a write-up on using graph neural networks for cross-platform identity resolution. Would love feedback from anyone working in OSINT or social network analysis.",
    "Anyone else find that stylometric features are more stable across platforms than username similarity? Testing this hypothesis now.",
    "Hot take: most identity resolution papers ignore the temporal dimension entirely. Posting cadence tells you more than vocabulary.",
    "Finally got PRAW auto-throttling working correctly. The key is not fighting it — just let it sleep when it needs to.",
    "Built a small CLI tool for bulk Reddit profile collection. Runs at ~3 users/minute without hitting rate limits.",
    "Question: is it ethical to build identity linkage systems for research purposes if the data is fully public?",
    "The PAN 2020 dataset is surprisingly underutilized for authorship verification tasks. Highly recommend it.",
    "Comparing BERT-tiny vs LSTM for stylometric feature extraction. BERT wins on accuracy, LSTM wins on inference speed.",
    "Posted in r/MachineLearning but it got buried — has anyone tried combining SHAP with GNN node embeddings for explainability?",
    "Good paper: 'StyleLink: Cross-Platform Identity Resolution via Stylometric Graph Alignment' (ICWSM 2025). Closest prior work to what we're building.",
  ];

  const sampleTwitter = [
    "Working on a new approach to cross-platform identity resolution — combining stylometry + GNN + SHAP. Thread incoming.",
    "Fascinating how much temporal patterns reveal about authorship. People are creatures of habit, even online.",
    "New paper dropped on authorship verification. Reading it now — the contrastive loss approach is interesting.",
    "Hot take: username similarity is the weakest signal for identity linkage. Change my mind.",
    "Just open-sourced our ARIA data collection layer. Reddit + Twitter, fully async, PostgreSQL backed.",
    "The OSINT community needs better tooling for ethical research. Building something about this.",
    "Running ablation experiments on our fusion model. Graph features matter more than expected.",
    "Anyone else using twikit for Twitter data collection? Curious about stability at scale.",
    "SHAP values for identity resolution explainability — actually pretty readable output. Investigators seem to like it.",
    "Hackathon deadline in 3 weeks. The grind is real. Also the GNN training on Colab keeps timing out.",
  ];

  const samples = platform === "reddit" ? sampleReddit : sampleTwitter;

  for (let i = 0; i < Math.min(limit, samples.length * 2); i++) {
    const isComment = platform === "reddit" && i % 3 === 2;
    const sub = subs[Math.floor(Math.random() * subs.length)];
    posts.push({
      text: samples[i % samples.length],
      timestamp: now - i * 3600 * (6 + Math.random() * 18),
      metadata: platform === "reddit"
        ? {
            type: isComment ? "comment" : "submission",
            subreddit: sub,
            score: Math.floor(Math.random() * 400) + 1,
            url: `https://reddit.com/r/${sub}/comments/abc${i}`,
          }
        : {
            type: "tweet",
            tweet_id: String(1800000000000000000n + BigInt(i)),
            retweet_count: Math.floor(Math.random() * 40),
            favorite_count: Math.floor(Math.random() * 200),
            reply_count: Math.floor(Math.random() * 20),
            lang: "en",
          },
    });
  }

  posts.sort((a, b) => b.timestamp - a.timestamp);

  const usedSubs = [...new Set(
    posts.filter(p => p.metadata?.subreddit).map(p => p.metadata.subreddit)
  )];

  return {
    platform,
    username,
    display_name: username.charAt(0).toUpperCase() + username.slice(1),
    bio: platform === "reddit"
      ? "Researcher @ PES University. Building ARIA — cross-platform identity resolution. ML + graphs + XAI."
      : "SOCMINT researcher. Building tools for ethical identity resolution. GNN + stylometry + SHAP.",
    location: platform === "twitter" ? "Bangalore, India" : "",
    profile_image_url: "",
    created_utc: now - 365 * 24 * 3600 * (2 + Math.random() * 4),
    posts,
    subreddits: platform === "reddit" ? usedSubs.sort() : [],
    karma: platform === "reddit" ? Math.floor(Math.random() * 8000) + 500 : null,
    follower_count: platform === "twitter" ? Math.floor(Math.random() * 2000) + 100 : null,
    following_count: platform === "twitter" ? Math.floor(Math.random() * 800) + 50 : null,
  };
}
