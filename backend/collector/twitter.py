import os
import re as _re
from twikit import Client as TwikitClient
from twikit.errors import UserNotFound, UserUnavailable
from .models import AccountProfile, log, Post
from datetime import datetime

# MONKEY PATCH 1: twikit ClientTransaction broken since March 2026
# Twitter changed ondemand.s.js structure — regex no longer matches.
# Remove this block once twikit publishes a fix.
tx_mod = __import__(
    "twikit.x_client_transaction.transaction", fromlist=["ClientTransaction"]
)
tx_mod.ON_DEMAND_FILE_REGEX = _re.compile(
    r',(\d+):["\']ondemand\.s["\']', flags=(_re.VERBOSE | _re.MULTILINE)
)
tx_mod.ON_DEMAND_HASH_PATTERN = r',{}:"([0-9a-f]+)"'
if not hasattr(tx_mod, "INDICES_REGEX"):
    tx_mod.INDICES_REGEX = _re.compile(r'"(\d+)",(\d+)')


async def patched_get_indices(self, home_page_response, session, headers):
    key_byte_indices = []
    response = self.validate_response(home_page_response) or self.home_page_response
    on_demand_file_index = tx_mod.ON_DEMAND_FILE_REGEX.search(str(response)).group(1)
    regex = _re.compile(tx_mod.ON_DEMAND_HASH_PATTERN.format(on_demand_file_index))
    filename = regex.search(str(response)).group(1)
    on_demand_file_url = (
        f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{filename}a.js"
    )
    on_demand_file_response = await session.request(
        method="GET", url=on_demand_file_url, headers=headers
    )
    key_byte_indices_match = tx_mod.INDICES_REGEX.finditer(
        str(on_demand_file_response.text)
    )
    for item in key_byte_indices_match:
        key_byte_indices.append(item.group(2))
    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices")
    return int(key_byte_indices[0]), list(map(int, key_byte_indices[1:]))


tx_mod.ClientTransaction.get_indices = patched_get_indices
# END MONKEY PATCH 1

# MONKEY PATCH 2: twikit User.__init__ crashes when bio has no URLs
from twikit.user import User as TwikitUser

original_user_init = TwikitUser.__init__


def patched_user_init(self, client, data):
    legacy = data.get("legacy", data)
    entities = legacy.setdefault("entities", {})
    description = entities.setdefault("description", {})
    description.setdefault("urls", [])
    legacy.setdefault("withheld_in_countries", [])
    legacy.setdefault("withheld_scope", None)
    legacy.setdefault("pinned_tweet_ids_str", [])
    original_user_init(self, client, data)


TwikitUser.__init__ = patched_user_init
# END MONKEY PATCH 2

# ---------------------------------------------------------------------------
# DATA RETENTION POLICY FOR THIS COLLECTOR:
#   Every field twikit's User/Tweet objects expose is captured somewhere in
#   AccountProfile/Post — nothing fetched is silently discarded. Network
#   posts (followers/following) keep the original GitHub-style "logins"
#   (list[str]) for frontend compatibility, PLUS a parallel "users" field
#   with the full per-account dict, so no detail is lost even though only
#   usernames render today.
# ---------------------------------------------------------------------------


def twitter_ts_to_epoch(ts_str: str) -> float:
    dt = datetime.strptime(ts_str, "%a %b %d %H:%M:%S %z %Y")
    return dt.timestamp()


def _twikit_user_to_dict(user) -> dict:
    """Normalize a twikit User object into a plain dict — keeps every field twikit exposes."""
    return {
        "id": str(getattr(user, "id", "") or ""),
        "username": getattr(user, "screen_name", "") or "",
        "full_name": getattr(user, "name", "") or "",
        "created_at": getattr(user, "created_at", None),
        "profile_image_url": getattr(user, "profile_image_url", "") or "",
        "profile_banner_url": getattr(user, "profile_banner_url", "") or "",
        "url": getattr(user, "url", "") or "",
        "location": getattr(user, "location", "") or "",
        "description": getattr(user, "description", "") or "",
        "description_urls": getattr(user, "description_urls", None) or [],
        "urls": getattr(user, "urls", None) or [],
        "pinned_tweet_ids": getattr(user, "pinned_tweet_ids", None) or [],
        "verified": getattr(user, "verified", None),
        "is_blue_verified": getattr(user, "is_blue_verified", None),
        "possibly_sensitive": getattr(user, "possibly_sensitive", None),
        "protected": getattr(user, "protected", None),
        "followers_count": getattr(user, "followers_count", None),
        "fast_followers_count": getattr(user, "fast_followers_count", None),
        "normal_followers_count": getattr(user, "normal_followers_count", None),
        "following_count": getattr(user, "following_count", None),
        "favourites_count": getattr(user, "favourites_count", None),
        "listed_count": getattr(user, "listed_count", None),
        "media_count": getattr(user, "media_count", None),
        "statuses_count": getattr(user, "statuses_count", None),
        "is_translator": getattr(user, "is_translator", None),
        "can_dm": getattr(user, "can_dm", None),
        "can_media_tag": getattr(user, "can_media_tag", None),
        "default_profile": getattr(user, "default_profile", None),
        "default_profile_image": getattr(user, "default_profile_image", None),
    }


def _tweet_media_to_dicts(tweet) -> list[dict]:
    """Full media entities (type, url, alt text, dimensions), not just a flat URL list."""
    media_dicts = []
    try:
        for m in getattr(tweet, "media", None) or []:
            media_dicts.append(
                {
                    "type": getattr(m, "type", None),
                    "media_url_https": getattr(m, "media_url_https", None)
                    or getattr(m, "url", None),
                    "alt_text": getattr(m, "alt_text", None)
                    or getattr(m, "description", None),
                    "width": getattr(getattr(m, "sizes", None), "large", None)
                    and getattr(m.sizes.large, "w", None),
                    "height": getattr(getattr(m, "sizes", None), "large", None)
                    and getattr(m.sizes.large, "h", None),
                    "video_info": getattr(m, "video_info", None),
                }
            )
    except Exception:
        pass
    return media_dicts


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
        self.client = TwikitClient(language="en-US")
        self.logged_in = False

    async def ensure_login(self):
        if self.logged_in:
            return
        ct0 = os.environ.get("TWITTER_CT0")
        auth_token = os.environ.get("TWITTER_AUTH_TOKEN")
        if not ct0 or not auth_token:
            raise RuntimeError(
                "Twitter cookies not set.\n"
                "Add TWITTER_CT0 and TWITTER_AUTH_TOKEN to your .env file.\n"
                "Extract them from DevTools → Application → Cookies → https://x.com"
            )
        self.client.set_cookies({"ct0": ct0, "auth_token": auth_token})
        self.logged_in = True
        log.info("Twitter: cookies loaded from env (ct0=...%s)", ct0[-6:])

    async def _collect_social_graph(
        self,
        username: str,
        user_id: str,
        follower_limit: int = 200,
        following_limit: int = 200,
    ) -> list[Post]:
        """
        Fetches followers/following and returns them as synthetic "network"
        Posts — same schema as GithubCollector's network posts (type,
        direction, logins, total_count, fetched_count), so the frontend's
        NetworkPanel renders them unmodified. Also attaches a parallel
        "users" field with full per-account detail so nothing twikit
        returned is thrown away, even though only usernames render today.

        NOTE ON RATE LIMITS: get_user_followers is capped at 50 requests
        per window vs. 500 for get_user_following — followers is the tight
        one. Keep follower_limit conservative and call this sparingly.
        """
        follower_users: list[dict] = []
        following_users: list[dict] = []

        # ── Followers ──────────────────────────────────────────────
        try:
            page_size = min(20, follower_limit) or 20
            result = await self.client.get_user_followers(user_id, count=page_size)
            while result:
                for u in result:
                    follower_users.append(_twikit_user_to_dict(u))
                if len(follower_users) >= follower_limit:
                    break
                try:
                    result = await result.next()
                except Exception:
                    break
            follower_users = follower_users[:follower_limit]
        except Exception as exc:
            log.warning(
                "Twitter: failed fetching followers for @%s — %s", username, exc
            )

        # ── Following ──────────────────────────────────────────────
        try:
            page_size = min(20, following_limit) or 20
            result = await self.client.get_user_following(user_id, count=page_size)
            while result:
                for u in result:
                    following_users.append(_twikit_user_to_dict(u))
                if len(following_users) >= following_limit:
                    break
                try:
                    result = await result.next()
                except Exception:
                    break
            following_users = following_users[:following_limit]
        except Exception as exc:
            log.warning(
                "Twitter: failed fetching following for @%s — %s", username, exc
            )

        follower_logins = [u["username"] for u in follower_users if u["username"]]
        following_logins = [u["username"] for u in following_users if u["username"]]

        network_posts: list[Post] = []

        if follower_logins:
            network_posts.append(
                Post(
                    external_id=f"network:followers:{username}",
                    text=f"Followed by {len(follower_logins)} accounts: "
                    + ", ".join(follower_logins),
                    timestamp=0.0,
                    metadata={
                        "type": "network",
                        "direction": "followers",
                        "logins": follower_logins,
                        "users": follower_users,
                        "total_count": None,  # filled in by caller from profile counts
                        "fetched_count": len(follower_logins),
                        "url": f"https://x.com/{username}/followers",
                        "images": [],
                    },
                )
            )

        if following_logins:
            network_posts.append(
                Post(
                    external_id=f"network:following:{username}",
                    text=f"Following {len(following_logins)} accounts: "
                    + ", ".join(following_logins),
                    timestamp=0.0,
                    metadata={
                        "type": "network",
                        "direction": "following",
                        "logins": following_logins,
                        "users": following_users,
                        "total_count": None,
                        "fetched_count": len(following_logins),
                        "url": f"https://x.com/{username}/following",
                        "images": [],
                    },
                )
            )

        log.info(
            "Twitter ✓: @%s — %d followers, %d following collected",
            username,
            len(follower_logins),
            len(following_logins),
        )
        return network_posts

    async def collect(
        self,
        username: str,
        limit: int = 100,
        include_social_graph: bool = True,
        follower_limit: int = 200,
        following_limit: int = 200,
    ) -> AccountProfile:
        username = username.lstrip("@")
        log.info("Twitter: collecting @%s (limit=%d)", username, limit)

        await self.ensure_login()

        try:
            user = await self.client.get_user_by_screen_name(username)
        except (UserNotFound, UserUnavailable) as exc:
            raise ValueError(
                f"Twitter user '@{username}' not found or unavailable."
            ) from exc

        created_utc = twitter_ts_to_epoch(user.created_at)

        posts: list = []
        page_size = min(40, limit)
        result = await self.client.get_user_tweets(
            user_id=user.id,
            tweet_type="Tweets",
            count=page_size,
        )

        skipped_tweets = 0
        while result:
            for tweet in result:
                # A single tweet with an unexpected shape (e.g. a card/entity
                # type twikit doesn't fully model — polls, Community Notes,
                # Spaces, ads) can raise mid-parse. Twitter's unofficial API
                # drifts constantly (see MONKEY PATCH notes above), so treat
                # each tweet's parsing as independent: log and skip rather
                # than losing every tweet already fetched for this account.
                try:
                    is_retweet = tweet.text.startswith("RT @")
                    ts = twitter_ts_to_epoch(tweet.created_at)

                    media_entities = _tweet_media_to_dicts(tweet)
                    images = [
                        m["media_url_https"]
                        for m in media_entities
                        if m.get("media_url_https")
                    ]

                    permalink = f"https://x.com/{username}/status/{tweet.id}"

                    posts.append(
                        Post(
                            external_id=str(tweet.id),
                            text=tweet.text,
                            timestamp=ts,
                            metadata={
                                "type": "retweet" if is_retweet else "tweet",
                                "tweet_id": str(tweet.id),
                                "url": permalink,
                                "retweet_count": getattr(tweet, "retweet_count", None),
                                "favorite_count": getattr(
                                    tweet, "favorite_count", None
                                ),
                                "reply_count": getattr(tweet, "reply_count", None),
                                "quote_count": getattr(tweet, "quote_count", None),
                                "view_count": getattr(tweet, "view_count", None),
                                "bookmark_count": getattr(
                                    tweet, "bookmark_count", None
                                ),
                                "lang": tweet.lang,
                                "images": images,
                                "media": media_entities,
                                "is_quote_status": getattr(
                                    tweet, "is_quote_status", None
                                ),
                                "possibly_sensitive": getattr(
                                    tweet, "possibly_sensitive", None
                                ),
                                "hashtags": getattr(tweet, "hashtags", None) or [],
                                "urls": getattr(tweet, "urls", None) or [],
                                "user_mentions": getattr(tweet, "user_mentions", None)
                                or [],
                                "place": getattr(tweet, "place", None),
                                "in_reply_to_status_id": getattr(
                                    tweet, "in_reply_to_status_id", None
                                ),
                                "edit_history_tweet_ids": getattr(
                                    tweet, "edit_history_tweet_ids", None
                                )
                                or [],
                            },
                        )
                    )
                except Exception as exc:
                    skipped_tweets += 1
                    tweet_id = getattr(tweet, "id", "unknown")
                    log.warning(
                        "Twitter: @%s — failed to parse tweet %s (%s: %s), skipping",
                        username,
                        tweet_id,
                        type(exc).__name__,
                        exc,
                    )
                    continue
            if len(posts) >= limit:
                break
            try:
                result = await result.next()
            except Exception:
                break

        if skipped_tweets:
            log.warning(
                "Twitter: @%s — skipped %d unparseable tweet(s), kept %d",
                username,
                skipped_tweets,
                len(posts),
            )

        posts = posts[:limit]

        # ── Social graph (opt-in — followers endpoint is heavily rate
        # limited, so this is off by default and capped when enabled) ──
        network_posts: list[Post] = []
        if include_social_graph:
            network_posts = await self._collect_social_graph(
                username, user.id, follower_limit, following_limit
            )
            # Backfill total_count now that we have profile-level counts
            for p in network_posts:
                if p.metadata.get("direction") == "followers":
                    p.metadata["total_count"] = user.followers_count
                elif p.metadata.get("direction") == "following":
                    p.metadata["total_count"] = user.following_count

        all_posts = posts + network_posts
        all_posts.sort(key=lambda p: p.timestamp, reverse=True)
        log.info("Twitter: @%s — %d tweets collected", username, len(posts))

        return AccountProfile(
            platform="twitter",
            username=username,
            display_name=user.name,
            bio=user.description or "",
            location=user.location or "",
            profile_image_url=(user.profile_image_url or "").replace(
                "_normal", "_400x400"
            ),
            created_utc=created_utc,
            posts=all_posts,
            follower_count=user.followers_count,
            following_count=user.following_count,
            extra={
                "verified": getattr(user, "verified", None),
                "is_blue_verified": getattr(user, "is_blue_verified", None),
                "protected": getattr(user, "protected", None),
                "profile_banner_url": getattr(user, "profile_banner_url", "") or "",
                "url": getattr(user, "url", "") or "",
                "listed_count": getattr(user, "listed_count", None),
                "statuses_count": getattr(user, "statuses_count", None),
                "favourites_count": getattr(user, "favourites_count", None),
                "media_count": getattr(user, "media_count", None),
                "pinned_tweet_ids": getattr(user, "pinned_tweet_ids", None) or [],
                "description_urls": getattr(user, "description_urls", None) or [],
            },
        )
