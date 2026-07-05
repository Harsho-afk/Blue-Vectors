"""
ARIA — Monitoring Engine

Background scheduler that:
1. Claims due monitor_targets via FOR UPDATE SKIP LOCKED
2. Captures snapshots (profile re-collection, Maigret, dorking, breach)
3. Diffs against baseline to detect changes
4. Creates monitor_events and alerts
5. Triggers correlation recomputation on identity-affecting changes

Runs as an asyncio background task inside the FastAPI process.
"""

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from auth import get_db_conn
from collector.base import collect_async, save_to_db, SUPPORTED_PLATFORMS
from correlator import correlate_case

log = logging.getLogger("aria.monitor_engine")

MAX_CONCURRENT_CHECKS = 3
SCHEDULER_INTERVAL = 30  # seconds between scheduler sweeps
MAX_CONSECUTIVE_FAILURES = 5


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════

async def start_scheduler():
    """Main loop — runs forever as a background task."""
    log.info("Monitor scheduler started")
    while True:
        try:
            await _run_scheduler_tick()
        except Exception:
            log.exception("Scheduler tick failed")
        await asyncio.sleep(SCHEDULER_INTERVAL)


async def _run_scheduler_tick():
    """Find and process due targets."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Expire overdue targets
        cur.execute(
            """
            UPDATE monitor_targets
            SET status = 'expired', updated_at = now()
            WHERE status IN ('active', 'pending_baseline', 'degraded')
              AND expires_at <= now()
            """
        )
        expired = cur.rowcount
        if expired:
            log.info("Expired %d monitor targets", expired)
            conn.commit()

        # Claim due targets
        cur.execute(
            """
            SELECT id FROM monitor_targets
            WHERE status IN ('active', 'pending_baseline')
              AND next_check_at <= now()
            ORDER BY next_check_at ASC
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (MAX_CONCURRENT_CHECKS,),
        )
        target_ids = [row["id"] for row in cur.fetchall()]
        conn.commit()
    finally:
        conn.close()

    if not target_ids:
        return

    log.info("Claimed %d targets for checking: %s", len(target_ids), target_ids)

    tasks = [_check_target(tid) for tid in target_ids]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _check_target(target_id: int):
    """Run all permitted checks for a single monitor target."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.*, a.platform, a.username, a.case_id,
                   ci.identifier_type, ci.value AS identifier_value
            FROM monitor_targets mt
            LEFT JOIN accounts a ON a.id = mt.account_id
            LEFT JOIN case_identifiers ci ON ci.id = mt.identifier_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        target = cur.fetchone()
        if not target:
            return

        permitted = target["permitted_sources"]
        if isinstance(permitted, str):
            permitted = json.loads(permitted)

        is_baseline = target["status"] == "pending_baseline"
        events_created = []

        # Run checks based on permitted sources
        if target["account_id"]:
            # Account-based monitoring
            if "platform_recollect" in permitted:
                evts = await _check_platform_recollect(conn, target, is_baseline)
                events_created.extend(evts)

            if "maigret" in permitted and target.get("username"):
                evts = await _check_maigret_expansion(conn, target, is_baseline)
                events_created.extend(evts)

        if target["identifier_id"]:
            # Identifier-based monitoring
            if "maigret" in permitted and target.get("identifier_type") == "username":
                evts = await _check_maigret_expansion(conn, target, is_baseline)
                events_created.extend(evts)
            if "breach" in permitted and target.get("identifier_type") == "email":
                evts = await _check_breach(conn, target, is_baseline)
                events_created.extend(evts)
            if "dorking" in permitted:
                evts = await _check_dorking(conn, target, is_baseline)
                events_created.extend(evts)

        # Update target state
        new_status = "active" if is_baseline else target["status"]
        next_check = datetime.now(timezone.utc) + timedelta(seconds=target["interval_seconds"])

        cur.execute(
            """
            UPDATE monitor_targets
            SET status = %s, last_checked_at = now(), next_check_at = %s, updated_at = now()
            WHERE id = %s
            """,
            (new_status, next_check, target_id),
        )
        conn.commit()

        # If identity-affecting events occurred, recompute correlations
        identity_events = {"profile_changed", "account_discovered", "hard_link_found"}
        if any(e["event_type"] in identity_events for e in events_created):
            await _recompute_correlations(target["case_id"], target_id, conn)

        log.info(
            "Target %d checked: %d events, next at %s",
            target_id, len(events_created), next_check.isoformat(),
        )

    except Exception:
        log.exception("Check failed for target %d", target_id)
        # Mark degraded after repeated failures
        try:
            conn.rollback()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE monitor_targets
                SET status = CASE
                        WHEN (SELECT count(*) FROM monitor_events
                              WHERE target_id = %s AND event_type = 'account_disappeared') >= %s
                        THEN 'degraded' ELSE status END,
                    last_checked_at = now(),
                    next_check_at = now() + (interval_seconds * interval '1 second'),
                    updated_at = now()
                WHERE id = %s
                """,
                (target_id, MAX_CONSECUTIVE_FAILURES, target_id),
            )
            conn.commit()
        except Exception:
            log.exception("Failed to update target %d after check failure", target_id)
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK: PLATFORM RE-COLLECTION (Profile + Posts Diffing)
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_platform_recollect(conn, target: dict, is_baseline: bool) -> list:
    """Re-collect a platform profile and diff against the stored baseline."""
    platform = target["platform"]
    username = target["username"]
    events = []

    if platform not in SUPPORTED_PLATFORMS:
        return events

    try:
        profile = await collect_async(platform, username, limit=50, include_social_graph=False)
    except Exception as e:
        log.warning("Re-collection failed for %s/%s: %s", platform, username, e)
        if not is_baseline:
            evt = _create_event(
                conn, target["id"],
                event_type="account_disappeared",
                source=platform,
                title=f"{platform}/{username} is inaccessible",
                current_json={"error": str(e)},
                priority="high",
                confidence="medium",
            )
            if evt:
                events.append(evt)
        return events

    # Build snapshot from profile
    # Exclude profile_image_url from the hash — CDN signatures change on every
    # request for some platforms (Instagram, Twitter).  We still store the URL
    # in the snapshot for display, but compare it separately via a stable
    # content hash if the image actually changed.
    snapshot = {
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "location": profile.location,
        "profile_image_url": profile.profile_image_url,
        "follower_count": profile.follower_count,
        "following_count": profile.following_count,
        "karma": profile.karma,
        "post_count": len(profile.posts),
        "latest_post_ids": sorted([p.external_id for p in profile.posts[:20]]),
    }

    # Hash only the stable fields (exclude profile_image_url)
    hash_fields = {k: v for k, v in snapshot.items() if k != "profile_image_url"}
    snapshot_hash = _hash_json(hash_fields)

    log.info(
        "Snapshot %s/%s: bio=%s, display_name=%s, hash=%s, baseline=%s",
        platform, username,
        repr((profile.bio or "")[:60]),
        repr(profile.display_name),
        snapshot_hash[:12],
        "CAPTURE" if is_baseline else "COMPARE",
    )

    if is_baseline:
        _save_snapshot(conn, target["id"], platform, snapshot, snapshot_hash, is_baseline=True)
        save_to_db(profile, conn, target["case_id"])
        log.info("Baseline saved for %s/%s (hash=%s)", platform, username, snapshot_hash[:12])
        return events

    # Get baseline
    cur = conn.cursor()
    cur.execute(
        """
        SELECT snapshot_json, content_hash FROM monitor_snapshots
        WHERE target_id = %s AND source = %s AND is_baseline = true
        ORDER BY observed_at DESC LIMIT 1
        """,
        (target["id"], platform),
    )
    baseline_row = cur.fetchone()

    if not baseline_row:
        log.warning("No baseline found for target %d/%s — saving fresh baseline", target["id"], platform)
        _save_snapshot(conn, target["id"], platform, snapshot, snapshot_hash, is_baseline=True)
        return events

    log.info(
        "Comparing hashes for %s/%s: current=%s baseline=%s match=%s",
        platform, username, snapshot_hash[:12], baseline_row["content_hash"][:12],
        snapshot_hash == baseline_row["content_hash"],
    )

    if snapshot_hash == baseline_row["content_hash"]:
        baseline_snap = baseline_row["snapshot_json"]
        if isinstance(baseline_snap, str):
            baseline_snap = json.loads(baseline_snap)
        log.info(
            "No change for %s/%s — baseline bio=%s, current bio=%s",
            platform, username,
            repr((baseline_snap.get("bio") or "")[:60]),
            repr((snapshot.get("bio") or "")[:60]),
        )
        return events

    baseline = baseline_row["snapshot_json"]
    if isinstance(baseline, str):
        baseline = json.loads(baseline)

    # Save new snapshot
    _save_snapshot(conn, target["id"], platform, snapshot, snapshot_hash, is_baseline=False)

    # Diff profile fields
    profile_changes = {}
    for field in ("display_name", "bio", "location", "profile_image_url"):
        old_val = baseline.get(field)
        new_val = snapshot.get(field)
        if old_val != new_val:
            profile_changes[field] = {"previous": old_val, "current": new_val}

    if profile_changes:
        evt = _create_event(
            conn, target["id"],
            event_type="profile_changed",
            source=platform,
            title=f"Profile changed: {', '.join(profile_changes.keys())}",
            previous_json={k: v["previous"] for k, v in profile_changes.items()},
            current_json={k: v["current"] for k, v in profile_changes.items()},
            evidence_json={"fields_changed": list(profile_changes.keys())},
            priority="high" if "bio" in profile_changes else "normal",
            confidence="high",
        )
        if evt:
            events.append(evt)

    # Diff posts (new activity)
    old_posts = set(baseline.get("latest_post_ids", []))
    new_posts = set(snapshot.get("latest_post_ids", []))
    added_posts = new_posts - old_posts

    if added_posts:
        evt = _create_event(
            conn, target["id"],
            event_type="new_posts",
            source=platform,
            title=f"{len(added_posts)} new public post(s) detected",
            previous_json={"post_count": baseline.get("post_count", 0)},
            current_json={"post_count": snapshot["post_count"], "new_ids": sorted(added_posts)[:10]},
            priority="normal",
            confidence="high",
        )
        if evt:
            events.append(evt)

    # Diff follower/following (significant changes only)
    for count_field, label in [("follower_count", "followers"), ("following_count", "following")]:
        old_c = baseline.get(count_field) or 0
        new_c = snapshot.get(count_field) or 0
        if old_c == 0:
            continue
        delta = abs(new_c - old_c)
        pct = (delta / old_c) * 100 if old_c else 0
        if delta >= 50 or pct >= 10:
            evt = _create_event(
                conn, target["id"],
                event_type="network_changed",
                source=platform,
                title=f"Significant {label} change: {old_c} → {new_c}",
                previous_json={count_field: old_c},
                current_json={count_field: new_c, "delta": new_c - old_c, "percent_change": round(pct, 1)},
                priority="normal",
                confidence="high",
            )
            if evt:
                events.append(evt)

    # Update the accounts table with fresh data
    save_to_db(profile, conn, target["case_id"])

    # Update baseline to current snapshot for next comparison
    cur.execute(
        """
        UPDATE monitor_snapshots SET is_baseline = false
        WHERE target_id = %s AND source = %s AND is_baseline = true
        """,
        (target["id"], platform),
    )
    _save_snapshot(conn, target["id"], platform, snapshot, snapshot_hash, is_baseline=True)
    conn.commit()

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK: MAIGRET EXPANSION (New Account Discovery)
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_maigret_expansion(conn, target: dict, is_baseline: bool) -> list:
    """Re-run Maigret to discover new accounts the subject registered on."""
    from osint import run_maigret

    username = target.get("username") or target.get("identifier_value")
    if not username:
        return []

    events = []
    try:
        result = await run_maigret(username, max_sites=300)
    except Exception as e:
        log.warning("Maigret expansion check failed for %s: %s", username, e)
        return events

    # Extract discovered platform URLs
    discovered = set()
    categories = result.get("categories", {})
    for cat_name, platforms in categories.items():
        if isinstance(platforms, list):
            for p in platforms:
                url = p.get("url") or p.get("url_user")
                if url:
                    discovered.add(url)

    snapshot = {"discovered_urls": sorted(discovered), "total_found": result.get("total_found", 0)}
    snapshot_hash = _hash_json(snapshot)

    if is_baseline:
        _save_snapshot(conn, target["id"], "maigret", snapshot, snapshot_hash, is_baseline=True)
        return events

    # Compare against baseline
    cur = conn.cursor()
    cur.execute(
        """
        SELECT snapshot_json FROM monitor_snapshots
        WHERE target_id = %s AND source = 'maigret' AND is_baseline = true
        ORDER BY observed_at DESC LIMIT 1
        """,
        (target["id"],),
    )
    baseline_row = cur.fetchone()

    if not baseline_row:
        _save_snapshot(conn, target["id"], "maigret", snapshot, snapshot_hash, is_baseline=True)
        return events

    baseline = baseline_row["snapshot_json"]
    if isinstance(baseline, str):
        baseline = json.loads(baseline)

    old_urls = set(baseline.get("discovered_urls", []))
    new_urls = discovered - old_urls

    if new_urls:
        # This is the money shot — new accounts discovered
        _save_snapshot(conn, target["id"], "maigret", snapshot, snapshot_hash, is_baseline=False)

        for url in list(new_urls)[:5]:  # Cap at 5 per check
            evt = _create_event(
                conn, target["id"],
                event_type="account_discovered",
                source="maigret",
                title=f"New account discovered: {url}",
                previous_json={"known_platforms": len(old_urls)},
                current_json={"url": url, "total_discovered": len(discovered)},
                source_url=url,
                priority="critical",
                confidence="high",
            )
            if evt:
                events.append(evt)

        # Auto-collect the new accounts if they're on supported platforms
        await _auto_collect_discoveries(conn, target, new_urls)

        # Update baseline
        cur.execute(
            "UPDATE monitor_snapshots SET is_baseline = false WHERE target_id = %s AND source = 'maigret' AND is_baseline = true",
            (target["id"],),
        )
        _save_snapshot(conn, target["id"], "maigret", snapshot, snapshot_hash, is_baseline=True)
        conn.commit()

    return events


async def _auto_collect_discoveries(conn, target: dict, new_urls: set):
    """Auto-collect newly discovered profiles on supported platforms."""
    import re

    platform_patterns = [
        (re.compile(r"github\.com/([A-Za-z0-9_-]+)", re.I), "github"),
        (re.compile(r"(?:reddit\.com|old\.reddit\.com)/u(?:ser)?/([A-Za-z0-9_-]+)", re.I), "reddit"),
        (re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", re.I), "twitter"),
        (re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I), "instagram"),
    ]

    for url in new_urls:
        for pattern, platform in platform_patterns:
            match = pattern.search(url)
            if match:
                discovered_username = match.group(1)
                try:
                    profile = await collect_async(platform, discovered_username, limit=30, include_social_graph=False)
                    save_to_db(profile, conn, target["case_id"])
                    log.info("Auto-collected %s/%s for case %d", platform, discovered_username, target["case_id"])
                except Exception as e:
                    log.warning("Auto-collect failed for %s/%s: %s", platform, discovered_username, e)
                break


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK: BREACH MONITORING
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_breach(conn, target: dict, is_baseline: bool) -> list:
    """Re-check for new breach exposure on monitored email."""
    from osint import breach_lookup

    email = target.get("identifier_value")
    if not email:
        return []

    events = []
    try:
        result = await breach_lookup(email)
    except Exception as e:
        log.warning("Breach check failed for %s: %s", email, e)
        return events

    breaches = set()
    if result.breaches:
        for b in result.breaches:
            breaches.add(b.name)

    snapshot = {"breaches": sorted(breaches), "total": len(breaches)}
    snapshot_hash = _hash_json(snapshot)

    if is_baseline:
        _save_snapshot(conn, target["id"], "breach", snapshot, snapshot_hash, is_baseline=True)
        return events

    cur = conn.cursor()
    cur.execute(
        """
        SELECT snapshot_json FROM monitor_snapshots
        WHERE target_id = %s AND source = 'breach' AND is_baseline = true
        ORDER BY observed_at DESC LIMIT 1
        """,
        (target["id"],),
    )
    baseline_row = cur.fetchone()

    if not baseline_row:
        _save_snapshot(conn, target["id"], "breach", snapshot, snapshot_hash, is_baseline=True)
        return events

    baseline = baseline_row["snapshot_json"]
    if isinstance(baseline, str):
        baseline = json.loads(baseline)

    old_breaches = set(baseline.get("breaches", []))
    new_breaches = breaches - old_breaches

    if new_breaches:
        _save_snapshot(conn, target["id"], "breach", snapshot, snapshot_hash, is_baseline=False)

        evt = _create_event(
            conn, target["id"],
            event_type="breach_detected",
            source="breach_lookup",
            title=f"New breach exposure: {', '.join(list(new_breaches)[:3])}",
            previous_json={"breaches": sorted(old_breaches)},
            current_json={"new_breaches": sorted(new_breaches), "total": len(breaches)},
            priority="critical",
            confidence="high",
        )
        if evt:
            events.append(evt)

        cur.execute(
            "UPDATE monitor_snapshots SET is_baseline = false WHERE target_id = %s AND source = 'breach' AND is_baseline = true",
            (target["id"],),
        )
        _save_snapshot(conn, target["id"], "breach", snapshot, snapshot_hash, is_baseline=True)
        conn.commit()

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK: DORKING (New Web Mentions)
# ═══════════════════════════════════════════════════════════════════════════════

async def _check_dorking(conn, target: dict, is_baseline: bool) -> list:
    """Re-run dorking to find new web mentions of an identifier."""
    from dorking import run_dorking

    identifier_value = target.get("identifier_value") or target.get("username")
    identifier_type = target.get("identifier_type") or "username"
    if not identifier_value:
        return []

    events = []
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: run_dorking(identifier_type, identifier_value, use_llm=False)
        )
    except Exception as e:
        log.warning("Dorking check failed for %s: %s", identifier_value, e)
        return events

    # Extract found URLs
    found_urls = set()
    results_list = result.get("results", [])
    for item in results_list:
        url = item.get("url")
        if url:
            found_urls.add(url)

    snapshot = {"urls": sorted(found_urls), "total_results": len(results_list)}
    snapshot_hash = _hash_json(snapshot)

    if is_baseline:
        _save_snapshot(conn, target["id"], "dorking", snapshot, snapshot_hash, is_baseline=True)
        return events

    cur = conn.cursor()
    cur.execute(
        """
        SELECT snapshot_json FROM monitor_snapshots
        WHERE target_id = %s AND source = 'dorking' AND is_baseline = true
        ORDER BY observed_at DESC LIMIT 1
        """,
        (target["id"],),
    )
    baseline_row = cur.fetchone()

    if not baseline_row:
        _save_snapshot(conn, target["id"], "dorking", snapshot, snapshot_hash, is_baseline=True)
        return events

    baseline = baseline_row["snapshot_json"]
    if isinstance(baseline, str):
        baseline = json.loads(baseline)

    old_urls = set(baseline.get("urls", []))
    new_urls = found_urls - old_urls

    if new_urls:
        _save_snapshot(conn, target["id"], "dorking", snapshot, snapshot_hash, is_baseline=False)

        for url in list(new_urls)[:3]:
            evt = _create_event(
                conn, target["id"],
                event_type="new_web_mention",
                source="dorking",
                title=f"New web mention found: {url[:80]}",
                current_json={"url": url},
                source_url=url,
                priority="normal",
                confidence="medium",
            )
            if evt:
                events.append(evt)

        cur.execute(
            "UPDATE monitor_snapshots SET is_baseline = false WHERE target_id = %s AND source = 'dorking' AND is_baseline = true",
            (target["id"],),
        )
        _save_snapshot(conn, target["id"], "dorking", snapshot, snapshot_hash, is_baseline=True)
        conn.commit()

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# CORRELATION DRIFT DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

async def _recompute_correlations(case_id: int, target_id: int, conn):
    """Recompute correlations for the case and detect drift."""
    cur = conn.cursor()

    # Get old correlation scores
    cur.execute(
        "SELECT account_a_id, account_b_id, confidence FROM linkage_results WHERE case_id = %s",
        (case_id,),
    )
    old_scores = {(r["account_a_id"], r["account_b_id"]): float(r["confidence"]) for r in cur.fetchall()}

    # Recompute
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: correlate_case(case_id))
    except Exception as e:
        log.warning("Correlation recomputation failed for case %d: %s", case_id, e)
        return

    # Get new scores
    cur.execute(
        "SELECT account_a_id, account_b_id, confidence, shap_json FROM linkage_results WHERE case_id = %s",
        (case_id,),
    )
    new_rows = cur.fetchall()
    new_scores = {(r["account_a_id"], r["account_b_id"]): float(r["confidence"]) for r in new_rows}

    def _band(score):
        if score >= 70:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    # Detect band crossings
    for pair, new_conf in new_scores.items():
        old_conf = old_scores.get(pair, 0)
        old_band = _band(old_conf)
        new_band = _band(new_conf)

        if old_band != new_band and new_band != "low":
            evt = _create_event(
                conn, target_id,
                event_type="correlation_drift",
                source="correlator",
                title=f"Correlation moved {old_band}→{new_band}: {old_conf:.0f}%→{new_conf:.0f}%",
                previous_json={"confidence": old_conf, "band": old_band, "pair": list(pair)},
                current_json={"confidence": new_conf, "band": new_band, "pair": list(pair)},
                priority="high" if new_band == "high" else "normal",
                confidence="high",
            )
            if evt:
                _create_alert_for_event(conn, evt, case_id)

    # Detect new pairs that didn't exist before
    for pair, new_conf in new_scores.items():
        if pair not in old_scores and new_conf >= 40:
            evt = _create_event(
                conn, target_id,
                event_type="correlation_drift",
                source="correlator",
                title=f"New correlation discovered: {new_conf:.0f}% confidence",
                current_json={"confidence": new_conf, "band": _band(new_conf), "pair": list(pair)},
                priority="high",
                confidence="high",
            )
            if evt:
                _create_alert_for_event(conn, evt, case_id)

    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _hash_json(data: dict) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:32]


def _save_snapshot(conn, target_id: int, source: str, snapshot: dict, content_hash: str, is_baseline: bool):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO monitor_snapshots (target_id, source, snapshot_json, content_hash, is_baseline)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (target_id, source, json.dumps(snapshot, default=str), content_hash, is_baseline),
    )
    conn.commit()


def _create_event(
    conn,
    target_id: int,
    event_type: str,
    source: str,
    title: str,
    previous_json: Optional[dict] = None,
    current_json: Optional[dict] = None,
    evidence_json: Optional[dict] = None,
    source_url: Optional[str] = None,
    priority: str = "normal",
    confidence: Optional[str] = None,
) -> Optional[dict]:
    """Create a monitor event with deduplication via fingerprint."""
    fingerprint_data = f"{event_type}:{source}:{json.dumps(current_json, sort_keys=True, default=str)}"
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:32]

    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO monitor_events
                (target_id, event_type, source, title, previous_json, current_json,
                 evidence_json, source_url, confidence, priority, fingerprint)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (target_id, source, fingerprint) DO NOTHING
            RETURNING id, event_type, title, priority
            """,
            (
                target_id, event_type, source, title,
                json.dumps(previous_json, default=str) if previous_json else None,
                json.dumps(current_json, default=str) if current_json else None,
                json.dumps(evidence_json, default=str) if evidence_json else None,
                source_url, confidence, priority, fingerprint,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        if row:
            evt = dict(row)
            # Auto-create alert for high/critical events
            if priority in ("high", "critical"):
                _create_alert_for_event(conn, evt, _get_case_id_for_target(conn, target_id))
            return evt
        return None  # Duplicate
    except Exception:
        conn.rollback()
        log.exception("Failed to create monitor event")
        return None


def _create_alert_for_event(conn, event: dict, case_id: int):
    """Create an alert for the investigator."""
    cur = conn.cursor()
    try:
        # Get investigator for this case
        cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
        row = cur.fetchone()
        if not row:
            return

        cur.execute(
            """
            INSERT INTO alerts (case_id, monitor_event_id, investigator_id, title, message, priority)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                case_id,
                event.get("id"),
                row["investigator_id"],
                event["title"],
                f"Monitoring detected: {event['title']}",
                event.get("priority", "normal"),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("Failed to create alert")


def _get_case_id_for_target(conn, target_id: int) -> Optional[int]:
    cur = conn.cursor()
    cur.execute("SELECT case_id FROM monitor_targets WHERE id = %s", (target_id,))
    row = cur.fetchone()
    return row["case_id"] if row else None
