"""
Function 6: Network Geography

Matches an account's subreddit activity against a dictionary of known
geographic subreddits. Counts distinct geographic signals per region.

REVISION: Confidence capped at "medium" always — diaspora/interest-vs-residence
ambiguity means subreddit-only geography should never read "high" on its own.
"""

import json
import logging
import os
from collections import Counter

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.network_geo")

_geo_dict: dict | None = None


def _load_geo_dict() -> dict:
    global _geo_dict
    if _geo_dict is not None:
        return _geo_dict

    data_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "geo_subreddits.json",
    )

    with open(data_path, encoding="utf-8") as f:
        raw = json.load(f)

    _geo_dict = {
        k.lower(): v for k, v in raw.items()
        if isinstance(v, dict) and "region" in v
    }

    log.info("Loaded %d geographic subreddit mappings", len(_geo_dict))
    return _geo_dict


def analyze_account(account_id: int, posts: list[dict]) -> list[InsightResult]:
    """Analyze geographic signals from an account's subreddit activity."""
    geo = _load_geo_dict()

    sub_counts: Counter = Counter()
    for p in posts:
        md = p.get("metadata")
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except (json.JSONDecodeError, TypeError):
                md = {}
        if not isinstance(md, dict):
            continue

        subreddit = (md.get("subreddit") or "").strip().lower()
        if subreddit:
            sub_counts[subreddit] += 1

    if not sub_counts:
        return []

    region_evidence: dict[str, list[tuple[str, int]]] = {}

    for sub, count in sub_counts.items():
        entry = geo.get(sub)
        if not entry:
            continue
        region = entry["region"]
        region_evidence.setdefault(region, []).append((sub, count))

    if not region_evidence:
        return []

    results: list[InsightResult] = []

    ranked = sorted(
        region_evidence.items(),
        key=lambda x: (len(x[1]), sum(c for _, c in x[1])),
        reverse=True,
    )

    for region, subs in ranked[:3]:
        distinct_subs = len(subs)
        total_posts = sum(count for _, count in subs)

        sub_details = ", ".join(
            f"r/{s} ({c} posts)" for s, c in sorted(subs, key=lambda x: -x[1])
        )

        if distinct_subs >= 2:
            confidence = "medium"
        else:
            confidence = "low"

        claim = f"Network signals suggest {region} ({distinct_subs} geographic subreddit(s), {total_posts} posts)"

        results.append(InsightResult(
            category="geography",
            claim=claim,
            confidence=confidence,
            account_id=account_id,
            evidence=[EvidenceItem(
                method="geographic_subreddit_membership",
                detail=f"Active in: {sub_details}",
                source_table="posts",
                source_id=None,
            )],
        ))

    return results


def run(conn, case_id: int) -> list[InsightResult]:
    """Run network geography analysis for all Reddit accounts in a case."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, platform FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = cur.fetchall()

    results: list[InsightResult] = []

    for acc in accounts:
        if acc["platform"] != "reddit":
            continue

        account_id = acc["id"]
        cur.execute(
            "SELECT metadata FROM posts WHERE account_id = %s",
            (account_id,),
        )
        posts = [dict(row) for row in cur.fetchall()]

        results.extend(analyze_account(account_id, posts))

    log.info("Case %d: network geography found %d geographic signals", case_id, len(results))
    return results
