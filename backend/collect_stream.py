"""
ARIA — shared "collect one platform, emitting progress events" helper.

Extracted from routes_run.py so that BOTH the one-click investigation
runner (/api/cases/{id}/run) and the single-identifier collect button
(/api/cases/{id}/collect) drive the exact same code path — including the
Instagram per-post streaming save. Previously routes_cases.py called the
old blocking collect_async()+save_to_db() directly, which is why the
single-identifier "Collect" button in the UI didn't show anything until
the ENTIRE Instagram account (all posts, all comments, all followers,
all following) had finished — often several minutes — since nothing was
written to the DB and no response was sent until the very end.

`emit` is an async callable, e.g. `queue.put`, matching what
_run_investigation already used. `case_id`/`platform`/`username` behave
exactly as they did in routes_run.py's private helpers.
"""

import asyncio
import logging

from auth import get_db_conn
from collector.base import (
    collect_async,
    collect_instagram_streaming,
    save_to_db,
    save_account_profile,
    save_post,
    update_post_comments,
)

log = logging.getLogger("aria.collect_stream")


async def collect_one_platform(
    case_id: int,
    platform: str,
    username: str,
    emit,
    limit: int = 100,
    include_social_graph: bool = True,
) -> int:
    """
    Collect a single platform/username for a case, emitting SSE-ready dict
    events via `emit` as progress happens. Returns the number of accounts
    added (0 or 1) so callers can tally collected_accounts.

    `limit`/`include_social_graph` are only honored for non-Instagram
    platforms — Instagram's streaming path (like /run) always collects
    posts/followers/following/comments unlimited (0 = no cap), since it
    saves incrementally instead of needing a cap to bound one big response.
    """
    await emit(
        {
            "step": "collect",
            "status": "running",
            "platform": platform,
            "username": username,
        }
    )

    if platform == "instagram":
        return await _collect_instagram_streaming(case_id, username, emit)

    try:
        profile = await collect_async(
            platform,
            username,
            limit=limit,
            include_social_graph=include_social_graph,
            follower_limit=0,
            following_limit=0,
            fetch_comments=True,
            comment_limit=0,
        )
        conn = get_db_conn()
        try:
            save_to_db(profile, conn, case_id)
        finally:
            conn.close()
        await emit(
            {
                "step": "collect",
                "status": "done",
                "platform": platform,
                "username": username,
                "posts": len(profile.posts),
                "display_name": profile.display_name,
            }
        )
        return 1
    except Exception as e:
        log.warning("Collection failed for %s/%s: %s", platform, username, e)
        await emit(
            {
                "step": "collect",
                "status": "error",
                "platform": platform,
                "username": username,
                "error": str(e),
            }
        )
        return 0


async def _collect_instagram_streaming(case_id: int, username: str, emit) -> int:
    """
    Instagram-specific collection path: unlike every other platform (which
    collects everything, then saves once), this saves and emits progress
    PER POST — each post (with up to 50 comments) lands in the DB and on
    the SSE stream the moment it's ready, instead of after the whole
    account (and every comment on every post) has been fetched.

    Comments beyond 50 on a given post are fetched in a background thread
    that keeps running while collection moves on to the next post; when it
    finishes, the post's comments are overwritten in the DB and a follow-up
    SSE event is emitted, even if that happens after this coroutine — and
    possibly the whole run — has already finished.
    """
    loop = asyncio.get_event_loop()
    state = {"account_id": None, "post_count": 0, "display_name": username}

    def _schedule(event: dict) -> None:
        # Called from worker threads (on_profile/on_post run in the
        # run_in_executor thread; on_extra_comments runs in its own
        # background thread spawned inside the collector) — never call
        # queue.put directly from a thread, schedule it onto the loop.
        asyncio.run_coroutine_threadsafe(emit(event), loop)

    def on_profile(profile) -> None:
        conn = get_db_conn()
        try:
            account_id = save_account_profile(profile, conn, case_id)
        finally:
            conn.close()
        state["account_id"] = account_id
        state["display_name"] = profile.display_name
        _schedule(
            {
                "step": "collect",
                "status": "running",
                "platform": "instagram",
                "username": username,
                "display_name": profile.display_name,
                "message": f"Profile loaded for @{username} — collecting posts...",
            }
        )

    def on_post(post) -> None:
        account_id = state["account_id"]
        if account_id is None:
            return
        conn = get_db_conn()
        try:
            save_post(account_id, post, conn)
        finally:
            conn.close()

        meta = post.metadata or {}
        is_network = meta.get("type") == "network"
        if not is_network:
            state["post_count"] += 1

        _schedule(
            {
                "step": "collect_post",
                "status": "done",
                "platform": "instagram",
                "username": username,
                "display_name": state["display_name"],
                "post_index": state["post_count"],
                "post_type": meta.get("type"),
                "comments_inline": meta.get("comments_fetched", 0),
                "comment_count": meta.get("comment_count"),
                "comments_pending": meta.get("comments_pending", False),
                "message": (
                    "Network data collected"
                    if is_network
                    else f"Post {state['post_count']} collected"
                ),
            }
        )

    def on_extra_comments(shortcode: str, comments: list) -> None:
        account_id = state["account_id"]
        if account_id is None:
            return
        conn = get_db_conn()
        try:
            update_post_comments(account_id, shortcode, comments, conn)
        finally:
            conn.close()
        _schedule(
            {
                "step": "collect_comments",
                "status": "done",
                "platform": "instagram",
                "username": username,
                "external_id": shortcode,
                "count": len(comments),
                "message": f"All {len(comments)} comments fetched for post {shortcode}",
            }
        )

    try:
        await collect_instagram_streaming(
            username,
            follower_limit=0,
            following_limit=0,
            fetch_comments=True,
            inline_comment_cap=50,
            on_profile=on_profile,
            on_post=on_post,
            on_extra_comments=on_extra_comments,
        )
        await emit(
            {
                "step": "collect",
                "status": "done",
                "platform": "instagram",
                "username": username,
                "posts": state["post_count"],
                "display_name": state["display_name"],
            }
        )
        return 1
    except Exception as e:
        log.warning("Instagram streaming collection failed for %s: %s", username, e)
        await emit(
            {
                "step": "collect",
                "status": "error",
                "platform": "instagram",
                "username": username,
                "error": str(e),
            }
        )
        return 0
