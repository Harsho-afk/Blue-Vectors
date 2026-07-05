"""
ARIA — SOCMINT Report routes.

POST   /api/cases/{case_id}/reports              Generate new versioned snapshot
GET    /api/cases/{case_id}/reports              List report versions
GET    /api/cases/{case_id}/reports/{report_id}  Retrieve structured report JSON
GET    /api/cases/{case_id}/reports/{report_id}/html  Render preview HTML
GET    /api/cases/{case_id}/reports/readiness    Check generation readiness
"""

import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import HTMLResponse
from auth import get_current_user, get_db_conn
from routes_cases import check_case_ownership
from reporting.builder import generate_report, compute_content_hash, check_readiness
from reporting.collector import load_case_data
from reporting.render_html import render_report_html
from reporting.render_pdf import render_report_pdf

log = logging.getLogger("aria.routes_reports")

router = APIRouter(prefix="/api/cases/{case_id}/reports", tags=["reports"])


@router.get("/readiness")
def get_readiness(case_id: int, current_user: dict = Depends(get_current_user)):
    """Check whether enough data exists to generate a meaningful report."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    case_data = load_case_data(case_id, current_user["id"])
    if case_data is None:
        raise HTTPException(status_code=404, detail="Case not found")

    warnings = check_readiness(case_data)

    return {
        "ready": len(warnings) == 0,
        "warnings": warnings,
        "data_available": {
            "accounts": len(case_data["accounts"]),
            "correlations": len(case_data["correlations"]),
            "insights": len(case_data["insights"]),
            "lookups": len(case_data["lookups"]),
            "intelligence": case_data["intelligence"] is not None,
        },
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_report(case_id: int, current_user: dict = Depends(get_current_user)):
    """Generate a new versioned report snapshot from stored case data."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])

        # Determine next version
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
            "FROM socmint_reports WHERE case_id = %s",
            (case_id,),
        )
        next_version = cur.fetchone()["next_version"]

        # Insert placeholder
        cur.execute(
            """
            INSERT INTO socmint_reports
            (case_id, version, status, generated_by, methodology_version)
            VALUES (%s, %s, 'generating', %s, '1.0')
            RETURNING id
            """,
            (case_id, next_version, current_user["id"]),
        )
        report_id = cur.fetchone()["id"]
        conn.commit()

    finally:
        conn.close()

    # Generate the report (reads stored data only, no external calls)
    try:
        report_json = generate_report(case_id, current_user["id"])
        content_hash = compute_content_hash(report_json)

        conn = get_db_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE socmint_reports
                SET status = 'ready',
                    report_json = %s,
                    content_hash = %s
                WHERE id = %s
                """,
                (json.dumps(report_json, default=str), content_hash, report_id),
            )
            conn.commit()
        finally:
            conn.close()

    except Exception as e:
        log.exception("Report generation failed for case %s", case_id)
        conn = get_db_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE socmint_reports
                SET status = 'failed', error_message = %s
                WHERE id = %s
                """,
                (str(e)[:500], report_id),
            )
            conn.commit()
        finally:
            conn.close()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)[:200]}",
        )

    return {
        "report_id": report_id,
        "version": next_version,
        "status": "ready",
        "content_hash": content_hash,
    }


@router.get("")
def list_reports(case_id: int, current_user: dict = Depends(get_current_user)):
    """List all report versions for a case."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])

        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, version, status, methodology_version,
                   generated_at, content_hash, error_message
            FROM socmint_reports
            WHERE case_id = %s
            ORDER BY version DESC
            """,
            (case_id,),
        )
        reports = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    return {"reports": reports}


@router.get("/{report_id}")
def get_report(
    case_id: int, report_id: int, current_user: dict = Depends(get_current_user)
):
    """Retrieve the full structured report JSON."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])

        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, version, status, report_json, methodology_version,
                   generated_at, content_hash, error_message
            FROM socmint_reports
            WHERE id = %s AND case_id = %s
            """,
            (report_id, case_id),
        )
        report = cur.fetchone()
    finally:
        conn.close()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    report = dict(report)
    if report["status"] == "failed":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Report generation failed: {report.get('error_message', 'Unknown error')}",
        )

    if isinstance(report["report_json"], str):
        report["report_json"] = json.loads(report["report_json"])

    return report


@router.get("/{report_id}/html", response_class=HTMLResponse)
def get_report_html(
    case_id: int, report_id: int, current_user: dict = Depends(get_current_user)
):
    """Render the report as a self-contained HTML page."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])

        cur = conn.cursor()
        cur.execute(
            """
            SELECT report_json, status
            FROM socmint_reports
            WHERE id = %s AND case_id = %s
            """,
            (report_id, case_id),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    if row["status"] != "ready":
        raise HTTPException(status_code=422, detail="Report is not ready")

    report_json = row["report_json"]
    if isinstance(report_json, str):
        report_json = json.loads(report_json)

    html_content = render_report_html(report_json)
    return HTMLResponse(content=html_content)


@router.get("/{report_id}/pdf")
def get_report_pdf(
    case_id: int, report_id: int, current_user: dict = Depends(get_current_user)
):
    """Generate the report as a PDF download."""
    conn = get_db_conn()
    try:
        check_case_ownership(conn, case_id, current_user["id"])

        cur = conn.cursor()
        cur.execute(
            """
            SELECT report_json, status
            FROM socmint_reports
            WHERE id = %s AND case_id = %s
            """,
            (report_id, case_id),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    if row["status"] != "ready":
        raise HTTPException(status_code=422, detail="Report is not ready")

    report_json = row["report_json"]
    if isinstance(report_json, str):
        report_json = json.loads(report_json)

    pdf_bytes = render_report_pdf(report_json)

    case_title = report_json.get("report_metadata", {}).get("case_title", "case")
    # Sanitize case title to create a valid safe filename
    import re
    safe_title = re.sub(r'[\\/*?:"<>|]', "", case_title).strip()
    safe_title = safe_title.replace(" ", "-")
    if not safe_title:
        safe_title = "case"
    filename = f"{safe_title}-report.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

