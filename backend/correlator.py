"""
ARIA — Pairwise identity correlation engine.

Fuses feature scores into a confidence value and runs all-pairs
comparison across accounts in a case.
"""

import json
import logging
from itertools import combinations

from features import username_similarity, bio_similarity, temporal_similarity
from auth import get_db_conn

log = logging.getLogger("aria.correlator")

WEIGHTS = {
    "username": 0.40,
    "bio": 0.35,
    "temporal": 0.25,
}


def correlate_pair(
    account_a: dict,
    posts_a: list[dict],
    account_b: dict,
    posts_b: list[dict],
) -> dict:
    """Compare two accounts using all available signals and produce a confidence score."""
    u_score = username_similarity(
        account_a.get("username", ""),
        account_a.get("display_name"),
        account_b.get("username", ""),
        account_b.get("display_name"),
    )

    b_score = bio_similarity(
        account_a.get("bio"),
        account_b.get("bio"),
    )

    t_score = temporal_similarity(posts_a, posts_b)

    signals: dict = {}
    available_weights: dict = {}
    notes: list[str] = []

    signals["username_score"] = round(u_score, 4)
    available_weights["username"] = WEIGHTS["username"]

    if b_score is not None:
        signals["bio_score"] = round(b_score, 4)
        available_weights["bio"] = WEIGHTS["bio"]
    else:
        signals["bio_score"] = None
        notes.append("Bio score unavailable — excluded, weights renormalized")

    if t_score is not None:
        signals["temporal_score"] = round(t_score, 4)
        available_weights["temporal"] = WEIGHTS["temporal"]
    else:
        signals["temporal_score"] = None
        notes.append("Temporal score unavailable — excluded, weights renormalized")

    if not available_weights:
        confidence = 0.0
    else:
        total_weight = sum(available_weights.values())
        confidence = sum(
            (available_weights[key] / total_weight) * signals[f"{key}_score"]
            for key in available_weights
            if signals.get(f"{key}_score") is not None
        )

    confidence = round(confidence, 4)
    confidence_pct = round(confidence * 100, 1)

    if confidence_pct <= 40:
        band = "Low"
    elif confidence_pct <= 70:
        band = "Medium"
    else:
        band = "High"

    a_id = account_a["id"]
    b_id = account_b["id"]
    if a_id > b_id:
        a_id, b_id = b_id, a_id

    return {
        "account_a_id": a_id,
        "account_b_id": b_id,
        "account_a_platform": account_a.get("platform", ""),
        "account_a_username": account_a.get("username", ""),
        "account_b_platform": account_b.get("platform", ""),
        "account_b_username": account_b.get("username", ""),
        **signals,
        "confidence": confidence,
        "confidence_pct": confidence_pct,
        "band": band,
        "notes": notes,
    }


def correlate_case(case_id: int) -> list[dict]:
    """
    Run pairwise correlation on all accounts in a case.
    Deletes previous results and replaces them.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        cur.execute(
            "SELECT id, case_id, platform, username, display_name, bio, location "
            "FROM accounts WHERE case_id = %s",
            (case_id,),
        )
        accounts = [dict(row) for row in cur.fetchall()]

        if len(accounts) < 2:
            log.info("Case %d has fewer than 2 accounts — nothing to correlate", case_id)
            return []

        account_posts: dict[int, list[dict]] = {}
        for acc in accounts:
            cur.execute(
                "SELECT text, timestamp, metadata FROM posts WHERE account_id = %s",
                (acc["id"],),
            )
            posts = []
            for row in cur.fetchall():
                row_dict = dict(row)
                md = row_dict.get("metadata")
                if isinstance(md, str):
                    try:
                        row_dict["metadata"] = json.loads(md)
                    except (json.JSONDecodeError, TypeError):
                        row_dict["metadata"] = {}
                posts.append(row_dict)
            account_posts[acc["id"]] = posts

        log.info(
            "Case %d: correlating %d accounts (%d pairs)",
            case_id, len(accounts), len(accounts) * (len(accounts) - 1) // 2,
        )

        cur.execute("DELETE FROM linkage_results WHERE case_id = %s", (case_id,))

        results = []
        for acc_a, acc_b in combinations(accounts, 2):
            result = correlate_pair(
                acc_a, account_posts.get(acc_a["id"], []),
                acc_b, account_posts.get(acc_b["id"], []),
            )
            result["case_id"] = case_id

            shap_data = {
                "username_score": result["username_score"],
                "bio_score": result["bio_score"],
                "temporal_score": result["temporal_score"],
                "confidence": result["confidence"],
                "confidence_pct": result["confidence_pct"],
                "band": result["band"],
                "notes": result["notes"],
            }

            cur.execute(
                """
                INSERT INTO linkage_results
                    (case_id, account_a_id, account_b_id, confidence, shap_json)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    case_id,
                    result["account_a_id"],
                    result["account_b_id"],
                    result["confidence_pct"],
                    json.dumps(shap_data),
                ),
            )

            results.append(result)

        conn.commit()
        log.info("Case %d: correlation complete — %d pairs scored", case_id, len(results))

    finally:
        conn.close()

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results
