import os
import time
import random
import json
from pathlib import Path
from .models import AccountProfile, Post, log

import instaloader
from instaloader.exceptions import (
    ProfileNotExistsException,
    PrivateProfileNotFollowedException,
    ConnectionException,
    TooManyRequestsException,
    LoginRequiredException,
    QueryReturnedNotFoundException,
    QueryReturnedForbiddenException,
    QueryReturnedBadRequestException,
    BadCredentialsException,
    InvalidArgumentException,
)

# ---------------------------------------------------------------------------
# Session-based collection — uses a saved instaloader session file.
#
# Instagram's /graphql/query endpoint returns 403 for ALL anonymous requests
# as of 2024/2025. A logged-in session cookie bypasses this entirely, the
# same way TWITTER_CT0 / TWITTER_AUTH_TOKEN bypass Cloudflare for twikit.
#
# How to get a session file:
#   1.  pip install instaloader
#   2.  instaloader --login YOUR_USERNAME
#       (enter password when prompted — this writes ~/.config/instaloader/session-YOUR_USERNAME)
#   3.  Set in .env:
#           INSTAGRAM_SESSION_FILE=~/.config/instaloader/session-YOUR_USERNAME
#       OR
#           INSTAGRAM_USERNAME=YOUR_USERNAME   (path is inferred automatically)
#
# The session file contains a cookie jar, NOT your password.
# Re-run `instaloader --login` if Instagram invalidates the session (~30 days).
#
# WARNING: use a dedicated burner/collector account, never your personal one.
#          Instagram can flag accounts that scrape at high volume.
# ---------------------------------------------------------------------------

REQUEST_DELAY_SECONDS = float(os.environ.get("INSTAGRAM_REQUEST_DELAY", "2.0"))

_SESSION_NOT_CONFIGURED = (
    "Instagram session not configured. "
    "Run: instaloader --login YOUR_USERNAME, then set "
    "INSTAGRAM_SESSION_FILE or INSTAGRAM_USERNAME in .env. "
    "See instagram.py header for full instructions."
)

_AUTH_WALL_MSG = (
    "Instagram returned 403 Forbidden even with a session cookie. "
    "The session may have expired — re-run: instaloader --login YOUR_USERNAME"
)


def _default_session_path(username: str) -> Path:
    """Instaloader's default session path: ~/.config/instaloader/session-<username>"""
    return Path.home() / ".config" / "instaloader" / f"session-{username}"


def _build_loader() -> instaloader.Instaloader:
    """Construct an Instaloader context — no metadata download to disk."""
    return instaloader.Instaloader(
        quiet=True,
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        post_metadata_txt_pattern="",
        max_connection_attempts=2,
    )


def _load_session(loader: instaloader.Instaloader) -> str:
    """
    Load a saved instaloader session into the loader context.
    Returns the session username on success; raises RuntimeError if not configured.
    """
    # Explicit path takes priority
    session_file = os.environ.get("INSTAGRAM_SESSION_FILE", "").strip()
    ig_username = os.environ.get("INSTAGRAM_USERNAME", "").strip()

    if session_file:
        session_path = Path(session_file).expanduser()
    elif ig_username:
        session_path = _default_session_path(ig_username)
    else:
        raise RuntimeError(_SESSION_NOT_CONFIGURED)

    if not session_path.exists():
        raise RuntimeError(
            f"Instagram session file not found: {session_path}\n"
            f"Run: instaloader --login {ig_username or 'YOUR_USERNAME'}"
        )

    try:
        loader.load_session_from_file(ig_username or session_path.stem.replace("session-", ""), session_path)
        session_username = ig_username or session_path.stem.replace("session-", "")
        log.info("Instagram: loaded session from %s (account: %s)", session_path, session_username)
        return session_username
    except Exception as exc:
        raise RuntimeError(
            f"Instagram: failed to load session from {session_path} — {exc}\n"
            f"Re-run: instaloader --login {ig_username or 'YOUR_USERNAME'}"
        ) from exc


def _post_type(post) -> str:
    """Classify an Instaloader Post as 'reel', 'carousel', or 'post'."""
    typename = getattr(post, "typename", "") or ""
    if typename == "GraphSidecar":
        return "carousel"
    if post.is_video:
        return "reel"
    return "post"


def _media_urls(post) -> list:
    """Return display URLs for a post, including all carousel children if present."""
    urls = []
    try:
        if getattr(post, "typename", "") == "GraphSidecar":
            for node in post.get_sidecar_nodes():
                if node.display_url:
                    urls.append(node.display_url)
        elif post.url:
            urls.append(post.url)
    except Exception as exc:
        log.warning(
            "Instagram: failed to extract media URLs for %s — %s", post.shortcode, exc
        )
    return urls


def _is_auth_error(exc: Exception) -> bool:
    """Return True if the exception signals an authentication/403 wall."""
    if isinstance(
        exc,
        (
            QueryReturnedForbiddenException,
            LoginRequiredException,
            QueryReturnedBadRequestException,
            BadCredentialsException,
        ),
    ):
        return True
    if isinstance(exc, ConnectionException):
        msg = str(exc).lower()
        if "403" in msg or "forbidden" in msg or "graphql" in msg:
            return True
    return False


class InstagramCollector:
    """
    Collects public Instagram profile + post data using a saved instaloader
    session (cookie-based auth). Private profiles are still inaccessible —
    the session grants the same view as a logged-in visitor, not admin access.

    Session setup (one-time):
        pip install instaloader
        instaloader --login YOUR_COLLECTOR_USERNAME
        # Set INSTAGRAM_USERNAME=YOUR_COLLECTOR_USERNAME in .env

    Reels and carousel posts are folded into the regular post stream with a
    `type` tag in metadata. Stories are intentionally out of scope.
    """

    def __init__(self):
        self.loader = _build_loader()
        self._session_loaded = False
        self._session_username: str = ""

    def _ensure_session(self):
        if self._session_loaded:
            return
        self._session_username = _load_session(self.loader)
        self._session_loaded = True

    def _throttle(self):
        time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0, 0.75))

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        """Collect and return an AccountProfile for the given Instagram username."""
        username = username.strip().lstrip("@")
        self._ensure_session()

        log.info(
            "Instagram [session=%s]: collecting @%s (limit=%d)",
            self._session_username,
            username,
            limit,
        )

        # ── Fetch profile ──────────────────────────────────────────────────────
        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
        except ProfileNotExistsException as exc:
            raise ValueError(f"Instagram user '@{username}' not found.") from exc
        except QueryReturnedNotFoundException as exc:
            raise ValueError(f"Instagram user '@{username}' not found.") from exc
        except TooManyRequestsException as exc:
            raise ValueError(
                "Instagram: rate limited. Increase INSTAGRAM_REQUEST_DELAY in .env "
                "and try again in a few minutes."
            ) from exc
        except Exception as exc:
            if _is_auth_error(exc):
                log.warning("Instagram: session auth error fetching @%s — %s", username, exc)
                raise ValueError(_AUTH_WALL_MSG) from exc
            raise ValueError(
                f"Instagram: error fetching profile @{username} — {exc}"
            ) from exc

        if profile.is_private:
            raise ValueError(
                f"Instagram user '@{username}' has a private profile — "
                "ARIA does not bypass privacy settings."
            )

        # ── Collect posts ──────────────────────────────────────────────────────
        posts: list = []
        try:
            for raw_post in profile.get_posts():
                if len(posts) >= limit:
                    break

                caption = raw_post.caption or ""
                ptype = _post_type(raw_post)
                images = _media_urls(raw_post)
                permalink = f"https://www.instagram.com/p/{raw_post.shortcode}/"

                like_count = None
                comment_count = None
                try:
                    like_count = raw_post.likes
                    comment_count = raw_post.comments
                except Exception:
                    pass

                posts.append(
                    Post(
                        external_id=raw_post.shortcode,
                        text=caption,
                        timestamp=raw_post.date_utc.timestamp(),
                        metadata={
                            "type": ptype,
                            "url": permalink,
                            "images": images,
                            "is_video": raw_post.is_video,
                            "like_count": like_count,
                            "comment_count": comment_count,
                            "video_view_count": (
                                getattr(raw_post, "video_view_count", None)
                                if raw_post.is_video
                                else None
                            ),
                        },
                    )
                )

                self._throttle()

        except PrivateProfileNotFollowedException as exc:
            raise ValueError(
                f"Instagram user '@{username}' is private — cannot collect posts."
            ) from exc

        except TooManyRequestsException as exc:
            log.warning(
                "Instagram: rate limited mid-collection for @%s after %d posts — "
                "returning partial. Increase INSTAGRAM_REQUEST_DELAY.",
                username,
                len(posts),
            )

        except Exception as exc:
            if _is_auth_error(exc):
                if posts:
                    log.warning(
                        "Instagram: auth error mid-pagination for @%s after %d posts "
                        "— returning partial. Session may have expired.",
                        username,
                        len(posts),
                    )
                else:
                    raise ValueError(_AUTH_WALL_MSG) from exc
            else:
                log.warning(
                    "Instagram: error mid-collection for @%s after %d posts — %s",
                    username,
                    len(posts),
                    exc,
                )

        posts.sort(key=lambda p: p.timestamp, reverse=True)

        log.info(
            "Instagram ✓ [session=%s]: @%s — %d posts collected",
            self._session_username,
            username,
            len(posts),
        )

        return AccountProfile(
            platform="instagram",
            username=profile.username,
            display_name=profile.full_name or profile.username,
            bio=profile.biography or "",
            location="",
            profile_image_url=profile.profile_pic_url or "",
            created_utc=None,
            posts=posts,
            follower_count=profile.followers,
            following_count=profile.followees,
        )
