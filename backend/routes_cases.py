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
import asyncio
from typing import Optional, Literal, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from auth import get_current_user, get_db_conn
from collect_stream import collect_one_platform

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
    platform: Literal["reddit", "twitter", "github", "instagram"]
    username: str
    limit: int = Field(default=50, ge=1, le=500)
    include_social_graph: bool = True
    # 0 = unlimited (paginate everything). Currently only honored by the
    # Instagram collector; other platforms accept but ignore these.
    follower_limit: int = Field(default=0, ge=0)
    following_limit: int = Field(default=0, ge=0)
    fetch_comments: bool = False
    comment_limit: int = Field(default=0, ge=0)


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
def get_case_owner(conn, case_id: int) -> Optional[int]:
    """Return investigator_id if case exists, else None."""
    cur = conn.cursor()
    cur.execute(
        "SELECT investigator_id FROM cases WHERE id = %s",
        (case_id,),
    )
    row = cur.fetchone()
    return row["investigator_id"] if row else None


def check_case_ownership(conn, case_id: int, user_id: int):
    """Raise 404 if case doesn't exist or 403 if user doesn't own it."""
    owner_id = get_case_owner(conn, case_id)
    if owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )
    if owner_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )


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
        cur.execute(
            """
            INSERT INTO cases (investigator_id, title, status)
            VALUES (%s, %s, 'open')
            RETURNING id
            """,
            (current_user["id"], body.title),
        )

        case_id = cur.fetchone()["id"]

        # Insert identifiers
        for identifier in body.identifiers:
            cur.execute(
                """
                INSERT INTO case_identifiers
                (case_id, identifier_type, value, platform_hint)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    case_id,
                    identifier.identifier_type,
                    identifier.value,
                    identifier.platform_hint,
                ),
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
        check_case_ownership(conn, case_id, current_user["id"])

        cur = conn.cursor()

        # Case
        cur.execute(
            "SELECT id, investigator_id, title, status, created_at, closed_at FROM cases WHERE id = %s",
            (case_id,),
        )
        case_row = dict(cur.fetchone())

        # Identifiers
        cur.execute(
            "SELECT id, case_id, identifier_type, value, platform_hint, created_at FROM case_identifiers WHERE case_id = %s",
            (case_id,),
        )
        identifiers = [dict(row) for row in cur.fetchall()]

        # Accounts + their posts
        cur.execute(
            "SELECT id, case_id, platform, username, display_name, bio, location, created_at, profile_image_url, karma, follower_count, following_count FROM accounts WHERE case_id = %s",
            (case_id,),
        )
        accounts = [dict(row) for row in cur.fetchall()]

        # Fetch posts for each account
        for acc in accounts:
            cur.execute(
                "SELECT id, account_id, text, timestamp, metadata FROM posts WHERE account_id = %s ORDER BY timestamp DESC",
                (acc["id"],),
            )
            acc["posts"] = [dict(row) for row in cur.fetchall()]

        # Linkage results
        cur.execute(
            "SELECT id, case_id, account_a_id, account_b_id, confidence, shap_json, created_at FROM linkage_results WHERE case_id = %s",
            (case_id,),
        )
        results = [dict(row) for row in cur.fetchall()]

        # OSINT lookups
        cur.execute(
            "SELECT id, lookup_type, input_value, result_json, created_at FROM osint_lookups WHERE case_id = %s ORDER BY created_at DESC",
            (case_id,),
        )
        osint_rows = [dict(row) for row in cur.fetchall()]

        # Insights
        cur.execute(
            "SELECT id, account_id, category, claim, confidence, evidence, created_at FROM insights WHERE case_id = %s ORDER BY id",
            (case_id,),
        )
        insight_rows = [dict(row) for row in cur.fetchall()]

        # Intelligence report (latest)
        cur.execute(
            "SELECT id, narrative, claims, label, created_at FROM intelligence_reports WHERE case_id = %s ORDER BY created_at DESC LIMIT 1",
            (case_id,),
        )
        intel_row = cur.fetchone()
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
                        "metadata": (
                            json.loads(p["metadata"])
                            if isinstance(p["metadata"], str)
                            else p["metadata"]
                        ),
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
        "osint_lookups": [
            {
                "id": o["id"],
                "lookup_type": o["lookup_type"],
                "input_value": o["input_value"],
                "result": (
                    json.loads(o["result_json"])
                    if isinstance(o["result_json"], str)
                    else o["result_json"]
                ),
                "created_at": str(o["created_at"]),
            }
            for o in osint_rows
        ],
        "insights": [
            {
                "id": ins["id"],
                "account_id": ins["account_id"],
                "category": ins["category"],
                "claim": ins["claim"],
                "confidence": ins["confidence"],
                "evidence": (
                    json.loads(ins["evidence"])
                    if isinstance(ins["evidence"], str)
                    else ins["evidence"]
                ),
                "created_at": str(ins["created_at"]),
            }
            for ins in insight_rows
        ],
        "intelligence": (
            {
                "id": intel_row["id"],
                "narrative": intel_row["narrative"],
                "claims": (
                    json.loads(intel_row["claims"])
                    if isinstance(intel_row["claims"], str)
                    else intel_row["claims"]
                ),
                "label": intel_row["label"],
                "created_at": str(intel_row["created_at"]),
            }
            if intel_row
            else None
        ),
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
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        cur.execute("DELETE FROM cases WHERE id = %s", (case_id,))
        conn.commit()
    finally:
        conn.close()


class CaseStatusUpdate(BaseModel):
    status: Literal["open", "closed"]


@router.patch("/{case_id}/status")
def update_case_status(
    case_id: int,
    body: CaseStatusUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Close or reopen a case."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        if body.status == "closed":
            cur.execute(
                "UPDATE cases SET status = 'closed', closed_at = NOW() WHERE id = %s",
                (case_id,),
            )
        else:
            cur.execute(
                "UPDATE cases SET status = 'open', closed_at = NULL WHERE id = %s",
                (case_id,),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": body.status}


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
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        for ident in body:
            cur.execute(
                "INSERT INTO case_identifiers (case_id, identifier_type, value, platform_hint) VALUES (%s, %s, %s, %s)",
                (case_id, ident.identifier_type, ident.value, ident.platform_hint),
            )
        conn.commit()
    finally:
        conn.close()

    return {"added": len(body)}


@router.put("/{case_id}/identifiers/{identifier_id}")
def update_identifier(
    case_id: int,
    identifier_id: int,
    body: IdentifierIn,
    current_user: dict = Depends(get_current_user),
):
    """Update an existing identifier's type, value, or platform_hint."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM case_identifiers WHERE id = %s AND case_id = %s",
            (identifier_id, case_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Identifier not found")
        cur.execute(
            """
            UPDATE case_identifiers
            SET identifier_type = %s, value = %s, platform_hint = %s
            WHERE id = %s AND case_id = %s
            """,
            (
                body.identifier_type,
                body.value,
                body.platform_hint,
                identifier_id,
                case_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return {"updated": identifier_id}


@router.delete(
    "/{case_id}/identifiers/{identifier_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_identifier(
    case_id: int,
    identifier_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a single identifier from a case."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM case_identifiers WHERE id = %s AND case_id = %s",
            (identifier_id, case_id),
        )
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Identifier not found")
        cur.execute(
            "DELETE FROM case_identifiers WHERE id = %s AND case_id = %s",
            (identifier_id, case_id),
        )
        conn.commit()
    finally:
        conn.close()


class CorrelateRequest(BaseModel):
    account_a_id: Optional[int] = None
    account_b_id: Optional[int] = None


@router.post("/{case_id}/correlate")
def run_correlation(
    case_id: int,
    body: Optional[CorrelateRequest] = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Run identity correlation on a case.
    No body or empty body → correlate all pairs.
    Body with account_a_id + account_b_id → correlate that specific pair only.
    """
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    if body and body.account_a_id is not None and body.account_b_id is not None:
        if body.account_a_id == body.account_b_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot correlate an account with itself",
            )
        from correlator import correlate_single_pair

        try:
            result = correlate_single_pair(
                case_id, body.account_a_id, body.account_b_id
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
        return {"results": [result]}
    else:
        from correlator import correlate_case

        results = correlate_case(case_id)
        return {"results": results}


@router.get("/{case_id}/results")
def get_correlation_results(
    case_id: int, current_user: dict = Depends(get_current_user)
):
    """Get stored correlation results for a case with per-signal breakdown."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        cur.execute(
            """
            SELECT lr.id, lr.case_id, lr.account_a_id, lr.account_b_id,
                   lr.confidence, lr.shap_json, lr.created_at,
                   a1.platform as a_platform, a1.username as a_username,
                   a1.display_name as a_display_name, a1.profile_image_url as a_avatar,
                   a2.platform as b_platform, a2.username as b_username,
                   a2.display_name as b_display_name, a2.profile_image_url as b_avatar
            FROM linkage_results lr
            JOIN accounts a1 ON lr.account_a_id = a1.id
            JOIN accounts a2 ON lr.account_b_id = a2.id
            WHERE lr.case_id = %s
            ORDER BY lr.confidence DESC
            """,
            (case_id,),
        )
        rows = cur.fetchall()
        results = []
        for row in rows:
            r = dict(row)
            if isinstance(r.get("shap_json"), str):
                try:
                    r["shap_json"] = json.loads(r["shap_json"])
                except (json.JSONDecodeError, TypeError):
                    r["shap_json"] = {}
            r["created_at"] = str(r["created_at"]) if r["created_at"] else None
            results.append(r)
    finally:
        conn.close()

    return {"results": results}


@router.post("/{case_id}/intelligence")
def run_intelligence(case_id: int, current_user: dict = Depends(get_current_user)):
    """
    Generate an AI intelligence briefing from the case's insights.
    Runs the Analyst LLM + citation check, stores the result.
    """
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    conn = get_db_conn()
    try:
        from llm.analyst import generate_briefing
        from llm.citation_check import validate_citations, save_report

        analyst_output = generate_briefing(conn, case_id)
        checked = validate_citations(conn, case_id, analyst_output)
        report_id = save_report(conn, case_id, checked)

        return {
            "report_id": report_id,
            "narrative": checked["narrative"],
            "claims": checked["claims"],
            "label": checked["label"],
            "citation_stats": checked["citation_stats"],
            "model": analyst_output.get("model"),
        }
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    finally:
        conn.close()


@router.get("/{case_id}/intelligence")
def get_intelligence(case_id: int, current_user: dict = Depends(get_current_user)):
    """Retrieve the stored intelligence report for a case."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
        cur = conn.cursor()
        cur.execute(
            "SELECT id, case_id, narrative, claims, label, created_at "
            "FROM intelligence_reports WHERE case_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (case_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return {"report": None}

    r = dict(row)
    if isinstance(r["claims"], str):
        r["claims"] = json.loads(r["claims"])
    r["created_at"] = str(r["created_at"]) if r["created_at"] else None

    return {"report": r}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


async def _run_single_collect(
    case_id: int,
    platform: str,
    username: str,
    limit: int,
    include_social_graph: bool,
    queue: "asyncio.Queue[Optional[dict]]",
) -> None:
    """Producer: runs one collect_one_platform() call, pushing SSE-ready
    dict events onto the queue as they happen (per-post for Instagram,
    one final event for everything else), then a None sentinel."""
    emit = queue.put
    try:
        await collect_one_platform(
            case_id, platform, username, emit, limit=limit,
            include_social_graph=include_social_graph,
        )
    finally:
        await queue.put(None)


async def _stream_single_collect(
    case_id: int, platform: str, username: str, limit: int, include_social_graph: bool
) -> AsyncGenerator[str, None]:
    queue: "asyncio.Queue[Optional[dict]]" = asyncio.Queue()
    producer_task = asyncio.create_task(
        _run_single_collect(case_id, platform, username, limit, include_social_graph, queue)
    )
    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            yield _sse(item)
    finally:
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except (asyncio.CancelledError, Exception):
                pass


@router.post("/{case_id}/collect")
async def collect_for_case(
    case_id: int,
    body: CollectRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Collect data for an identifier and save it to the case.

    Streams progress as Server-Sent Events (same event shape as
    /api/cases/{id}/run's collect step) instead of blocking until the
    whole account is done. For Instagram this means each post (with up to
    50 comments) is saved and emitted the moment it's ready, rather than
    the frontend waiting minutes for one big response at the end. Other
    platforms still emit a single "done" event once their collection
    finishes, since they don't have a per-post streaming path.

    follower_limit / following_limit / comment_limit are accepted for
    backwards compatibility with existing callers but are currently always
    treated as "unlimited" (0) for Instagram, matching /run's behavior;
    other platforms accept and ignore them.
    """
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    return StreamingResponse(
        _stream_single_collect(
            case_id, body.platform, body.username,
            limit=body.limit, include_social_graph=body.include_social_graph,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
