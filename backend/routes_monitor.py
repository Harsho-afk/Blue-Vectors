"""
ARIA — Watchlist Monitoring API

Endpoints for enrolling targets, managing monitoring state, and reading alerts.
"""

import json
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import Optional, List

from auth import get_current_user, get_db_conn

router = APIRouter(prefix="/api", tags=["monitoring"])
log = logging.getLogger("aria.monitor")


# ── Request/Response Models ──────────────────────────────────────────────────

class MonitorTargetCreate(BaseModel):
    account_id: Optional[int] = None
    identifier_id: Optional[int] = None
    reason: str = Field(..., min_length=5, max_length=500)
    permitted_sources: List[str] = ["platform_recollect", "maigret", "dorking", "breach"]
    interval_minutes: int = Field(default=60, ge=5, le=1440)
    expires_in_days: int = Field(default=30, ge=1, le=90)


class MonitorTargetUpdate(BaseModel):
    permitted_sources: Optional[List[str]] = None
    interval_minutes: Optional[int] = Field(default=None, ge=5, le=1440)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=90)


class AlertUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(read|acknowledged|dismissed)$")
    dismiss_reason: Optional[str] = None


# ── Monitor Target Endpoints ─────────────────────────────────────────────────

@router.post("/cases/{case_id}/monitor-targets", status_code=status.HTTP_201_CREATED)
async def create_monitor_target(
    case_id: int,
    body: MonitorTargetCreate,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    if not body.account_id and not body.identifier_id:
        raise HTTPException(400, "Either account_id or identifier_id is required")
    if body.account_id and body.identifier_id:
        raise HTTPException(400, "Provide only one of account_id or identifier_id")

    conn = get_db_conn()
    try:
        cur = conn.cursor()

        # Verify case ownership
        cur.execute("SELECT id FROM cases WHERE id = %s AND investigator_id = %s", (case_id, current_user["id"]))
        if not cur.fetchone():
            raise HTTPException(404, "Case not found")

        # Verify target exists and belongs to case
        if body.account_id:
            cur.execute("SELECT id FROM accounts WHERE id = %s AND case_id = %s", (body.account_id, case_id))
            if not cur.fetchone():
                raise HTTPException(404, "Account not found in this case")
            # Check not already monitored
            cur.execute(
                "SELECT id FROM monitor_targets WHERE account_id = %s AND status NOT IN ('expired', 'revoked')",
                (body.account_id,),
            )
            if cur.fetchone():
                raise HTTPException(409, "Account is already under active monitoring")
        else:
            cur.execute("SELECT id FROM case_identifiers WHERE id = %s AND case_id = %s", (body.identifier_id, case_id))
            if not cur.fetchone():
                raise HTTPException(404, "Identifier not found in this case")
            cur.execute(
                "SELECT id FROM monitor_targets WHERE identifier_id = %s AND status NOT IN ('expired', 'revoked')",
                (body.identifier_id,),
            )
            if cur.fetchone():
                raise HTTPException(409, "Identifier is already under active monitoring")

        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

        cur.execute(
            """
            INSERT INTO monitor_targets
                (case_id, created_by, account_id, identifier_id, reason,
                 permitted_sources, interval_seconds, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, status, created_at
            """,
            (
                case_id,
                current_user["id"],
                body.account_id,
                body.identifier_id,
                body.reason,
                json.dumps(body.permitted_sources),
                body.interval_minutes * 60,
                expires_at,
            ),
        )
        row = cur.fetchone()
        conn.commit()

        log.info("Monitor target %d created for case %d by user %d", row["id"], case_id, current_user["id"])

        # Capture baseline immediately (don't wait for scheduler tick)
        target_id = row["id"]
        background_tasks.add_task(_run_baseline_now, target_id)

        return {
            "id": target_id,
            "case_id": case_id,
            "account_id": body.account_id,
            "identifier_id": body.identifier_id,
            "status": row["status"],
            "reason": body.reason,
            "permitted_sources": body.permitted_sources,
            "interval_minutes": body.interval_minutes,
            "expires_at": expires_at.isoformat(),
            "created_at": row["created_at"].isoformat(),
        }
    finally:
        conn.close()


async def _run_baseline_now(target_id: int):
    """Fire baseline capture immediately after target creation."""
    from monitor_engine import _check_target
    try:
        await _check_target(target_id)
        log.info("Immediate baseline captured for target %d", target_id)
    except Exception:
        log.exception("Immediate baseline capture failed for target %d", target_id)


@router.get("/cases/{case_id}/monitor-targets")
def list_monitor_targets(
    case_id: int,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM cases WHERE id = %s AND investigator_id = %s", (case_id, current_user["id"]))
        if not cur.fetchone():
            raise HTTPException(404, "Case not found")

        cur.execute(
            """
            SELECT mt.*,
                   a.platform AS account_platform,
                   a.username AS account_username,
                   a.display_name AS account_display_name,
                   a.profile_image_url AS account_image,
                   ci.identifier_type,
                   ci.value AS identifier_value,
                   (SELECT count(*) FROM monitor_events me WHERE me.target_id = mt.id) AS event_count,
                   (SELECT count(*) FROM alerts al
                    WHERE al.case_id = mt.case_id
                      AND al.monitor_event_id IN (SELECT id FROM monitor_events WHERE target_id = mt.id)
                      AND al.status = 'unread') AS unread_alerts
            FROM monitor_targets mt
            LEFT JOIN accounts a ON a.id = mt.account_id
            LEFT JOIN case_identifiers ci ON ci.id = mt.identifier_id
            WHERE mt.case_id = %s
            ORDER BY mt.created_at DESC
            """,
            (case_id,),
        )
        targets = cur.fetchall()

        return [_format_target(dict(t)) for t in targets]
    finally:
        conn.close()


@router.get("/monitor-targets/{target_id}")
def get_monitor_target(
    target_id: int,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.*, c.investigator_id
            FROM monitor_targets mt
            JOIN cases c ON c.id = mt.case_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if not row or row["investigator_id"] != current_user["id"]:
            raise HTTPException(404, "Monitor target not found")
        return dict(row)
    finally:
        conn.close()


@router.patch("/monitor-targets/{target_id}")
def update_monitor_target(
    target_id: int,
    body: MonitorTargetUpdate,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.id, mt.status, c.investigator_id
            FROM monitor_targets mt
            JOIN cases c ON c.id = mt.case_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if not row or row["investigator_id"] != current_user["id"]:
            raise HTTPException(404, "Monitor target not found")
        if row["status"] in ("expired", "revoked"):
            raise HTTPException(400, "Cannot update a terminated monitor target")

        updates = []
        params = []
        if body.permitted_sources is not None:
            updates.append("permitted_sources = %s")
            params.append(json.dumps(body.permitted_sources))
        if body.interval_minutes is not None:
            updates.append("interval_seconds = %s")
            params.append(body.interval_minutes * 60)
        if body.expires_in_days is not None:
            updates.append("expires_at = %s")
            params.append(datetime.now(timezone.utc) + timedelta(days=body.expires_in_days))

        if not updates:
            raise HTTPException(400, "No fields to update")

        updates.append("updated_at = now()")
        params.append(target_id)

        cur.execute(
            f"UPDATE monitor_targets SET {', '.join(updates)} WHERE id = %s RETURNING *",
            params,
        )
        updated = cur.fetchone()
        conn.commit()
        return dict(updated)
    finally:
        conn.close()


@router.post("/monitor-targets/{target_id}/pause")
def pause_monitor_target(
    target_id: int,
    current_user: dict = Depends(get_current_user),
):
    return _set_target_status(target_id, "paused", current_user)


@router.post("/monitor-targets/{target_id}/resume")
def resume_monitor_target(
    target_id: int,
    current_user: dict = Depends(get_current_user),
):
    return _set_target_status(target_id, "active", current_user)


@router.delete("/monitor-targets/{target_id}")
def revoke_monitor_target(
    target_id: int,
    current_user: dict = Depends(get_current_user),
):
    return _set_target_status(target_id, "revoked", current_user)


@router.post("/monitor-targets/{target_id}/check")
def manual_check(
    target_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Trigger an immediate check cycle for this target."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.id, mt.status, c.investigator_id
            FROM monitor_targets mt
            JOIN cases c ON c.id = mt.case_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if not row or row["investigator_id"] != current_user["id"]:
            raise HTTPException(404, "Monitor target not found")
        if row["status"] not in ("active", "pending_baseline"):
            raise HTTPException(400, f"Cannot check target in '{row['status']}' state")

        # Set next_check_at to now so the scheduler picks it up immediately
        cur.execute(
            "UPDATE monitor_targets SET next_check_at = now() WHERE id = %s",
            (target_id,),
        )
        conn.commit()
        return {"message": "Check scheduled", "target_id": target_id}
    finally:
        conn.close()


@router.post("/monitor-targets/{target_id}/reset-baseline")
async def reset_baseline(
    target_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Delete all snapshots and events, reset to pending_baseline so the next
    check captures a fresh baseline from the current profile state."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.id, mt.status, c.investigator_id
            FROM monitor_targets mt
            JOIN cases c ON c.id = mt.case_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if not row or row["investigator_id"] != current_user["id"]:
            raise HTTPException(404, "Monitor target not found")
        if row["status"] in ("expired", "revoked"):
            raise HTTPException(400, "Cannot reset a terminated monitor target")

        cur.execute("DELETE FROM monitor_snapshots WHERE target_id = %s", (target_id,))
        snaps_deleted = cur.rowcount
        cur.execute("DELETE FROM monitor_events WHERE target_id = %s", (target_id,))
        events_deleted = cur.rowcount
        cur.execute(
            """
            UPDATE monitor_targets
            SET status = 'pending_baseline', next_check_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (target_id,),
        )
        conn.commit()
        log.info(
            "Baseline reset for target %d: %d snapshots, %d events deleted",
            target_id, snaps_deleted, events_deleted,
        )

        # Immediately re-capture baseline
        background_tasks.add_task(_run_baseline_now, target_id)

        return {
            "message": "Baseline reset — capturing fresh baseline now",
            "snapshots_deleted": snaps_deleted,
            "events_deleted": events_deleted,
        }
    finally:
        conn.close()


# ── Monitor Events ───────────────────────────────────────────────────────────

@router.get("/monitor-targets/{target_id}/events")
def list_monitor_events(
    target_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.id, c.investigator_id
            FROM monitor_targets mt
            JOIN cases c ON c.id = mt.case_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if not row or row["investigator_id"] != current_user["id"]:
            raise HTTPException(404, "Monitor target not found")

        cur.execute(
            """
            SELECT * FROM monitor_events
            WHERE target_id = %s
            ORDER BY observed_at DESC
            LIMIT %s OFFSET %s
            """,
            (target_id, limit, offset),
        )
        events = cur.fetchall()

        cur.execute("SELECT count(*) AS total FROM monitor_events WHERE target_id = %s", (target_id,))
        total = cur.fetchone()["total"]

        return {"events": [dict(e) for e in events], "total": total}
    finally:
        conn.close()


# ── Alerts ───────────────────────────────────────────────────────────────────

@router.get("/alerts")
def list_alerts(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    case_id: Optional[int] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        conditions = ["investigator_id = %s"]
        params = [current_user["id"]]

        if status_filter:
            conditions.append("status = %s")
            params.append(status_filter)
        if case_id:
            conditions.append("case_id = %s")
            params.append(case_id)
        if priority:
            conditions.append("priority = %s")
            params.append(priority)

        where = " AND ".join(conditions)
        cur.execute(
            f"""
            SELECT * FROM alerts
            WHERE {where}
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3
                END,
                created_at DESC
            LIMIT %s OFFSET %s
            """,
            params + [limit, offset],
        )
        alerts = cur.fetchall()

        cur.execute(f"SELECT count(*) AS total FROM alerts WHERE {where}", params)
        total = cur.fetchone()["total"]

        # Unread count (always unfiltered by status)
        cur.execute(
            "SELECT count(*) AS unread FROM alerts WHERE investigator_id = %s AND status = 'unread'",
            (current_user["id"],),
        )
        unread = cur.fetchone()["unread"]

        return {"alerts": [dict(a) for a in alerts], "total": total, "unread": unread}
    finally:
        conn.close()


@router.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    body: AlertUpdate,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM alerts WHERE id = %s AND investigator_id = %s",
            (alert_id, current_user["id"]),
        )
        alert = cur.fetchone()
        if not alert:
            raise HTTPException(404, "Alert not found")

        now = datetime.now(timezone.utc)
        timestamp_field = {
            "read": "read_at",
            "acknowledged": "acknowledged_at",
            "dismissed": "dismissed_at",
        }.get(body.status)

        updates = [f"status = %s", f"{timestamp_field} = %s"]
        params = [body.status, now]

        if body.status == "dismissed" and body.dismiss_reason:
            updates.append("dismiss_reason = %s")
            params.append(body.dismiss_reason)

        params.append(alert_id)
        cur.execute(
            f"UPDATE alerts SET {', '.join(updates)} WHERE id = %s RETURNING *",
            params,
        )
        updated = cur.fetchone()
        conn.commit()
        return dict(updated)
    finally:
        conn.close()


@router.get("/alerts/dashboard")
def dashboard_alerts(
    limit: int = Query(default=15, ge=1, le=50),
    current_user: dict = Depends(get_current_user),
):
    """Recent alerts across all cases with case titles and event diff data."""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT a.*,
                   c.title AS case_title,
                   me.previous_json,
                   me.current_json,
                   me.event_type,
                   me.source AS event_source
            FROM alerts a
            JOIN cases c ON c.id = a.case_id
            LEFT JOIN monitor_events me ON me.id = a.monitor_event_id
            WHERE a.investigator_id = %s
            ORDER BY
                CASE a.priority
                    WHEN 'critical' THEN 0
                    WHEN 'high' THEN 1
                    WHEN 'normal' THEN 2
                    WHEN 'low' THEN 3
                END,
                a.created_at DESC
            LIMIT %s
            """,
            (current_user["id"], limit),
        )
        alerts = [dict(r) for r in cur.fetchall()]

        cur.execute(
            "SELECT count(*) AS unread FROM alerts WHERE investigator_id = %s AND status = 'unread'",
            (current_user["id"],),
        )
        unread = cur.fetchone()["unread"]

        return {"alerts": alerts, "unread": unread}
    finally:
        conn.close()


@router.post("/alerts/mark-all-read")
def mark_all_read(
    case_id: Optional[int] = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        now = datetime.now(timezone.utc)
        if case_id:
            cur.execute(
                """
                UPDATE alerts SET status = 'read', read_at = %s
                WHERE investigator_id = %s AND case_id = %s AND status = 'unread'
                """,
                (now, current_user["id"], case_id),
            )
        else:
            cur.execute(
                """
                UPDATE alerts SET status = 'read', read_at = %s
                WHERE investigator_id = %s AND status = 'unread'
                """,
                (now, current_user["id"]),
            )
        count = cur.rowcount
        conn.commit()
        return {"marked_read": count}
    finally:
        conn.close()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _set_target_status(target_id: int, new_status: str, current_user: dict):
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT mt.id, mt.status, c.investigator_id
            FROM monitor_targets mt
            JOIN cases c ON c.id = mt.case_id
            WHERE mt.id = %s
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if not row or row["investigator_id"] != current_user["id"]:
            raise HTTPException(404, "Monitor target not found")

        valid_transitions = {
            "paused": ("active", "pending_baseline", "degraded"),
            "active": ("paused",),
            "revoked": ("active", "paused", "pending_baseline", "degraded"),
        }
        allowed_from = valid_transitions.get(new_status, ())
        if row["status"] not in allowed_from:
            raise HTTPException(400, f"Cannot transition from '{row['status']}' to '{new_status}'")

        cur.execute(
            "UPDATE monitor_targets SET status = %s, updated_at = now() WHERE id = %s RETURNING *",
            (new_status, target_id),
        )
        updated = cur.fetchone()
        conn.commit()
        log.info("Monitor target %d -> %s by user %d", target_id, new_status, current_user["id"])
        return dict(updated)
    finally:
        conn.close()


def _format_target(t: dict) -> dict:
    """Clean up joined target row for API response."""
    return {
        "id": t["id"],
        "case_id": t["case_id"],
        "account_id": t["account_id"],
        "identifier_id": t["identifier_id"],
        "status": t["status"],
        "reason": t["reason"],
        "permitted_sources": t.get("permitted_sources"),
        "interval_seconds": t["interval_seconds"],
        "next_check_at": t["next_check_at"].isoformat() if t.get("next_check_at") else None,
        "last_checked_at": t["last_checked_at"].isoformat() if t.get("last_checked_at") else None,
        "expires_at": t["expires_at"].isoformat() if t.get("expires_at") else None,
        "created_at": t["created_at"].isoformat() if t.get("created_at") else None,
        "event_count": t.get("event_count", 0),
        "unread_alerts": t.get("unread_alerts", 0),
        "account": {
            "platform": t.get("account_platform"),
            "username": t.get("account_username"),
            "display_name": t.get("account_display_name"),
            "image": t.get("account_image"),
        } if t.get("account_platform") else None,
        "identifier": {
            "type": t.get("identifier_type"),
            "value": t.get("identifier_value"),
        } if t.get("identifier_type") else None,
    }
