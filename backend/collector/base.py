import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from .twitter import TwitterCollector
from .phone import collect_phone  # noqa: F401  (re-exported)
from .reddit import RedditCollector
from .github import GitHubCollector
from .instagram import InstagramCollector
from .models import AccountProfile, PhoneProfile, log  # noqa: F401

load_dotenv()


# PostgreSQL storage helper
def save_account_profile(profile: AccountProfile, conn, case_id: int) -> int:
    """
    Upsert just the account row (no posts). Split out from save_to_db so
    streaming collectors (e.g. Instagram) can persist the account/profile
    the moment it's fetched — before any posts exist — so the frontend has
    something to show right away instead of waiting for the whole
    collection to finish.
    """
    cur = conn.cursor()

    created_at_dt = (
        datetime.fromtimestamp(profile.created_utc, tz=timezone.utc)
        if profile.created_utc is not None
        else None
    )

    # Compute CLIP embedding while the profile image URL is still live
    image_embedding = None
    if profile.profile_image_url:
        try:
            from features import compute_image_embedding
            image_embedding = compute_image_embedding(profile.profile_image_url)
            if image_embedding:
                log.info("CLIP embedding computed for %s/%s", profile.platform, profile.username)
        except Exception as e:
            log.warning("CLIP embedding failed for %s/%s: %s", profile.platform, profile.username, e)

    cur.execute(
        """
        INSERT INTO accounts
            (case_id, platform, username, display_name, bio, location, created_at,
             profile_image_url, image_embedding, karma, follower_count, following_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (case_id, platform, username) DO UPDATE SET
            display_name      = EXCLUDED.display_name,
            bio               = EXCLUDED.bio,
            location          = EXCLUDED.location,
            created_at        = EXCLUDED.created_at,
            profile_image_url = EXCLUDED.profile_image_url,
            image_embedding   = EXCLUDED.image_embedding,
            karma             = EXCLUDED.karma,
            follower_count    = EXCLUDED.follower_count,
            following_count   = EXCLUDED.following_count
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
            json.dumps(image_embedding) if image_embedding else None,
            profile.karma,
            profile.follower_count,
            profile.following_count,
        ),
    )
    account_id: int = cur.fetchone()["id"]
    conn.commit()
    log.info(
        "DB: saved account_id=%d (%s/%s) under case_id=%d",
        account_id,
        profile.platform,
        profile.username,
        case_id,
    )
    return account_id


def save_post(account_id: int, post, conn) -> None:
    """Upsert a single post. Used by streaming collectors so each post can
    be persisted (and therefore visible to the frontend) as soon as it's
    collected, instead of waiting for the entire timeline."""
    cur = conn.cursor()
    post_dt = datetime.fromtimestamp(post.timestamp, tz=timezone.utc)
    cur.execute(
        """
        INSERT INTO posts
        (account_id, external_id, text, timestamp, metadata)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (account_id, external_id)
        DO UPDATE SET
            text     = EXCLUDED.text,
            metadata = EXCLUDED.metadata
        """,
        (
            account_id,
            post.external_id,
            post.text,
            post_dt,
            json.dumps(post.metadata),
        ),
    )
    conn.commit()


def update_post_comments(account_id: int, external_id: str, comments: list, conn) -> None:
    """
    Overwrite a post's comment list (+ comments_fetched/comments_pending)
    once a background thread has finished paging past the inline cap.
    No-op if the post isn't found (e.g. collection failed before it saved).
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT metadata FROM posts WHERE account_id = %s AND external_id = %s",
        (account_id, external_id),
    )
    row = cur.fetchone()
    if not row:
        log.warning(
            "DB: update_post_comments — no post found for account_id=%d external_id=%s",
            account_id, external_id,
        )
        return

    meta = row["metadata"] or {}
    if isinstance(meta, str):
        meta = json.loads(meta)

    meta["comments"] = comments
    meta["comments_fetched"] = len(comments)
    meta["comments_pending"] = False

    cur.execute(
        "UPDATE posts SET metadata = %s WHERE account_id = %s AND external_id = %s",
        (json.dumps(meta), account_id, external_id),
    )
    conn.commit()
    log.info(
        "DB: updated comments for account_id=%d external_id=%s — %d comments (background fetch complete)",
        account_id, external_id, len(comments),
    )


def save_to_db(profile: AccountProfile, conn, case_id: int) -> int:
    """Save a fully-collected AccountProfile (account + all its posts) in
    one shot. For streaming collection, prefer save_account_profile() +
    save_post() per post instead."""
    account_id = save_account_profile(profile, conn, case_id)
    for post in profile.posts:
        save_post(account_id, post, conn)
    return account_id


# Public entry-points
SUPPORTED_PLATFORMS = ("reddit", "twitter", "github", "instagram")


def collect(
    platform: str,
    username: str,
    limit: int = 100,
    include_social_graph: bool = True,
    follower_limit: int = 0,
    following_limit: int = 0,
    fetch_comments: bool = False,
    comment_limit: int = 0,
) -> AccountProfile:
    platform = platform.lower().strip()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform '{platform}'. Choose from: {SUPPORTED_PLATFORMS}"
        )
    if platform == "reddit":
        return RedditCollector().collect(username, limit=limit)
    if platform == "twitter":
        return asyncio.run(collect_twitter(username, limit, include_social_graph))
    if platform == "github":
        return GitHubCollector().collect(username, limit=limit)
    if platform == "instagram":
        return InstagramCollector().collect(
            username,
            limit=limit,
            include_social_graph=include_social_graph,
            follower_limit=follower_limit,
            following_limit=following_limit,
            fetch_comments=fetch_comments,
            comment_limit=comment_limit,
        )
    raise ValueError(f"Unhandled platform: {platform}")


async def collect_async(
    platform: str,
    username: str,
    limit: int = 100,
    include_social_graph: bool = True,
    follower_limit: int = 0,
    following_limit: int = 0,
    fetch_comments: bool = False,
    comment_limit: int = 0,
) -> AccountProfile:
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
        return await collect_twitter(username, limit, include_social_graph)
    if platform == "github":
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: GitHubCollector().collect(username, limit=limit)
        )
    if platform == "instagram":
        # instaloader is synchronous (requests-based) — offload to a thread
        # so it doesn't block FastAPI's event loop, same pattern as Reddit/GitHub.
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: InstagramCollector().collect(
                username,
                limit=limit,
                include_social_graph=include_social_graph,
                follower_limit=follower_limit,
                following_limit=following_limit,
                fetch_comments=fetch_comments,
                comment_limit=comment_limit,
            ),
        )
    raise ValueError(f"Unhandled platform: {platform}")


async def collect_twitter(
    username: str, limit: int, include_social_graph: bool = True
) -> AccountProfile:
    collector = TwitterCollector()
    return await collector.collect(
        username, limit=limit, include_social_graph=include_social_graph
    )


async def collect_instagram_streaming(
    username: str,
    limit: int = 100,
    include_social_graph: bool = True,
    follower_limit: int = 0,
    following_limit: int = 0,
    fetch_comments: bool = True,
    inline_comment_cap: int = 50,
    on_profile=None,
    on_post=None,
    on_extra_comments=None,
) -> AccountProfile:
    """
    Async wrapper around InstagramCollector.collect_streaming(), offloaded
    to a thread the same way collect_async() does for Instagram (instagrapi
    is synchronous/requests-based).

    Unlike collect_async("instagram", ...), this streams: on_profile fires
    once the account is fetched, on_post fires per post (with up to
    inline_comment_cap comments attached), and on_extra_comments fires later
    — possibly after this coroutine has already returned — for any post
    whose full comment list took longer than the cap to fetch. This lets a
    caller persist/display the profile and each post immediately instead of
    waiting for the entire account (and every comment) to finish.
    """
    loop = asyncio.get_event_loop()
    collector = InstagramCollector()
    return await loop.run_in_executor(
        None,
        lambda: collector.collect_streaming(
            username,
            limit=limit,
            include_social_graph=include_social_graph,
            follower_limit=follower_limit,
            following_limit=following_limit,
            fetch_comments=fetch_comments,
            inline_comment_cap=inline_comment_cap,
            on_profile=on_profile,
            on_post=on_post,
            on_extra_comments=on_extra_comments,
        ),
    )
