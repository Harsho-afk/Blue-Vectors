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

_IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
_IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "i.imgur.com", "imgur.com")


def _extract_image_urls(md_el) -> list:
    """
    Extract image URLs from an old.reddit.com .md element.
    Also removes the image link tags from the DOM so get_text() stays clean.
    """
    if not md_el:
        return []
    urls = []
    to_remove = []
    for a in md_el.select("a"):
        href = a.get("href", "")
        if not href:
            continue
        is_image_ext = any(href.split("?")[0].lower().endswith(ext) for ext in _IMAGE_EXTENSIONS)
        is_image_host = any(host in href for host in _IMAGE_HOSTS)
        if is_image_ext or is_image_host:
            if not href.startswith("http"):
                href = "https:" + href if href.startswith("//") else "https://" + href
            urls.append(href)
            to_remove.append(a)
    for a in to_remove:
        a.decompose()
    return urls


def _get_thumbnail(thing_el) -> str:
    """Extract thumbnail URL from an old.reddit.com .thing element."""
    img = thing_el.select_one("a.thumbnail img")
    if not img:
        return ""
    src = img.get("src", "")
    if src and not src.startswith("http"):
        src = "https:" + src if src.startswith("//") else ""
    return src


_REDLIB_INSTANCES = [
    "https://redlib.privacyredirect.com",
    "https://redlib.lunar.icu",
    "https://redlib.catsarch.com",
    "https://redlib.perennialte.ch",
    "https://rl.bloat.cat",
    "https://redlib.seasi.dev",
    "https://safereddit.com",
    "https://redlib.freedit.eu",
    "https://redlib.tux.pizza",
    "https://redlib.nadeko.net",
    "https://redlib.r4fo.com",
    "https://redlib.private.coffee",
    "https://redlib.ducks.party",
]

_REDLIB_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


def _fetch_reddit_avatar(username: str) -> str:
    """
    Fetch Reddit profile image. Tries three strategies in order:
    1. Reddit OAuth API (if REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are set)
    2. Redlib instances (scrape the avatar from any that respond)
    3. Give up — return empty string (frontend shows letter fallback)
    """
    # ── Strategy 1: Reddit OAuth ──
    client_id = os.environ.get("REDDIT_CLIENT_ID", "")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET", "")
    if client_id and client_secret:
        try:
            token_r = httpx.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": "ARIA-OSINT/1.0"},
                timeout=10,
            )
            if token_r.status_code == 200:
                access_token = token_r.json().get("access_token", "")
                if access_token:
                    api_r = httpx.get(
                        f"https://oauth.reddit.com/user/{username}/about",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "User-Agent": "ARIA-OSINT/1.0",
                        },
                        timeout=10,
                    )
                    if api_r.status_code == 200:
                        data = api_r.json().get("data", {})
                        avatar = data.get("snoovatar_img") or data.get("icon_img") or ""
                        if avatar and "?" in avatar:
                            avatar = avatar.split("?")[0]
                        if avatar:
                            log.info("Reddit avatar: got via OAuth")
                            return avatar
        except Exception as exc:
            log.debug("Reddit OAuth avatar failed: %s", exc)

    # ── Strategy 2: Redlib scrape ──
    for base in _REDLIB_INSTANCES:
        try:
            r = httpx.get(
                f"{base}/user/{username}",
                headers=_REDLIB_HEADERS,
                timeout=6,
                follow_redirects=True,
            )
            if r.status_code != 200 or len(r.text) < 5000:
                continue
            # Skip anti-bot challenge pages
            low = r.text[:2000].lower()
            if "just a moment" in low or "enable cookies" in low or "checking your browser" in low:
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            img_el = soup.select_one("#user_icon") or soup.select_one("#user img")
            if img_el:
                src = img_el.get("src", "")
                if src:
                    if src.startswith("/"):
                        src = base + src
                    log.info("Reddit avatar: got via Redlib (%s)", base)
                    return src
        except Exception:
            continue

    log.debug("Reddit avatar: unavailable for u/%s (no OAuth creds, no Redlib)", username)
    return ""


class RedditCollector:
    """
    Collects public Reddit profile data.
    Tries old.reddit.com first (most reliable), falls back to Redlib instances.
    Whichever source responds first is used for the entire collection.
    """

    BROWSER_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def _fetch(self, base: str, path: str) -> httpx.Response:
        """Fetch a page, raise ValueError on non-200 or bot-challenge."""
        r = httpx.get(
            f"{base}{path}",
            headers=self.BROWSER_HEADERS,
            timeout=15,
            follow_redirects=True,
        )
        if r.status_code != 200:
            raise ValueError(f"{base} returned {r.status_code} for {path}")
        low = r.text[:2000].lower()
        if "just a moment" in low or "enable cookies" in low or "checking your browser" in low or "not a bot" in low:
            raise ValueError(f"{base} returned anti-bot challenge for {path}")
        return r

    def _pick_source(self, username: str) -> tuple:
        """
        Try Redlib instances first (provides avatar), fall back to old.reddit.com.
        Returns (base_url, profile_soup, source_type) for the first that works.
        """
        sources = [("https://old.reddit.com", "oldreddit")] + [
            (inst, "redlib") for inst in _REDLIB_INSTANCES
        ]
        for base, stype in sources:
            try:
                r = self._fetch(base, f"/user/{username}")
                if len(r.text) < 3000:
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                log.info("Reddit: using %s (%s) for u/%s", stype, base, username)
                return base, soup, stype
            except Exception as exc:
                log.debug("Reddit source %s failed: %s", base, exc)
                continue
        raise ValueError(
            f"Reddit user '{username}' not found — all sources (old.reddit.com + Redlib) failed."
        )

    # ── old.reddit.com parsers ───────────────────────────

    def _parse_profile_oldreddit(self, soup):
        display_name, bio, karma, created_utc = "", "", None, None
        titlebox = soup.select_one(".titlebox")
        if not titlebox:
            return display_name, bio, karma, created_utc

        h1 = titlebox.select_one("h1")
        if h1:
            name_text = h1.find(string=True, recursive=False)
            if name_text:
                display_name = name_text.strip()

        bio_el = titlebox.select_one(".md")
        if bio_el:
            bio = bio_el.get_text(separator=" ").strip()

        karma_els = titlebox.select("span.karma")
        pk, ck = 0, 0
        if len(karma_els) >= 1:
            try: pk = int(karma_els[0].text.strip().replace(",", ""))
            except Exception: pass
        if len(karma_els) >= 2:
            try: ck = int(karma_els[1].text.strip().replace(",", ""))
            except Exception: pass
        karma = pk + ck

        age_el = titlebox.select_one(".age time")
        if age_el:
            dt_str = age_el.get("datetime", "")
            if dt_str:
                try: created_utc = datetime.fromisoformat(dt_str).timestamp()
                except Exception: pass

        return display_name, bio, karma, created_utc

    def _parse_submissions_oldreddit(self, base, username, limit):
        posts, subreddits, after, fetched = [], set(), "", 0
        page_size = min(25, limit)
        while fetched < limit:
            path = f"/user/{username}/submitted?limit={page_size}"
            if after:
                path += f"&after={after}"
            try:
                r = self._fetch(base, path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Reddit: submissions page failed — %s", exc)
                break
            items = soup.select(".thing[data-type='link']")
            if not items:
                break
            for item in items:
                if fetched >= limit:
                    break
                title_el = item.select_one("a.title")
                body_el = item.select_one(".usertext-body .md")
                time_el = item.select_one("time")
                score_el = item.select_one(".score.unvoted")

                text = title_el.text.strip() if title_el else ""
                permalink = item.get("data-permalink", "")
                url = ("https://reddit.com" + permalink) if permalink else ""
                body_images = _extract_image_urls(body_el)
                if body_el:
                    bt = body_el.get_text(separator=" ").strip()
                    if bt:
                        text = (text + " " + bt).strip()

                ts = 0.0
                if time_el:
                    dt_str = time_el.get("datetime", "")
                    if dt_str:
                        try: ts = datetime.fromisoformat(dt_str).timestamp()
                        except Exception: pass

                sub = item.get("data-subreddit", "")
                if sub and not sub.startswith("u_"):
                    subreddits.add(sub)
                elif sub.startswith("u_"):
                    sub = ""

                score = 0
                if score_el:
                    try: score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception: pass

                images = []
                thumb = _get_thumbnail(item)
                if thumb:
                    images.append(thumb)
                images.extend(body_images)
                data_url = item.get("data-url", "")
                if data_url and any(data_url.split("?")[0].lower().endswith(ext) for ext in _IMAGE_EXTENSIONS):
                    if not data_url.startswith("http"):
                        data_url = "https://reddit.com" + data_url
                    images.append(data_url)

                posts.append(Post(text=text, timestamp=ts, metadata={
                    "type": "submission", "subreddit": sub, "score": score,
                    "url": url, "images": images,
                }))
                fetched += 1

            next_el = soup.select_one(".next-button a")
            if next_el:
                qs = parse_qs(urlparse(next_el.get("href", "")).query)
                after = qs.get("after", [""])[0]
            else:
                break
            if not after:
                break
        return posts, subreddits

    def _parse_comments_oldreddit(self, base, username, limit):
        posts, subreddits, after, fetched = [], set(), "", 0
        page_size = min(25, limit)
        while fetched < limit:
            path = f"/user/{username}/comments?limit={page_size}"
            if after:
                path += f"&after={after}"
            try:
                r = self._fetch(base, path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Reddit: comments page failed — %s", exc)
                break
            items = soup.select(".thing[data-type='comment']")
            if not items:
                break
            for item in items:
                if fetched >= limit:
                    break
                body_el = item.select_one(".md")
                time_el = item.select_one("time")
                score_el = item.select_one(".score.unvoted")
                link_el = item.select_one("a.bylink")

                images = _extract_image_urls(body_el)
                text = body_el.get_text(separator="\n").strip() if body_el else ""

                url = ""
                if link_el:
                    raw = link_el.get("href", "")
                    if raw:
                        url = raw.split("?")[0].replace("old.reddit.com", "reddit.com")

                ts = 0.0
                if time_el:
                    dt_str = time_el.get("datetime", "")
                    if dt_str:
                        try: ts = datetime.fromisoformat(dt_str).timestamp()
                        except Exception: pass

                sub = item.get("data-subreddit", "")
                if sub and not sub.startswith("u_"):
                    subreddits.add(sub)
                elif sub.startswith("u_"):
                    sub = ""

                score = 0
                if score_el:
                    try: score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception: pass

                posts.append(Post(text=text, timestamp=ts, metadata={
                    "type": "comment", "subreddit": sub, "score": score,
                    "url": url, "images": images,
                }))
                fetched += 1

            next_el = soup.select_one(".next-button a")
            if next_el:
                qs = parse_qs(urlparse(next_el.get("href", "")).query)
                after = qs.get("after", [""])[0]
            else:
                break
            if not after:
                break
        return posts, subreddits

    # ── Redlib parsers ───────────────────────────────────

    def _parse_profile_redlib(self, soup, base):
        display_name, bio, karma, created_utc, avatar = "", "", None, None, ""

        name_el = soup.select_one("#user_title") or soup.select_one("#user > header h1")
        if name_el:
            display_name = name_el.text.strip().lstrip("u/").strip()

        bio_el = soup.select_one("#user_description") or soup.select_one("p.description")
        if bio_el:
            bio = bio_el.text.strip()

        details_el = soup.select_one("#user_details")
        if details_el:
            labels = [el.text.strip().lower() for el in details_el.select("label")]
            values = [el.text.strip() for el in details_el.select("div")]
            for i, label in enumerate(labels):
                if i >= len(values):
                    break
                if "karma" in label:
                    try: karma = int(values[i].replace(",", "").replace(".", ""))
                    except Exception: pass
                elif "created" in label:
                    try:
                        raw = values[i].strip().replace("'", "20")
                        created_utc = datetime.strptime(raw, "%b %d %Y").replace(
                            tzinfo=timezone.utc).timestamp()
                    except Exception: pass

        img_el = soup.select_one("#user_icon") or soup.select_one("#user img")
        if img_el:
            src = img_el.get("src", "")
            if src:
                avatar = (base + src) if src.startswith("/") else src

        return display_name, bio, karma, created_utc, avatar

    def _parse_submissions_redlib(self, base, username, limit):
        posts, subreddits, after, fetched = [], set(), "", 0
        while fetched < limit:
            path = f"/user/{username}/submitted"
            if after:
                path += f"?after={after}"
            try:
                r = self._fetch(base, path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Reddit: Redlib submissions failed — %s", exc)
                break
            items = soup.select(".post")
            if not items:
                break
            for item in items:
                if fetched >= limit:
                    break
                title_links = item.select(".post_title a")
                title_el = title_links[-1] if title_links else None
                body_el = item.select_one(".post_body")
                created_el = item.select_one(".created")
                sub_el = item.select_one(".post_subreddit")
                score_el = item.select_one(".post_score")

                text, url = "", ""
                if title_el:
                    text = title_el.text.strip()
                    raw_href = title_el.get("href", "")
                    if raw_href.startswith("/"):
                        url = "https://reddit.com" + raw_href
                if body_el:
                    bt = body_el.text.strip()
                    if bt:
                        text = (text + " " + bt).strip()

                ts = 0.0
                if created_el and created_el.get("title"):
                    try:
                        ts = datetime.strptime(
                            created_el["title"], "%b %d %Y, %H:%M:%S UTC"
                        ).replace(tzinfo=timezone.utc).timestamp()
                    except Exception: pass

                sub = ""
                if sub_el:
                    raw_sub = sub_el.text.strip()
                    if raw_sub.startswith("r/"):
                        sub = raw_sub[2:]
                    if sub:
                        subreddits.add(sub)

                score = 0
                if score_el:
                    try: score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception: pass

                posts.append(Post(text=text, timestamp=ts, metadata={
                    "type": "submission", "subreddit": sub, "score": score, "url": url,
                }))
                fetched += 1

            next_el = soup.select_one("a[rel='next']")
            if next_el:
                qs = parse_qs(urlparse(next_el.get("href", "")).query)
                after = qs.get("after", [""])[0]
            else:
                break
            if not after:
                break
        return posts, subreddits

    def _parse_comments_redlib(self, base, username, limit):
        posts, subreddits, after, fetched = [], set(), "", 0
        while fetched < limit:
            path = f"/user/{username}/comments"
            if after:
                path += f"?after={after}"
            try:
                r = self._fetch(base, path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Reddit: Redlib comments failed — %s", exc)
                break
            items = soup.select(".comment")
            if not items:
                break
            for item in items:
                if fetched >= limit:
                    break
                body_el = item.select_one(".comment_body")
                created_el = item.select_one(".created")
                sub_el = item.select_one(".comment_subreddit")
                score_el = item.select_one(".comment_score")
                link_el = item.select_one(".comment_link")

                raw_text = body_el.get_text(separator="\n").strip() if body_el else ""
                # Strip Redlib-proxied image paths from text, collect as image URLs
                images = []
                clean_lines = []
                for line in raw_text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("/preview/pre/") or stripped.startswith("/img/"):
                        images.append(base + stripped)
                    else:
                        clean_lines.append(line)
                text = "\n".join(clean_lines).strip()

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
                    except Exception: pass

                sub = ""
                if sub_el:
                    raw_sub = sub_el.text.strip()
                    if raw_sub.startswith("r/"):
                        sub = raw_sub[2:]
                    if sub:
                        subreddits.add(sub)

                score = 0
                if score_el:
                    try: score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception: pass

                posts.append(Post(text=text, timestamp=ts, metadata={
                    "type": "comment", "subreddit": sub, "score": score,
                    "url": url, "images": images,
                }))
                fetched += 1

            next_el = soup.find("a", string=lambda t: t and t.strip().upper() == "NEXT")
            if not next_el:
                break
            qs = parse_qs(urlparse(next_el.get("href", "")).query)
            after = qs.get("after", [""])[0]
            if not after:
                break
        return posts, subreddits

    # ── Main entry point ─────────────────────────────────

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        log.info("Reddit: collecting u/%s (limit=%d)", username, limit)

        base, profile_soup, stype = self._pick_source(username)

        if stype == "oldreddit":
            display_name, bio, karma, created_utc = self._parse_profile_oldreddit(profile_soup)
            profile_image_url = _fetch_reddit_avatar(username)
            sub_posts, sub_subs = self._parse_submissions_oldreddit(base, username, limit)
            com_posts, com_subs = self._parse_comments_oldreddit(base, username, limit)
        else:
            display_name, bio, karma, created_utc, profile_image_url = self._parse_profile_redlib(
                profile_soup, base)
            sub_posts, sub_subs = self._parse_submissions_redlib(base, username, limit)
            com_posts, com_subs = self._parse_comments_redlib(base, username, limit)

        all_posts = sub_posts + com_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)
        all_subs = sub_subs | com_subs

        display_name = display_name or username

        log.info("Reddit: u/%s — %d posts, %d subreddits (via %s)",
                 username, len(all_posts), len(all_subs), stype)

        return AccountProfile(
            platform="reddit",
            username=username,
            display_name=display_name,
            bio=bio,
            location="",
            profile_image_url=profile_image_url,
            created_utc=created_utc,
            posts=all_posts,
            subreddits=sorted(s for s in all_subs if s),
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

def save_to_db(profile: AccountProfile, conn, case_id: int) -> int:
    """
    Upsert an AccountProfile into PostgreSQL.
    Run schema.sql first to create the required tables.

    Args:
        profile : AccountProfile returned by collect()
        conn    : open psycopg2 connection
        case_id : ID of the case this profile belongs to

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
            (case_id, platform, username, display_name, bio, location, created_at, profile_image_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id, platform, username) DO UPDATE SET
            display_name      = EXCLUDED.display_name,
            bio               = EXCLUDED.bio,
            location          = EXCLUDED.location,
            profile_image_url = EXCLUDED.profile_image_url
        RETURNING id
        """,
        (
            case_id,
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
        "DB: saved account_id=%d (%s/%s) under case_id=%d",
        account_id, profile.platform, profile.username, case_id,
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
