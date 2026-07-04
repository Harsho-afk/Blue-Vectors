"""
Function 2: Username Distinctiveness Scorer

Uses Maigret empirical data: distinctiveness = 1 - (hits / total_checked).
NOT an insight row — returns a float that the correlation engine uses as a
multiplier on username similarity.

"xj9_voidwalker_2003" found on 3/500 sites = 0.994 distinctiveness.
"alex" found on 200/500 = 0.60 distinctiveness.
"""

import json
import logging

log = logging.getLogger("aria.insights.distinctiveness")


def compute_distinctiveness(conn, case_id: int, username: str) -> float:
    """
    Compute username distinctiveness from Maigret results.

    Returns 0.0-1.0 where higher = more distinctive.
    Falls back to 0.5 (neutral) if no Maigret data is available.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT result_json FROM osint_lookups
        WHERE case_id = %s AND lookup_type = 'maigret'
        ORDER BY created_at DESC
        """,
        (case_id,),
    )
    rows = cur.fetchall()

    for row in rows:
        raw = row["result_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)

        if raw.get("username", "").lower() != username.lower():
            continue

        total_found = raw.get("total_found", 0)
        total_checked = raw.get("total_checked", 0)

        if total_checked == 0:
            continue

        distinctiveness = 1.0 - (total_found / total_checked)
        distinctiveness = max(0.0, min(1.0, distinctiveness))

        log.info(
            "Username '%s': %d/%d platforms → distinctiveness %.3f",
            username, total_found, total_checked, distinctiveness,
        )
        return distinctiveness

    log.info("Username '%s': no Maigret data found, defaulting to 0.5", username)
    return 0.5


def get_case_distinctiveness(conn, case_id: int) -> dict[str, float]:
    """
    Compute distinctiveness for all usernames that have Maigret data in this case.
    Returns {username_lower: distinctiveness_score}.
    """
    cur = conn.cursor()
    cur.execute(
        """
        SELECT result_json FROM osint_lookups
        WHERE case_id = %s AND lookup_type = 'maigret'
        ORDER BY created_at DESC
        """,
        (case_id,),
    )
    rows = cur.fetchall()

    scores: dict[str, float] = {}

    for row in rows:
        raw = row["result_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)

        username = raw.get("username", "").lower()
        if not username or username in scores:
            continue

        total_found = raw.get("total_found", 0)
        total_checked = raw.get("total_checked", 0)

        if total_checked == 0:
            continue

        scores[username] = max(0.0, min(1.0, 1.0 - (total_found / total_checked)))

    log.info("Case %d: computed distinctiveness for %d usernames", case_id, len(scores))
    return scores
