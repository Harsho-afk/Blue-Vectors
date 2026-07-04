"""
Function 9 (Pass 2): Identity Consistency Checker

Runs after Pass 1. Reads the insights table and account metadata,
flags contradictions:
  1. Declared location vs timezone estimate mismatch
  2. Cross-platform display-name divergence when usernames are similar

Category: identity_consistency
"""

import logging
import re

from rapidfuzz import fuzz

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.consistency")

TZ_CLAIM_RE = re.compile(r"UTC([+-]?\d+):00 to UTC([+-]?\d+):00")

LOCATION_TO_TZ = {
    "india": (5, 6), "mumbai": (5, 6), "delhi": (5, 6), "new delhi": (5, 6),
    "bangalore": (5, 6), "bengaluru": (5, 6), "chennai": (5, 6),
    "kolkata": (5, 6), "hyderabad": (5, 6), "pune": (5, 6),
    "jaipur": (5, 6), "lucknow": (5, 6), "ahmedabad": (5, 6),
    "new york": (-5, -4), "nyc": (-5, -4), "boston": (-5, -4),
    "washington": (-5, -4), "atlanta": (-5, -4), "miami": (-5, -4),
    "philadelphia": (-5, -4), "detroit": (-5, -4),
    "chicago": (-6, -5), "dallas": (-6, -5), "houston": (-6, -5),
    "austin": (-6, -5), "minneapolis": (-6, -5),
    "denver": (-7, -6), "phoenix": (-7, -7), "salt lake city": (-7, -6),
    "los angeles": (-8, -7), "san francisco": (-8, -7), "seattle": (-8, -7),
    "portland": (-8, -7), "california": (-8, -7),
    "london": (0, 1), "uk": (0, 1), "united kingdom": (0, 1),
    "england": (0, 1), "manchester": (0, 1), "scotland": (0, 1),
    "paris": (1, 2), "france": (1, 2), "berlin": (1, 2), "germany": (1, 2),
    "amsterdam": (1, 2), "netherlands": (1, 2), "madrid": (1, 2),
    "spain": (1, 2), "rome": (1, 2), "italy": (1, 2),
    "zurich": (1, 2), "switzerland": (1, 2), "vienna": (1, 2),
    "athens": (2, 3), "greece": (2, 3), "istanbul": (3, 3),
    "bucharest": (2, 3), "helsinki": (2, 3),
    "dubai": (4, 4), "uae": (4, 4), "riyadh": (3, 3),
    "tokyo": (9, 9), "japan": (9, 9), "beijing": (8, 8), "china": (8, 8),
    "shanghai": (8, 8), "singapore": (8, 8), "hong kong": (8, 8),
    "seoul": (9, 9), "korea": (9, 9),
    "bangkok": (7, 7), "thailand": (7, 7), "jakarta": (7, 7),
    "manila": (8, 8), "philippines": (8, 8),
    "karachi": (5, 5), "pakistan": (5, 5), "dhaka": (6, 6), "bangladesh": (6, 6),
    "sydney": (10, 11), "melbourne": (10, 11), "australia": (8, 11),
    "auckland": (12, 13), "new zealand": (12, 13),
    "sao paulo": (-3, -3), "brazil": (-3, -3), "rio": (-3, -3),
    "buenos aires": (-3, -3), "argentina": (-3, -3),
    "toronto": (-5, -4), "vancouver": (-8, -7), "montreal": (-5, -4),
    "calgary": (-7, -6),
}

DISPLAY_NAME_LOW_THRESHOLD = 0.40


def _match_location(location: str) -> tuple[str, tuple[int, int]] | None:
    """Match a location string against known timezone regions."""
    loc = location.lower().strip()
    for keyword, tz_range in LOCATION_TO_TZ.items():
        if keyword in loc:
            return keyword, tz_range
    return None


def _ranges_overlap(r1: tuple[int, int], r2: tuple[int, int]) -> bool:
    return r1[0] <= r2[1] and r2[0] <= r1[1]


def check_location_vs_timezone(conn, case_id: int) -> list[InsightResult]:
    """Flag accounts where declared location contradicts timezone estimate."""
    cur = conn.cursor()

    cur.execute(
        "SELECT id, platform, username, location FROM accounts "
        "WHERE case_id = %s AND location IS NOT NULL AND location != ''",
        (case_id,),
    )
    accounts_with_loc = [dict(row) for row in cur.fetchall()]

    if not accounts_with_loc:
        return []

    cur.execute(
        "SELECT account_id, claim FROM insights "
        "WHERE case_id = %s AND category = 'geography'",
        (case_id,),
    )
    tz_insights = {row["account_id"]: row["claim"] for row in cur.fetchall()}

    results: list[InsightResult] = []

    for acc in accounts_with_loc:
        location = acc["location"]
        match = _match_location(location)
        if not match:
            continue

        keyword, expected_range = match

        claim_text = tz_insights.get(acc["id"])
        if not claim_text:
            continue

        tz_match = TZ_CLAIM_RE.search(claim_text)
        if not tz_match:
            continue

        tz_low = int(tz_match.group(1))
        tz_high = int(tz_match.group(2))
        estimated_range = (tz_low, tz_high)

        if _ranges_overlap(expected_range, estimated_range):
            continue

        label = f"{acc['platform']}:{acc['username']}"
        claim = (
            f"Location mismatch for {label}: "
            f"declared '{location}' (expected UTC{expected_range[0]:+d} to UTC{expected_range[1]:+d}) "
            f"but posting pattern suggests UTC{tz_low:+d} to UTC{tz_high:+d}"
        )

        results.append(InsightResult(
            category="identity_consistency",
            claim=claim,
            confidence="medium",
            account_id=acc["id"],
            evidence=[EvidenceItem(
                method="location_timezone_crosscheck",
                detail=(
                    f"Declared location: '{location}' matched keyword '{keyword}' "
                    f"-> expected UTC{expected_range[0]:+d}:00 to UTC{expected_range[1]:+d}:00. "
                    f"Timezone insight: {claim_text}"
                ),
                source_table="insights",
                source_id=None,
            )],
        ))

    return results


def check_display_name_consistency(conn, case_id: int) -> list[InsightResult]:
    """Flag pairs of accounts with similar usernames but divergent display names."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, platform, username, display_name FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = [dict(row) for row in cur.fetchall()]

    if len(accounts) < 2:
        return []

    results: list[InsightResult] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, a in enumerate(accounts):
        for j, b in enumerate(accounts):
            if i >= j:
                continue

            pair_key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            ua = (a.get("username") or "").lower()
            ub = (b.get("username") or "").lower()
            if not ua or not ub:
                continue

            username_sim = fuzz.ratio(ua, ub) / 100.0
            if username_sim < 0.70:
                continue

            da = (a.get("display_name") or "").strip()
            db = (b.get("display_name") or "").strip()
            if not da or not db:
                continue

            display_sim = fuzz.ratio(da.lower(), db.lower()) / 100.0
            if display_sim >= DISPLAY_NAME_LOW_THRESHOLD:
                continue

            a_label = f"{a['platform']}:{a['username']}"
            b_label = f"{b['platform']}:{b['username']}"

            claim = (
                f"Display name divergence: {a_label} uses '{da}' vs "
                f"{b_label} uses '{db}' "
                f"(username similarity: {username_sim*100:.0f}%, "
                f"display name similarity: {display_sim*100:.0f}%)"
            )

            results.append(InsightResult(
                category="identity_consistency",
                claim=claim,
                confidence="low",
                evidence=[EvidenceItem(
                    method="display_name_crosscheck",
                    detail=(
                        f"Usernames '{ua}' vs '{ub}' similarity: {username_sim:.2f}. "
                        f"Display names '{da}' vs '{db}' similarity: {display_sim:.2f}. "
                        f"Threshold for flag: display < {DISPLAY_NAME_LOW_THRESHOLD}"
                    ),
                    source_table="accounts",
                    source_id=None,
                )],
            ))

    return results


def run(conn, case_id: int) -> list[InsightResult]:
    """Run identity consistency checks (Pass 2 - depends on Pass 1 insights)."""
    results: list[InsightResult] = []
    results.extend(check_location_vs_timezone(conn, case_id))
    results.extend(check_display_name_consistency(conn, case_id))

    log.info("Case %d: consistency checker found %d issues", case_id, len(results))
    return results
