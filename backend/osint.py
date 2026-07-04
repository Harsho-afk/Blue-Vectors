"""
ARIA — OSINT Lookup Module

1. Username enumeration: Sherlock project site database (400+ platforms)
   Uses sherlock-project's data.json for site definitions with our own
   async httpx checker for concurrent speed.

2. Breach lookup: XposedOrNot free API (no key required, real data)
   Falls back to HIBP v3 if HIBP_API_KEY is set.
"""

import os
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("aria.osint")


# ──────────────────────────────────────────────
# Sherlock site database
# ──────────────────────────────────────────────

def _load_sherlock_sites() -> dict:
    """Load site definitions from the installed sherlock-project package."""
    for module_name in ("sherlock_project", "sherlock"):
        try:
            mod = __import__(module_name)
            pkg_dir = os.path.dirname(mod.__file__)
            data_path = os.path.join(pkg_dir, "resources", "data.json")
            if not os.path.exists(data_path):
                continue
            with open(data_path, encoding="utf-8") as f:
                data = json.load(f)
            sites = {k: v for k, v in data.items() if isinstance(v, dict) and "url" in v}
            log.info("Sherlock: loaded %d site definitions from %s", len(sites), module_name)
            return sites
        except (ImportError, Exception):
            continue
    log.warning("sherlock-project not installed — run: pip install sherlock-project")
    return {}


SHERLOCK_SITES: dict = _load_sherlock_sites()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ──────────────────────────────────────────────
# Username Enumeration (Sherlock-powered)
# ──────────────────────────────────────────────

@dataclass
class PlatformResult:
    platform: str
    url: str
    exists: bool
    status_code: int
    response_time_ms: int


@dataclass
class UsernameSearchResult:
    username: str
    platforms_checked: int
    platforms_found: list[PlatformResult] = field(default_factory=list)
    platforms_not_found: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


STATUS_SKIPPED = -1


async def _check_site(
    client: httpx.AsyncClient,
    site_name: str,
    site_data: dict,
    username: str,
    semaphore: asyncio.Semaphore,
) -> PlatformResult:
    """Check if a username exists on a site using Sherlock's detection logic."""
    url = site_data["url"].replace("{}", username)
    error_type = site_data.get("errorType", "status_code")

    regex = site_data.get("regexCheck")
    if regex:
        try:
            if not re.match(regex, username):
                return PlatformResult(site_name, url, False, STATUS_SKIPPED, 0)
        except re.error:
            pass

    async with semaphore:
        try:
            req_headers = dict(HEADERS)
            site_headers = site_data.get("headers")
            if site_headers and isinstance(site_headers, dict):
                req_headers.update(site_headers)

            resp = await client.get(
                url, headers=req_headers, follow_redirects=True, timeout=10,
            )
            sc = resp.status_code
            elapsed = int(resp.elapsed.total_seconds() * 1000)

            exists = False

            if error_type == "status_code":
                exists = (200 <= sc < 300)
                if exists:
                    body_sample = resp.text[:100_000].lower()
                    if username.lower() not in body_sample:
                        exists = False

            elif error_type == "message":
                error_msg = site_data.get("errorMsg", "")
                if 200 <= sc < 300:
                    if isinstance(error_msg, list):
                        exists = not any(msg in resp.text for msg in error_msg)
                    elif error_msg:
                        exists = error_msg not in resp.text
                    else:
                        exists = True

            elif error_type == "response_url":
                error_url = site_data.get("errorUrl", "")
                if error_url:
                    exists = error_url not in str(resp.url)
                else:
                    exists = (200 <= sc < 300)

            return PlatformResult(site_name, url, exists, sc, elapsed)

        except Exception:
            return PlatformResult(site_name, url, False, 0, 0)


async def username_search(username: str, max_concurrent: int = 30) -> UsernameSearchResult:
    """
    Check if a username exists across 400+ platforms using Sherlock's site DB.

    Args:
        username: The handle to search for (no @/u/ prefix).
        max_concurrent: Max parallel HTTP requests.

    Returns:
        UsernameSearchResult with found/not-found/error breakdown.
    """
    username = username.strip().lstrip("@").lstrip("u/")

    if not SHERLOCK_SITES:
        return UsernameSearchResult(
            username=username, platforms_checked=0,
            errors=["sherlock-project package not installed"],
        )

    sites = {k: v for k, v in SHERLOCK_SITES.items() if not v.get("isNSFW", False)}

    log.info("OSINT: username search for '%s' across %d sites", username, len(sites))

    semaphore = asyncio.Semaphore(max_concurrent)
    result = UsernameSearchResult(username=username, platforms_checked=len(sites))

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [
            _check_site(client, name, data, username, semaphore)
            for name, data in sites.items()
        ]
        platform_results = await asyncio.gather(*tasks)

    for pr in platform_results:
        if pr.status_code == STATUS_SKIPPED:
            continue
        elif pr.status_code == 0:
            result.errors.append(f"{pr.platform}: unreachable")
        elif pr.exists:
            result.platforms_found.append(pr)
        else:
            result.platforms_not_found.append(pr.platform)

    result.platforms_found.sort(key=lambda p: p.platform)
    log.info(
        "OSINT: '%s' found on %d / %d platforms (%d errors)",
        username, len(result.platforms_found), len(sites), len(result.errors),
    )
    return result


# ──────────────────────────────────────────────
# Breach Lookup (XposedOrNot + optional HIBP)
# ──────────────────────────────────────────────

HIBP_API_KEY = os.environ.get("HIBP_API_KEY", "")
XON_BASE = "https://api.xposedornot.com/v1"


@dataclass
class BreachInfo:
    name: str
    domain: str
    breach_date: str
    data_classes: list[str]
    description: str
    is_verified: bool


@dataclass
class BreachLookupResult:
    email: str
    total_breaches: int
    breaches: list[BreachInfo] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


async def breach_lookup(email: str) -> BreachLookupResult:
    """
    Check if an email appeared in known data breaches.

    Primary: XposedOrNot (free, no API key required).
    Fallback: HIBP v3 if HIBP_API_KEY env var is set.
    """
    email = email.strip().lower()
    log.info("OSINT: breach lookup for '%s'", email)

    if HIBP_API_KEY:
        return await _hibp_lookup(email)

    return await _xon_lookup(email)


async def _xon_lookup(email: str) -> BreachLookupResult:
    """Breach lookup via XposedOrNot (free API, real data)."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{XON_BASE}/breach-analytics",
                params={"email": email},
                headers={"User-Agent": "ARIA-SOCMINT-Platform"},
                timeout=15,
            )

            if resp.status_code == 404:
                return BreachLookupResult(email=email, total_breaches=0)

            if resp.status_code == 429:
                return BreachLookupResult(
                    email=email, total_breaches=0,
                    error="XposedOrNot rate limit — try again later",
                )

            if resp.status_code != 200:
                return BreachLookupResult(
                    email=email, total_breaches=0,
                    error=f"XposedOrNot returned HTTP {resp.status_code}",
                )

            data = resp.json()
            if not data or not isinstance(data, dict):
                return BreachLookupResult(email=email, total_breaches=0)

            exposed = data.get("ExposedBreaches")
            if not exposed or not isinstance(exposed, dict):
                return BreachLookupResult(email=email, total_breaches=0)

            details = exposed.get("breaches_details")
            if not details or not isinstance(details, list):
                return BreachLookupResult(email=email, total_breaches=0)

            breaches = []
            for b in details:
                xposed_date = b.get("xposed_date", "")
                breach_date = xposed_date[:10] if len(xposed_date) >= 10 else xposed_date

                xposed_data = b.get("xposed_data", "")
                data_classes = [d.strip() for d in xposed_data.split(";") if d.strip()] if xposed_data else []

                breaches.append(BreachInfo(
                    name=b.get("breach", "Unknown"),
                    domain=b.get("domain", ""),
                    breach_date=breach_date,
                    data_classes=data_classes,
                    description=b.get("details", ""),
                    is_verified=b.get("verified", "No") == "Yes",
                ))

            log.info("OSINT: email '%s' found in %d breaches (XposedOrNot)", email, len(breaches))
            return BreachLookupResult(
                email=email,
                total_breaches=len(breaches),
                breaches=breaches,
            )

    except Exception as exc:
        log.error("OSINT: XposedOrNot lookup failed — %s", exc)
        return BreachLookupResult(
            email=email, total_breaches=0,
            error=f"Breach lookup failed: {exc}",
        )


async def _hibp_lookup(email: str) -> BreachLookupResult:
    """Breach lookup via HaveIBeenPwned v3 (requires paid API key)."""
    headers = {
        "hibp-api-key": HIBP_API_KEY,
        "user-agent": "ARIA-SOCMINT-Platform",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
                headers=headers,
                params={"truncateResponse": "false"},
                timeout=15,
            )

            if resp.status_code == 404:
                return BreachLookupResult(email=email, total_breaches=0)

            if resp.status_code == 401:
                log.warning("HIBP key invalid, falling back to XposedOrNot")
                return await _xon_lookup(email)

            if resp.status_code == 429:
                return BreachLookupResult(
                    email=email, total_breaches=0,
                    error="HIBP rate limit exceeded — try again later",
                )

            if resp.status_code != 200:
                return BreachLookupResult(
                    email=email, total_breaches=0,
                    error=f"HIBP returned HTTP {resp.status_code}",
                )

            data = resp.json()
            breaches = [
                BreachInfo(
                    name=b.get("Name", ""),
                    domain=b.get("Domain", ""),
                    breach_date=b.get("BreachDate", ""),
                    data_classes=b.get("DataClasses", []),
                    description=b.get("Description", ""),
                    is_verified=b.get("IsVerified", False),
                )
                for b in data
            ]

            log.info("OSINT: email '%s' found in %d breaches (HIBP)", email, len(breaches))
            return BreachLookupResult(
                email=email,
                total_breaches=len(breaches),
                breaches=breaches,
            )

    except Exception as exc:
        log.error("OSINT: HIBP lookup failed — %s", exc)
        return BreachLookupResult(
            email=email, total_breaches=0,
            error=f"Request failed: {exc}",
        )


# ──────────────────────────────────────────────
# DB persistence helpers
# ──────────────────────────────────────────────

def save_username_search(conn, case_id: int, result: UsernameSearchResult) -> int:
    """Save username search results to osint_lookups table."""
    cur = conn.cursor()
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO osint_lookups (case_id, lookup_type, input_value, result_json)
        VALUES (%s, 'sherlock', %s, %s)
        RETURNING id
        """,
        (case_id, result.username, result_json),
    )
    conn.commit()
    return cur.fetchone()["id"]


def save_breach_lookup(conn, case_id: int, result: BreachLookupResult) -> int:
    """Save breach lookup results to osint_lookups table."""
    cur = conn.cursor()
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO osint_lookups (case_id, lookup_type, input_value, result_json)
        VALUES (%s, 'hibp', %s, %s)
        RETURNING id
        """,
        (case_id, result.email, result_json),
    )
    conn.commit()
    return cur.fetchone()["id"]


# ──────────────────────────────────────────────
# CLI for testing
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="ARIA OSINT Lookups")
    sub = parser.add_subparsers(dest="cmd")

    p_user = sub.add_parser("username", help="Search username across platforms (Sherlock)")
    p_user.add_argument("username")

    p_breach = sub.add_parser("breach", help="Check email in breaches (XposedOrNot)")
    p_breach.add_argument("email")

    args = parser.parse_args()

    if args.cmd == "username":
        result = asyncio.run(username_search(args.username))
        print(f"\nUsername: {result.username}")
        print(f"Checked: {result.platforms_checked} platforms (Sherlock DB)")
        print(f"Found on {len(result.platforms_found)} platforms:\n")
        for p in result.platforms_found:
            print(f"  [+] {p.platform:20s}  {p.url}  ({p.response_time_ms}ms)")
        if result.errors:
            print(f"\nErrors ({len(result.errors)}):")
            for e in result.errors:
                print(f"  [!] {e}")

    elif args.cmd == "breach":
        result = asyncio.run(breach_lookup(args.email))
        print(f"\nEmail: {result.email}")
        print(f"Breaches: {result.total_breaches}")
        if result.error:
            print(f"Note: {result.error}")
        for b in result.breaches:
            print(f"\n  [{b.breach_date}] {b.name} ({b.domain})")
            print(f"    Exposed: {', '.join(b.data_classes)}")

    else:
        parser.print_help()
