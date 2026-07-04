from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs, urlencode
import httpx
import os
from .models import AccountProfile, Post, log
from bs4 import BeautifulSoup
from datetime import datetime, timezone

load_dotenv()
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")
IMAGE_HOSTS = ("i.redd.it", "preview.redd.it", "i.imgur.com", "imgur.com")

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

JSON_HEADERS = {
    "User-Agent": "ARIA-OSINT/1.0 (by /u/aria_osint)",
    "Accept": "application/json",
}

# Self-hosted Redlib (Docker service name)
SELF_HOSTED_REDLIB = os.environ.get("REDLIB_URL", "http://aria-redlib:8080")
PUBLIC_REDLIB_URL = os.environ.get("REDLIB_PUBLIC_URL", "http://localhost:8080")

PUBLIC_REDLIB_INSTANCES = [
]


def is_bot_challenge(text: str) -> bool:
    low = text[:2000].lower()
    return (
        "just a moment" in low
        or "enable cookies" in low
        or "checking your browser" in low
        or "not a bot" in low
    )


def normalize_url(href: str) -> str:
    """Ensure a URL has a proper http(s) scheme."""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return "https:" + href
    return "https://" + href


def is_image_url(url: str) -> bool:
    """Return True if the URL points to an image by extension or known host."""
    path = url.split("?")[0].lower()
    return any(path.endswith(ext) for ext in IMAGE_EXTENSIONS) or any(
        host in url for host in IMAGE_HOSTS
    )


def extract_image_urls(md_el) -> list:
    """
    Extract image URLs from <a> and <img> tags inside a BeautifulSoup element.
    Matching elements are decomposed (removed) from the tree so they don't
    pollute the text extracted afterwards.
    """
    if not md_el:
        return []
    urls = []
    seen = set()
    to_remove = []

    # <a href="..."> pointing to images
    for a in md_el.select("a"):
        href = a.get("href", "").strip()
        if not href:
            continue
        if is_image_url(href):
            href = normalize_url(href)
            if href not in seen:
                seen.add(href)
                urls.append(href)
            to_remove.append(a)

    # inline <img src="...">
    for img in md_el.select("img"):
        src = img.get("src", "").strip()
        if not src:
            continue
        src = normalize_url(src)
        if src not in seen:
            seen.add(src)
            urls.append(src)
        to_remove.append(img)

    for el in to_remove:
        el.decompose()

    return urls


def get_thumbnail(thing_el) -> str:
    """Return the thumbnail image URL for a post element, or empty string."""
    img = thing_el.select_one("a.thumbnail img")
    if not img:
        return ""
    src = img.get("src", "").strip()
    if not src:
        return ""
    if not src.startswith("http"):
        src = "https:" + src if src.startswith("//") else ""
    return src


def dedupe(lst: list) -> list:
    """Return list with duplicates removed, preserving order."""
    seen = set()
    out = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


# SOURCE 1: Reddit JSON API
class RedditJSONCollector:
    """
    Collects Reddit data via the public JSON API.
    No credentials required for public profiles.
    Endpoint pattern: https://www.reddit.com/user/<username>/<type>.json
    """

    BASE = "https://www.reddit.com"
    TIMEOUT = 12

    def get(self, path: str, params: dict = None) -> dict:
        url = f"{self.BASE}{path}"
        if params:
            url += "?" + urlencode(params)
        r = httpx.get(
            url, headers=JSON_HEADERS, timeout=self.TIMEOUT, follow_redirects=True
        )
        if r.status_code == 404:
            raise ValueError(f"Reddit JSON API: user not found at {path}")
        if r.status_code == 403:
            raise ValueError(
                f"Reddit JSON API: forbidden (private/suspended) at {path}"
            )
        if r.status_code == 429:
            raise ValueError("Reddit JSON API: rate limited")
        if r.status_code != 200:
            raise ValueError(f"Reddit JSON API: HTTP {r.status_code} at {path}")
        return r.json()

    def fetch_about(self, username: str) -> dict:
        data = self.get(f"/user/{username}/about.json")
        if data.get("kind") != "t2":
            raise ValueError(
                f"Reddit JSON API: unexpected about.json shape for u/{username}"
            )
        return data["data"]

    def fetch_listings(self, username: str, endpoint: str, limit: int) -> list:
        """
        Paginate through /user/<u>/<endpoint>.json and return raw 'children' dicts.
        endpoint: 'submitted' | 'comments'
        """
        items = []
        after = None
        page_size = min(100, limit)

        while len(items) < limit:
            params = {"limit": page_size, "raw_json": 1}
            if after:
                params["after"] = after

            try:
                data = self.get(f"/user/{username}/{endpoint}.json", params)
            except ValueError:
                break

            listing = data.get("data", {})
            children = listing.get("children", [])
            if not children:
                break

            items.extend(children)

            after = listing.get("after")
            if not after:
                break

        return items[:limit]

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        log.info("Reddit [1/4 JSON API]: collecting u/%s (limit=%d)", username, limit)

        about = self.fetch_about(username)

        display_name = about.get("name", username)
        bio = about.get("subreddit", {}).get("public_description", "") or ""
        karma = (about.get("link_karma") or 0) + (about.get("comment_karma") or 0)
        created_utc = about.get("created_utc")

        # Avatar: prefer snoovatar, fall back to icon_img
        avatar = about.get("snoovatar_img") or about.get("icon_img") or ""
        if avatar and "?" in avatar:
            avatar = avatar.split("?")[0]

        # Collect submissions
        sub_children = self.fetch_listings(username, "submitted", limit)
        sub_posts, subreddits = self.parse_submission_children(sub_children)
        log.info(
            "Reddit [JSON API]: u/%s — %d submissions fetched", username, len(sub_posts)
        )

        # Collect comments
        com_children = self.fetch_listings(username, "comments", limit)
        com_posts, com_subs = self.parse_comment_children(com_children)
        subreddits |= com_subs
        log.info(
            "Reddit [JSON API]: u/%s — %d comments fetched", username, len(com_posts)
        )

        all_posts = sub_posts + com_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)

        log.info(
            "Reddit [JSON API] ✓: u/%s — %d total posts, %d subreddits (source: reddit.com JSON)",
            username,
            len(all_posts),
            len(subreddits),
        )

        return AccountProfile(
            platform="reddit",
            username=username,
            display_name=display_name,
            bio=bio,
            location="",
            profile_image_url=avatar,
            created_utc=created_utc,
            posts=all_posts,
            subreddits=sorted(s for s in subreddits if s),
            karma=karma,
        )

    def parse_submission_children(self, children: list) -> tuple:
        posts = []
        subreddits = set()
        for child in children:
            if child.get("kind") != "t3":
                continue
            d = child["data"]
            sub = d.get("subreddit", "")
            if sub and not sub.startswith("u_"):
                subreddits.add(sub)
            else:
                sub = ""

            title = d.get("title", "")
            selftext = d.get("selftext", "")
            text = title
            if selftext and selftext not in ("[removed]", "[deleted]"):
                text = (title + " " + selftext).strip()

            # ── Image extraction ──────────────────────────────────────────────
            images = []

            # 1. Direct post URL (e.g. i.redd.it link or image upload)
            url = d.get("url", "")
            if url and is_image_url(url):
                images.append(url)

            # 2. Reddit preview images (decode &amp; entities)
            preview = d.get("preview", {})
            for img in preview.get("images", []):
                src = img.get("source", {}).get("url", "").replace("&amp;", "&")
                if src:
                    images.append(src)

            # 3. Gallery images
            media_metadata = d.get("media_metadata") or {}
            for item in media_metadata.values():
                if item.get("status") != "valid":
                    continue
                # 's' key holds the full-size source
                s = item.get("s", {})
                src = s.get("u", "") or s.get("gif", "")
                src = src.replace("&amp;", "&")
                if src:
                    images.append(src)

            # 4. Thumbnail — only when it's a real image URL
            thumbnail = d.get("thumbnail", "")
            if thumbnail and thumbnail.startswith("http") and is_image_url(thumbnail):
                images.append(thumbnail)

            images = dedupe(images)
            # ─────────────────────────────────────────────────────────────────

            permalink = d.get("permalink", "")
            post_url = ("https://reddit.com" + permalink) if permalink else ""

            posts.append(
                Post(
                    external_id=f"t3_{d['id']}",
                    text=text,
                    timestamp=float(d.get("created_utc", 0)),
                    metadata={
                        "type": "submission",
                        "subreddit": sub,
                        "score": d.get("score", 0),
                        "url": post_url,
                        "images": images,
                    },
                )
            )
        return posts, subreddits

    def parse_comment_children(self, children: list) -> tuple:
        posts = []
        subreddits = set()
        for child in children:
            if child.get("kind") != "t1":
                continue
            d = child["data"]
            sub = d.get("subreddit", "")
            if sub and not sub.startswith("u_"):
                subreddits.add(sub)
            else:
                sub = ""

            body = d.get("body", "")
            if body in ("[removed]", "[deleted]"):
                body = ""

            # ── Image extraction from body_html ───────────────────────────────
            images = []
            body_html = d.get("body_html", "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
            if body_html:
                soup = BeautifulSoup(body_html, "html.parser")
                images = extract_image_urls(soup)
            # ─────────────────────────────────────────────────────────────────

            permalink = d.get("permalink", "")
            post_url = ("https://reddit.com" + permalink) if permalink else ""

            posts.append(
                Post(
                    external_id=f"t1_{d['id']}",
                    text=body,
                    timestamp=float(d.get("created_utc", 0)),
                    metadata={
                        "type": "comment",
                        "subreddit": sub,
                        "score": d.get("score", 0),
                        "url": post_url,
                        "images": images,
                    },
                )
            )
        return posts, subreddits


# SOURCE 2: Redlib HTML (self-hosted)
class RedlibCollector:
    """
    Collects Reddit data by scraping a Redlib instance (HTML).
    Used for both self-hosted (aria-redlib:8080) and public instances.
    """

    def __init__(self, base_url: str, label: str):
        self.base = base_url.rstrip("/")
        self.label = label  # for logging

    def fetch(self, path: str) -> httpx.Response:
        r = httpx.get(
            f"{self.base}{path}",
            headers=BROWSER_HEADERS,
            timeout=12,
            follow_redirects=True,
        )
        if r.status_code != 200:
            raise ValueError(f"Redlib [{self.label}]: HTTP {r.status_code} for {path}")
        if len(r.text) < 3000:
            raise ValueError(
                f"Redlib [{self.label}]: response too short for {path} — likely down"
            )
        if is_bot_challenge(r.text):
            raise ValueError(f"Redlib [{self.label}]: anti-bot challenge for {path}")
        return r

    def probe(self) -> bool:
        """Quick liveness check — returns True if instance is reachable."""
        try:
            r = httpx.get(
                f"{self.base}/",
                headers=BROWSER_HEADERS,
                timeout=5,
                follow_redirects=True,
            )
            return r.status_code == 200 and not is_bot_challenge(r.text)
        except Exception:
            return False

    def resolve_url(self, src: str) -> str:
        """
        Turn a relative Redlib path into an absolute URL.
        Uses PUBLIC_REDLIB_URL when the internal Docker hostname is detected.
        """
        if src.startswith("http"):
            return src
        base = self.base
        if "aria-redlib" in base:
            base = PUBLIC_REDLIB_URL
        if src.startswith("/"):
            return base + src
        return src

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        log.info(
            "Reddit [Redlib/%s]: collecting u/%s (limit=%d)",
            self.label,
            username,
            limit,
        )

        profile_r = self.fetch(f"/user/{username}")
        soup = BeautifulSoup(profile_r.text, "html.parser")

        display_name, bio, karma, created_utc, avatar = self.parse_profile(soup)

        sub_posts, sub_subs = self.parse_submissions(username, limit)
        com_posts, com_subs = self.parse_comments(username, limit)

        all_posts = sub_posts + com_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)
        all_subs = sub_subs | com_subs

        log.info(
            "Reddit [Redlib/%s] ✓: u/%s — %d total posts, %d subreddits",
            self.label,
            username,
            len(all_posts),
            len(all_subs),
        )

        return AccountProfile(
            platform="reddit",
            username=username,
            display_name=display_name or username,
            bio=bio,
            location="",
            profile_image_url=avatar,
            created_utc=created_utc,
            posts=all_posts,
            subreddits=sorted(s for s in all_subs if s),
            karma=karma,
        )

    def parse_profile(self, soup) -> tuple:
        display_name, bio, karma, created_utc, avatar = "", "", None, None, ""

        name_el = soup.select_one("#user_title") or soup.select_one("#user > header h1")
        if name_el:
            display_name = name_el.text.strip().lstrip("u/").strip()

        bio_el = soup.select_one("#user_description") or soup.select_one(
            "p.description"
        )
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
                    try:
                        karma = int(values[i].replace(",", "").replace(".", ""))
                    except Exception:
                        pass
                elif "created" in label:
                    try:
                        raw = values[i].strip().replace("'", "20")
                        created_utc = (
                            datetime.strptime(raw, "%b %d %Y")
                            .replace(tzinfo=timezone.utc)
                            .timestamp()
                        )
                    except Exception:
                        pass

        img_el = soup.select_one("#user_icon") or soup.select_one("#user img")
        if img_el:
            src = img_el.get("src", "").strip()
            if src:
                avatar = self.resolve_url(src)

        return display_name, bio, karma, created_utc, avatar

    def parse_submissions(self, username: str, limit: int) -> tuple:
        posts, subreddits, after, fetched = [], set(), "", 0
        while fetched < limit:
            path = f"/user/{username}/submitted"
            if after:
                path += f"?after={after}"
            try:
                r = self.fetch(path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning(
                    "Redlib [%s]: submissions page failed — %s", self.label, exc
                )
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

                # ── Image extraction ──────────────────────────────────────────
                images = []

                # Thumbnail from the post card
                thumb = get_thumbnail(item)
                if thumb:
                    images.append(thumb)

                # Images linked/embedded in the post body
                if body_el:
                    for img_url in extract_image_urls(body_el):
                        resolved = self.resolve_url(img_url)
                        if resolved not in images:
                            images.append(resolved)

                # Redlib renders submission images inside div.post_media_content
                # as <svg><image href="/img/..."> — not a regular <img src>
                media_content = item.select_one(".post_media_content")
                if media_content:
                    # SVG <image href="...">
                    for svg_img in media_content.select("image"):
                        src = svg_img.get("href", "").strip()
                        if src:
                            resolved = self.resolve_url(src)
                            if resolved not in images:
                                images.append(resolved)
                    # fallback: regular <img src="..."> inside desc or elsewhere
                    for img_tag in media_content.select("img"):
                        src = img_tag.get("src", "").strip()
                        if src:
                            resolved = self.resolve_url(src)
                            if resolved not in images:
                                images.append(resolved)
                    # fallback: <a class="post_media_image" href="..."> direct link
                    a_tag = media_content.select_one("a.post_media_image")
                    if a_tag:
                        href = a_tag.get("href", "").strip()
                        if href and is_image_url(href):
                            resolved = self.resolve_url(href)
                            if resolved not in images:
                                images.append(resolved)

                images = dedupe(images)
                # ─────────────────────────────────────────────────────────────

                text, url = "", ""
                if title_el:
                    text = title_el.text.strip()
                    raw_href = title_el.get("href", "")
                    if raw_href.startswith("/"):
                        url = "https://reddit.com" + raw_href
                if body_el:
                    bt = body_el.get_text(separator=" ").strip()
                    if bt:
                        text = (text + " " + bt).strip()

                ts = 0.0
                if created_el and created_el.get("title"):
                    try:
                        ts = (
                            datetime.strptime(
                                created_el["title"], "%b %d %Y, %H:%M:%S UTC"
                            )
                            .replace(tzinfo=timezone.utc)
                            .timestamp()
                        )
                    except Exception:
                        pass

                sub = ""
                if sub_el:
                    raw_sub = sub_el.text.strip()
                    if raw_sub.startswith("r/"):
                        sub = raw_sub[2:]
                    if sub:
                        subreddits.add(sub)

                score = 0
                if score_el:
                    try:
                        score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception:
                        pass

                posts.append(
                    Post(
                        external_id=f"submission:{url or ts}",
                        text=text,
                        timestamp=ts,
                        metadata={
                            "type": "submission",
                            "subreddit": sub,
                            "score": score,
                            "url": url,
                            "images": images,
                        },
                    )
                )
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

    def parse_comments(self, username: str, limit: int) -> tuple:
        posts, subreddits, after, fetched = [], set(), "", 0
        while fetched < limit:
            path = f"/user/{username}/comments"
            if after:
                path += f"?after={after}"
            try:
                r = self.fetch(path)
                soup = BeautifulSoup(r.text, "html.parser")
            except Exception as exc:
                log.warning("Redlib [%s]: comments page failed — %s", self.label, exc)
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

                # ── Image extraction ──────────────────────────────────────────
                # Redlib renders comment images as:
                #   p.comment_body > div.md > figure > a > img
                # Directly select every <img> inside a <figure> in the comment
                # and resolve the src. Done BEFORE get_text() so nodes are present.
                images = []
                for img_tag in item.select("figure img"):
                    src = img_tag.get("src", "").strip()
                    if src:
                        resolved = self.resolve_url(src)
                        if resolved not in images:
                            images.append(resolved)

                # get_text after image collection
                raw_text = body_el.get_text(separator="\n").strip() if body_el else ""
                clean_lines = []
                for line in raw_text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("/preview/pre/") or stripped.startswith("/img/"):
                        resolved = self.resolve_url(stripped)
                        if resolved not in images:
                            images.append(resolved)
                    else:
                        clean_lines.append(line)
                text = "\n".join(clean_lines).strip()

                images = dedupe(images)
                # ─────────────────────────────────────────────────────────────

                url = ""
                if link_el:
                    raw_href = link_el.get("href", "")
                    if raw_href.startswith("/"):
                        url = "https://reddit.com" + raw_href.split("#")[0]

                ts = 0.0
                if created_el and created_el.get("title"):
                    try:
                        ts = (
                            datetime.strptime(
                                created_el["title"], "%b %d %Y, %H:%M:%S UTC"
                            )
                            .replace(tzinfo=timezone.utc)
                            .timestamp()
                        )
                    except Exception:
                        pass

                sub = ""
                if sub_el:
                    raw_sub = sub_el.text.strip()
                    if raw_sub.startswith("r/"):
                        sub = raw_sub[2:]
                    if sub:
                        subreddits.add(sub)

                score = 0
                if score_el:
                    try:
                        score = int(score_el.get("title", "0").replace(",", ""))
                    except Exception:
                        pass

                posts.append(
                    Post(
                        external_id=f"comment:{url or ts}",
                        text=text,
                        timestamp=ts,
                        metadata={
                            "type": "comment",
                            "subreddit": sub,
                            "score": score,
                            "url": url,
                            "images": images,
                        },
                    )
                )
                fetched += 1

            next_el = soup.find("a", string=lambda t: t and t.strip().upper() == "NEXT")
            if not next_el:
                break
            qs = parse_qs(urlparse(next_el.get("href", "")).query)
            after = qs.get("after", [""])[0]
            if not after:
                break
        return posts, subreddits


# RedditCollector — priority waterfall
class RedditCollector:
    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        errors = []

        # ── Priority 1: Self-hosted Redlib ───────────────
        self_hosted = RedlibCollector(SELF_HOSTED_REDLIB, label="self-hosted")
        try:
            if self_hosted.probe():
                return self_hosted.collect(username, limit=limit)
            else:
                msg = f"self-hosted Redlib at {SELF_HOSTED_REDLIB} not reachable"
                log.info("Reddit [1/3 Redlib/self-hosted]: %s", msg)
                errors.append(msg)
        except Exception as exc:
            log.warning(
                "Reddit [1/3 Redlib/self-hosted] failed for u/%s: %s", username, exc
            )
            errors.append(f"self-hosted Redlib: {exc}")

        # ── Priority 2: Reddit JSON API ──────────────────
        try:
            return RedditJSONCollector().collect(username, limit=limit)
        except Exception as exc:
            log.warning("Reddit [2/3 JSON API] failed for u/%s: %s", username, exc)
            errors.append(f"JSON API: {exc}")

        # ── Priority 3: Public Redlib instances ──────────
        for idx, instance_url in enumerate(PUBLIC_REDLIB_INSTANCES, start=1):
            label = f"public-{idx}"
            collector = RedlibCollector(instance_url, label=label)
            try:
                if not collector.probe():
                    log.debug(
                        "Reddit [3/3 Redlib/%s]: %s not reachable, skipping",
                        label,
                        instance_url,
                    )
                    continue
                return collector.collect(username, limit=limit)
            except Exception as exc:
                log.warning(
                    "Reddit [3/3 Redlib/%s] failed for u/%s: %s",
                    label,
                    username,
                    exc,
                )
                errors.append(f"Redlib {instance_url}: {exc}")

        raise ValueError(
            f"Reddit user '{username}' could not be collected — all sources failed:\n"
            + "\n".join(f"  • {e}" for e in errors)
        )
