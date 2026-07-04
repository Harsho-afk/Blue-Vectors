"""
ARIA — OSINT Lookup routes

POST /api/cases/{case_id}/osint/username-search   { username, max_sites? }  → Maigret results
POST /api/cases/{case_id}/osint/breach-lookup      { email }                → breach list
POST /api/cases/{case_id}/osint/phone-lookup       { phone }                → phone OSINT
GET  /api/cases/{case_id}/osint                    list all OSINT lookups for a case
POST /api/cases/{case_id}/osint/import-account     { platform, username, url, ... } → account_id
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from auth import get_current_user, get_db_conn
from osint import run_maigret, breach_lookup, save_maigret_search, save_breach_lookup
from collector.phone import PhoneCollector
from lead_scorer import score_maigret_results

router = APIRouter(prefix="/api/cases", tags=["osint"])


# ── Pydantic Models ───────────────────────────────────────────────────────────

class UsernameSearchRequest(BaseModel):
    username: str
    max_sites: int = 500


class BreachLookupRequest(BaseModel):
    email: EmailStr


class PhoneLookupRequest(BaseModel):
    phone: str


class ImportAccountRequest(BaseModel):
    platform: str
    username: str
    url: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    location: Optional[str] = None


# ── Helper ────────────────────────────────────────────────────────────────────

def _check_case_ownership(conn, case_id: int, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if row["investigator_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/{case_id}/osint/username-search")
async def run_username_search(
    case_id: int,
    body: UsernameSearchRequest,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    result = await run_maigret(body.username, max_sites=body.max_sites)

    conn = get_db_conn()
    try:
        lookup_id = save_maigret_search(conn, case_id, result)
    finally:
        conn.close()

    return {"lookup_id": lookup_id, **result}


@router.post("/{case_id}/osint/breach-lookup")
async def run_breach_lookup(
    case_id: int,
    body: BreachLookupRequest,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    result = await breach_lookup(body.email)

    conn = get_db_conn()
    try:
        lookup_id = save_breach_lookup(conn, case_id, result)
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


@router.post("/{case_id}/osint/phone-lookup")
async def run_phone_lookup(
    case_id: int,
    body: PhoneLookupRequest,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    try:
        profile = await PhoneCollector().collect(body.phone)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Phone lookup failed: {e}")

    result = profile.to_dict()

    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO osint_lookups (case_id, lookup_type, input_value, result_json)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (case_id, "phone", body.phone, json.dumps(result)),
        )
        lookup_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    return {"lookup_id": lookup_id, **result}


@router.get("/{case_id}/osint")
def list_osint_lookups(
    case_id: int,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
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

        if row["lookup_type"] == "maigret" and "lead_summary" not in result_data:
            result_data = score_maigret_results(result_data)

        lookups.append({
            "id": row["id"],
            "case_id": row["case_id"],
            "lookup_type": row["lookup_type"],
            "input_value": row["input_value"],
            "result": result_data,
            "created_at": str(row["created_at"]),
        })

    return {"lookups": lookups}


@router.post("/{case_id}/osint/import-account", status_code=status.HTTP_201_CREATED)
def import_account(
    case_id: int,
    body: ImportAccountRequest,
    current_user: dict = Depends(get_current_user),
):
    """Import a discovered OSINT account into the case's accounts table."""
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO accounts (case_id, platform, username, display_name, bio,
                                  location, profile_image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (case_id, platform, username) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                bio = EXCLUDED.bio,
                location = EXCLUDED.location,
                profile_image_url = EXCLUDED.profile_image_url
            RETURNING id
            """,
            (
                case_id,
                body.platform.lower(),
                body.username,
                body.display_name,
                body.bio,
                body.location,
                body.avatar_url,
            ),
        )
        account_id = cur.fetchone()["id"]
        conn.commit()
    finally:
        conn.close()

    return {"account_id": account_id, "message": "Account imported"}
