"""
ARIA -- One-click investigation runner

POST /api/cases/{case_id}/run  -> SSE stream of progress events

Orchestrates: Maigret -> deep collectors (platform_hint only) -> breach -> phone -> correlation -> insights
Each step streams progress via Server-Sent Events so the frontend can show live updates.

PARALLEL EXECUTION MODEL
------------------------
- All seed collectors (username -> Maigret [+ deep-collect only if a
  platform_hint was set on the identifier], email -> breach, phone -> phone
  OSINT) run CONCURRENTLY via asyncio.gather. Each still streams its own
  progress events; events from different tasks interleave on the SSE
  stream as they complete, multiplexed through an asyncio.Queue.
- A username identifier with NO platform_hint stops at Maigret. Maigret is
  a broad, shallow 500+ site presence check and its "found" results are
  leads, not confirmed accounts — many sites false-positive on common
  usernames. ARIA does NOT automatically deep-collect any platform Maigret
  flags; the platforms it found are surfaced in the "collectible_platforms"
  field of the maigret SSE event for the person to review and collect from
  explicitly (via the per-identifier /collect endpoint or by setting a
  platform_hint), rather than being deep-collected sight-unseen.
- Correlation and Insights are independent of each other (insights functions
  only read accounts/posts/osint_lookups, never linkage_results) so they run
  CONCURRENTLY too, each offloaded to a worker thread since both are
  blocking/sync under the hood.
- The Intelligence briefing runs AFTER correlation + insights finish, since
  the Analyst LLM prompt is built from both insights and correlation results.
"""

import json
import logging
import asyncio
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from auth import get_current_user, get_db_conn
from osint import run_maigret, breach_lookup, save_maigret_search, save_breach_lookup
from collector.base import SUPPORTED_PLATFORMS
from collector.phone import PhoneCollector
from collect_stream import collect_one_platform
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

import re
from urllib.parse import urlparse

URL_PLATFORM_PATTERNS = [
    (
        re.compile(
            r"(?:reddit\.com|old\.reddit\.com)/u(?:ser)?/([A-Za-z0-9_-]+)", re.I
        ),
        "reddit",
    ),
    (re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", re.I), "twitter"),
    (re.compile(r"github\.com/([A-Za-z0-9_-]+)", re.I), "github"),
    (re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I), "instagram"),
]


def _parse_profile_url(url: str) -> tuple[str, str] | None:
    """Extract (platform, username) from a profile URL. Returns None if unrecognized."""
    for pattern, platform in URL_PLATFORM_PATTERNS:
        m = pattern.search(url)
        if m:
            username = m.group(1)
            if username.lower() not in (
                "explore",
                "search",
                "about",
                "settings",
                "login",
            ):
                return (platform, username)
    return None


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _check_case_ownership(conn, case_id: int, user_id: int):
    cur = conn.cursor()
    cur.execute("SELECT investigator_id FROM cases WHERE id = %s", (case_id,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )
    if row["investigator_id"] != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )


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


# ─────────────────────────────────────────────────────────────────────────
# Per-seed worker coroutines. Each one owns its own DB connections (opened
# and closed within the coroutine) so they're safe to run concurrently —
# no connection is ever shared across tasks. Each emits its own SSE events
# via `emit` (an async callable — in practice `queue.put`) and returns the
# number of accounts it collected (0 for email/phone, which don't add
# accounts).
# ─────────────────────────────────────────────────────────────────────────


async def _process_username_seed(case_id: int, ident: dict, emit) -> int:
    """Handle one username identifier: direct collect if platform_hint known,
    otherwise Maigret discovery ONLY. Maigret is a broad, shallow, 500+
    site presence-check — its "found" results are informational leads, not
    confirmed accounts (many sites false-positive on common usernames), so
    ARIA does NOT auto deep-collect anything it finds. Deep collection for
    a discovered platform is a separate, explicit action (via the
    per-identifier /collect endpoint) once a person reviews the leads."""
    username = ident["value"]
    platform_hint = ident.get("platform_hint")

    if platform_hint and platform_hint in SUPPORTED_PLATFORMS:
        return await collect_one_platform(case_id, platform_hint, username, emit)

    await emit(
        {
            "step": "maigret",
            "status": "running",
            "seed": username,
            "message": "Searching 500+ platforms...",
        }
    )
    try:
        maigret_result = await run_maigret(username)

        conn = get_db_conn()
        try:
            save_maigret_search(conn, case_id, maigret_result)
        finally:
            conn.close()

        total_found = maigret_result.get("total_found", 0)
        lead_summary = maigret_result.get("lead_summary", {})
        collectible = _find_collectible_platforms(maigret_result)
        await emit(
            {
                "step": "maigret",
                "status": "done",
                "seed": username,
                "found": total_found,
                "lead_summary": lead_summary,
                "collectible_platforms": collectible,
                "message": (
                    f"Found on {total_found} platforms ({lead_summary.get('high', 0)} strong, "
                    f"{lead_summary.get('medium', 0)} medium leads)"
                    + (
                        f" — review and collect manually: {', '.join(collectible)}"
                        if collectible
                        else ""
                    )
                ),
            }
        )

        # Intentionally stop here. Maigret only confirms presence/absence
        # heuristically — it is NOT a deep collector, and auto-triggering
        # e.g. a Twitter/Instagram/etc. deep-collect for every platform it
        # flags leads to false-positive collections. The person reviews the
        # leads and kicks off deep collection explicitly per platform.
        return 0

    except Exception as e:
        log.error("Maigret failed for '%s': %s", username, e)
        await emit(
            {
                "step": "maigret",
                "status": "error",
                "seed": username,
                "error": str(e),
            }
        )
        return 0


async def _process_email_seed(case_id: int, ident: dict, emit) -> int:
    email = ident["value"]
    await emit(
        {
            "step": "breach",
            "status": "running",
            "seed": email,
            "message": "Checking breach databases...",
        }
    )
    try:
        result = await breach_lookup(email)
        conn = get_db_conn()
        try:
            save_breach_lookup(conn, case_id, result)
        finally:
            conn.close()
        await emit(
            {
                "step": "breach",
                "status": "done",
                "seed": email,
                "breaches": result.total_breaches,
                "message": f"Found in {result.total_breaches} breach(es)",
            }
        )
    except Exception as e:
        log.error("Breach lookup failed for '%s': %s", email, e)
        await emit(
            {"step": "breach", "status": "error", "seed": email, "error": str(e)}
        )
    return 0


async def _process_phone_seed(case_id: int, ident: dict, emit) -> int:
    phone = ident["value"]
    await emit(
        {
            "step": "phone",
            "status": "running",
            "seed": phone,
            "message": "Looking up phone number...",
        }
    )
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

        await emit(
            {
                "step": "phone",
                "status": "done",
                "seed": phone,
                "message": "Phone lookup complete",
            }
        )
    except Exception as e:
        log.error("Phone lookup failed for '%s': %s", phone, e)
        await emit({"step": "phone", "status": "error", "seed": phone, "error": str(e)})
    return 0


async def _process_profile_url_seed(case_id: int, ident: dict, emit) -> int:
    """Handle a profile_url identifier: parse URL, extract platform+username, collect."""
    url = ident["value"]
    parsed = _parse_profile_url(url)
    if not parsed:
        await emit(
            {
                "step": "collect",
                "status": "error",
                "platform": "unknown",
                "username": url,
                "error": f"Could not parse platform/username from URL: {url}",
            }
        )
        return 0

    platform, username = parsed
    await emit(
        {
            "step": "collect",
            "status": "running",
            "platform": platform,
            "username": username,
            "message": f"Collecting from {platform}/{username} (parsed from URL)",
        }
    )
    return await collect_one_platform(case_id, platform, username, emit)


# ─────────────────────────────────────────────────────────────────────────
# Analysis phase workers (correlation + insights). Both are blocking/sync
# under the hood (psycopg2, numpy, sklearn), so each is offloaded to a
# worker thread via run_in_executor — that's what lets them genuinely run
# in parallel with each other rather than just interleaving on one thread.
# ─────────────────────────────────────────────────────────────────────────


async def _process_correlation(case_id: int, emit) -> None:
    await emit(
        {
            "step": "correlate",
            "status": "running",
            "message": "Running identity correlation...",
        }
    )
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, correlate_case, case_id)
        await emit(
            {
                "step": "correlate",
                "status": "done",
                "pairs": len(results),
                "message": f"Correlated {len(results)} pair(s)",
            }
        )
    except Exception as e:
        log.error("Correlation failed for case %d: %s", case_id, e)
        await emit({"step": "correlate", "status": "error", "error": str(e)})


async def _process_insights(case_id: int, emit) -> None:
    await emit(
        {"step": "insights", "status": "running", "message": "Computing insights..."}
    )
    try:
        conn = get_db_conn()
        try:
            loop = asyncio.get_event_loop()
            insight_results = await loop.run_in_executor(
                None, run_insights, conn, case_id
            )
        finally:
            conn.close()
        await emit(
            {
                "step": "insights",
                "status": "done",
                "count": len(insight_results),
                "message": f"Generated {len(insight_results)} insight(s)",
            }
        )
    except Exception as e:
        log.error("Insights failed for case %d: %s", case_id, e)
        await emit({"step": "insights", "status": "error", "error": str(e)})


async def _process_intelligence(case_id: int, emit) -> None:
    import os

    has_llm_key = (
        os.environ.get("GROQ_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
    )
    if not has_llm_key:
        await emit(
            {
                "step": "intelligence",
                "status": "skipped",
                "message": "No LLM API key configured (GROQ_API_KEY or GEMINI_API_KEY)",
            }
        )
        return

    await emit(
        {
            "step": "intelligence",
            "status": "running",
            "message": "Generating intelligence briefing...",
        }
    )
    try:
        from llm.analyst import generate_briefing
        from llm.citation_check import validate_citations, save_report

        loop = asyncio.get_event_loop()

        def _run_briefing():
            conn = get_db_conn()
            try:
                analyst_output = generate_briefing(conn, case_id)
                checked = validate_citations(conn, case_id, analyst_output)
                save_report(conn, case_id, checked)
                return checked
            finally:
                conn.close()

        checked = await loop.run_in_executor(None, _run_briefing)
        await emit(
            {
                "step": "intelligence",
                "status": "done",
                "claims": len(checked["claims"]),
                "message": f"Intelligence briefing generated ({len(checked['claims'])} cited claims)",
            }
        )
    except Exception as e:
        log.error("Intelligence briefing failed for case %d: %s", case_id, e)
        await emit({"step": "intelligence", "status": "error", "error": str(e)})


# ─────────────────────────────────────────────────────────────────────────
# Producer: drives the whole pipeline, pushing SSE-ready dicts onto a
# queue. A `None` sentinel signals completion (success or failure).
# ─────────────────────────────────────────────────────────────────────────


async def _run_producer(
    case_id: int, user_id: int, queue: "asyncio.Queue[Optional[dict]]"
) -> None:
    emit = queue.put  # async callable: emit(dict) -> awaits queue.put(dict)

    conn = get_db_conn()
    try:
        _check_case_ownership(conn, case_id, user_id)
        identifiers = _load_identifiers(conn, case_id)
    finally:
        conn.close()

    if not identifiers:
        await emit(
            {
                "step": "error",
                "status": "error",
                "message": "No identifiers found. Add seeds first.",
            }
        )
        await queue.put(None)
        return

    usernames = [i for i in identifiers if i["identifier_type"] == "username"]
    emails = [i for i in identifiers if i["identifier_type"] == "email"]
    phones = [i for i in identifiers if i["identifier_type"] == "phone"]
    profile_urls = [i for i in identifiers if i["identifier_type"] == "profile_url"]

    await emit(
        {
            "step": "init",
            "status": "running",
            "message": f"Starting investigation with {len(identifiers)} seed(s) ({len(usernames) + len(emails) + len(phones) + len(profile_urls)} running in parallel)",
            "total_seeds": len(identifiers),
            "usernames": len(usernames),
            "emails": len(emails),
            "phones": len(phones),
        }
    )

    # ── Phase 1: all seed collectors, concurrently ──────────────────────────
    collector_tasks = (
        [_process_username_seed(case_id, ident, emit) for ident in usernames]
        + [_process_email_seed(case_id, ident, emit) for ident in emails]
        + [_process_phone_seed(case_id, ident, emit) for ident in phones]
        + [_process_profile_url_seed(case_id, ident, emit) for ident in profile_urls]
    )

    collected_accounts = 0
    if collector_tasks:
        results = await asyncio.gather(*collector_tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                log.error(
                    "Case %d: a collector task raised unexpectedly: %s", case_id, r
                )
            else:
                collected_accounts += r

    await emit(
        {
            "step": "collection_phase",
            "status": "done",
            "accounts_collected": collected_accounts,
            "message": f"Collection complete — {collected_accounts} account(s) gathered",
        }
    )

    # ── Phase 2: correlation + insights, concurrently ───────────────────────
    analysis_tasks = []

    if collected_accounts >= 2:
        analysis_tasks.append(_process_correlation(case_id, emit))
    else:
        await emit(
            {
                "step": "correlate",
                "status": "skipped",
                "message": f"Need 2+ accounts to correlate (have {collected_accounts})",
            }
        )

    if collected_accounts >= 1:
        analysis_tasks.append(_process_insights(case_id, emit))
    else:
        await emit(
            {
                "step": "insights",
                "status": "skipped",
                "message": "No accounts collected",
            }
        )

    if analysis_tasks:
        await asyncio.gather(*analysis_tasks, return_exceptions=True)

    # ── Phase 3: intelligence briefing (depends on insights + correlation) ──
    if collected_accounts >= 1:
        await _process_intelligence(case_id, emit)

    await emit(
        {
            "step": "complete",
            "status": "done",
            "message": "Investigation complete",
            "accounts_collected": collected_accounts,
        }
    )
    await queue.put(None)


async def _run_investigation(case_id: int, user_id: int) -> AsyncGenerator[str, None]:
    """Async generator that drives the pipeline via a producer task and
    yields SSE events as they're pushed onto the queue, so events from
    concurrently-running collectors/analysis steps interleave live."""
    queue: "asyncio.Queue[Optional[dict]]" = asyncio.Queue()
    producer_task = asyncio.create_task(_run_producer(case_id, user_id, queue))

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
        else:
            exc = producer_task.exception()
            if exc:
                log.error("Case %d: investigation producer failed: %s", case_id, exc)


@router.post("/{case_id}/run")
async def run_investigation(
    case_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    Run the full investigation pipeline for a case.
    Streams progress as Server-Sent Events. Collectors run in parallel;
    correlation and insights run in parallel with each other afterward.
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
