"""
ARIA — OSINT Lookup routes
POST /api/cases/{case_id}/osint/username-search   { username }  → platforms found
POST /api/cases/{case_id}/osint/breach-lookup      { email }     → breach list
GET  /api/cases/{case_id}/osint                    list all OSINT lookups for a case
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from auth import get_current_user, get_db_conn, DB_TYPE
from osint import username_search, breach_lookup, save_username_search, save_breach_lookup

router = APIRouter(prefix="/api/cases", tags=["osint"])


# ── Pydantic Models ───────────────────────────────────────────────────────────

class UsernameSearchRequest(BaseModel):
    username: str


class BreachLookupRequest(BaseModel):
    email: EmailStr


# ── Helper ────────────────────────────────────────────────────────────────────

def _check_case_ownership(conn, case_id: int, user_id: int):
    cur = conn.cursor()
    if DB_TYPE == "sqlite":
        cur.execute("SELECT investigator_id FROM cases WHERE id = ?", (case_id,))
    else:
        cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if row[0] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/{case_id}/osint/username-search")
async def run_username_search(
    case_id: int,
    body: UsernameSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Search for a username across 50+ platforms.
    Results are saved to osint_lookups and returned immediately.
    """
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    result = await username_search(body.username)

    conn = get_db_conn()
    try:
        lookup_id = save_username_search(conn, case_id, result, db_type=DB_TYPE)
    finally:
        conn.close()

    return {
        "lookup_id": lookup_id,
        "username": result.username,
        "platforms_checked": result.platforms_checked,
        "platforms_found": [
            {
                "platform": p.platform,
                "url": p.url,
                "response_time_ms": p.response_time_ms,
            }
            for p in result.platforms_found
        ],
        "platforms_found_count": len(result.platforms_found),
        "errors_count": len(result.errors),
    }


@router.post("/{case_id}/osint/breach-lookup")
async def run_breach_lookup(
    case_id: int,
    body: BreachLookupRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Check if an email appeared in known data breaches (HaveIBeenPwned).
    Results are saved to osint_lookups and returned immediately.
    """
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    result = await breach_lookup(body.email)

    conn = get_db_conn()
    try:
        lookup_id = save_breach_lookup(conn, case_id, result, db_type=DB_TYPE)
    finally:
        conn.close()

    return {
        "lookup_id": lookup_id,
        "email": result.email,
        "total_breaches": result.total_breaches,
        "breaches": [
            {
                "name": b.name,
                "domain": b.domain,
                "breach_date": b.breach_date,
                "data_classes": b.data_classes,
                "is_verified": b.is_verified,
            }
            for b in result.breaches
        ],
        "error": result.error,
    }


@router.get("/{case_id}/osint")
def list_osint_lookups(
    case_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    List all OSINT lookups for a case (username searches + breach lookups).
    """
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()

        if DB_TYPE == "sqlite":
            cur.execute(
                """
                SELECT id, case_id, lookup_type, input_value, result_json, created_at
                FROM osint_lookups
                WHERE case_id = ?
                ORDER BY created_at DESC
                """,
                (case_id,),
            )
        else:
            cur.execute(
                """
                SELECT id, case_id, lookup_type, input_value, result_json, created_at
                FROM osint_lookups
                WHERE case_id = %s
                ORDER BY created_at DESC
                """,
                (case_id,),
            )

        rows = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    lookups = []
    for row in rows:
        result_data = row["result_json"]
        if isinstance(result_data, str):
            result_data = json.loads(result_data)

        lookups.append({
            "id": row["id"],
            "lookup_type": row["lookup_type"],
            "input_value": row["input_value"],
            "result": result_data,
            "created_at": str(row["created_at"]),
        })

    return {"lookups": lookups}
