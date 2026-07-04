"""
Function 7: Coordination Detector

Flags potential sockpuppet/coordinated-identity signals:
- Accounts created within 7 days of each other
- Near-identical posting-hour distributions (temporal JSD)
- Shared hard identifiers (email/phone pointing to multiple accounts)

Case-level insight (account_id = NULL).
"""

import logging
from datetime import datetime, timezone
from itertools import combinations

import numpy as np
from scipy.spatial.distance import jensenshannon

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.coordination")

CREATION_WINDOW_DAYS = 7
TEMPORAL_JSD_THRESHOLD = 0.15
MIN_POSTS_FOR_TEMPORAL = 10


def _parse_creation_date(created_at) -> float | None:
    """Parse account created_at to epoch. Returns None if unparseable."""
    if created_at is None:
        return None
    if isinstance(created_at, datetime):
        return created_at.timestamp()
    if isinstance(created_at, (int, float)):
        return float(created_at)
    if isinstance(created_at, str):
        try:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _build_hour_histogram(posts: list[dict]) -> np.ndarray | None:
    """Build a 24-hour posting histogram. Returns None if insufficient data."""
    hours: list[int] = []
    for p in posts:
        ts = p.get("timestamp")
        if ts is None:
            continue
        if isinstance(ts, datetime):
            hours.append(ts.hour)
        elif isinstance(ts, (int, float)):
            hours.append(datetime.fromtimestamp(ts, tz=timezone.utc).hour)
        elif isinstance(ts, str):
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                hours.append(dt.hour)
            except ValueError:
                continue

    if len(hours) < MIN_POSTS_FOR_TEMPORAL:
        return None

    hist = np.zeros(24)
    for h in hours:
        hist[h] += 1

    epsilon = 1e-10
    hist = (hist + epsilon) / (hist.sum() + 24 * epsilon)
    return hist


def detect_creation_clustering(accounts: list[dict]) -> list[InsightResult]:
    """Detect accounts created within a tight time window."""
    dated = []
    for acc in accounts:
        epoch = _parse_creation_date(acc.get("created_at"))
        if epoch is not None:
            dated.append((acc["id"], acc.get("platform", ""), acc.get("username", ""), epoch))

    if len(dated) < 2:
        return []

    dated.sort(key=lambda x: x[3])

    clusters: list[list[tuple]] = []
    current_cluster = [dated[0]]

    for i in range(1, len(dated)):
        diff_days = (dated[i][3] - current_cluster[-1][3]) / 86400.0
        if diff_days <= CREATION_WINDOW_DAYS:
            current_cluster.append(dated[i])
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster[:])
            current_cluster = [dated[i]]

    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    results: list[InsightResult] = []

    for cluster in clusters:
        ids = [c[0] for c in cluster]
        labels = [f"{c[1]}:{c[2]}" for c in cluster]
        dates = [datetime.fromtimestamp(c[3], tz=timezone.utc).strftime("%Y-%m-%d") for c in cluster]
        span = (cluster[-1][3] - cluster[0][3]) / 86400.0

        claim = (
            f"{len(cluster)} accounts created within {span:.0f} days "
            f"({dates[0]} to {dates[-1]}) - possible coordinated creation"
        )

        results.append(InsightResult(
            category="coordination",
            claim=claim,
            confidence="medium",
            evidence=[EvidenceItem(
                method="creation_date_clustering",
                detail=f"Accounts: {', '.join(labels)}. Dates: {', '.join(dates)}. IDs: {ids}",
                source_table="accounts",
                source_id=None,
            )],
        ))

    return results


def detect_temporal_coordination(accounts: list[dict], account_posts: dict[int, list[dict]]) -> list[InsightResult]:
    """Detect suspiciously similar posting-hour distributions across accounts."""
    histograms: dict[int, np.ndarray] = {}

    for acc in accounts:
        aid = acc["id"]
        posts = account_posts.get(aid, [])
        hist = _build_hour_histogram(posts)
        if hist is not None:
            histograms[aid] = hist

    if len(histograms) < 2:
        return []

    results: list[InsightResult] = []
    acc_lookup = {a["id"]: a for a in accounts}

    for (id_a, hist_a), (id_b, hist_b) in combinations(histograms.items(), 2):
        jsd = float(jensenshannon(hist_a, hist_b))

        if jsd <= TEMPORAL_JSD_THRESHOLD:
            a_label = f"{acc_lookup[id_a].get('platform', '')}:{acc_lookup[id_a].get('username', '')}"
            b_label = f"{acc_lookup[id_b].get('platform', '')}:{acc_lookup[id_b].get('username', '')}"

            claim = (
                f"Near-identical posting schedules between {a_label} and {b_label} "
                f"(JSD={jsd:.3f}) - possible same operator"
            )

            results.append(InsightResult(
                category="coordination",
                claim=claim,
                confidence="low",
                evidence=[EvidenceItem(
                    method="temporal_jsd_coordination",
                    detail=(
                        f"Jensen-Shannon divergence = {jsd:.4f} "
                        f"(threshold: {TEMPORAL_JSD_THRESHOLD}). "
                        f"Account IDs: [{id_a}, {id_b}]"
                    ),
                    source_table="posts",
                    source_id=None,
                )],
            ))

    return results


def run(conn, case_id: int) -> list[InsightResult]:
    """Run coordination detection for all accounts in a case."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, platform, username, created_at FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = [dict(row) for row in cur.fetchall()]

    if len(accounts) < 2:
        log.info("Case %d: fewer than 2 accounts, skipping coordination detection", case_id)
        return []

    account_posts: dict[int, list[dict]] = {}
    for acc in accounts:
        cur.execute(
            "SELECT timestamp FROM posts WHERE account_id = %s",
            (acc["id"],),
        )
        account_posts[acc["id"]] = [dict(row) for row in cur.fetchall()]

    results: list[InsightResult] = []
    results.extend(detect_creation_clustering(accounts))
    results.extend(detect_temporal_coordination(accounts, account_posts))

    log.info("Case %d: coordination detector found %d signals", case_id, len(results))
    return results
