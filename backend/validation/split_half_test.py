"""
ARIA Validation Harness — Split-Half Correlation Test

For N Reddit users, splits each user's posts 50/50 by index, runs the
correlator on same-author halves (should score HIGH) vs cross-author
pairs (should score LOW), and reports score distributions + AUC.

Usage (inside the backend container):
    python -m validation.split_half_test

If fewer than 10 Reddit accounts exist in the DB, collects a set of
well-known Reddit users first.
"""

import asyncio
import json
import logging
import random
import sys
from itertools import combinations

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(name)s | %(message)s",
)
log = logging.getLogger("aria.validation")

MIN_ACCOUNTS = 10
MIN_POSTS = 10

SEED_USERNAMES = [
    "spez",
    "GovSchwarzenegger",
    "thisisbillgates",
    "Here_Comes_The_King",
    "PeterMayhew",
    "williamshatner",
    "StanGetz753",
    "Shitty_Watercolour",
    "iamMothership",
    "ElonMuskOfficial",
    "Poem_for_your_sprog",
    "awkwardtheturtle",
    "gallowboob",
    "way_fairer",
    "unidan",
]


def _collect_reddit_users(conn, case_id: int, usernames: list[str]):
    """Collect Reddit profiles into the given case."""
    from collector.base import collect_async, save_to_db

    async def _collect_all():
        for username in usernames:
            cur = conn.cursor()
            cur.execute(
                "SELECT id FROM accounts WHERE case_id = %s AND platform = 'reddit' AND username = %s",
                (case_id, username),
            )
            if cur.fetchone():
                log.info("  %s already collected, skipping", username)
                continue

            try:
                log.info("  Collecting %s ...", username)
                profile = await collect_async("reddit", username)
                save_to_db(profile, conn, case_id)
                log.info("  %s: %d posts", username, len(profile.posts))
            except Exception as e:
                log.warning("  %s failed: %s", username, e)

    asyncio.run(_collect_all())


def _load_reddit_accounts(conn, case_id: int) -> list[dict]:
    """Load Reddit accounts with their posts."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, platform, username, display_name, bio, location, profile_image_url "
        "FROM accounts WHERE case_id = %s AND platform = 'reddit'",
        (case_id,),
    )
    accounts = [dict(row) for row in cur.fetchall()]

    for acc in accounts:
        cur.execute(
            "SELECT text, timestamp, metadata FROM posts WHERE account_id = %s ORDER BY id",
            (acc["id"],),
        )
        posts = []
        for row in cur.fetchall():
            r = dict(row)
            if isinstance(r.get("metadata"), str):
                try:
                    r["metadata"] = json.loads(r["metadata"])
                except (json.JSONDecodeError, TypeError):
                    r["metadata"] = {}
            posts.append(r)
        acc["posts"] = posts

    return [a for a in accounts if len(a["posts"]) >= MIN_POSTS]


def _make_synthetic_account(source: dict, half_label: str, posts: list[dict]) -> dict:
    """Create a synthetic account dict from a source account and a post subset."""
    return {
        "id": hash((source["id"], half_label)) % (10**9),
        "platform": source["platform"],
        "username": source["username"],
        "display_name": source.get("display_name"),
        "bio": source.get("bio"),
        "location": source.get("location"),
        "profile_image_url": source.get("profile_image_url"),
        "image_embedding": None,
        "posts": posts,
    }


def _run_validation(accounts: list[dict]) -> dict:
    """Split each account, correlate pairs, return score distributions."""
    from correlator import correlate_pair

    same_author_scores = []
    diff_author_scores = []

    synth_accounts = []
    for acc in accounts:
        posts = acc["posts"]
        mid = len(posts) // 2
        half_a = posts[:mid]
        half_b = posts[mid:]

        synth_a = _make_synthetic_account(acc, "A", half_a)
        synth_b = _make_synthetic_account(acc, "B", half_b)
        synth_accounts.append((acc["username"], synth_a, synth_b))

    log.info("Running same-author pairs (%d pairs)...", len(synth_accounts))
    for username, synth_a, synth_b in synth_accounts:
        result = correlate_pair(
            synth_a, synth_a["posts"],
            synth_b, synth_b["posts"],
            maigret_links=[],
            distinctiveness={},
            geo_insights={},
        )
        score = result["confidence"]
        same_author_scores.append(score)
        log.info(
            "  SAME  %-20s: %.1f%% [temporal=%.2f community=%.2f stylometry=%.2f]",
            username,
            score * 100,
            result.get("temporal_score") or 0,
            result.get("community_score") or 0,
            result.get("stylometry_score") or 0,
        )

    cross_pairs = list(combinations(range(len(synth_accounts)), 2))
    if len(cross_pairs) > 50:
        random.seed(42)
        cross_pairs = random.sample(cross_pairs, 50)

    log.info("Running cross-author pairs (%d pairs)...", len(cross_pairs))
    for i, j in cross_pairs:
        _, synth_a_i, _ = synth_accounts[i]
        _, _, synth_b_j = synth_accounts[j]

        result = correlate_pair(
            synth_a_i, synth_a_i["posts"],
            synth_b_j, synth_b_j["posts"],
            maigret_links=[],
            distinctiveness={},
            geo_insights={},
        )
        score = result["confidence"]
        diff_author_scores.append(score)

    return {
        "same_author_scores": same_author_scores,
        "diff_author_scores": diff_author_scores,
    }


def _compute_auc(same_scores: list[float], diff_scores: list[float]) -> float:
    """Compute AUC via the Mann-Whitney U statistic."""
    n_same = len(same_scores)
    n_diff = len(diff_scores)
    if n_same == 0 or n_diff == 0:
        return 0.0

    concordant = 0
    tied = 0
    for s in same_scores:
        for d in diff_scores:
            if s > d:
                concordant += 1
            elif s == d:
                tied += 1

    return (concordant + 0.5 * tied) / (n_same * n_diff)


def _report(results: dict):
    """Print a formatted report."""
    same = results["same_author_scores"]
    diff = results["diff_author_scores"]

    auc = _compute_auc(same, diff)

    def stats(scores):
        if not scores:
            return {"n": 0, "mean": 0, "min": 0, "max": 0, "median": 0}
        s = sorted(scores)
        return {
            "n": len(s),
            "mean": sum(s) / len(s),
            "min": s[0],
            "max": s[-1],
            "median": s[len(s) // 2],
        }

    same_s = stats(same)
    diff_s = stats(diff)

    print("\n" + "=" * 60)
    print("  ARIA CORRELATION ENGINE — SPLIT-HALF VALIDATION")
    print("=" * 60)

    print(f"\n  Same-author pairs:   {same_s['n']}")
    print(f"  Cross-author pairs:  {diff_s['n']}")

    print(f"\n  {'Metric':<25} {'Same-Author':>12} {'Cross-Author':>12}")
    print(f"  {'-'*25} {'-'*12} {'-'*12}")
    print(f"  {'Mean confidence':<25} {same_s['mean']*100:>11.1f}% {diff_s['mean']*100:>11.1f}%")
    print(f"  {'Median confidence':<25} {same_s['median']*100:>11.1f}% {diff_s['median']*100:>11.1f}%")
    print(f"  {'Min confidence':<25} {same_s['min']*100:>11.1f}% {diff_s['min']*100:>11.1f}%")
    print(f"  {'Max confidence':<25} {same_s['max']*100:>11.1f}% {diff_s['max']*100:>11.1f}%")

    print(f"\n  AUC (higher = better separation): {auc:.3f}")

    if auc >= 0.80:
        verdict = "GOOD — engine reliably separates same vs. different authors"
    elif auc >= 0.65:
        verdict = "FAIR — some separation, room for weight tuning"
    else:
        verdict = "POOR — engine cannot distinguish same vs. different authors"

    print(f"  Verdict: {verdict}")

    # Separation gap
    gap = same_s["mean"] - diff_s["mean"]
    print(f"  Mean score gap: {gap*100:+.1f} percentage points")

    print("\n" + "=" * 60)


def main():
    from auth import get_db_conn

    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Find or create a validation case
        cur.execute("SELECT id FROM cases WHERE title = '__validation_split_half__'")
        row = cur.fetchone()
        if row:
            case_id = row["id"]
            log.info("Using existing validation case %d", case_id)
        else:
            cur.execute(
                "INSERT INTO cases (investigator_id, title, status) VALUES (1, '__validation_split_half__', 'open') RETURNING id"
            )
            case_id = cur.fetchone()["id"]
            conn.commit()
            log.info("Created validation case %d", case_id)

        # Check existing Reddit accounts
        accounts = _load_reddit_accounts(conn, case_id)
        log.info("Found %d Reddit accounts with >= %d posts", len(accounts), MIN_POSTS)

        if len(accounts) < MIN_ACCOUNTS:
            log.info("Need %d+ accounts. Collecting Reddit users...", MIN_ACCOUNTS)
            _collect_reddit_users(conn, case_id, SEED_USERNAMES)
            accounts = _load_reddit_accounts(conn, case_id)
            log.info("Now have %d usable accounts", len(accounts))

        if len(accounts) < 3:
            print("ERROR: Need at least 3 accounts with %d+ posts. Got %d." % (MIN_POSTS, len(accounts)))
            sys.exit(1)

        log.info(
            "Accounts: %s",
            ", ".join("%s(%dp)" % (a["username"], len(a["posts"])) for a in accounts),
        )

        results = _run_validation(accounts)
        _report(results)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
