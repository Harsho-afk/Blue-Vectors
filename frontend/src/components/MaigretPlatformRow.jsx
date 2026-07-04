import { useState } from "react";
import { API } from "../lib/api";

export default function MaigretPlatformRow({ platform, caseId, searchedUsername, onImported }) {
  const [isImporting, setIsImporting] = useState(false);
  const [isImported, setIsImported] = useState(false);
  const [error, setError] = useState(null);

  const parsed = platform.parsed_data || {};

  const handleImport = async () => {
    setIsImporting(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/cases/${caseId}/osint/import-account`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          platform: platform.platform.toLowerCase(),
          username: searchedUsername,
          url: platform.url,
          display_name: parsed.display_name || null,
          bio: parsed.bio || null,
          avatar_url: parsed.avatar_url || null,
          location: parsed.location || null,
        }),
      });
      if (!res.ok) {
        const detail = await res.json().then(d => d.detail).catch(() => res.statusText);
        throw new Error(detail);
      }
      setIsImported(true);
      onImported?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <div className="maigret-platform-row">
      <div className="maigret-platform-row__main">
        {parsed.avatar_url ? (
          <img
            src={parsed.avatar_url}
            className="maigret-platform-row__avatar"
            alt={platform.platform}
            onError={e => { e.target.style.display = "none"; }}
          />
        ) : (
          <div className="maigret-platform-row__avatar-fallback">
            {platform.platform[0].toUpperCase()}
          </div>
        )}

        <div className="maigret-platform-row__info">
          <div className="maigret-platform-row__name-row">
            <span className="maigret-platform-row__platform-name">
              {platform.platform}
            </span>
            {parsed.display_name && (
              <span className="maigret-platform-row__display-name">
                {parsed.display_name}
              </span>
            )}
          </div>

          {parsed.bio && (
            <p className="maigret-platform-row__bio">{parsed.bio}</p>
          )}

          <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 2 }}>
            {parsed.location && (
              <span className="maigret-platform-row__location">
                ◈ {parsed.location}
              </span>
            )}
            {parsed.followers != null && (
              <span className="maigret-platform-row__followers">
                {parsed.followers.toLocaleString()} followers
              </span>
            )}
          </div>

          {error && (
            <span style={{ fontSize: 10, color: "#FF4444", marginTop: 2 }}>{error}</span>
          )}
        </div>

        <div className="maigret-platform-row__actions">
          <a
            href={platform.url}
            target="_blank"
            rel="noopener noreferrer"
            className="maigret-platform-row__open-btn"
          >
            OPEN ↗
          </a>
          <button
            className={`maigret-platform-row__import-btn${isImported ? " maigret-platform-row__import-btn--done" : ""}`}
            disabled={isImporting || isImported}
            onClick={handleImport}
          >
            {isImported ? "IMPORTED ✓" : isImporting ? "IMPORTING..." : "IMPORT ▶"}
          </button>
        </div>
      </div>
    </div>
  );
}
