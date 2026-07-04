import json
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from .twitter import TwitterCollector
from .reddit import RedditCollector
from .models import AccountProfile, log

load_dotenv()


# PostgreSQL storage helper
def save_to_db(profile: AccountProfile, conn, case_id: int) -> int:
    cur = conn.cursor()

    created_at_dt = (
        datetime.fromtimestamp(profile.created_utc, tz=timezone.utc)
        if profile.created_utc is not None
        else None
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
    account_id: int = cur.fetchone()["id"]

    for post in profile.posts:
        post_dt = datetime.fromtimestamp(post.timestamp, tz=timezone.utc)
        cur.execute(
            """
            INSERT INTO posts
            (account_id, external_id, text, timestamp, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (account_id, external_id)
            DO NOTHING
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
    log.info(
        "DB: saved account_id=%d (%s/%s) under case_id=%d",
        account_id,
        profile.platform,
        profile.username,
        case_id,
    )
    return account_id


# Public entry-points
SUPPORTED_PLATFORMS = ("reddit", "twitter")


def collect(platform: str, username: str, limit: int = 100) -> AccountProfile:
    platform = platform.lower().strip()
    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(
            f"Unsupported platform '{platform}'. Choose from: {SUPPORTED_PLATFORMS}"
        )
    if platform == "reddit":
        return RedditCollector().collect(username, limit=limit)
    if platform == "twitter":
        return asyncio.run(collect_twitter(username, limit))
    raise ValueError(f"Unhandled platform: {platform}")


async def collect_async(
    platform: str, username: str, limit: int = 100
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
        return await collect_twitter(username, limit)
    raise ValueError(f"Unhandled platform: {platform}")


async def collect_twitter(username: str, limit: int) -> AccountProfile:
    collector = TwitterCollector()
    return await collector.collect(username, limit=limit)
