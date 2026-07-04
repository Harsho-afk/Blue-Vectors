"""
ARIA — Layer 1: Data Collection

Reddit  : Redlib (public frontend scraping — no credentials needed)
Twitter : twikit (browser cookies — ct0 + auth_token from DevTools)

.env file:
    TWITTER_CT0=...
    TWITTER_AUTH_TOKEN=...

Install:
    pip install httpx beautifulsoup4 twikit psycopg2-binary python-dotenv
"""

import os
import re as _re
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup
from twikit import Client as TwikitClient
from twikit.errors import UserNotFound, UserUnavailable
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("aria.collector")


# ──────────────────────────────────────────────
# MONKEY PATCH 1: twikit ClientTransaction broken since March 2026
# Twitter changed ondemand.s.js structure — regex no longer matches.
# Remove this block once twikit publishes a fix.
# ──────────────────────────────────────────────
_tx_mod = __import__(
    'twikit.x_client_transaction.transaction',
    fromlist=['ClientTransaction']
)
_tx_mod.ON_DEMAND_FILE_REGEX = _re.compile(
    r',(\d+):["\']ondemand\.s["\']',
    flags=(_re.VERBOSE | _re.MULTILINE)
)
_tx_mod.ON_DEMAND_HASH_PATTERN = r',{}:"([0-9a-f]+)"'
# Ensure INDICES_REGEX is present — twikit 2.3+ may not define it at module level.
# Pattern: '"label",byteIndex' — group(2) is the byte index value.
if not hasattr(_tx_mod, "INDICES_REGEX"):
    _tx_mod.INDICES_REGEX = _re.compile(r'"(\d+)",(\d+)')


async def _patched_get_indices(self, home_page_response, session, headers):
    key_byte_indices = []
    response = self.validate_response(home_page_response) or self.home_page_response
    on_demand_file_index = _tx_mod.ON_DEMAND_FILE_REGEX.search(str(response)).group(1)
    regex = _re.compile(_tx_mod.ON_DEMAND_HASH_PATTERN.format(on_demand_file_index))
    filename = regex.search(str(response)).group(1)
    on_demand_file_url = (
        f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{filename}a.js"
    )
    on_demand_file_response = await session.request(
        method="GET", url=on_demand_file_url, headers=headers
    )
    key_byte_indices_match = _tx_mod.INDICES_REGEX.finditer(
        str(on_demand_file_response.text)
    )
    for item in key_byte_indices_match:
        key_byte_indices.append(item.group(2))
    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices")
    return int(key_byte_indices[0]), list(map(int, key_byte_indices[1:]))


_tx_mod.ClientTransaction.get_indices = _patched_get_indices
# END MONKEY PATCH 1


# ──────────────────────────────────────────────
# MONKEY PATCH 2: twikit User.__init__ crashes when bio has no URLs
# ──────────────────────────────────────────────
from twikit.user import User as _TwikitUser
_original_user_init = _TwikitUser.__init__


def _patched_user_init(self, client, data):
    # Ensure the entities/description/urls path always exists
    legacy = data.get('legacy', data)
    entities = legacy.setdefault('entities', {})
    description = entities.setdefault('description', {})
    description.setdefault('urls', [])
    # Twitter's API omits these fields for some accounts; twikit does a hard
    # dict lookup and crashes with KeyError if they're absent.
    legacy.setdefault('withheld_in_countries', [])
    legacy.setdefault('withheld_scope', None)
    _original_user_init(self, client, data)


_TwikitUser.__init__ = _patched_user_init
# END MONKEY PATCH 2


# ──────────────────────────────────────────────
# Data schemas
# ──────────────────────────────────────────────

@dataclass
class Post:
    text: str
    timestamp: float        # Unix epoch (UTC)
    metadata: dict = field(default_factory=dict)


@dataclass
class AccountProfile:
    platform: str           # "reddit" | "twitter"
    username: str
    display_name: str
    bio: str
    location: str
    profile_image_url: str
    created_utc: Optional[float]
    posts: list = field(default_factory=list)       # list[Post]
    subreddits: list = field(default_factory=list)  # Reddit only
    karma: Optional[int] = None                     # Reddit only
    follower_count: Optional[int] = None            # Twitter only
    following_count: Optional[int] = None           # Twitter only

    def to_dict(self) -> dict:
        """Serialize to a plain dict — safe for JSON and PostgreSQL JSONB."""
        return asdict(self)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _twitter_ts_to_epoch(ts_str: str) -> float:
    """
    Convert a Twitter timestamp string to a UTC Unix epoch float.
    Twitter format: 'Thu Apr 06 15:28:43 +0000 2017'
    """
    dt = datetime.strptime(ts_str, "%a %b %d %H:%M:%S %z %Y")
    return dt.timestamp()


# ──────────────────────────────────────────────
# Reddit collector  (Redlib — no credentials)
# ──────────────────────────────────────────────

class RedditCollector:
    """
    Collects public Reddit profile data by scraping Redlib instances.
    No API key, no credentials, no approval process.

    Tries each public Redlib instance in order until one responds.
    """

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
    }

    # Public Redlib instances — tries each until one works
    INSTANCES = [
        "https://redlib.catsarch.com",
        "https://redlib.perennialte.ch",
        "https://rl.bloat.cat",
        "https://redlib.privacyredirect.com",
        "https://redlib.seasi.dev",
    ]

    def _get(self, path: str) -> httpx.Response:
        """Try each Redlib instance until one returns 200."""
        last_exc = None
        for base in self.INSTANCES:
            try:
                r = httpx.get(
                    f"{base}{path}",
                    headers=self.HEADERS,
                    timeout=15,
                    follow_redirects=True,
                )
                if r.status_code == 200:
                    self._last_base = base
                    return r
                log.debug("Redlib %s returned %d for %s", base, r.status_code, path)
            except Exception as exc:
                log.debug("Redlib %s failed: %s", base, exc)
                last_exc = exc
        raise ValueError(
            f"All Redlib instances failed for {path}. Last error: {last_exc}"
        )

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        """
        Fetch public profile and posts for a Reddit user via Redlib.

        Args:
            username : Reddit username without the u/ prefix.
            limit    : Max submissions to fetch.

        Returns:
            AccountProfile

        Raises:
            ValueError: User not found or all instances unreachable.
        """
        log.info("Reddit: collecting u/%s via Redlib (limit=%d)", username, limit)

        # ── Profile ─────────────────────────────────────
        try:
            r = self._get(f"/user/{username}")
        except ValueError as exc:
            raise ValueError(f"Reddit user '{username}' not found or suspended.") from exc

        soup = BeautifulSoup(r.text, "html.parser")

        display_name = username
        bio = ""
        karma = None
        created_utc = None
        profile_image_url = ""

        name_el = soup.select_one("#user_title") or soup.select_one("#user > header h1")
        if name_el:
            # Redlib prefixes the title with "u/" — strip it
            display_name = name_el.text.strip().lstrip("u/").strip()

        # Bio / description
        bio_el = soup.select_one("#user_description") or soup.select_one("p.description")
        if bio_el:
            bio = bio_el.text.strip()

        # Karma and created — Redlib renders #user_details as a CSS grid:
        #   <label>Karma</label><label>Created</label>
        #   <div>939024</div><div>Jun 06 '05</div>
        # Labels and values are siblings; grab by index.
        details_el = soup.select_one("#user_details")
        if details_el:
            labels = [el.text.strip().lower() for el in details_el.select("label")]
            values = [el.text.strip() for el in details_el.select("div")]
            for i, label in enumerate(labels):
                if i >= len(values):
                    break
                if "karma" in label:
                    try:
                        karma = int(values[i].replace(",", "").replace(".", ""))
                    except Exception:
                        pass
                elif "created" in label:
                    # Format: "Jun 06 '05" — parse as "Jun 06 20YY"
                    try:
                        raw = values[i].strip().replace("'", "20")
                        created_utc = datetime.strptime(raw, "%b %d %Y").replace(
                            tzinfo=timezone.utc
                        ).timestamp()
                    except Exception:
                        pass

        # Profile image — Redlib serves a relative /style/... path; prepend instance base
        img_el = soup.select_one("#user_icon") or soup.select_one("#user img")
        if img_el:
            src = img_el.get("src", "")
            if src.startswith("http"):
                profile_image_url = src
            elif src.startswith("/"):
                profile_image_url = getattr(self, "_last_base", "") + src

        # ── Submissions ──────────────────────────────────
        posts: list = []
        subreddits: set = set()
        after = ""
        fetched = 0

        while fetched < limit:
            path = f"/user/{username}/submitted"
            if after:
                path += f"?after={after}"

            try:
                r = self._get(path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Reddit: page fetch failed — %s", exc)
                break

            items = soup.select(".post")
            if not items:
                break

            for item in items:
                if fetched >= limit:
                    break

                # Title — <h2 class="post_title"><a class="post_flair">...<a href>title</a>
                # The flair <a> comes first; we want the last <a> which is the actual post link.
                title_el = None
                title_links = item.select(".post_title a")
                if title_links:
                    title_el = title_links[-1]

                body_el  = item.select_one(".post_body")

                # Timestamp — <span class="created" title="Jun 03 2026, 15:11:07 UTC">
                created_el = item.select_one(".created")

                # Subreddit — <a class="post_subreddit" href="/r/...">r/name</a>
                sub_el = item.select_one(".post_subreddit")

                # Score — <div class="post_score" title="97">
                score_el = item.select_one(".post_score")

                text = ""
                url  = ""
                if title_el:
                    text = title_el.text.strip()
                    # href is a Redlib-relative path e.g. /r/sub/comments/id/slug/
                    raw_href = title_el.get("href", "")
                    if raw_href.startswith("/"):
                        url = "https://reddit.com" + raw_href
                if body_el:
                    body_text = body_el.text.strip()
                    if body_text:
                        text = (text + " " + body_text).strip()

                ts = 0.0
                if created_el and created_el.get("title"):
                    # Format: "Jun 03 2026, 15:11:07 UTC"
                    try:
                        ts = datetime.strptime(
                            created_el["title"], "%b %d %Y, %H:%M:%S UTC"
                        ).replace(tzinfo=timezone.utc).timestamp()
                    except Exception:
                        pass

                subreddit = ""
                if sub_el:
                    raw_sub = sub_el.text.strip()
                    # removeprefix is exact, unlike lstrip which strips individual chars
                    if raw_sub.startswith("r/"):
                        subreddit = raw_sub[2:]
                    # Skip u/ profile posts — not a real subreddit
                    if subreddit:
                        subreddits.add(subreddit)

                score = 0
                if score_el:
                    # title attribute holds the clean integer e.g. title="97"
                    try:
                        score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception:
                        try:
                            score = int(score_el.text.strip().replace(",", ""))
                        except Exception:
                            pass

                posts.append(Post(
                    text=text,
                    timestamp=ts,
                    metadata={
                        "type":      "submission",
                        "subreddit": subreddit,
                        "score":     score,
                        "url":       url,
                    },
                ))
                fetched += 1

            # Pagination — parse 'after' token robustly; href may have multiple params
            next_el = soup.select_one("a[rel='next']")
            if next_el:
                href = next_el.get("href", "")
                qs = parse_qs(urlparse(href).query)
                after = qs.get("after", [""])[0]
            else:
                break
            if not after:
                break

        # ── Comments ─────────────────────────────────────
        after = ""
        fetched = 0

        while fetched < limit:
            path = f"/user/{username}/comments"
            if after:
                path += f"?after={after}"

            try:
                r = self._get(path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Reddit: comments page fetch failed — %s", exc)
                break

            items = soup.select(".comment")
            if not items:
                break

            for item in items:
                if fetched >= limit:
                    break

                body_el    = item.select_one(".comment_body")
                created_el = item.select_one(".created")
                sub_el     = item.select_one(".comment_subreddit")
                score_el   = item.select_one(".comment_score")
                link_el    = item.select_one(".comment_link")

                raw_text = body_el.get_text(separator="\n").strip() if body_el else ""

                # Extract Redlib-proxied image URLs (/preview/pre/... lines)
                # and clean them out of the display text
                import re as _re2
                image_urls = []
                clean_lines = []
                for line in raw_text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("/preview/pre/") or stripped.startswith("/img/"):
                        base = getattr(self, "_last_base", "https://redlib.perennialte.ch")
                        image_urls.append(base + stripped)
                    else:
                        clean_lines.append(line)
                text = "\n".join(clean_lines).strip()

                # Permalink — .comment_link href is already a Redlib path
                url = ""
                if link_el:
                    raw_href = link_el.get("href", "")
                    if raw_href.startswith("/"):
                        url = "https://reddit.com" + raw_href.split("#")[0]

                ts = 0.0
                if created_el and created_el.get("title"):
                    try:
                        ts = datetime.strptime(
                            created_el["title"], "%b %d %Y, %H:%M:%S UTC"
                        ).replace(tzinfo=timezone.utc).timestamp()
                    except Exception:
                        pass

                subreddit = ""
                if sub_el:
                    raw_sub = sub_el.text.strip()
                    if raw_sub.startswith("r/"):
                        subreddit = raw_sub[2:]
                    if subreddit:
                        subreddits.add(subreddit)

                score = 0
                if score_el:
                    try:
                        score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception:
                        pass

                posts.append(Post(
                    text=text,
                    timestamp=ts,
                    metadata={
                        "type":      "comment",
                        "subreddit": subreddit,
                        "score":     score,
                        "url":       url,
                        "images":    image_urls,
                    },
                ))
                fetched += 1

            # Pagination — comments use <a>NEXT</a> with no rel attribute
            next_el = soup.find("a", string=lambda t: t and t.strip().upper() == "NEXT")
            if not next_el:
                break
            href = next_el.get("href", "")
            qs = parse_qs(urlparse(href).query)
            after = qs.get("after", [""])[0]
            if not after:
                break

        posts.sort(key=lambda p: p.timestamp, reverse=True)
        log.info("Reddit: u/%s — %d posts, %d subreddits", username, len(posts), len(subreddits))

        return AccountProfile(
            platform="reddit",
            username=username,
            display_name=display_name,
            bio=bio,
            location="",
            profile_image_url=profile_image_url,
            created_utc=created_utc,
            posts=posts,
            subreddits=sorted(s for s in subreddits if s),
            karma=karma,
        )


# ──────────────────────────────────────────────
# Twitter collector  (twikit — browser cookies)
# ──────────────────────────────────────────────

class TwitterCollector:
    """
    Collects public Twitter data using twikit with browser-extracted cookies.
    No login flow, no password — bypasses Cloudflare entirely.

    How to get cookies:
        1. Log into x.com in your browser
        2. DevTools (F12) → Application → Cookies → https://x.com
        3. Copy values for 'ct0' and 'auth_token'
        4. Add to .env:
               TWITTER_CT0=<value>
               TWITTER_AUTH_TOKEN=<value>

    Cookies expire after a few weeks — re-extract from browser when they do.
    """

    def __init__(self):
        self._client = TwikitClient(language="en-US")
        self._logged_in = False

    async def _ensure_login(self):
        """Load cookies from env vars — no login flow needed."""
        if self._logged_in:
            return

        ct0        = os.environ.get("TWITTER_CT0")
        auth_token = os.environ.get("TWITTER_AUTH_TOKEN")

        if not ct0 or not auth_token:
            raise RuntimeError(
                "Twitter cookies not set.\n"
                "Add TWITTER_CT0 and TWITTER_AUTH_TOKEN to your .env file.\n"
                "Extract them from DevTools → Application → Cookies → https://x.com"
            )

        self._client.set_cookies({"ct0": ct0, "auth_token": auth_token})
        self._logged_in = True
        log.info("Twitter: cookies loaded from env (ct0=...%s)", ct0[-6:])

    async def collect(self, username: str, limit: int = 100) -> AccountProfile:
        """
        Fetch public profile and recent tweets for a Twitter user.

        Args:
            username : Twitter handle with or without @.
            limit    : Max tweets to collect.

        Returns:
            AccountProfile

        Raises:
            ValueError: User not found or unavailable.
        """
        username = username.lstrip("@")
        log.info("Twitter: collecting @%s (limit=%d)", username, limit)

        await self._ensure_login()

        # ── Resolve user ─────────────────────────────────
        try:
            user = await self._client.get_user_by_screen_name(username)
        except (UserNotFound, UserUnavailable) as exc:
            raise ValueError(
                f"Twitter user '@{username}' not found or unavailable."
            ) from exc

        created_utc = _twitter_ts_to_epoch(user.created_at)

        # ── Timeline ─────────────────────────────────────
        posts: list = []
        page_size = min(40, limit)
        result = await self._client.get_user_tweets(
            user_id=user.id,
            tweet_type="Tweets",
            count=page_size,
        )

        while result:
            for tweet in result:
                # Skip retweets
                if tweet.text.startswith("RT @"):
                    continue
                ts = _twitter_ts_to_epoch(tweet.created_at)

                # Extract media (photos/videos) attached to the tweet
                images = []
                try:
                    media_list = getattr(tweet, "media", None) or []
                    for m in media_list:
                        # twikit media object: m.type ("photo"/"video"), m.media_url_https
                        media_url = getattr(m, "media_url_https", None) or getattr(m, "url", None)
                        if media_url:
                            images.append(media_url)
                except Exception:
                    pass

                permalink = f"https://x.com/{username}/status/{tweet.id}"

                posts.append(Post(
                    text=tweet.text,
                    timestamp=ts,
                    metadata={
                        "type":           "tweet",
                        "tweet_id":       str(tweet.id),
                        "url":            permalink,
                        "retweet_count":  tweet.retweet_count,
                        "favorite_count": tweet.favorite_count,
                        "reply_count":    tweet.reply_count,
                        "lang":           tweet.lang,
                        "images":         images,
                    },
                ))
            if len(posts) >= limit:
                break
            try:
                result = await result.next()
            except Exception:
                break

        posts = posts[:limit]
        posts.sort(key=lambda p: p.timestamp, reverse=True)
        log.info("Twitter: @%s — %d tweets collected", username, len(posts))

        return AccountProfile(
            platform="twitter",
            username=username,
            display_name=user.name,
            bio=user.description or "",
            location=user.location or "",
            # twikit returns _normal (48×48); replace with _400x400 for a usable size
            profile_image_url=(user.profile_image_url or "").replace("_normal", "_400x400"),
            created_utc=created_utc,
            posts=posts,
            follower_count=user.followers_count,
            following_count=user.following_count,
        )


# ──────────────────────────────────────────────
# Public entry-points
# ──────────────────────────────────────────────

SUPPORTED_PLATFORMS = ("reddit", "twitter")

_twitter_collector: Optional[TwitterCollector] = None


def collect(platform: str, username: str, limit: int = 100) -> AccountProfile:
    """
    Collect public data for one account. Synchronous wrapper.

    Args:
        platform : "reddit" or "twitter"
        username : account handle
        limit    : max posts / tweets to fetch (default 100)

    Returns:
        AccountProfile

    Raises:
        ValueError: unsupported platform, or user not found / suspended
    """
    platform = platform.lower().strip()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform '{platform}'. Choose from: {SUPPORTED_PLATFORMS}"
        )
    if platform == "reddit":
        return RedditCollector().collect(username, limit=limit)
    if platform == "twitter":
        return asyncio.run(_collect_twitter(username, limit))
    raise ValueError(f"Unhandled platform: {platform}")


async def collect_async(platform: str, username: str, limit: int = 100) -> AccountProfile:
    """
    Async version of collect(). Use inside FastAPI or other async contexts.

    Reddit collection is synchronous (httpx.get) and is offloaded to a thread
    via run_in_executor so it does not block the event loop.
    """
    platform = platform.lower().strip()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform '{platform}'. Choose from: {SUPPORTED_PLATFORMS}"
        )
    if platform == "reddit":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: RedditCollector().collect(username, limit=limit)
        )
    if platform == "twitter":
        return await _collect_twitter(username, limit)
    raise ValueError(f"Unhandled platform: {platform}")


async def _collect_twitter(username: str, limit: int) -> AccountProfile:
    global _twitter_collector
    if _twitter_collector is None:
        _twitter_collector = TwitterCollector()
    return await _twitter_collector.collect(username, limit=limit)


# ──────────────────────────────────────────────
# PostgreSQL storage helper
# ──────────────────────────────────────────────

def save_to_db(profile: AccountProfile, conn) -> int:
    """
    Upsert an AccountProfile into PostgreSQL.
    Run schema.sql first to create the required tables.

    Args:
        profile : AccountProfile returned by collect()
        conn    : open psycopg2 connection

    Returns:
        account_id of the inserted or updated row
    """
    cur = conn.cursor()

    created_at_dt = (
        datetime.fromtimestamp(profile.created_utc, tz=timezone.utc)
        if profile.created_utc is not None else None
    )

    cur.execute(
        """
        INSERT INTO accounts
            (platform, username, display_name, bio, location, created_at, profile_image_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (platform, username) DO UPDATE SET
            display_name      = EXCLUDED.display_name,
            bio               = EXCLUDED.bio,
            location          = EXCLUDED.location,
            profile_image_url = EXCLUDED.profile_image_url
        RETURNING id
        """,
        (
            profile.platform,
            profile.username,
            profile.display_name,
            profile.bio,
            profile.location,
            created_at_dt,
            profile.profile_image_url,
        ),
    )
    account_id: int = cur.fetchone()[0]

    for post in profile.posts:
        post_dt = datetime.fromtimestamp(post.timestamp, tz=timezone.utc)
        cur.execute(
            """
            INSERT INTO posts (account_id, text, timestamp, metadata)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (account_id, post.text, post_dt, json.dumps(post.metadata)),
        )

    conn.commit()
    log.info(
        "DB: saved account_id=%d (%s/%s)",
        account_id, profile.platform, profile.username,
    )
    return account_id


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ARIA Layer 1 — Data Collection")
    sub = parser.add_subparsers(dest="cmd")

    p_collect = sub.add_parser("collect", help="Collect an account")
    p_collect.add_argument("platform", choices=SUPPORTED_PLATFORMS)
    p_collect.add_argument("username")
    p_collect.add_argument("--limit", type=int, default=100)
    p_collect.add_argument("--out", help="Write JSON to this path")

    args = parser.parse_args()

    if args.cmd == "collect":
        profile = collect(args.platform, args.username, limit=args.limit)
        output  = json.dumps(profile.to_dict(), indent=2, ensure_ascii=False)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(output)
            print(f"Saved to {args.out}")
        else:
            print(output)

    else:
        parser.print_help()
