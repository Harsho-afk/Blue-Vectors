import { useState } from "react";

export default function PostRow({ post, index, visible }) {
  const [expanded, setExpanded] = useState(false);

  const rawTs = post.timestamp;
  const ts = rawTs
    ? (() => {
        const d = typeof rawTs === "number"
          ? new Date(rawTs * 1000)
          : new Date(rawTs);
        return isNaN(d.getTime()) ? "—" : d.toISOString().replace("T", " ").slice(0, 16) + "Z";
      })()
    : "—";

  const type   = post.metadata?.type || "post";
  const sub    = post.metadata?.subreddit;
  const score  = post.metadata?.score;
  const rt     = post.metadata?.retweet_count;
  const fav    = post.metadata?.favorite_count;
  const url    = post.metadata?.url || "";
  const images = post.metadata?.images || [];

  const text = post.text || "—";
  const CLAMP = 3;
  // Rough line count — long enough to warrant a toggle
  const needsToggle = text.length > 180 || text.split("\n").length > CLAMP;

  return (
    <div className={`post-row${visible ? " post-row--visible" : ""}`}>
      <div className="post-row__meta">
        <span className="post-row__index">{String(index + 1).padStart(3, "0")}</span>
        <span className={`post-row__type post-row__type--${type}`}>
          {type.toUpperCase()}
        </span>
        {sub && <span className="post-row__subreddit">r/{sub}</span>}
        <span className="post-row__ts">{ts}</span>
        {url && (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="post-row__link"
            title="Open original"
          >
            ↗
          </a>
        )}
      </div>

      <p className={`post-row__text${expanded ? " post-row__text--expanded" : ""}`}>
        {text}
      </p>

      {needsToggle && (
        <button
          className="post-row__toggle"
          onClick={() => setExpanded(e => !e)}
        >
          {expanded ? "▲ collapse" : "▼ expand"}
        </button>
      )}

      {images.length > 0 && (
        <div className="post-row__images">
          {images.map((src, i) => (
            <a key={i} href={src} target="_blank" rel="noopener noreferrer">
              <img
                src={src}
                alt=""
                className="post-row__image"
                loading="lazy"
              />
            </a>
          ))}
        </div>
      )}

      {(score != null || rt != null) && (
        <div className="post-row__stats">
          {score != null && <span className="post-row__stat">▲ {score}</span>}
          {rt    != null && <span className="post-row__stat">⟳ {rt}</span>}
          {fav   != null && <span className="post-row__stat">♥ {fav}</span>}
        </div>
      )}
    </div>
  );
}
