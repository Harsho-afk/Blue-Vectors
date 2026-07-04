import os
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
# DATA RETENTION POLICY FOR THIS COLLECTOR:
#   Every field instagrapi's pydantic models expose for profile/media/user
#   objects is captured somewhere in AccountProfile/Post — nothing fetched
#   is silently discarded. Network posts (followers/following) keep the
#   original GitHub-style "logins" (list[str]) for frontend compatibility,
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


class InstagramCollector:
    """
    Collects public Instagram profile + post metadata via instagrapi.
    Uses Instagram's private mobile API — the same endpoints as the official app.
    """

    def __init__(self):
        self._client: Client | None = None

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
        follower_limit: int = 200,
        following_limit: int = 200,
    ) -> list[Post]:
        """
        Fetches followers/following and returns them as synthetic "network"
        Posts — same schema as GithubCollector's network posts (type,
        direction, logins, total_count, fetched_count), so the frontend's
        NetworkPanel renders them unmodified. Also attaches a parallel
        "users" field with full per-account detail (pk, full_name,
        profile_pic_url, is_private, is_verified) so nothing instagrapi
        returned is thrown away, even though only usernames render today.

        Capped by follower_limit/following_limit (default 200 each) via
        instagrapi's `amount` param — without a cap, a large account (e.g.
        a brand with millions of followers) would try to paginate its
        entire follower list, which is impractically slow and gets rate
        limited almost immediately.

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
        follower_limit: int = 200,
        following_limit: int = 200,
    ) -> AccountProfile:
        username = username.strip().lstrip("@")
        self._ensure_client()
        cl = self._client

        log.info("Instagram: collecting @%s (limit=%d)", username, limit)

        # ── Profile ────────────────────────────────────────────────────
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

        # ── Posts ──────────────────────────────────────────────────────
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
        log.info(
            "Instagram ✓: @%s — %d posts collected (private=%s)",
            username, len(posts), user.is_private,
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
