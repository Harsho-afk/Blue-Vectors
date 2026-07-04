"""
ARIA — GitHub Collector

Uses GitHub's public REST API v3. No auth required for public profiles.
Rate limits:
  - Unauthenticated: 60 requests/hour per IP
  - Authenticated:   5,000 requests/hour (set GITHUB_TOKEN in .env)

What we collect per user:
  - Profile: name, bio, location, avatar, followers/following counts,
             account creation date, public repo count
  - Repos:   up to limit//2 most-recently-pushed public repos, each treated
             as a "post" (name + description + language + topics + star/fork)
  - Events:  up to 300 public events (push, issue, PR, comment, fork, star)
             — gives temporal signal for Layer 2 behavioral analysis
  - Followers list: logins only, stored in a single "network" post
  - Following list: logins only, stored in a single "network" post

AccountProfile mapping:
  platform          = "github"
  username          = login
  display_name      = name or login
  bio               = bio
  location          = location
  profile_image_url = avatar_url
  created_utc       = created_at (ISO → epoch)
  karma             = None
  follower_count    = followers  (count from profile)
  following_count   = following  (count from profile)
  posts             = repos + events + 2 network posts (sorted by timestamp desc)
  subreddits        = []  (unused for GitHub)

Post.metadata fields (GitHub-specific):
  type        : "repo" | "push" | "pr" | "issue" | "comment" |
                "fork" | "star" | "create" | "release" | "event" |
                "network"
  url         : link to the resource
  language    : primary language (repos only)
  topics      : list[str] (repos only)
  stars       : int (repos only)
  forks       : int (repos only)
  repo        : repo name the event belongs to (events only)
  event_type  : raw GitHub event type string (events only)
  logins      : list[str] (network posts only — follower/following usernames)
  direction   : "followers" | "following" (network posts only)
"""

import os
from datetime import datetime, timezone
from dotenv import load_dotenv
import httpx

from .models import AccountProfile, Post, log

load_dotenv()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
API_BASE     = "https://api.github.com"
TIMEOUT      = 12

# Max follower/following usernames to fetch (each page = 1 API call, 100 per page)
NETWORK_LIMIT = 100


def headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ARIA-SOCMINT/1.0",
    }
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def iso_to_epoch(iso: str) -> float:
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except Exception:
        return 0.0


def get(path: str, params: dict = None) -> dict | list:
    url = f"{API_BASE}{path}"
    r   = httpx.get(url, headers=headers(), params=params or {}, timeout=TIMEOUT)

    if r.status_code == 404:
        raise ValueError(f"GitHub: not found — {path}")
    if r.status_code == 403:
        reset = r.headers.get("X-RateLimit-Reset", "?")
        raise ValueError(
            f"GitHub: rate limit hit — resets at epoch {reset}. "
            "Set GITHUB_TOKEN in .env for 5000 req/hr."
        )
    if r.status_code != 200:
        raise ValueError(f"GitHub: HTTP {r.status_code} for {path}")

    return r.json()


def paginate(path: str, limit: int, params: dict = None) -> list:
    """Paginate a GitHub list endpoint, returning up to `limit` items."""
    items    = []
    page     = 1
    per_page = min(100, limit)

    while len(items) < limit:
        p = dict(params or {})
        p.update({"per_page": per_page, "page": page})
        batch = get(path, p)
        if not batch:
            break
        items.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    return items[:limit]


def fetch_logins(path: str, limit: int) -> list[str]:
    """
    Fetch a list of GitHub user objects from a paginated endpoint and
    return only their login names. Costs ceil(limit / 100) API calls.
    """
    raw = paginate(path, limit)
    return [u["login"] for u in raw if u.get("login")]


class GitHubCollector:
    """Collects public GitHub profile data via the REST API."""

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        username = username.lstrip("@").strip()
        log.info("GitHub: collecting @%s (limit=%d)", username, limit)

        # ── Profile ───────────────────────────────────────────────────────────
        user = get(f"/users/{username}")

        display_name    = user.get("name") or username
        bio             = user.get("bio") or ""
        location        = user.get("location") or ""
        avatar          = user.get("avatar_url") or ""
        created_utc     = iso_to_epoch(user.get("created_at", ""))
        follower_count  = user.get("followers")
        following_count = user.get("following")
        public_repos    = user.get("public_repos", 0)

        # ── Repos ─────────────────────────────────────────────────────────────
        repo_limit = max(1, limit // 2)
        raw_repos  = paginate(
            f"/users/{username}/repos",
            limit=repo_limit,
            params={"sort": "pushed", "direction": "desc", "type": "owner"},
        )

        repo_posts = []
        for r in raw_repos:
            pushed = iso_to_epoch(r.get("pushed_at") or r.get("created_at", ""))
            name   = r.get("name", "")
            desc   = r.get("description") or ""
            lang   = r.get("language") or ""
            stars  = r.get("stargazers_count", 0)
            forks  = r.get("forks_count", 0)
            topics = r.get("topics") or []
            url    = r.get("html_url", "")

            text_parts = [name]
            if desc:
                text_parts.append(desc)
            if lang:
                text_parts.append(f"Language: {lang}")
            if topics:
                text_parts.append("Topics: " + ", ".join(topics))

            repo_posts.append(Post(
                external_id=f"repo:{r.get('id', name)}",
                text=" — ".join(text_parts),
                timestamp=pushed,
                metadata={
                    "type": "repo",
                    "url": url,
                    "language": lang,
                    "topics": topics,
                    "stars": stars,
                    "forks": forks,
                    "images": [],
                },
            ))

        log.info("GitHub: @%s — %d repos", username, len(repo_posts))

        # ── Public events ──────────────────────────────────────────────────────
        event_limit = min(300, max(1, limit - len(repo_posts)))
        raw_events  = paginate(f"/users/{username}/events/public", limit=event_limit)

        event_posts = []
        for ev in raw_events:
            etype     = ev.get("type", "Event")
            created   = iso_to_epoch(ev.get("created_at", ""))
            payload   = ev.get("payload", {})
            repo_name = (ev.get("repo") or {}).get("name", "")
            url       = f"https://github.com/{repo_name}" if repo_name else ""

            text = summarise_event(etype, payload, repo_name)
            if not text:
                continue

            event_posts.append(Post(
                external_id=f"event:{ev.get('id', created)}",
                text=text,
                timestamp=created,
                metadata={
                    "type": simplify_event_type(etype),
                    "event_type": etype,
                    "url": url,
                    "repo": repo_name,
                    "images": [],
                },
            ))

        log.info("GitHub: @%s — %d events", username, len(event_posts))

        # ── Followers (logins only) ────────────────────────────────────────────
        # Cap at NETWORK_LIMIT usernames — each 100 costs 1 API call
        fetch_count = min(NETWORK_LIMIT, follower_count or 0)
        follower_logins: list[str] = []
        if fetch_count > 0:
            try:
                follower_logins = fetch_logins(
                    f"/users/{username}/followers", fetch_count
                )
                log.info(
                    "GitHub: @%s — %d/%d followers fetched",
                    username, len(follower_logins), follower_count,
                )
            except Exception as exc:
                log.warning("GitHub: followers fetch failed for @%s — %s", username, exc)

        # ── Following (logins only) ────────────────────────────────────────────
        fetch_count = min(NETWORK_LIMIT, following_count or 0)
        following_logins: list[str] = []
        if fetch_count > 0:
            try:
                following_logins = fetch_logins(
                    f"/users/{username}/following", fetch_count
                )
                log.info(
                    "GitHub: @%s — %d/%d following fetched",
                    username, len(following_logins), following_count,
                )
            except Exception as exc:
                log.warning("GitHub: following fetch failed for @%s — %s", username, exc)

        # Store network lists as synthetic posts so they persist in the DB
        # and are available to the Layer 2 correlation engine via posts metadata.
        # Timestamp = created_utc so they sort to the "oldest" position in the feed.
        network_posts = []

        if follower_logins:
            network_posts.append(Post(
                external_id=f"network:followers:{username}",
                text=f"Followed by {len(follower_logins)} accounts: "
                     + ", ".join(follower_logins),
                timestamp=created_utc or 0.0,
                metadata={
                    "type": "network",
                    "direction": "followers",
                    "logins": follower_logins,
                    "total_count": follower_count,
                    "fetched_count": len(follower_logins),
                    "url": f"https://github.com/{username}?tab=followers",
                    "images": [],
                },
            ))

        if following_logins:
            network_posts.append(Post(
                external_id=f"network:following:{username}",
                text=f"Following {len(following_logins)} accounts: "
                     + ", ".join(following_logins),
                timestamp=created_utc or 0.0,
                metadata={
                    "type": "network",
                    "direction": "following",
                    "logins": following_logins,
                    "total_count": following_count,
                    "fetched_count": len(following_logins),
                    "url": f"https://github.com/{username}?tab=following",
                    "images": [],
                },
            ))

        # ── Merge + sort ───────────────────────────────────────────────────────
        all_posts = repo_posts + event_posts + network_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)

        log.info(
            "GitHub ✓: @%s — %d total posts (repos=%d events=%d network=%d) "
            "followers=%s following=%s public_repos=%d",
            username,
            len(all_posts),
            len(repo_posts),
            len(event_posts),
            len(network_posts),
            follower_count,
            following_count,
            public_repos,
        )

        return AccountProfile(
            platform="github",
            username=username,
            display_name=display_name,
            bio=bio,
            location=location,
            profile_image_url=avatar,
            created_utc=created_utc,
            posts=all_posts,
            subreddits=[],
            karma=None,
            follower_count=follower_count,
            following_count=following_count,
        )


# ── Event helpers ──────────────────────────────────────────────────────────────

def simplify_event_type(etype: str) -> str:
    return {
        "PushEvent":                     "push",
        "PullRequestEvent":              "pr",
        "IssuesEvent":                   "issue",
        "IssueCommentEvent":             "comment",
        "PullRequestReviewCommentEvent": "comment",
        "CommitCommentEvent":            "comment",
        "ForkEvent":                     "fork",
        "WatchEvent":                    "star",
        "CreateEvent":                   "create",
        "DeleteEvent":                   "delete",
        "ReleaseEvent":                  "release",
        "GollumEvent":                   "wiki",
    }.get(etype, "event")


def summarise_event(etype: str, payload: dict, repo: str) -> str:
    """Return a short human-readable summary, or '' to skip the event."""

    if etype == "PushEvent":
        commits = payload.get("commits") or []
        if not commits:
            return ""
        msg    = commits[-1].get("message", "").split("\n")[0].strip()
        suffix = f" (+{len(commits)-1} more)" if len(commits) > 1 else ""
        return (
            f"Pushed to {repo}: {msg}{suffix}"
            if msg else
            f"Pushed {len(commits)} commit(s) to {repo}"
        )

    if etype == "PullRequestEvent":
        pr     = payload.get("pull_request", {})
        title  = pr.get("title", "")
        action = payload.get("action", "")
        return f"PR {action}: {title} [{repo}]" if title else ""

    if etype == "IssuesEvent":
        issue  = payload.get("issue", {})
        title  = issue.get("title", "")
        action = payload.get("action", "")
        return f"Issue {action}: {title} [{repo}]" if title else ""

    if etype in ("IssueCommentEvent", "PullRequestReviewCommentEvent", "CommitCommentEvent"):
        body = (payload.get("comment", {}).get("body") or "").strip().split("\n")[0][:200]
        return f"Commented on {repo}: {body}" if body else ""

    if etype == "ForkEvent":
        forkee = payload.get("forkee", {}).get("full_name", repo)
        return f"Forked {repo} → {forkee}"

    if etype == "WatchEvent":
        return f"Starred {repo}"

    if etype == "CreateEvent":
        ref_type = payload.get("ref_type", "")
        ref      = payload.get("ref") or ""
        desc     = payload.get("description") or ""
        base     = f"Created {ref_type} {ref} in {repo}".strip()
        return f"{base} — {desc}" if desc else base

    if etype == "ReleaseEvent":
        release = payload.get("release", {})
        tag     = release.get("tag_name", "") or release.get("name", "")
        return f"Released {tag} [{repo}]" if tag else ""

    return ""
