"""
ARIA -- One-click investigation runner

POST /api/cases/{case_id}/run  -> SSE stream of progress events

Orchestrates: Maigret -> deep collectors -> breach -> phone -> correlation -> insights
Each step streams progress via Server-Sent Events so the frontend can show live updates.
"""

import json
import logging
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from auth import get_current_user, get_db_conn
from osint import run_maigret, breach_lookup, save_maigret_search, save_breach_lookup
from collector.base import collect_async, save_to_db, SUPPORTED_PLATFORMS
from collector.phone import PhoneCollector
from correlator import correlate_case
from insights.orchestrator import run_all as run_insights

router = APIRouter(prefix="/api/cases", tags=["run"])
log = logging.getLogger("aria.run")

PLATFORM_ALIASES = {
    "github": "github",
    "reddit": "reddit",
    "twitter": "twitter",
    "x": "twitter",
    "instagram": "instagram",
}


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _check_case_ownership(conn, case_id: int, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    if row["investigator_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")


def _load_identifiers(conn, case_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, identifier_type, value, platform_hint FROM case_identifiers WHERE case_id = %s",
        (case_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def _find_collectible_platforms(maigret_result: dict) -> list[str]:
    """Extract platforms from Maigret results that have deep collectors."""
    found: set[str] = set()
    for platforms in maigret_result.get("categories", {}).values():
        for entry in platforms:
            name = PLATFORM_ALIASES.get(entry["platform"].lower())
            if name and name in SUPPORTED_PLATFORMS:
                found.add(name)
    return sorted(found)


async def _run_investigation(case_id: int, user_id: int) -> AsyncGenerator[str, None]:
    """Async generator that runs the full investigation pipeline and yields SSE events."""

    # Load identifiers
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, user_id)
        identifiers = _load_identifiers(conn, case_id)
    finally:
        conn.close()

    if not identifiers:
        yield _sse({"step": "error", "status": "error", "message": "No identifiers found. Add seeds first."})
        return

    usernames = [i for i in identifiers if i["identifier_type"] == "username"]
    emails = [i for i in identifiers if i["identifier_type"] == "email"]
    phones = [i for i in identifiers if i["identifier_type"] == "phone"]

    total_steps = len(usernames) + len(emails) + len(phones) + 2  # +2 for correlate + insights
    yield _sse({
        "step": "init",
        "status": "running",
        "message": f"Starting investigation with {len(identifiers)} seed(s)",
        "total_seeds": len(identifiers),
        "usernames": len(usernames),
        "emails": len(emails),
        "phones": len(phones),
    })

    collected_accounts = 0

    # ── Phase 1: Username seeds ──────────────────────────────────────────────
    for ident in usernames:
        username = ident["value"]
        platform_hint = ident.get("platform_hint")

        if platform_hint and platform_hint in SUPPORTED_PLATFORMS:
            # Direct collection from known platform
            yield _sse({"step": "collect", "status": "running", "platform": platform_hint, "username": username})
            try:
                profile = await collect_async(platform_hint, username)
                conn = get_db_conn()
                try:
                    save_to_db(profile, conn, case_id)
                finally:
                    conn.close()
                collected_accounts += 1
                yield _sse({
                    "step": "collect", "status": "done",
                    "platform": platform_hint, "username": username,
                    "posts": len(profile.posts),
                    "display_name": profile.display_name,
                })
            except Exception as e:
                log.warning("Collection failed for %s/%s: %s", platform_hint, username, e)
                yield _sse({
                    "step": "collect", "status": "error",
                    "platform": platform_hint, "username": username,
                    "error": str(e),
                })
        else:
            # No platform hint → run Maigret first, then collect from found platforms
            yield _sse({"step": "maigret", "status": "running", "seed": username, "message": "Searching 500+ platforms..."})
            try:
                maigret_result = await run_maigret(username)

                conn = get_db_conn()
                try:
                    save_maigret_search(conn, case_id, maigret_result)
                finally:
                    conn.close()

                total_found = maigret_result.get("total_found", 0)
                lead_summary = maigret_result.get("lead_summary", {})
                yield _sse({
                    "step": "maigret", "status": "done",
                    "seed": username, "found": total_found,
                    "lead_summary": lead_summary,
                    "message": f"Found on {total_found} platforms ({lead_summary.get('high', 0)} strong, {lead_summary.get('medium', 0)} medium leads)",
                })

                # Deep-collect from supported platforms
                collectible = _find_collectible_platforms(maigret_result)
                for platform in collectible:
                    yield _sse({"step": "collect", "status": "running", "platform": platform, "username": username})
                    try:
                        profile = await collect_async(platform, username)
                        conn = get_db_conn()
                        try:
                            save_to_db(profile, conn, case_id)
                        finally:
                            conn.close()
                        collected_accounts += 1
                        yield _sse({
                            "step": "collect", "status": "done",
                            "platform": platform, "username": username,
                            "posts": len(profile.posts),
                            "display_name": profile.display_name,
                        })
                    except Exception as e:
                        log.warning("Collection failed for %s/%s: %s", platform, username, e)
                        yield _sse({
                            "step": "collect", "status": "error",
                            "platform": platform, "username": username,
                            "error": str(e),
                        })

            except Exception as e:
                log.error("Maigret failed for '%s': %s", username, e)
                yield _sse({
                    "step": "maigret", "status": "error",
                    "seed": username, "error": str(e),
                })

    # ── Phase 2: Email seeds ─────────────────────────────────────────────────
    for ident in emails:
        email = ident["value"]
        yield _sse({"step": "breach", "status": "running", "seed": email, "message": "Checking breach databases..."})
        try:
            result = await breach_lookup(email)
            conn = get_db_conn()
            try:
                save_breach_lookup(conn, case_id, result)
            finally:
                conn.close()
            yield _sse({
                "step": "breach", "status": "done",
                "seed": email, "breaches": result.total_breaches,
                "message": f"Found in {result.total_breaches} breach(es)",
            })
        except Exception as e:
            log.error("Breach lookup failed for '%s': %s", email, e)
            yield _sse({"step": "breach", "status": "error", "seed": email, "error": str(e)})

    # ── Phase 3: Phone seeds ─────────────────────────────────────────────────
    for ident in phones:
        phone = ident["value"]
        yield _sse({"step": "phone", "status": "running", "seed": phone, "message": "Looking up phone number..."})
        try:
            collector = PhoneCollector()
            profile = await collector.collect(phone)
            result_dict = profile.to_dict()

            conn = get_db_conn()
            try:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO osint_lookups (case_id, lookup_type, input_value, result_json)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (case_id, "phone", phone, json.dumps(result_dict)),
                )
                conn.commit()
            finally:
                conn.close()

            yield _sse({
                "step": "phone", "status": "done",
                "seed": phone,
                "message": "Phone lookup complete",
            })
        except Exception as e:
            log.error("Phone lookup failed for '%s': %s", phone, e)
            yield _sse({"step": "phone", "status": "error", "seed": phone, "error": str(e)})

    # ── Phase 4: Correlation ─────────────────────────────────────────────────
    if collected_accounts >= 2:
        yield _sse({"step": "correlate", "status": "running", "message": "Running identity correlation..."})
        try:
            results = correlate_case(case_id)
            yield _sse({
                "step": "correlate", "status": "done",
                "pairs": len(results),
                "message": f"Correlated {len(results)} pair(s)",
            })
        except Exception as e:
            log.error("Correlation failed for case %d: %s", case_id, e)
            yield _sse({"step": "correlate", "status": "error", "error": str(e)})
    else:
        yield _sse({
            "step": "correlate", "status": "skipped",
            "message": f"Need 2+ accounts to correlate (have {collected_accounts})",
        })

    # ── Phase 5: Insights ────────────────────────────────────────────────────
    if collected_accounts >= 1:
        yield _sse({"step": "insights", "status": "running", "message": "Computing insights..."})
        try:
            conn = get_db_conn()
            try:
                insight_results = run_insights(conn, case_id)
            finally:
                conn.close()
            yield _sse({
                "step": "insights", "status": "done",
                "count": len(insight_results),
                "message": f"Generated {len(insight_results)} insight(s)",
            })
        except Exception as e:
            log.error("Insights failed for case %d: %s", case_id, e)
            yield _sse({"step": "insights", "status": "error", "error": str(e)})
    else:
        yield _sse({"step": "insights", "status": "skipped", "message": "No accounts collected"})

    # ── Phase 6: Intelligence Briefing (LLM) ──────────────────────────────
    if collected_accounts >= 1:
        import os
        has_llm_key = os.environ.get("GROQ_API_KEY", "").strip() or os.environ.get("GEMINI_API_KEY", "").strip()
        if has_llm_key:
            yield _sse({"step": "intelligence", "status": "running", "message": "Generating intelligence briefing..."})
            try:
                from llm.analyst import generate_briefing
                from llm.citation_check import validate_citations, save_report
                conn = get_db_conn()
                try:
                    analyst_output = generate_briefing(conn, case_id)
                    checked = validate_citations(conn, case_id, analyst_output)
                    save_report(conn, case_id, checked)
                finally:
                    conn.close()
                yield _sse({
                    "step": "intelligence", "status": "done",
                    "claims": len(checked["claims"]),
                    "message": f"Intelligence briefing generated ({len(checked['claims'])} cited claims)",
                })
            except Exception as e:
                log.error("Intelligence briefing failed for case %d: %s", case_id, e)
                yield _sse({"step": "intelligence", "status": "error", "error": str(e)})
        else:
            yield _sse({"step": "intelligence", "status": "skipped", "message": "No LLM API key configured (GROQ_API_KEY or GEMINI_API_KEY)"})

    # ── Done ─────────────────────────────────────────────────────────────────
    yield _sse({
        "step": "complete", "status": "done",
        "message": "Investigation complete",
        "accounts_collected": collected_accounts,
    })


@router.post("/{case_id}/run")
async def run_investigation(
    case_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Run the full investigation pipeline for a case.
    Streams progress as Server-Sent Events.
    """
    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, current_user["id"])
    finally:
        conn.close()

    return StreamingResponse(
        _run_investigation(case_id, current_user["id"]),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
