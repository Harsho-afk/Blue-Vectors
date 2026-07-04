"""
Load all authorized case data needed for report generation.
No external lookups — reads stored results only.
"""

import json
from auth import get_db_conn


def load_case_data(case_id: int, user_id: int) -> dict:
    """
    Load complete case data for report generation.
    Returns a dict with all sections needed by the builder.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Case metadata
        cur.execute(
            """
            SELECT c.id, c.title, c.status, c.created_at, c.closed_at,
                   u.full_name AS investigator_name, u.email AS investigator_email
            FROM cases c
            JOIN users u ON u.id = c.investigator_id
            WHERE c.id = %s AND c.investigator_id = %s
            """,
            (case_id, user_id),
        )
        case = cur.fetchone()
        if not case:
            return None

        # Seed identifiers
        cur.execute(
            """
            SELECT id, identifier_type, value, platform_hint, created_at
            FROM case_identifiers
            WHERE case_id = %s
            ORDER BY created_at
            """,
            (case_id,),
        )
        identifiers = [dict(r) for r in cur.fetchall()]

        # Collected accounts
        cur.execute(
            """
            SELECT id, platform, username, display_name, bio, location,
                   profile_image_url, created_at, karma,
                   follower_count, following_count
            FROM accounts
            WHERE case_id = %s
            ORDER BY platform, username
            """,
            (case_id,),
        )
        accounts = [dict(r) for r in cur.fetchall()]

        # Posts per account (count + date range)
        account_ids = [a["id"] for a in accounts]
        posts_meta = {}
        if account_ids:
            cur.execute(
                """
                SELECT account_id,
                       COUNT(*) AS post_count,
                       MIN(timestamp) AS earliest_post,
                       MAX(timestamp) AS latest_post
                FROM posts
                WHERE account_id = ANY(%s)
                  AND (metadata IS NULL OR metadata->>'type' != 'network')
                GROUP BY account_id
                """,
                (account_ids,),
            )
            for r in cur.fetchall():
                posts_meta[r["account_id"]] = dict(r)

        # Correlation results
        cur.execute(
            """
            SELECT lr.id, lr.account_a_id, lr.account_b_id,
                   lr.confidence, lr.shap_json, lr.created_at
            FROM linkage_results lr
            WHERE lr.case_id = %s
            ORDER BY lr.confidence DESC
            """,
            (case_id,),
        )
        correlations = []
        for r in cur.fetchall():
            row = dict(r)
            if isinstance(row["shap_json"], str):
                row["shap_json"] = json.loads(row["shap_json"])
            correlations.append(row)

        # Insights
        cur.execute(
            """
            SELECT id, account_id, category, claim, confidence, evidence, created_at
            FROM insights
            WHERE case_id = %s
            ORDER BY category, confidence DESC
            """,
            (case_id,),
        )
        insights = [dict(r) for r in cur.fetchall()]

        # OSINT lookups
        cur.execute(
            """
            SELECT id, lookup_type, input_value, result_json, created_at
            FROM osint_lookups
            WHERE case_id = %s
            ORDER BY created_at
            """,
            (case_id,),
        )
        lookups = []
        for r in cur.fetchall():
            row = dict(r)
            if isinstance(row["result_json"], str):
                row["result_json"] = json.loads(row["result_json"])
            lookups.append(row)

        # Intelligence briefing (optional)
        cur.execute(
            """
            SELECT id, narrative, claims, label, created_at
            FROM intelligence_reports
            WHERE case_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (case_id,),
        )
        intelligence = cur.fetchone()
        if intelligence:
            intelligence = dict(intelligence)
            if isinstance(intelligence["claims"], str):
                intelligence["claims"] = json.loads(intelligence["claims"])

        return {
            "case": dict(case),
            "identifiers": identifiers,
            "accounts": accounts,
            "posts_meta": posts_meta,
            "correlations": correlations,
            "insights": insights,
            "lookups": lookups,
            "intelligence": intelligence,
        }
    finally:
        conn.close()
