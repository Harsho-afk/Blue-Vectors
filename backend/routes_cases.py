"""
ARIA — Case Management routes (Layer 0)
POST   /api/cases                        { title, identifiers[] } → case_id
GET    /api/cases                         list cases for logged-in investigator
GET    /api/cases/{case_id}               case details + identifiers + accounts (with posts) + results
DELETE /api/cases/{case_id}               delete case + cascade
POST   /api/cases/{case_id}/identifiers   add identifier(s) to existing case
POST   /api/cases/{case_id}/collect       collect data for a case identifier
"""

import json
from typing import Optional, Literal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from auth import get_current_user, get_db_conn, DB_TYPE
from collector import collect_async

router = APIRouter(prefix="/api/cases", tags=["cases"])


# ── Pydantic Models ───────────────────────────────────────────────────────────

class IdentifierIn(BaseModel):
    identifier_type: Literal["username", "email", "phone", "profile_url"]
    value: str
    platform_hint: Optional[str] = None


class CaseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    identifiers: list[IdentifierIn] = Field(..., min_items=1)


class CollectRequest(BaseModel):
    platform: Literal["reddit", "twitter"]
    username: str
    limit: int = Field(default=50, ge=1, le=500)


class CaseResponse(BaseModel):
    id: int
    investigator_id: int
    title: str
    status: str
    created_at: str
    closed_at: Optional[str] = None


class IdentifierResponse(BaseModel):
    id: int
    case_id: int
    identifier_type: str
    value: str
    platform_hint: Optional[str]
    created_at: str


class AccountResponse(BaseModel):
    id: int
    case_id: Optional[int]
    platform: str
    username: str
    display_name: Optional[str]
    bio: Optional[str]
    location: Optional[str]
    created_at: Optional[str]
    profile_image_url: Optional[str]


class LinkageResultResponse(BaseModel):
    id: int
    case_id: int
    account_a_id: int
    account_b_id: int
    confidence: float
    shap_json: Optional[str]
    created_at: str


class CaseDetailResponse(BaseModel):
    case: CaseResponse
    identifiers: list[IdentifierResponse]
    accounts: list[AccountResponse]
    results: list[LinkageResultResponse]


# ── Helper: Ownership check ───────────────────────────────────────────────────

def _get_case_owner(conn, case_id: int) -> Optional[int]:
    """Return investigator_id if case exists, else None."""
    cur = conn.cursor()
    if DB_TYPE == "sqlite":
        cur.execute("SELECT investigator_id FROM cases WHERE id = ?", (case_id,))
    else:
        cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _check_case_ownership(conn, case_id: int, user_id: int):
    """Raise 404 if case doesn't exist or 403 if user doesn't own it."""
    owner_id = _get_case_owner(conn, case_id)
    if owner_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if owner_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED)
def create_case(body: CaseCreate, current_user: dict = Depends(get_current_user)):
    """
    Create a new case with one or more seed identifiers.
    
    Body: { title, identifiers: [{ identifier_type, value, platform_hint? }] }
    Returns: { case_id }
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        
        # Insert case
        if DB_TYPE == "sqlite":
            cur.execute(
                "INSERT INTO cases (investigator_id, title, status) VALUES (?, ?, 'open')",
                (current_user["id"], body.title),
            )
            conn.commit()
            # Get last inserted id
            cur.execute("SELECT last_insert_rowid() as id")
            case_id = cur.fetchone()[0]
        else:
            cur.execute(
                """
                INSERT INTO cases (investigator_id, title, status)
                VALUES (%s, %s, 'open')
                RETURNING id
                """,
                (current_user["id"], body.title),
            )
            case_id = cur.fetchone()[0]
        
        # Insert identifiers
        for identifier in body.identifiers:
            if DB_TYPE == "sqlite":
                cur.execute(
                    """
                    INSERT INTO case_identifiers (case_id, identifier_type, value, platform_hint)
                    VALUES (?, ?, ?, ?)
                    """,
                    (case_id, identifier.identifier_type, identifier.value, identifier.platform_hint),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO case_identifiers (case_id, identifier_type, value, platform_hint)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (case_id, identifier.identifier_type, identifier.value, identifier.platform_hint),
                )
        
        conn.commit()
    finally:
        conn.close()
    
    return {"case_id": case_id}


@router.get("")
def list_cases(current_user: dict = Depends(get_current_user)):
    """
    List all cases belonging to the current investigator.
    Sorted by created_at DESC (newest first).
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        if DB_TYPE == "sqlite":
            cur.execute(
                """
                SELECT id, investigator_id, title, status, created_at, closed_at
                FROM cases
                WHERE investigator_id = ?
                ORDER BY created_at DESC
                """,
                (current_user["id"],),
            )
        else:
            cur.execute(
                """
                SELECT id, investigator_id, title, status, created_at, closed_at
                FROM cases
                WHERE investigator_id = %s
                ORDER BY created_at DESC
                """,
                (current_user["id"],),
            )
        
        cases = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    
    return {
        "cases": [
            {
                "id": c["id"],
                "investigator_id": c["investigator_id"],
                "title": c["title"],
                "status": c["status"],
                "created_at": str(c["created_at"]),
                "closed_at": str(c["closed_at"]) if c["closed_at"] else None,
            }
            for c in cases
        ]
    }


@router.get("/{case_id}")
def get_case(case_id: int, current_user: dict = Depends(get_current_user)):
    """
    Get detailed case information: case metadata + identifiers + linked accounts + results.
    Ownership check: 404 if not found or not owned.
    """
    conn = get_db_conn()
    try:
        # Check ownership
        _check_case_ownership(conn, case_id, current_user["id"])
        
        cur = conn.cursor()
        
        # Case
        if DB_TYPE == "sqlite":
            cur.execute(
                "SELECT id, investigator_id, title, status, created_at, closed_at FROM cases WHERE id = ?",
                (case_id,),
            )
        else:
            cur.execute(
                "SELECT id, investigator_id, title, status, created_at, closed_at FROM cases WHERE id = %s",
                (case_id,),
            )
        case_row = dict(cur.fetchone())
        
        # Identifiers
        if DB_TYPE == "sqlite":
            cur.execute(
                "SELECT id, case_id, identifier_type, value, platform_hint, created_at FROM case_identifiers WHERE case_id = ?",
                (case_id,),
            )
        else:
            cur.execute(
                "SELECT id, case_id, identifier_type, value, platform_hint, created_at FROM case_identifiers WHERE case_id = %s",
                (case_id,),
            )
        identifiers = [dict(row) for row in cur.fetchall()]
        
        # Accounts + their posts
        if DB_TYPE == "sqlite":
            cur.execute(
                "SELECT id, case_id, platform, username, display_name, bio, location, created_at, profile_image_url, karma, follower_count, following_count FROM accounts WHERE case_id = ?",
                (case_id,),
            )
        else:
            cur.execute(
                "SELECT id, case_id, platform, username, display_name, bio, location, created_at, profile_image_url, karma, follower_count, following_count FROM accounts WHERE case_id = %s",
                (case_id,),
            )
        accounts = [dict(row) for row in cur.fetchall()]

        # Fetch posts for each account
        for acc in accounts:
            if DB_TYPE == "sqlite":
                cur.execute(
                    "SELECT id, account_id, text, timestamp, metadata FROM posts WHERE account_id = ? ORDER BY timestamp DESC",
                    (acc["id"],),
                )
            else:
                cur.execute(
                    "SELECT id, account_id, text, timestamp, metadata FROM posts WHERE account_id = %s ORDER BY timestamp DESC",
                    (acc["id"],),
                )
            acc["posts"] = [dict(row) for row in cur.fetchall()]

        # Linkage results
        if DB_TYPE == "sqlite":
            cur.execute(
                "SELECT id, case_id, account_a_id, account_b_id, confidence, shap_json, created_at FROM linkage_results WHERE case_id = ?",
                (case_id,),
            )
        else:
            cur.execute(
                "SELECT id, case_id, account_a_id, account_b_id, confidence, shap_json, created_at FROM linkage_results WHERE case_id = %s",
                (case_id,),
            )
        results = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    
    return {
        "case": {
            "id": case_row["id"],
            "investigator_id": case_row["investigator_id"],
            "title": case_row["title"],
            "status": case_row["status"],
            "created_at": str(case_row["created_at"]),
            "closed_at": str(case_row["closed_at"]) if case_row["closed_at"] else None,
        },
        "identifiers": [
            {
                "id": i["id"],
                "case_id": i["case_id"],
                "identifier_type": i["identifier_type"],
                "value": i["value"],
                "platform_hint": i["platform_hint"],
                "created_at": str(i["created_at"]),
            }
            for i in identifiers
        ],
        "accounts": [
            {
                "id": a["id"],
                "case_id": a["case_id"],
                "platform": a["platform"],
                "username": a["username"],
                "display_name": a["display_name"],
                "bio": a["bio"],
                "location": a["location"],
                "created_at": str(a["created_at"]) if a["created_at"] else None,
                "profile_image_url": a["profile_image_url"],
                "karma": a["karma"],
                "follower_count": a["follower_count"],
                "following_count": a["following_count"],
                "posts": [
                    {
                        "id": p["id"],
                        "text": p["text"],
                        "timestamp": str(p["timestamp"]),
                        "metadata": json.loads(p["metadata"]) if isinstance(p["metadata"], str) else p["metadata"],
                    }
                    for p in a.get("posts", [])
                ],
            }
            for a in accounts
        ],
        "results": [
            {
                "id": r["id"],
                "case_id": r["case_id"],
                "account_a_id": r["account_a_id"],
                "account_b_id": r["account_b_id"],
                "confidence": r["confidence"],
                "shap_json": r["shap_json"],
                "created_at": str(r["created_at"]),
            }
            for r in results
        ],
    }


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case(case_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete a case and all related data (identifiers, accounts, posts, results).
    Ownership check: 404 if not found or not owned.
    """
    conn = get_db_conn()
    try:
        # Check ownership
        _check_case_ownership(conn, case_id, current_user["id"])
        
        cur = conn.cursor()
        if DB_TYPE == "sqlite":
            cur.execute("DELETE FROM cases WHERE id = ?", (case_id,))
        else:
            cur.execute("DELETE FROM cases WHERE id = %s", (case_id,))

        conn.commit()
    finally:
        conn.close()


@router.post("/{case_id}/identifiers", status_code=status.HTTP_201_CREATED)
def add_identifiers(
    case_id: int,
    body: list[IdentifierIn],
    current_user: dict = Depends(get_current_user),
):
    """Add one or more identifiers to an existing case."""
    if not body:
        raise HTTPException(status_code=400, detail="At least one identifier required")

    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        for ident in body:
            if DB_TYPE == "sqlite":
                cur.execute(
                    "INSERT INTO case_identifiers (case_id, identifier_type, value, platform_hint) VALUES (?, ?, ?, ?)",
                    (case_id, ident.identifier_type, ident.value, ident.platform_hint),
                )
            else:
                cur.execute(
                    "INSERT INTO case_identifiers (case_id, identifier_type, value, platform_hint) VALUES (%s, %s, %s, %s)",
                    (case_id, ident.identifier_type, ident.value, ident.platform_hint),
                )
        conn.commit()
    finally:
        conn.close()

    return {"added": len(body)}


@router.post("/{case_id}/collect")
async def collect_for_case(
    case_id: int,
    body: CollectRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Collect data for an identifier and save it to the case.
    Calls the Layer 1 collector and persists the account + posts to the DB.
    """
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    try:
        profile = await collect_async(body.platform, body.username, limit=body.limit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    conn = get_db_conn()
    try:
        cur = conn.cursor()

        created_at_dt = None
        if profile.created_utc is not None:
            created_at_dt = datetime.fromtimestamp(profile.created_utc, tz=timezone.utc).isoformat()

        if DB_TYPE == "sqlite":
            cur.execute(
                """
                INSERT INTO accounts (case_id, platform, username, display_name, bio, location, created_at, profile_image_url, karma, follower_count, following_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (case_id, platform, username) DO UPDATE SET
                    display_name      = excluded.display_name,
                    bio               = excluded.bio,
                    location          = excluded.location,
                    created_at        = excluded.created_at,
                    profile_image_url = excluded.profile_image_url,
                    karma             = excluded.karma,
                    follower_count    = excluded.follower_count,
                    following_count   = excluded.following_count
                """,
                (case_id, profile.platform, profile.username, profile.display_name,
                 profile.bio, profile.location, created_at_dt, profile.profile_image_url,
                 profile.karma, profile.follower_count, profile.following_count),
            )
            conn.commit()
            cur.execute(
                "SELECT id FROM accounts WHERE case_id = ? AND platform = ? AND username = ?",
                (case_id, profile.platform, profile.username),
            )
            account_id = cur.fetchone()[0]
        else:
            cur.execute(
                """
                INSERT INTO accounts (case_id, platform, username, display_name, bio, location, created_at, profile_image_url, karma, follower_count, following_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (case_id, platform, username) DO UPDATE SET
                    display_name      = EXCLUDED.display_name,
                    bio               = EXCLUDED.bio,
                    location          = EXCLUDED.location,
                    created_at        = EXCLUDED.created_at,
                    profile_image_url = EXCLUDED.profile_image_url,
                    karma             = EXCLUDED.karma,
                    follower_count    = EXCLUDED.follower_count,
                    following_count   = EXCLUDED.following_count
                RETURNING id
                """,
                (case_id, profile.platform, profile.username, profile.display_name,
                 profile.bio, profile.location, created_at_dt, profile.profile_image_url,
                 profile.karma, profile.follower_count, profile.following_count),
            )
            account_id = cur.fetchone()[0]

        for post in profile.posts:
            post_dt = datetime.fromtimestamp(post.timestamp, tz=timezone.utc).isoformat()
            if DB_TYPE == "sqlite":
                cur.execute(
                    """
                    INSERT INTO posts (account_id, text, timestamp, metadata)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    (account_id, post.text, post_dt, json.dumps(post.metadata)),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO posts (account_id, text, timestamp, metadata)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (account_id, post.text, post_dt, json.dumps(post.metadata)),
                )

        conn.commit()
    finally:
        conn.close()

    return {
        "account_id": account_id,
        "platform": profile.platform,
        "username": profile.username,
        "display_name": profile.display_name,
        "posts_collected": len(profile.posts),
    }
