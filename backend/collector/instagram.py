import os
import time
import random
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
)

# Anonymous, public-data-only collection — no login, no session cookies.
# We never authenticate as the target or as any other account; this only
# reads what Instagram already serves to a logged-out visitor. Private
# profiles are therefore inaccessible and correctly raise an error rather
# than being bypassed.
#
# NOTE (2025): Instagram has progressively moved profile data behind
# authentication walls. The /graphql/query endpoint now returns 403 for
# anonymous requests on most profiles. This is a platform-level restriction,
# not a bug. Instagram collection is therefore unreliable in anonymous mode
# and is disabled for the hackathon demo. The architecture supports adding
# authenticated collection post-hackathon with proper rate limiting and a
# dedicated session account.
#
# Throttle between paginated requests to stay a reasonable, low-volume
# anonymous client and reduce (not eliminate) the chance of a 429/checkpoint.
REQUEST_DELAY_SECONDS = float(os.environ.get("INSTAGRAM_REQUEST_DELAY", "1.5"))

# Human-readable explanation shown in the UI when Instagram blocks us
_INSTAGRAM_BLOCKED_MSG = (
    "Instagram now requires authentication for profile data — anonymous access "
    "returns 403 Forbidden. This is a platform-level restriction introduced in "
    "2024/2025, not a bug. Instagram collection has been deprioritized for the "
    "hackathon; it will be added post-demo with a dedicated session account and "
    "proper rate limiting."
)


def _build_loader() -> instaloader.Instaloader:
    """Construct an anonymous Instaloader context — no login, no metadata download to disk."""
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
        max_connection_attempts=1,
    )


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


def _is_auth_required_error(exc: Exception) -> bool:
    """
    Return True if the exception indicates Instagram is demanding authentication.

    Instaloader surfaces this in several ways depending on the endpoint and
    instaloader version: QueryReturnedForbiddenException, LoginRequiredException,
    or a ConnectionException whose message contains '403'.
    """
    if isinstance(
        exc,
        (
            QueryReturnedForbiddenException,
            LoginRequiredException,
            QueryReturnedBadRequestException,
        ),
    ):
        return True
    if isinstance(exc, ConnectionException):
        msg = str(exc).lower()
        if "403" in msg or "forbidden" in msg or "graphql" in msg:
            return True
    return False


class InstagramCollector:
    """Collects public Instagram profile + post data anonymously via instaloader.

    No login, no session cookies, no Stories (Stories are never public and are
    intentionally out of scope — see README). Reels and carousel posts are
    folded into the regular post stream with a `type` tag.

    As of 2025, Instagram's /graphql/query endpoint returns 403 for anonymous
    requests on most profiles. When this happens the collector raises a clear
    ValueError rather than crashing with a stack trace. See _INSTAGRAM_BLOCKED_MSG.
    """

    def __init__(self):
        self.loader = _build_loader()

    def _throttle(self):
        time.sleep(REQUEST_DELAY_SECONDS + random.uniform(0, 0.5))

    def collect(self, username: str, limit: int = 100) -> AccountProfile:
        """Collect and return an AccountProfile for the given Instagram username."""
        username = username.strip().lstrip("@")
        log.info("Instagram [anonymous]: collecting @%s (limit=%d)", username, limit)

        try:
            profile = instaloader.Profile.from_username(self.loader.context, username)
        except ProfileNotExistsException as exc:
            raise ValueError(f"Instagram user '@{username}' not found.") from exc
        except QueryReturnedForbiddenException as exc:
            log.warning(
                "Instagram: 403 Forbidden fetching @%s — auth wall hit", username
            )
            raise ValueError(_INSTAGRAM_BLOCKED_MSG) from exc
        except LoginRequiredException as exc:
            log.warning(
                "Instagram: login required fetching @%s — auth wall hit", username
            )
            raise ValueError(_INSTAGRAM_BLOCKED_MSG) from exc
        except TooManyRequestsException as exc:
            raise ValueError(
                "Instagram: rate limited by anonymous access. Try again later — "
                "this collector intentionally does not use login to bypass this."
            ) from exc
        except ConnectionException as exc:
            # Catch 403 surfaced as a generic ConnectionException
            if _is_auth_required_error(exc):
                log.warning(
                    "Instagram: auth wall (ConnectionException) for @%s — %s",
                    username,
                    exc,
                )
                raise ValueError(_INSTAGRAM_BLOCKED_MSG) from exc
            raise ValueError(
                f"Instagram: connection error fetching @{username} — {exc}"
            ) from exc

        if profile.is_private:
            raise ValueError(
                f"Instagram user '@{username}' has a private profile — "
                "ARIA does not bypass privacy settings, so no post data is available."
            )

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

        except (
            QueryReturnedForbiddenException,
            LoginRequiredException,
            QueryReturnedBadRequestException,
        ) as exc:
            if posts:
                # Partial result — return what we got, log the cutoff
                log.warning(
                    "Instagram: auth wall mid-pagination for @%s after %d posts — returning partial",
                    username,
                    len(posts),
                )
            else:
                raise ValueError(_INSTAGRAM_BLOCKED_MSG) from exc

        except PrivateProfileNotFollowedException as exc:
            raise ValueError(
                f"Instagram user '@{username}' is private — cannot collect posts."
            ) from exc

        except TooManyRequestsException as exc:
            log.warning(
                "Instagram: rate limited mid-collection for @%s after %d posts",
                username,
                len(posts),
            )

        except ConnectionException as exc:
            if _is_auth_required_error(exc):
                if posts:
                    log.warning(
                        "Instagram: auth wall (ConnectionException) mid-pagination "
                        "for @%s after %d posts — returning partial",
                        username,
                        len(posts),
                    )
                else:
                    raise ValueError(_INSTAGRAM_BLOCKED_MSG) from exc
            else:
                log.warning(
                    "Instagram: connection error mid-collection for @%s after %d posts — %s",
                    username,
                    len(posts),
                    exc,
                )

        posts.sort(key=lambda p: p.timestamp, reverse=True)

        log.info(
            "Instagram [anonymous] ✓: @%s — %d posts collected",
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
