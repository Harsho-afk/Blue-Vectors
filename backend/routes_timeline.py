"""
ARIA — Timeline endpoint
GET /api/cases/{case_id}/timeline   → { events[], accounts[], time_range }

Assembles chronological events from:
- accounts (creation dates)
- posts (all activity)
- osint_lookups (discovery events + breach dates)
- linkage_results (correlation events)
- insights (analytical events)
- intelligence_reports (report generation events)
"""
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from auth import get_current_user, get_db_conn

router = APIRouter(prefix="/api/cases", tags=["timeline"])


def _check_case_ownership(conn, case_id: int, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if row["investigator_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


def _parse_json(val):
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return {}
    return val or {}


def _ts(val):
    """Convert a datetime/timestamp to ISO string, or None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _post_event_type(metadata):
    """Map post metadata.type to a timeline event_type."""
    t = (metadata or {}).get("type", "post")
    mapping = {
        "submission": "post",
        "comment": "comment",
        "tweet": "post",
        "repo": "repo",
        "push": "push",
        "pr": "push",
        "issue": "comment",
        "fork": "repo",
        "star": "repo",
        "create": "repo",
        "release": "repo",
        "event": "post",
        "network": "network",
        "post": "post",
        "reel": "post",
        "video": "post",
        "carousel": "post",
    }
    return mapping.get(t, "post")


@router.get("/{case_id}/timeline")
def get_case_timeline(case_id: int, current_user: dict = Depends(get_current_user)):
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()

        events = []

        # ─── 1. Account map ─────────────────────────────────────────────────
        cur.execute(
            """SELECT id, platform, username, display_name, profile_image_url, created_at
               FROM accounts WHERE case_id = %s""",
            (case_id,),
        )
        accounts_list = []
        account_map = {}
        for row in cur.fetchall():
            a = dict(row)
            account_map[a["id"]] = a
            accounts_list.append({
                "id": a["id"],
                "platform": a["platform"],
                "username": a["username"],
                "display_name": a["display_name"],
                "avatar": a["profile_image_url"],
            })

            # Account creation event
            if a["created_at"]:
                events.append({
                    "id": f"account_created:{a['id']}",
                    "timestamp": _ts(a["created_at"]),
                    "event_type": "account_created",
                    "platform": a["platform"],
                    "account_id": a["id"],
                    "account_label": f"{a['platform']}:{a['username']}",
                    "title": f"Account created on {a['platform'].title()}",
                    "description": a["display_name"] or a["username"],
                })

        # ─── 2. Posts (activity events) ──────────────────────────────────────
        if account_map:
            account_ids = list(account_map.keys())
            placeholders = ",".join(["%s"] * len(account_ids))
            cur.execute(
                f"""SELECT id, account_id, text, timestamp, metadata, spike_flag
                    FROM posts
                    WHERE account_id IN ({placeholders})
                    AND (metadata->>'type' IS NULL OR metadata->>'type' != 'network')
                    ORDER BY timestamp""",
                tuple(account_ids),
            )
            for row in cur.fetchall():
                p = dict(row)
                meta = _parse_json(p["metadata"])
                acct = account_map.get(p["account_id"], {})
                event_type = _post_event_type(meta)
                platform = acct.get("platform", "")
                username = acct.get("username", "")

                # Build title based on event type
                post_type = meta.get("type", "post")
                if post_type == "submission":
                    sub = meta.get("subreddit", "")
                    title = f"Posted in r/{sub}" if sub else "Reddit post"
                elif post_type == "comment":
                    sub = meta.get("subreddit", "")
                    title = f"Commented in r/{sub}" if sub else "Comment"
                elif post_type == "tweet":
                    title = "Tweet"
                elif post_type == "repo":
                    title = f"Repository: {meta.get('repo', '')}" if meta.get("repo") else "Repository event"
                elif post_type == "push":
                    title = f"Push to {meta.get('repo', '')}" if meta.get("repo") else "Code push"
                elif post_type in ("pr", "issue"):
                    title = f"{'PR' if post_type == 'pr' else 'Issue'} on {meta.get('repo', '')}"
                elif post_type in ("post", "reel", "video", "carousel"):
                    title = f"Instagram {post_type}" if platform == "instagram" else post_type.title()
                else:
                    title = f"{platform.title()} activity"

                text_preview = (p["text"] or "")[:150]
                if len(p["text"] or "") > 150:
                    text_preview += "…"

                events.append({
                    "id": f"post:{p['id']}",
                    "timestamp": _ts(p["timestamp"]),
                    "event_type": event_type,
                    "platform": platform,
                    "account_id": p["account_id"],
                    "account_label": f"{platform}:{username}",
                    "title": title,
                    "description": text_preview or None,
                    "spike": p.get("spike_flag", False),
                    "metadata": {
                        k: v for k, v in meta.items()
                        if k in ("subreddit", "repo", "language", "topics", "score",
                                 "retweet_count", "favorite_count", "like_count",
                                 "comment_count", "url")
                    } or None,
                })

        # ─── 3. OSINT Lookups ────────────────────────────────────────────────
        cur.execute(
            """SELECT id, lookup_type, input_value, result_json, created_at
               FROM osint_lookups WHERE case_id = %s""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            result = _parse_json(r["result_json"])
            lookup_type = r["lookup_type"]

            # Discovery event
            events.append({
                "id": f"osint:{r['id']}",
                "timestamp": _ts(r["created_at"]),
                "event_type": "osint_lookup",
                "platform": None,
                "account_id": None,
                "account_label": None,
                "title": f"OSINT lookup: {lookup_type}",
                "description": f"Searched for '{r['input_value']}'",
            })

            # Extract breach dates
            if lookup_type in ("hibp", "xposedornot"):
                breaches = result.get("breaches", [])
                for b in breaches[:10]:
                    breach_date = b.get("breach_date") or b.get("BreachDate")
                    if breach_date:
                        events.append({
                            "id": f"breach:{r['id']}:{b.get('name', b.get('Name', ''))}",
                            "timestamp": breach_date if "T" in str(breach_date) else f"{breach_date}T00:00:00Z",
                            "event_type": "breach",
                            "platform": None,
                            "account_id": None,
                            "account_label": None,
                            "title": f"Breach: {b.get('name', b.get('Name', 'Unknown'))}",
                            "description": f"Email '{r['input_value']}' found in data breach",
                            "metadata": {
                                "domain": b.get("domain", b.get("Domain")),
                                "data_classes": b.get("data_classes", b.get("DataClasses", [])),
                            },
                        })

        # ─── 4. Correlation events ───────────────────────────────────────────
        cur.execute(
            """SELECT lr.id, lr.confidence, lr.shap_json, lr.created_at,
                      a1.platform as a_platform, a1.username as a_username,
                      a2.platform as b_platform, a2.username as b_username
               FROM linkage_results lr
               JOIN accounts a1 ON lr.account_a_id = a1.id
               JOIN accounts a2 ON lr.account_b_id = a2.id
               WHERE lr.case_id = %s""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            shap = _parse_json(r["shap_json"])
            conf = float(r["confidence"] or 0)
            band = shap.get("band", "Low")
            events.append({
                "id": f"correlation:{r['id']}",
                "timestamp": _ts(r["created_at"]),
                "event_type": "correlation",
                "platform": None,
                "account_id": None,
                "account_label": None,
                "title": f"Correlation: {r['a_platform']}:{r['a_username']} ↔ {r['b_platform']}:{r['b_username']}",
                "description": f"{conf:.0f}% confidence ({band})",
                "confidence": band.lower(),
            })

        # ─── 5. Insight events ───────────────────────────────────────────────
        cur.execute(
            """SELECT id, account_id, category, claim, confidence, created_at
               FROM insights WHERE case_id = %s""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            acct = account_map.get(r["account_id"], {})
            label = f"{acct['platform']}:{acct['username']}" if acct else None
            events.append({
                "id": f"insight:{r['id']}",
                "timestamp": _ts(r["created_at"]),
                "event_type": "insight",
                "platform": acct.get("platform"),
                "account_id": r["account_id"],
                "account_label": label,
                "title": f"Insight: {r['category'].replace('_', ' ').title()}",
                "description": r["claim"],
                "confidence": r["confidence"],
            })

        # ─── 6. Intelligence report events ───────────────────────────────────
        cur.execute(
            """SELECT id, created_at, label FROM intelligence_reports WHERE case_id = %s""",
            (case_id,),
        )
        for row in cur.fetchall():
            r = dict(row)
            events.append({
                "id": f"report:{r['id']}",
                "timestamp": _ts(r["created_at"]),
                "event_type": "report",
                "platform": None,
                "account_id": None,
                "account_label": None,
                "title": "Intelligence Report Generated",
                "description": r.get("label", ""),
            })

        # ─── Sort all events by timestamp ────────────────────────────────────
        def sort_key(e):
            ts = e.get("timestamp")
            if not ts:
                return ""
            return ts

        events.sort(key=sort_key)

        # ─── Compute time range ─────────────────────────────────────────────
        timestamps = [e["timestamp"] for e in events if e.get("timestamp")]
        time_range = {
            "earliest": timestamps[0] if timestamps else None,
            "latest": timestamps[-1] if timestamps else None,
            "total_events": len(events),
        }

    finally:
        conn.close()

    return {
        "events": events,
        "accounts": accounts_list,
        "time_range": time_range,
    }
