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


def twitter_ts_to_epoch(ts_str: str) -> float:
    dt = datetime.strptime(ts_str, "%a %b %d %H:%M:%S %z %Y")
    return dt.timestamp()


# Twitter collector  (twikit — browser cookies)
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

    async def collect(self, username: str, limit: int = 100) -> AccountProfile:
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

        while result:
            for tweet in result:
                if tweet.text.startswith("RT @"):
                    continue
                ts = twitter_ts_to_epoch(tweet.created_at)

                images = []
                try:
                    media_list = getattr(tweet, "media", None) or []
                    for m in media_list:
                        media_url = getattr(m, "media_url_https", None) or getattr(
                            m, "url", None
                        )
                        if media_url:
                            images.append(media_url)
                except Exception:
                    pass

                permalink = f"https://x.com/{username}/status/{tweet.id}"

                posts.append(
                    Post(
                        external_id=str(tweet.id),
                        text=tweet.text,
                        timestamp=ts,
                        metadata={
                            "type": "tweet",
                            "tweet_id": str(tweet.id),
                            "url": permalink,
                            "retweet_count": tweet.retweet_count,
                            "favorite_count": tweet.favorite_count,
                            "reply_count": tweet.reply_count,
                            "lang": tweet.lang,
                            "images": images,
                        },
                    )
                )
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
            profile_image_url=(user.profile_image_url or "").replace(
                "_normal", "_400x400"
            ),
            created_utc=created_utc,
            posts=posts,
            follower_count=user.followers_count,
            following_count=user.following_count,
        )
