/**
 * NetworkPanel — shows GitHub followers / following username lists.
 *
 * Reads the two synthetic "network" posts stored by the GitHub collector
 * (type === "network", direction === "followers" | "following") and renders
 * them as searchable, compact username lists.
 *
 * Usage (inside CaseDetail, below ProfileCard for GitHub accounts):
 *
 *   import NetworkPanel from "./NetworkPanel";
 *   ...
 *   {acc.platform === "github" && (
 *     <NetworkPanel posts={posts} username={acc.username} />
 *   )}
 */

import { useState, useMemo } from "react";

export default function NetworkPanel({ posts, username }) {
  const [query, setQuery]         = useState("");
  const [activeTab, setActiveTab] = useState("followers");

  // Pull the two network posts out of the full posts list
  const followerPost = useMemo(
    () => posts.find(
      p => p.metadata?.type === "network" && p.metadata?.direction === "followers"
    ),
    [posts]
  );

  const followingPost = useMemo(
    () => posts.find(
      p => p.metadata?.type === "network" && p.metadata?.direction === "following"
    ),
    [posts]
  );

  if (!followerPost && !followingPost) return null;

  const activePost  = activeTab === "followers" ? followerPost : followingPost;
  const logins      = activePost?.metadata?.logins ?? [];
  const totalCount  = activePost?.metadata?.total_count ?? 0;
  const fetchedCount = activePost?.metadata?.fetched_count ?? 0;

  const filtered = query.trim()
    ? logins.filter(l => l.toLowerCase().includes(query.toLowerCase()))
    : logins;

  return (
    <div className="network-panel">
      <div className="network-panel__header">
        <span className="network-panel__title">NETWORK</span>

        <div className="network-panel__tabs">
          {followerPost && (
            <button
              className={`network-tab${activeTab === "followers" ? " network-tab--active" : ""}`}
              onClick={() => { setActiveTab("followers"); setQuery(""); }}
            >
              FOLLOWERS
              <span className="network-tab__count">
                {followerPost.metadata?.total_count ?? 0}
              </span>
            </button>
          )}
          {followingPost && (
            <button
              className={`network-tab${activeTab === "following" ? " network-tab--active" : ""}`}
              onClick={() => { setActiveTab("following"); setQuery(""); }}
            >
              FOLLOWING
              <span className="network-tab__count">
                {followingPost.metadata?.total_count ?? 0}
              </span>
            </button>
          )}
        </div>

        {logins.length > 0 && (
          <input
            className="network-panel__search"
            placeholder="filter..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        )}
      </div>

      {logins.length === 0 ? (
        <p className="network-panel__empty">No {activeTab} collected</p>
      ) : (
        <>
          <div className="network-panel__grid">
            {filtered.map(login => (
              <a
                key={login}
                href={`https://github.com/${login}`}
                target="_blank"
                rel="noopener noreferrer"
                className="network-login"
              >
                {login}
              </a>
            ))}
            {filtered.length === 0 && (
              <p className="network-panel__empty">No matches for "{query}"</p>
            )}
          </div>

          {fetchedCount < totalCount && (
            <p className="network-panel__truncation">
              Showing {fetchedCount} of {totalCount} — set GITHUB_TOKEN to raise the limit
            </p>
          )}
        </>
      )}
    </div>
  );
}
