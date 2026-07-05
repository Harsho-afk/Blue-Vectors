import os
import threading
from instagrapi import Client
from instagrapi.exceptions import (
    UserNotFound,
    PrivateAccount,
    LoginRequired,
    RateLimitError,
    ClientError,
)
from .models import AccountProfile, Post, log

# ---------------------------------------------------------------------------
# Instagram collector using instagrapi (github.com/subzeroid/instagrapi)
# 6.4k stars, 2,759 commits, actively maintained 2026.
#
# Uses Instagram's private mobile API — same endpoints as the official app.
# Far more stable than web endpoints (no rotating doc_ids, no GraphQL breaks).
# Built-in curl_cffi TLS impersonation via the [curl] extra.
#
# REQUIRED .env:
#   INSTAGRAM_SESSION_ID   — sessionid cookie from your browser
#   INSTAGRAM_USERNAME     — your collector account's username
#
# HOW TO GET SESSION ID:
#   1. Log into instagram.com in your browser
#   2. DevTools → Application → Cookies → https://www.instagram.com
#   3. Copy the value of 'sessionid'
#   Expires ~90 days or on logout. Re-extract when it does.
#
# OPTIONAL .env:
#   INSTAGRAM_PROXY        — e.g. http://user:pass@host:port
#                            Required only if running on a datacenter IP.
#
# INSTALL:
#   pip install "instagrapi[curl]"
#
# UNLIMITED COLLECTION NOTE:
#   follower_limit, following_limit, and comment_limit all accept 0 to mean
#   "no cap" — instagrapi paginates through the ENTIRE list internally when
#   amount=0. This can mean hundreds of requests for large/popular accounts
#   and significantly increases the chance of hitting Instagram's own rate
#   limits (RateLimitError), independent of any cap in this code.
#
# DATA RETENTION POLICY FOR THIS COLLECTOR:
#   Every field instagrapi's pydantic models expose for profile/media/user/
#   comment objects is captured somewhere in AccountProfile/Post — nothing
#   fetched is silently discarded. Network posts (followers/following) keep
#   the original GitHub-style "logins" (list[str]) for frontend compatibility,
#   PLUS a parallel "users" field with the full per-account dict, so no
#   detail is lost even though only usernames render today.
# ---------------------------------------------------------------------------

_NOT_CONFIGURED = (
    "Instagram credentials not configured. "
    "Add INSTAGRAM_SESSION_ID and INSTAGRAM_USERNAME to your .env. "
    "Extract sessionid from DevTools → Application → Cookies → "
    "https://www.instagram.com"
)


def _build_client() -> Client:
    session_id = os.environ.get("INSTAGRAM_SESSION_ID", "").strip()
    username   = os.environ.get("INSTAGRAM_USERNAME", "").strip()
    proxy      = os.environ.get("INSTAGRAM_PROXY", "").strip() or None

    if not session_id or not username:
        raise RuntimeError(_NOT_CONFIGURED)

    cl = Client(
        # Use curl_cffi for TLS fingerprint impersonation on public endpoints
        public_transport="curl",
        public_transport_impersonate="chrome",
        proxy=proxy,
    )

    try:
        cl.login_by_sessionid(session_id)
    except LoginRequired as exc:
        raise RuntimeError(
            "Instagram: sessionid rejected (login_required). "
            "Your INSTAGRAM_SESSION_ID has expired — re-extract it from "
            "DevTools → Application → Cookies → https://www.instagram.com"
        ) from exc
    except Exception as exc:
        err_msg = str(exc).lower()
        if "redirect" in err_msg:
            raise RuntimeError(
                "Instagram: session expired (redirect loop). "
                "Your INSTAGRAM_SESSION_ID is no longer valid. "
                "Re-login at instagram.com and copy a fresh sessionid from "
                "DevTools → Application → Cookies → https://www.instagram.com"
            ) from exc
        raise RuntimeError(
            f"Instagram: login_by_sessionid failed — {exc}"
        ) from exc

    log.info("Instagram: logged in via sessionid (username=%s)", username)
    return cl


def _user_short_to_dict(user_short) -> dict:
    """
    Normalize instagrapi's UserShort into a plain dict.
    Used for post usertags AND the rich "users" side of network posts.
    """
    return {
        "pk":              str(getattr(user_short, "pk", "") or ""),
        "username":        getattr(user_short, "username", "") or "",
        "full_name":       getattr(user_short, "full_name", "") or "",
        "profile_pic_url": str(getattr(user_short, "profile_pic_url", "") or ""),
        "is_private":      getattr(user_short, "is_private", None),
        "is_verified":     getattr(user_short, "is_verified", None),
    }


def _location_to_dict(location) -> dict | None:
    """Normalize instagrapi's Location model — keep every field, not just name."""
    if not location:
        return None
    return {
        "pk":          getattr(location, "pk", None),
        "name":        getattr(location, "name", "") or "",
        "address":     getattr(location, "address", "") or "",
        "lng":         getattr(location, "lng", None),
        "lat":         getattr(location, "lat", None),
        "external_id": getattr(location, "external_id", None),
        "external_id_source": getattr(location, "external_id_source", None),
    }


def _usertag_to_dict(tag) -> dict:
    """Normalize instagrapi's Usertag — keeps the (x, y) position, not just the user."""
    return {
        **_user_short_to_dict(tag.user),
        "x": getattr(tag, "x", None),
        "y": getattr(tag, "y", None),
    }


def _comment_to_dict(comment) -> dict:
    """Normalize instagrapi's Comment model into a plain dict."""
    user = getattr(comment, "user", None)
    created = getattr(comment, "created_at_utc", None) or getattr(comment, "created_at", None)
    created_ts = None
    if created is not None:
        try:
            created_ts = created.timestamp()
        except AttributeError:
            created_ts = None

    return {
        "pk":              str(getattr(comment, "pk", "") or ""),
        "text":            getattr(comment, "text", "") or "",
        "username":        getattr(user, "username", "") or "",
        "user_pk":         str(getattr(user, "pk", "") or ""),
        "created_at":      created_ts,
        "like_count":      getattr(comment, "like_count", None),
        "reply_count":     len(getattr(comment, "child_comments", None) or []),
    }


def _fetch_comments(cl: Client, media_pk, amount: int, username: str, shortcode: str) -> list[dict]:
    """
    Fetch comments for a single post.
    amount=0 tells instagrapi to paginate through ALL comments rather than
    stopping at a cap — for posts with heavy engagement this can be many
    requests and increases the odds of a RateLimitError.
    """
    try:
        raw = cl.media_comments(media_pk, amount=amount)
        return [_comment_to_dict(c) for c in raw]
    except RateLimitError as exc:
        log.warning(
            "Instagram: rate limited fetching comments for @%s/%s — %s",
            username, shortcode, exc,
        )
        return []
    except Exception as exc:
        log.warning(
            "Instagram: failed to fetch comments for @%s/%s — %s",
            username, shortcode, exc,
        )
        return []


def _fetch_comments_capped(
    cl: Client, media_pk, cap: int, username: str, shortcode: str
) -> list[dict]:
    """
    Like _fetch_comments, but bounded to `cap` comments — used for the fast,
    inline fetch that happens before a post is displayed/persisted. Any
    remaining comments beyond the cap are picked up later by a background
    fetch (see collect_streaming).
    """
    return _fetch_comments(cl, media_pk, cap, username, shortcode)


class InstagramCollector:
    """
    Collects public Instagram profile + post metadata via instagrapi.
    Uses Instagram's private mobile API — the same endpoints as the official app.
    """

    def __init__(self):
        self._client: Client | None = None
        # instagrapi's Client wraps a single requests/curl_cffi session that
        # is not documented as thread-safe. collect_streaming() fires off
        # background threads (to fetch the "rest" of a post's comments
        # without blocking the next post), so every call through `cl` —
        # whether from the main collection loop or a background thread —
        # is serialized through this lock.
        self._client_lock = threading.Lock()

    def _ensure_client(self):
        if self._client is not None:
            return
        self._client = _build_client()

    def _collect_social_graph(
        self,
        username: str,
        user_id,
        is_private: bool,
        follower_count: int | None,
        following_count: int | None,
        follower_limit: int = 0,
        following_limit: int = 0,
    ) -> list[Post]:
        """
        Fetches followers/following and returns them as synthetic "network"
        Posts — same schema as GithubCollector's network posts (type,
        direction, logins, total_count, fetched_count), so the frontend's
        NetworkPanel renders them unmodified. Also attaches a parallel
        "users" field with full per-account detail (pk, full_name,
        profile_pic_url, is_private, is_verified) so nothing instagrapi
        returned is thrown away, even though only usernames render today.

        follower_limit/following_limit default to 0, which tells instagrapi
        to paginate through the ENTIRE follower/following list rather than
        stopping at a cap. For large accounts (e.g. a brand with millions of
        followers) this means many more requests, a much longer collection
        time, and a real risk of Instagram's own rate limiting kicking in —
        that ceiling is now Instagram's, not this code's.

        Skipped automatically for private accounts (same restriction as posts).
        Can raise ValueError on rate limit / client errors, same pattern as
        the rest of the collector, so callers can decide whether to treat
        it as fatal or degrade gracefully.
        """
        cl = self._client

        if is_private:
            log.info(
                "Instagram: @%s is private — skipping follower/following graph.",
                username,
            )
            return []

        try:
            followers_raw = cl.user_followers(user_id, amount=follower_limit)
            following_raw = cl.user_following(user_id, amount=following_limit)
        except PrivateAccount:
            log.warning("Instagram: @%s private — no social graph collected.", username)
            return []
        except RateLimitError as exc:
            raise ValueError(
                f"Instagram: rate limited fetching followers/following for @{username}. "
                "Wait a few minutes before retrying."
            ) from exc
        except ClientError as exc:
            raise ValueError(
                f"Instagram: error fetching social graph for @{username} — {exc}"
            ) from exc

        follower_users  = [_user_short_to_dict(u) for u in followers_raw.values()]
        following_users = [_user_short_to_dict(u) for u in following_raw.values()]
        follower_logins  = [u["username"] for u in follower_users if u["username"]]
        following_logins = [u["username"] for u in following_users if u["username"]]

        network_posts: list[Post] = []

        if follower_logins:
            network_posts.append(Post(
                external_id=f"network:followers:{username}",
                text=f"Followed by {len(follower_logins)} accounts: "
                     + ", ".join(follower_logins),
                timestamp=0.0,
                metadata={
                    "type": "network",
                    "direction": "followers",
                    "logins": follower_logins,
                    "users": follower_users,
                    "total_count": follower_count,
                    "fetched_count": len(follower_logins),
                    "url": f"https://www.instagram.com/{username}/",
                    "images": [],
                },
            ))

        if following_logins:
            network_posts.append(Post(
                external_id=f"network:following:{username}",
                text=f"Following {len(following_logins)} accounts: "
                     + ", ".join(following_logins),
                timestamp=0.0,
                metadata={
                    "type": "network",
                    "direction": "following",
                    "logins": following_logins,
                    "users": following_users,
                    "total_count": following_count,
                    "fetched_count": len(following_logins),
                    "url": f"https://www.instagram.com/{username}/",
                    "images": [],
                },
            ))

        log.info(
            "Instagram ✓: @%s — %d followers, %d following collected",
            username, len(follower_logins), len(following_logins),
        )
        return network_posts

    def collect(
        self,
        username: str,
        limit: int = 100,
        include_social_graph: bool = True,
        follower_limit: int = 0,
        following_limit: int = 0,
        fetch_comments: bool = False,
        comment_limit: int = 0,
    ) -> AccountProfile:
        """
        Collect a full Instagram profile.

        limit:            max posts to fetch (0 = unlimited — paginates the
                           entire post history; can be slow/rate-limit-prone
                           on large accounts).
        follower_limit:   max followers to fetch (0 = unlimited).
        following_limit:  max following to fetch (0 = unlimited).
        fetch_comments:   if True, fetch comments for each post.
        comment_limit:    max comments per post (0 = unlimited).
        """
        username = username.strip().lstrip("@")
        self._ensure_client()
        cl = self._client

        log.info(
            "Instagram: collecting @%s (limit=%s, comments=%s/%s)",
            username,
            limit or "unlimited",
            fetch_comments,
            comment_limit or "unlimited",
        )

        # ── Profile ────────────────────────────────────────────────────────
        try:
            user_id = cl.user_id_from_username(username)
            user    = cl.user_info(user_id)
        except UserNotFound as exc:
            raise ValueError(f"Instagram user '@{username}' not found.") from exc
        except PrivateAccount as exc:
            raise ValueError(
                f"Instagram user '@{username}' has a private profile — "
                "ARIA does not bypass privacy settings."
            ) from exc
        except LoginRequired as exc:
            raise ValueError(
                "Instagram: session expired mid-collection. "
                "Re-extract INSTAGRAM_SESSION_ID from your browser."
            ) from exc
        except RateLimitError as exc:
            raise ValueError(
                f"Instagram: rate limited fetching @{username}. "
                "Wait a few minutes before retrying."
            ) from exc
        except ClientError as exc:
            raise ValueError(
                f"Instagram: error fetching profile for @{username} — {exc}"
            ) from exc

        # ── Posts ──────────────────────────────────────────────────────────
        posts: list[Post] = []

        if user.is_private:
            log.info("Instagram: @%s is private — skipping posts, returning profile only.", username)
            medias = []
        else:
            try:
                medias = cl.user_medias(user_id, amount=limit)
            except PrivateAccount:
                medias = []
                log.warning("Instagram: @%s private — no posts collected.", username)
            except RateLimitError as exc:
                raise ValueError(
                    f"Instagram: rate limited fetching posts for @{username}. "
                    "Wait a few minutes before retrying."
                ) from exc
            except ClientError as exc:
                raise ValueError(
                    f"Instagram: error fetching posts for @{username} — {exc}"
                ) from exc

        for media in medias:
            images: list[str] = []
            try:
                if media.resources:  # carousel
                    images = [str(r.thumbnail_url) for r in media.resources if r.thumbnail_url]
                elif media.thumbnail_url:
                    images = [str(media.thumbnail_url)]
            except Exception:
                pass

            media_type = getattr(media, "media_type", None)
            # instagrapi media_type: 1=photo, 2=video, 8=carousel
            if media_type == 8:
                ptype = "carousel"
            elif media_type == 2:
                ptype = "reel" if getattr(media, "product_type", "") == "clips" else "video"
            else:
                ptype = "post"

            shortcode = media.code or str(media.pk)

            # Accounts tagged in the post — keeps (x, y) position, not just identity
            tagged_accounts: list[dict] = []
            try:
                for tag in getattr(media, "usertags", None) or []:
                    tagged_accounts.append(_usertag_to_dict(tag))
            except Exception:
                pass

            # Per-slide data for carousels — resource-level usertags/media types
            # would otherwise be lost since only the top-level media surfaces above.
            carousel_resources: list[dict] = []
            try:
                for r in getattr(media, "resources", None) or []:
                    carousel_resources.append({
                        "pk":            str(getattr(r, "pk", "") or ""),
                        "media_type":    getattr(r, "media_type", None),
                        "thumbnail_url": str(getattr(r, "thumbnail_url", "") or ""),
                        "video_url":     str(getattr(r, "video_url", "") or "") or None,
                        "usertags": [
                            _usertag_to_dict(t) for t in (getattr(r, "usertags", None) or [])
                        ],
                    })
            except Exception:
                pass

            # Comments — opt-in, since each post costs an extra request (or
            # many, when uncapped). Skipped for accounts with zero comments
            # or when the caller didn't ask for them.
            comments: list[dict] = []
            if fetch_comments and not user.is_private and (media.comment_count or 0) > 0:
                comments = _fetch_comments(cl, media.pk, comment_limit, username, shortcode)

            posts.append(Post(
                external_id=shortcode,
                text=media.caption_text or "",
                timestamp=media.taken_at.timestamp() if media.taken_at else 0.0,
                metadata={
                    "type":                  ptype,
                    "pk":                    str(getattr(media, "pk", "") or ""),
                    "id":                    getattr(media, "id", None),
                    "product_type":          getattr(media, "product_type", "") or "",
                    "url":                   f"https://www.instagram.com/p/{shortcode}/",
                    "images":                images,
                    "is_video":              media_type == 2,
                    "video_url":             str(getattr(media, "video_url", "") or "") or None,
                    "video_duration":        getattr(media, "video_duration", None),
                    "title":                 getattr(media, "title", "") or "",
                    "like_count":            media.like_count,
                    "comment_count":         media.comment_count,
                    "comments":              comments,
                    "comments_fetched":      len(comments),
                    "video_view_count":      getattr(media, "view_count", None) if media_type == 2 else None,
                    "play_count":            getattr(media, "play_count", None),
                    "location":              media.location.name if media.location else None,
                    "location_detail":       _location_to_dict(media.location),
                    "accessibility_caption": getattr(media, "accessibility_caption", None),
                    "tagged_accounts":       tagged_accounts,
                    "carousel_resources":    carousel_resources,
                },
            ))

        # ── Social graph (opt-in — costs extra requests, so off by default) ──
        network_posts: list[Post] = []
        if include_social_graph:
            try:
                network_posts = self._collect_social_graph(
                    username, user_id, user.is_private,
                    user.follower_count, user.following_count,
                    follower_limit, following_limit,
                )
            except (ValueError, Exception) as exc:
                log.warning(
                    "Instagram: social graph failed for @%s — returning profile+posts without it. Error: %s",
                    username, exc,
                )

        all_posts = posts + network_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)

        total_comments = sum(p.metadata.get("comments_fetched", 0) for p in posts)
        log.info(
            "Instagram ✓: @%s — %d posts collected (private=%s), %d comments fetched",
            username, len(posts), user.is_private, total_comments,
        )

        return AccountProfile(
            platform="instagram",
            username=username,
            display_name=user.full_name or username,
            bio=user.biography or "",
            location="",
            profile_image_url=str(user.profile_pic_url) if user.profile_pic_url else "",
            created_utc=None,
            posts=all_posts,
            follower_count=user.follower_count,
            following_count=user.following_count,
            extra={
                "is_private":   user.is_private,
                "is_verified":  getattr(user, "is_verified", None),
                "is_business":  getattr(user, "is_business", None),
                "media_count":  getattr(user, "media_count", None),
                "external_url": str(getattr(user, "external_url", "") or "") or None,
            },
        )

    # ------------------------------------------------------------------
    # Streaming collection
    # ------------------------------------------------------------------
    def collect_streaming(
        self,
        username: str,
        limit: int = 100,
        include_social_graph: bool = True,
        follower_limit: int = 0,
        following_limit: int = 0,
        fetch_comments: bool = False,
        inline_comment_cap: int = 50,
        on_profile=None,
        on_post=None,
        on_extra_comments=None,
    ) -> AccountProfile:
        """
        Streaming variant of collect().

        Instead of blocking until EVERY post and EVERY comment has been
        fetched before returning anything, this processes the timeline one
        post at a time so each post can be persisted/displayed the moment
        it's ready:

          1. Profile is fetched → on_profile(profile) fires once.
          2. For each post (oldest-fetched-first, i.e. as instagrapi returns
             them):
               - up to `inline_comment_cap` comments are fetched
                 synchronously and attached to the post.
               - on_post(post) fires immediately — the caller is expected to
                 persist it (e.g. to Postgres) and/or push it to the
                 frontend right here, without waiting for other posts.
               - if the post actually has MORE than `inline_comment_cap`
                 comments, a background thread is spawned to page through
                 ALL of them (amount=0). Collection moves on to the next
                 post immediately — it does NOT wait on this thread.
                 When the background thread finishes, it invokes
                 on_extra_comments(shortcode, full_comment_list) with the
                 complete comment set for that post, so the caller can
                 overwrite what's stored/displayed for it. This may fire
                 well after collect_streaming() has already returned.
          3. Social graph (followers/following), if requested, is collected
             last and streamed through on_post as synthetic "network" posts,
             same as collect().

        Returns the same AccountProfile shape as collect() (posts sorted
        newest-first) once every post has fired on_post — note background
        comment threads may still be running when this returns.
        """
        username = username.strip().lstrip("@")
        self._ensure_client()
        cl = self._client
        bg_threads: list[threading.Thread] = []

        log.info(
            "Instagram (streaming): collecting @%s (limit=%s, comments=%s, inline_cap=%d)",
            username, limit or "unlimited", fetch_comments, inline_comment_cap,
        )

        # ── Profile ────────────────────────────────────────────────────────
        try:
            with self._client_lock:
                user_id = cl.user_id_from_username(username)
                user = cl.user_info(user_id)
        except UserNotFound as exc:
            raise ValueError(f"Instagram user '@{username}' not found.") from exc
        except PrivateAccount as exc:
            raise ValueError(
                f"Instagram user '@{username}' has a private profile — "
                "ARIA does not bypass privacy settings."
            ) from exc
        except LoginRequired as exc:
            raise ValueError(
                "Instagram: session expired mid-collection. "
                "Re-extract INSTAGRAM_SESSION_ID from your browser."
            ) from exc
        except RateLimitError as exc:
            raise ValueError(
                f"Instagram: rate limited fetching @{username}. "
                "Wait a few minutes before retrying."
            ) from exc
        except ClientError as exc:
            raise ValueError(
                f"Instagram: error fetching profile for @{username} — {exc}"
            ) from exc

        profile = AccountProfile(
            platform="instagram",
            username=username,
            display_name=user.full_name or username,
            bio=user.biography or "",
            location="",
            profile_image_url=str(user.profile_pic_url) if user.profile_pic_url else "",
            created_utc=None,
            posts=[],
            follower_count=user.follower_count,
            following_count=user.following_count,
            extra={
                "is_private":   user.is_private,
                "is_verified":  getattr(user, "is_verified", None),
                "is_business":  getattr(user, "is_business", None),
                "media_count":  getattr(user, "media_count", None),
                "external_url": str(getattr(user, "external_url", "") or "") or None,
            },
        )
        if on_profile:
            try:
                on_profile(profile)
            except Exception:
                log.exception("Instagram: on_profile callback failed for @%s", username)

        # ── Posts ──────────────────────────────────────────────────────────
        posts: list[Post] = []

        if user.is_private:
            log.info("Instagram: @%s is private — skipping posts, returning profile only.", username)
            medias = []
        else:
            try:
                with self._client_lock:
                    medias = cl.user_medias(user_id, amount=limit)
            except PrivateAccount:
                medias = []
                log.warning("Instagram: @%s private — no posts collected.", username)
            except RateLimitError as exc:
                raise ValueError(
                    f"Instagram: rate limited fetching posts for @{username}. "
                    "Wait a few minutes before retrying."
                ) from exc
            except ClientError as exc:
                raise ValueError(
                    f"Instagram: error fetching posts for @{username} — {exc}"
                ) from exc

        for media in medias:
            images: list[str] = []
            try:
                if media.resources:  # carousel
                    images = [str(r.thumbnail_url) for r in media.resources if r.thumbnail_url]
                elif media.thumbnail_url:
                    images = [str(media.thumbnail_url)]
            except Exception:
                pass

            media_type = getattr(media, "media_type", None)
            if media_type == 8:
                ptype = "carousel"
            elif media_type == 2:
                ptype = "reel" if getattr(media, "product_type", "") == "clips" else "video"
            else:
                ptype = "post"

            shortcode = media.code or str(media.pk)

            tagged_accounts: list[dict] = []
            try:
                for tag in getattr(media, "usertags", None) or []:
                    tagged_accounts.append(_usertag_to_dict(tag))
            except Exception:
                pass

            carousel_resources: list[dict] = []
            try:
                for r in getattr(media, "resources", None) or []:
                    carousel_resources.append({
                        "pk":            str(getattr(r, "pk", "") or ""),
                        "media_type":    getattr(r, "media_type", None),
                        "thumbnail_url": str(getattr(r, "thumbnail_url", "") or ""),
                        "video_url":     str(getattr(r, "video_url", "") or "") or None,
                        "usertags": [
                            _usertag_to_dict(t) for t in (getattr(r, "usertags", None) or [])
                        ],
                    })
            except Exception:
                pass

            # ── Comments: fetch only up to inline_comment_cap here so the
            # post can display right away. Anything beyond the cap is
            # backgrounded (see below) instead of blocking this post — and
            # therefore every subsequent post — from showing up.
            comments: list[dict] = []
            comment_count = media.comment_count or 0
            needs_background = False
            if fetch_comments and not user.is_private and comment_count > 0:
                with self._client_lock:
                    comments = _fetch_comments_capped(
                        cl, media.pk, inline_comment_cap, username, shortcode
                    )
                needs_background = comment_count > len(comments)

            post = Post(
                external_id=shortcode,
                text=media.caption_text or "",
                timestamp=media.taken_at.timestamp() if media.taken_at else 0.0,
                metadata={
                    "type":                  ptype,
                    "pk":                    str(getattr(media, "pk", "") or ""),
                    "id":                    getattr(media, "id", None),
                    "product_type":          getattr(media, "product_type", "") or "",
                    "url":                   f"https://www.instagram.com/p/{shortcode}/",
                    "images":                images,
                    "is_video":              media_type == 2,
                    "video_url":             str(getattr(media, "video_url", "") or "") or None,
                    "video_duration":        getattr(media, "video_duration", None),
                    "title":                 getattr(media, "title", "") or "",
                    "like_count":            media.like_count,
                    "comment_count":         media.comment_count,
                    "comments":              comments,
                    "comments_fetched":      len(comments),
                    "comments_pending":      needs_background,
                    "video_view_count":      getattr(media, "view_count", None) if media_type == 2 else None,
                    "play_count":            getattr(media, "play_count", None),
                    "location":              media.location.name if media.location else None,
                    "location_detail":       _location_to_dict(media.location),
                    "accessibility_caption": getattr(media, "accessibility_caption", None),
                    "tagged_accounts":       tagged_accounts,
                    "carousel_resources":    carousel_resources,
                },
            )
            posts.append(post)

            # Fire the callback for THIS post right now — don't wait for
            # comments beyond the cap, and don't wait for other posts.
            if on_post:
                try:
                    on_post(post)
                except Exception:
                    log.exception(
                        "Instagram: on_post callback failed for @%s/%s", username, shortcode
                    )

            # Kick off the "rest of the comments" fetch in the background
            # and move straight on to the next post.
            if needs_background and on_extra_comments:
                def _bg_fetch(pk=media.pk, sc=shortcode, cc=comment_count):
                    with self._client_lock:
                        full = _fetch_comments(cl, pk, 0, username, sc)
                    log.info(
                        "Instagram: background comment fetch done for @%s/%s — %d/%d comments",
                        username, sc, len(full), cc,
                    )
                    try:
                        on_extra_comments(sc, full)
                    except Exception:
                        log.exception(
                            "Instagram: on_extra_comments callback failed for @%s/%s",
                            username, sc,
                        )

                t = threading.Thread(target=_bg_fetch, daemon=True)
                t.start()
                bg_threads.append(t)

        # ── Social graph (opt-in — costs extra requests, so off by default) ──
        network_posts: list[Post] = []
        if include_social_graph:
            try:
                with self._client_lock:
                    network_posts = self._collect_social_graph(
                        username, user_id, user.is_private,
                        user.follower_count, user.following_count,
                        follower_limit, following_limit,
                    )
            except (ValueError, Exception) as exc:
                log.warning(
                    "Instagram: social graph failed for @%s — returning profile+posts without it. Error: %s",
                    username, exc,
                )

        for net_post in network_posts:
            if on_post:
                try:
                    on_post(net_post)
                except Exception:
                    log.exception(
                        "Instagram: on_post callback failed for @%s network post", username
                    )

        all_posts = posts + network_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)
        profile.posts = all_posts

        total_comments = sum(p.metadata.get("comments_fetched", 0) for p in posts)
        pending = sum(1 for p in posts if p.metadata.get("comments_pending"))
        log.info(
            "Instagram ✓ (streaming): @%s — %d posts collected (private=%s), "
            "%d comments fetched inline, %d post(s) with comment fetches still running in background",
            username, len(posts), user.is_private, total_comments, pending,
        )

        return profile
