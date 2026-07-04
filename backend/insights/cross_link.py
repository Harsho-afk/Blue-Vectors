"""
Function 1: Bio Cross-Link Extractor

Scans account bios for URLs, @handles, email addresses, and "find me on"
patterns. Also pulls Maigret's linked_accounts from osint_lookups.

Every cross-link is a hard pivot — self-declared connection between accounts.
Always confidence: high.
"""

import json
import logging
import re
from typing import Optional

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.cross_link")

URL_RE = re.compile(
    r'https?://[^\s<>\'")\]]+',
    re.IGNORECASE,
)

HANDLE_RE = re.compile(
    r'(?:^|[\s(])@([A-Za-z0-9_.]{1,30})',
)

EMAIL_RE = re.compile(
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
)

PLATFORM_DOMAINS = {
    "twitter.com": "twitter",
    "x.com": "twitter",
    "instagram.com": "instagram",
    "github.com": "github",
    "reddit.com": "reddit",
    "linkedin.com": "linkedin",
    "facebook.com": "facebook",
    "t.me": "telegram",
    "youtube.com": "youtube",
    "tiktok.com": "tiktok",
    "twitch.tv": "twitch",
    "discord.gg": "discord",
    "linktr.ee": "linktree",
    "mastodon.social": "mastodon",
    "threads.net": "threads",
    "bsky.app": "bluesky",
}


def _detect_platform(url: str) -> Optional[str]:
    url_lower = url.lower()
    for domain, platform in PLATFORM_DOMAINS.items():
        if domain in url_lower:
            return platform
    return None


def _extract_username_from_url(url: str) -> Optional[str]:
    """Try to extract a username from a social media URL."""
    parts = url.rstrip("/").split("/")
    if len(parts) >= 4:
        candidate = parts[3].lstrip("@")
        if candidate and len(candidate) <= 30 and not candidate.startswith("?"):
            return candidate
    return None


def extract_bio_links(account_id: int, bio: str) -> list[InsightResult]:
    """Extract cross-reference insights from a single bio string."""
    if not bio or len(bio.strip()) < 3:
        return []

    results: list[InsightResult] = []

    for match in URL_RE.finditer(bio):
        url = match.group(0).rstrip(".,;:!?)")
        platform = _detect_platform(url)
        username = _extract_username_from_url(url) if platform else None

        claim_parts = [f"Bio contains link to {url}"]
        if platform:
            claim_parts.append(f"(platform: {platform})")
        if username:
            claim_parts.append(f"(handle: {username})")

        results.append(InsightResult(
            category="cross_reference",
            claim=" ".join(claim_parts),
            confidence="high",
            account_id=account_id,
            evidence=[EvidenceItem(
                method="bio_url_extraction",
                detail=f"URL found in bio: {url}",
                source_table="accounts",
                source_id=account_id,
            )],
        ))

    for match in HANDLE_RE.finditer(bio):
        handle = match.group(1)
        if handle.lower() in ("gmail", "yahoo", "hotmail", "outlook", "protonmail"):
            continue
        results.append(InsightResult(
            category="cross_reference",
            claim=f"Bio mentions handle @{handle}",
            confidence="high",
            account_id=account_id,
            evidence=[EvidenceItem(
                method="bio_handle_extraction",
                detail=f"@{handle} found in bio text",
                source_table="accounts",
                source_id=account_id,
            )],
        ))

    for match in EMAIL_RE.finditer(bio):
        email = match.group(0)
        results.append(InsightResult(
            category="cross_reference",
            claim=f"Bio contains email address: {email}",
            confidence="high",
            account_id=account_id,
            evidence=[EvidenceItem(
                method="bio_email_extraction",
                detail=f"Email found in bio: {email}",
                source_table="accounts",
                source_id=account_id,
            )],
        ))

    return results


def extract_maigret_links(case_id: int, conn) -> list[InsightResult]:
    """Pull linked_accounts from Maigret osint_lookups for this case."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, result_json FROM osint_lookups WHERE case_id = %s AND lookup_type = 'maigret'",
        (case_id,),
    )
    rows = cur.fetchall()

    results: list[InsightResult] = []

    for row in rows:
        lookup_id = row["id"]
        raw = row["result_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)

        linked = raw.get("linked_accounts", [])
        for link in linked:
            username = link.get("username", "")
            source_platform = link.get("source_platform", "")
            how_found = link.get("how_found", "")

            if not username:
                continue

            results.append(InsightResult(
                category="cross_reference",
                claim=f"Maigret discovered linked username '{username}' via {source_platform}",
                confidence="high",
                evidence=[EvidenceItem(
                    method="maigret_linked_account",
                    detail=f"{how_found}. Username: {username}",
                    source_table="osint_lookups",
                    source_id=lookup_id,
                )],
            ))

    return results


def run(conn, case_id: int) -> list[InsightResult]:
    """Run bio cross-link extraction for all accounts in a case + Maigret links."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id, bio FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = cur.fetchall()

    all_results: list[InsightResult] = []

    for acc in accounts:
        bio = acc.get("bio") or ""
        all_results.extend(extract_bio_links(acc["id"], bio))

    all_results.extend(extract_maigret_links(case_id, conn))

    log.info("Case %d: cross-link extractor found %d links", case_id, len(all_results))
    return all_results
