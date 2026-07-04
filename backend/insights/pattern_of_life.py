"""
Function 3: Pattern-of-Life Analyzer

Classifies an account's activity pattern from post timestamps:
- Weekday vs weekend ratio
- Most active hours (morning/afternoon/evening/night)
- Posting regularity (stddev of inter-post intervals)
- Burst detection (3+ posts within 30 minutes)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.pattern_of_life")

MIN_POSTS = 10

HOUR_BUCKETS = {
    "early_morning": (5, 8),
    "morning": (8, 12),
    "afternoon": (12, 17),
    "evening": (17, 21),
    "night": (21, 24),
    "late_night": (0, 5),
}


def _parse_timestamps(posts: list[dict]) -> list[datetime]:
    """Extract datetime objects from post rows."""
    dts: list[datetime] = []
    for p in posts:
        ts = p.get("timestamp")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            dt = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        elif isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            continue
        dts.append(dt)
    return dts


def _classify_hours(hours: list[int]) -> str:
    """Find the dominant activity bucket."""
    counts: dict[str, int] = {name: 0 for name in HOUR_BUCKETS}

    for h in hours:
        for name, (start, end) in HOUR_BUCKETS.items():
            if start <= h < end:
                counts[name] += 1
                break

    peak = max(counts, key=counts.get)
    return peak.replace("_", " ")


def _detect_bursts(timestamps: list[datetime], window_minutes: int = 30, min_count: int = 3) -> int:
    """Count burst events (min_count+ posts within window_minutes)."""
    if len(timestamps) < min_count:
        return 0

    sorted_ts = sorted(timestamps)
    bursts = 0
    i = 0

    while i < len(sorted_ts):
        window_end = sorted_ts[i].timestamp() + window_minutes * 60
        j = i + 1
        while j < len(sorted_ts) and sorted_ts[j].timestamp() <= window_end:
            j += 1
        count_in_window = j - i
        if count_in_window >= min_count:
            bursts += 1
            i = j
        else:
            i += 1

    return bursts


def analyze_account(account_id: int, posts: list[dict]) -> Optional[InsightResult]:
    """Analyze posting patterns for a single account."""
    dts = _parse_timestamps(posts)

    if len(dts) < MIN_POSTS:
        return None

    hours = [dt.hour for dt in dts]
    weekdays = [dt.weekday() for dt in dts]

    weekday_count = sum(1 for wd in weekdays if wd < 5)
    weekend_count = len(weekdays) - weekday_count
    weekday_pct = round(weekday_count / len(weekdays) * 100, 1)

    peak_bucket = _classify_hours(hours)

    sorted_ts = sorted(dt.timestamp() for dt in dts)
    if len(sorted_ts) >= 2:
        intervals = np.diff(sorted_ts) / 3600.0
        median_interval = round(float(np.median(intervals)), 1)
        std_interval = round(float(np.std(intervals)), 1)
    else:
        median_interval = 0.0
        std_interval = 0.0

    burst_count = _detect_bursts(dts)

    day_pref = "weekday-heavy" if weekday_pct > 65 else (
        "weekend-heavy" if weekday_pct < 35 else "balanced"
    )

    regularity = "regular" if std_interval < median_interval * 0.8 else (
        "irregular" if std_interval > median_interval * 1.5 else "moderate"
    )

    burst_desc = f"{burst_count} burst(s) detected" if burst_count > 0 else "no burst activity"

    claim = (
        f"{day_pref.capitalize()} poster, peak activity in {peak_bucket} hours, "
        f"{regularity} cadence, {burst_desc}"
    )

    span_days = (max(sorted_ts) - min(sorted_ts)) / 86400.0
    confidence = "medium" if span_days >= 14 and len(dts) >= 20 else "low"

    return InsightResult(
        category="pattern_of_life",
        claim=claim,
        confidence=confidence,
        account_id=account_id,
        evidence=[EvidenceItem(
            method="temporal_pattern_classification",
            detail=(
                f"{weekday_pct}% weekday posts, peak hours: {peak_bucket}, "
                f"median inter-post interval {median_interval}h (std={std_interval}h), "
                f"{burst_count} bursts detected, span {round(span_days)}d"
            ),
            source_table="posts",
            source_id=None,
        )],
    )


def run(conn, case_id: int) -> list[InsightResult]:
    """Run pattern-of-life analysis for all accounts in a case."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = cur.fetchall()

    results: list[InsightResult] = []

    for acc in accounts:
        account_id = acc["id"]
        cur.execute(
            "SELECT timestamp FROM posts WHERE account_id = %s",
            (account_id,),
        )
        posts = [dict(row) for row in cur.fetchall()]

        insight = analyze_account(account_id, posts)
        if insight:
            results.append(insight)

    log.info("Case %d: pattern-of-life analyzed %d accounts, produced %d insights",
             case_id, len(accounts), len(results))
    return results
