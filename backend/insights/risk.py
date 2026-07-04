"""
Function 4: Risk/Exposure Scorer

Composite digital exposure score from:
- Breach count (weighted by severity — password breaches > email-only)
- Platform spread (Maigret total platforms found)
- PII exposure in bios (regex for emails, phones, real-name patterns)

Produces a 0-100 risk score with a breakdown.
"""

import json
import logging
import re

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.risk")

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}')

PASSWORD_BREACH_KEYWORDS = {"passwords", "password", "hashed passwords", "credentials"}


def _score_breaches(breaches: list[dict]) -> tuple[int, str]:
    """Score breach severity. Returns (score 0-40, detail string)."""
    if not breaches:
        return 0, "No known breaches"

    password_breaches = 0
    email_only_breaches = 0

    for b in breaches:
        data_classes = b.get("data_classes", [])
        if isinstance(data_classes, str):
            data_classes = [d.strip() for d in data_classes.split(";") if d.strip()]

        has_password = any(
            kw in dc.lower() for dc in data_classes for kw in PASSWORD_BREACH_KEYWORDS
        )
        if has_password:
            password_breaches += 1
        else:
            email_only_breaches += 1

    score = min(40, password_breaches * 15 + email_only_breaches * 5)

    parts = []
    if password_breaches:
        parts.append(f"{password_breaches} password breach(es)")
    if email_only_breaches:
        parts.append(f"{email_only_breaches} email-only breach(es)")

    detail = ", ".join(parts) if parts else "No breaches"
    return score, detail


def _score_platform_spread(total_found: int) -> tuple[int, str]:
    """Score based on number of platforms found. Returns (score 0-30, detail)."""
    if total_found >= 50:
        score = 30
    elif total_found >= 20:
        score = 20
    elif total_found >= 10:
        score = 15
    elif total_found >= 5:
        score = 10
    else:
        score = total_found * 2

    return score, f"{total_found} platform accounts discovered"


def _score_pii_exposure(accounts: list[dict]) -> tuple[int, list[str]]:
    """Score PII visible in bios. Returns (score 0-30, list of details)."""
    score = 0
    details: list[str] = []

    for acc in accounts:
        bio = (acc.get("bio") or "").strip()
        platform = acc.get("platform", "")
        if not bio:
            continue

        if EMAIL_RE.search(bio):
            score += 10
            details.append(f"Email visible in {platform} bio")

        if PHONE_RE.search(bio):
            score += 15
            details.append(f"Phone number visible in {platform} bio")

    return min(30, score), details


def run(conn, case_id: int) -> list[InsightResult]:
    """Run risk/exposure scoring for a case."""
    cur = conn.cursor()

    # Get breach data
    cur.execute(
        "SELECT id, result_json FROM osint_lookups WHERE case_id = %s AND lookup_type IN ('xposedornot', 'hibp')",
        (case_id,),
    )
    breach_rows = cur.fetchall()

    all_breaches: list[dict] = []
    breach_lookup_ids: list[int] = []
    for row in breach_rows:
        raw = row["result_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        breaches = raw.get("breaches", [])
        all_breaches.extend(breaches)
        if breaches:
            breach_lookup_ids.append(row["id"])

    # Get Maigret platform spread
    cur.execute(
        "SELECT id, result_json FROM osint_lookups WHERE case_id = %s AND lookup_type = 'maigret'",
        (case_id,),
    )
    maigret_rows = cur.fetchall()

    total_found = 0
    maigret_lookup_ids: list[int] = []
    for row in maigret_rows:
        raw = row["result_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)
        found = raw.get("total_found", 0)
        total_found = max(total_found, found)
        if found > 0:
            maigret_lookup_ids.append(row["id"])

    # Get account bios for PII check
    cur.execute(
        "SELECT id, platform, bio FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = [dict(r) for r in cur.fetchall()]

    breach_score, breach_detail = _score_breaches(all_breaches)
    spread_score, spread_detail = _score_platform_spread(total_found)
    pii_score, pii_details = _score_pii_exposure(accounts)

    total_score = min(100, breach_score + spread_score + pii_score)

    if total_score >= 70:
        level = "High"
        confidence = "high"
    elif total_score >= 40:
        level = "Moderate"
        confidence = "medium"
    else:
        level = "Low"
        confidence = "low"

    claim_parts = [f"{level} digital exposure (score: {total_score}/100)"]
    if total_found > 0:
        claim_parts.append(f"{total_found} platform accounts")
    if all_breaches:
        claim_parts.append(f"{len(all_breaches)} breach(es)")
    if pii_details:
        claim_parts.append(", ".join(pii_details))

    evidence: list[EvidenceItem] = []

    if all_breaches:
        breach_names = [b.get("name", "Unknown") for b in all_breaches[:5]]
        evidence.append(EvidenceItem(
            method="breach_count",
            detail=f"{breach_detail}. Breaches: {', '.join(breach_names)}",
            source_table="osint_lookups",
            source_id=breach_lookup_ids[0] if breach_lookup_ids else None,
        ))

    if total_found > 0:
        evidence.append(EvidenceItem(
            method="platform_spread",
            detail=spread_detail,
            source_table="osint_lookups",
            source_id=maigret_lookup_ids[0] if maigret_lookup_ids else None,
        ))

    if pii_details:
        evidence.append(EvidenceItem(
            method="pii_exposure",
            detail="; ".join(pii_details),
            source_table="accounts",
            source_id=None,
        ))

    if not evidence:
        log.info("Case %d: risk scorer found no data to score", case_id)
        return []

    result = InsightResult(
        category="risk",
        claim=", ".join(claim_parts),
        confidence=confidence,
        evidence=evidence,
    )

    log.info("Case %d: risk score = %d/100 (%s)", case_id, total_score, level)
    return [result]
