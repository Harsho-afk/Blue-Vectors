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
            "Your INSTAGRAM_SESSION_ID may have expired — re-extract it from "
            "DevTools → Application → Cookies → https://www.instagram.com"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Instagram: login_by_sessionid failed — {exc}"
        ) from exc

    log.info("Instagram: logged in via sessionid (username=%s)", username)
    return cl


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

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
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

            posts.append(Post(
                external_id=shortcode,
                text=media.caption_text or "",
                timestamp=media.taken_at.timestamp() if media.taken_at else 0.0,
                metadata={
                    "type":             ptype,
                    "url":              f"https://www.instagram.com/p/{shortcode}/",
                    "images":           images,
                    "is_video":         media_type == 2,
                    "like_count":       media.like_count,
                    "comment_count":    media.comment_count,
                    "video_view_count": getattr(media, "view_count", None) if media_type == 2 else None,
                    "location":         media.location.name if media.location else None,
                    "accessibility_caption": getattr(media, "accessibility_caption", None),
                },
            ))

        posts.sort(key=lambda p: p.timestamp, reverse=True)
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
            posts=posts,
            follower_count=user.follower_count,
            following_count=user.following_count,
            extra={"is_private": user.is_private},
        )
