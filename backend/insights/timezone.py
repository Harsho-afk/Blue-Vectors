"""
Function 5: Timezone Estimator

Sleep-trough method: build a 24-hour UTC histogram, find the quietest
6-hour window (the "sleep trough"). The midpoint of the trough is
approximately 3-4 AM local time. Offset from UTC gives timezone band.

Guards:
- Trough depth: only emit if quietest 6h window has <15% of posts
  AND busiest 6h window has >25% of posts (flat histograms = no signal)
- Span: downgrade confidence if posting span < 30 days
- Minimum: skip entirely if < 10 posts with valid timestamps
"""

import logging
from datetime import datetime, timezone as tz

import numpy as np

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.timezone")

MIN_POSTS = 10
WINDOW_SIZE = 6

TIMEZONE_NAMES = {
    -12: "UTC-12:00 (Baker Island)",
    -11: "UTC-11:00 (Samoa)",
    -10: "UTC-10:00 (Hawaii)",
    -9: "UTC-09:00 (Alaska)",
    -8: "UTC-08:00 (PST/Pacific)",
    -7: "UTC-07:00 (MST/Mountain)",
    -6: "UTC-06:00 (CST/Central)",
    -5: "UTC-05:00 (EST/Eastern)",
    -4: "UTC-04:00 (AST/Atlantic)",
    -3: "UTC-03:00 (BRT/Brasilia)",
    -2: "UTC-02:00 (Mid-Atlantic)",
    -1: "UTC-01:00 (Azores)",
    0: "UTC+00:00 (GMT/London)",
    1: "UTC+01:00 (CET/Paris)",
    2: "UTC+02:00 (EET/Cairo)",
    3: "UTC+03:00 (MSK/Moscow)",
    4: "UTC+04:00 (GST/Dubai)",
    5: "UTC+05:00 (PKT/Karachi)",
    6: "UTC+06:00 (BST/Dhaka)",
    7: "UTC+07:00 (ICT/Bangkok)",
    8: "UTC+08:00 (CST/Singapore)",
    9: "UTC+09:00 (JST/Tokyo)",
    10: "UTC+10:00 (AEST/Sydney)",
    11: "UTC+11:00 (SBT/Solomon)",
    12: "UTC+12:00 (NZST/Auckland)",
}

IST_COMPATIBLE = {5, 6}


def _parse_utc_hours(posts: list[dict]) -> tuple[list[int], float]:
    """Extract UTC hours from post timestamps. Returns (hours, span_days)."""
    hours: list[int] = []
    min_ts = float("inf")
    max_ts = float("-inf")

    for p in posts:
        ts = p.get("timestamp")
        if ts is None:
            continue

        if isinstance(ts, datetime):
            dt = ts if ts.tzinfo else ts.replace(tzinfo=tz.utc)
        elif isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=tz.utc)
        elif isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
        else:
            continue

        epoch = dt.timestamp()
        min_ts = min(min_ts, epoch)
        max_ts = max(max_ts, epoch)
        hours.append(dt.hour)

    span_days = (max_ts - min_ts) / 86400.0 if min_ts < max_ts else 0.0
    return hours, span_days


def _find_sleep_trough(hist: np.ndarray) -> tuple[int, float, float]:
    """
    Find the quietest 6-hour window in a 24-hour histogram.
    Returns (trough_start_hour, trough_fraction, peak_fraction).
    """
    total = hist.sum()
    if total == 0:
        return 0, 1.0, 0.0

    min_sum = float("inf")
    min_start = 0
    max_sum = float("-inf")

    for start in range(24):
        window_sum = sum(hist[(start + i) % 24] for i in range(WINDOW_SIZE))
        if window_sum < min_sum:
            min_sum = window_sum
            min_start = start
        if window_sum > max_sum:
            max_sum = window_sum

    trough_frac = min_sum / total
    peak_frac = max_sum / total

    return min_start, trough_frac, peak_frac


def estimate_timezone(account_id: int, posts: list[dict]) -> list[InsightResult]:
    """Estimate timezone for a single account from its post timestamps."""
    hours, span_days = _parse_utc_hours(posts)

    if len(hours) < MIN_POSTS:
        return []

    hist = np.zeros(24)
    for h in hours:
        hist[h] += 1

    trough_start, trough_frac, peak_frac = _find_sleep_trough(hist)

    if trough_frac >= 0.15 or peak_frac <= 0.25:
        log.info(
            "Account %d: histogram too flat (trough=%.1f%%, peak=%.1f%%) — skipping timezone",
            account_id, trough_frac * 100, peak_frac * 100,
        )
        return []

    trough_midpoint = (trough_start + WINDOW_SIZE / 2) % 24
    local_3am = 3.0
    offset = int(round(local_3am - trough_midpoint)) % 24
    if offset > 12:
        offset -= 24

    offset_low = offset - 1
    offset_high = offset + 1

    tz_name = TIMEZONE_NAMES.get(offset, f"UTC{offset:+d}:00")

    ist_note = ""
    if offset in IST_COMPATIBLE:
        ist_note = " (IST-compatible)"

    claim = f"Estimated timezone: UTC{offset_low:+d}:00 to UTC{offset_high:+d}:00 - {tz_name}{ist_note}"

    if len(hours) >= 50 and span_days >= 14:
        confidence = "high"
    elif len(hours) >= 20:
        confidence = "medium"
    else:
        confidence = "low"

    if span_days < 30:
        if confidence == "high":
            confidence = "medium"

    return [InsightResult(
        category="geography",
        claim=claim,
        confidence=confidence,
        account_id=account_id,
        evidence=[EvidenceItem(
            method="sleep_trough_analysis",
            detail=(
                f"Quietest 6h window: {trough_start:02d}:00-{(trough_start+6)%24:02d}:00 UTC "
                f"({trough_frac*100:.1f}% of posts). "
                f"Peak 6h window has {peak_frac*100:.1f}% of posts. "
                f"Sleep midpoint ~{trough_midpoint:.0f}:00 UTC -> local 03:00 ~ UTC{offset:+d}. "
                f"Based on {len(hours)} posts over {span_days:.0f} days."
            ),
            source_table="posts",
            source_id=None,
        )],
    )]


def run(conn, case_id: int) -> list[InsightResult]:
    """Run timezone estimation for all accounts in a case."""
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

        results.extend(estimate_timezone(account_id, posts))

    log.info("Case %d: timezone estimator produced %d insights from %d accounts",
             case_id, len(results), len(accounts))
    return results
