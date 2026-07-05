"""
ARIA — OSINT Lookup Module

1. Username enumeration: Maigret (500+ platforms, structured profile data,
   category tagging, profile extraction)
   Primary: library API. Fallback: subprocess CLI.

2. Breach lookup: XposedOrNot free API (no key required, real data)
   Falls back to HIBP v3 if HIBP_API_KEY is set.
"""

import os
import asyncio
import json
import logging
import tempfile
from dataclasses import dataclass, field, asdict
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("aria.osint")


# ──────────────────────────────────────────────
# Category mapping (Maigret tags → ARIA categories)
# ──────────────────────────────────────────────

CATEGORY_MAP = {
    "social": "social_media",
    "dating": "social_media",
    "microblogging": "social_media",

    "coding": "developer",
    "hacking": "developer",
    "tech": "developer",
    "openSource": "developer",

    "gaming": "gaming",
    "esports": "gaming",

    "video": "streaming",
    "music": "streaming",
    "podcast": "streaming",
    "audio": "streaming",

    "business": "professional",
    "career": "professional",
    "finance": "professional",

    "art": "creative",
    "design": "creative",
    "photography": "creative",
    "writing": "creative",
    "blog": "creative",

    "messenger": "messaging",
    "communication": "messaging",

    "shopping": "shopping",
    "marketplace": "shopping",
    "crowdfunding": "shopping",
}

CATEGORY_ORDER = [
    "social_media", "developer", "gaming", "streaming",
    "professional", "creative", "messaging", "shopping", "other",
]

CATEGORY_DISPLAY = {
    "social_media": "Social Media",
    "developer": "Developer & Tech",
    "gaming": "Gaming",
    "streaming": "Streaming & Media",
    "professional": "Professional",
    "creative": "Creative & Art",
    "messaging": "Messaging",
    "shopping": "Shopping & Finance",
    "other": "Other Platforms",
}


# ──────────────────────────────────────────────
# Maigret Username Enumeration
# ──────────────────────────────────────────────

async def run_maigret(username: str, max_sites: int = 500) -> dict:
    """
    Search for a username across platforms using Maigret CLI subprocess.
    Returns a structured dict with categorized results.
    """
    username = username.strip().lstrip("@").lstrip("u/")
    log.info("OSINT: Maigret search for '%s' (top %d sites)", username, max_sites)

    try:
        return await _run_maigret_subprocess(username, max_sites)
    except Exception as exc:
        log.error("Maigret search failed: %s", exc)
        return {
            "username": username,
            "total_found": 0,
            "total_checked": 0,
            "categories": {},
            "linked_accounts": [],
            "error": f"Maigret search failed: {exc}",
        }


async def _run_maigret_subprocess(username: str, max_sites: int) -> dict:
    """Run maigret CLI as a subprocess and parse the JSON output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "maigret", username,
            "--top-sites", str(max_sites),
            "--json", "simple",
            "--folderoutput", tmpdir,
            "--no-color",
            "--no-progressbar",
            "--no-autoupdate",
        ]

        log.info("Maigret subprocess: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if stderr:
            log.warning("Maigret stderr (last 1000 chars): %s",
                        stderr.decode(errors="replace")[-1000:])
        if stdout:
            log.info("Maigret stdout: %s",
                     stdout.decode(errors="replace")[-500:])

        expected_name = f"report_{username}_simple.json"
        json_files = [f for f in os.listdir(tmpdir) if f.endswith(".json")]

        if not json_files:
            raise FileNotFoundError(
                f"Maigret produced no JSON output (exit {proc.returncode})"
            )

        primary = expected_name if expected_name in json_files else json_files[0]
        log.info("Maigret output files: %s (using %s)", json_files, primary)

        with open(os.path.join(tmpdir, primary), encoding="utf-8") as fh:
            raw = json.load(fh)

        return _parse_maigret_json(raw, username)


# ──────────────────────────────────────────────
# Result parser
# ──────────────────────────────────────────────

def _parse_maigret_json(raw_json, username: str) -> dict:
    """
    Parse maigret --json simple output into ARIA's categorized format.

    The JSON is a dict keyed by site name. Each value has:
      url_user        — profile URL
      status.status   — "Claimed" / "Available" / etc.
      status.ids      — extracted profile data (fullname, bio, image, …)
      status.tags     — list of tag strings
      is_similar      — True for fuzzy/similar matches
    """
    if not isinstance(raw_json, dict):
        return _empty_result(username)

    categories: dict[str, list] = {}
    found_count = 0
    total_checked = len(raw_json)
    linked_accounts: list[dict] = []
    seen_alt_usernames: set[str] = set()

    for site_name, entry in raw_json.items():
        if not isinstance(entry, dict):
            continue

        status_obj = entry.get("status", {})
        if isinstance(status_obj, str):
            status_str = status_obj
            ids = {}
            tags = []
        elif isinstance(status_obj, dict):
            status_str = status_obj.get("status", "")
            ids = status_obj.get("ids", {}) or {}
            tags = status_obj.get("tags", []) or []
        else:
            continue

        if "Claimed" not in status_str:
            continue

        if entry.get("is_similar", False):
            continue

        found_count += 1
        url = entry.get("url_user", "")

        if not tags:
            site_def = entry.get("site", {})
            if isinstance(site_def, dict):
                tags = site_def.get("tags", []) or []

        category = _map_tags_to_category(tags)

        parsed_data = {}
        for field, keys in [
            ("display_name", ["fullname", "name", "display_name"]),
            ("bio", ["bio", "description", "about"]),
            ("avatar_url", ["image", "avatar", "avatar_url", "photo"]),
            ("location", ["location", "country", "city", "timezone"]),
        ]:
            for k in keys:
                val = ids.get(k)
                if val and str(val).strip() and str(val).strip().lower() != "true":
                    parsed_data[field] = str(val).strip()
                    break

        for k in ("follower_count", "followers"):
            val = ids.get(k)
            if val is not None:
                try:
                    parsed_data["followers"] = int(val)
                    break
                except (ValueError, TypeError):
                    pass

        categories.setdefault(category, []).append({
            "platform": status_obj.get("site_name", site_name),
            "url": url,
            "status": "Claimed",
            "tags": list(tags),
            "parsed_data": parsed_data if parsed_data else None,
        })

        alt_usernames = entry.get("ids_usernames", {}) or {}
        for alt_name, _ in alt_usernames.items():
            if alt_name.lower() != username.lower() and alt_name not in seen_alt_usernames:
                seen_alt_usernames.add(alt_name)
                linked_accounts.append({
                    "username": alt_name,
                    "source_platform": site_name,
                    "source_url": url,
                    "how_found": f"Found in {site_name} profile metadata",
                })

    for cat_list in categories.values():
        cat_list.sort(key=lambda p: p["platform"].lower())

    log.info("Maigret: '%s' found on %d / %d platforms", username, found_count, total_checked)

    from lead_scorer import score_maigret_results

    result = {
        "username": username,
        "total_found": found_count,
        "total_checked": total_checked,
        "categories": categories,
        "linked_accounts": linked_accounts,
    }
    return score_maigret_results(result)


def _empty_result(username: str) -> dict:
    return {
        "username": username,
        "total_found": 0,
        "total_checked": 0,
        "categories": {},
        "linked_accounts": [],
    }


def _map_tags_to_category(tags: list) -> str:
    """Map a list of maigret tags to an ARIA category key."""
    for tag in tags:
        mapped = CATEGORY_MAP.get(tag)
        if mapped:
            return mapped
    return "other"



# ──────────────────────────────────────────────
# Category helpers (for frontend/API consumers)
# ──────────────────────────────────────────────

def get_category_display_name(category_key: str) -> str:
    return CATEGORY_DISPLAY.get(category_key, category_key.replace("_", " ").title())


def get_category_order() -> list[str]:
    return list(CATEGORY_ORDER)


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

def save_maigret_search(conn, case_id: int, result: dict) -> int:
    """Save Maigret username search results to osint_lookups table."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM osint_lookups WHERE case_id = %s AND lookup_type = 'maigret' AND input_value = %s",
        (case_id, result["username"]),
    )
    result_json = json.dumps(result, ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO osint_lookups (case_id, lookup_type, input_value, result_json)
        VALUES (%s, 'maigret', %s, %s)
        RETURNING id
        """,
        (case_id, result["username"], result_json),
    )
    conn.commit()
    return cur.fetchone()["id"]


def save_breach_lookup(conn, case_id: int, result: BreachLookupResult) -> int:
    """Save breach lookup results to osint_lookups table."""
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM osint_lookups WHERE case_id = %s AND lookup_type = 'xposedornot' AND input_value = %s",
        (case_id, result.email),
    )
    result_json = json.dumps(result.to_dict(), ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO osint_lookups (case_id, lookup_type, input_value, result_json)
        VALUES (%s, 'xposedornot', %s, %s)
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

    p_user = sub.add_parser("username", help="Search username across platforms (Maigret)")
    p_user.add_argument("username")
    p_user.add_argument("--top", type=int, default=500, help="Top N sites to check")

    p_breach = sub.add_parser("breach", help="Check email in breaches (XposedOrNot)")
    p_breach.add_argument("email")

    args = parser.parse_args()

    if args.cmd == "username":
        result = asyncio.run(run_maigret(args.username, max_sites=args.top))
        print(f"\nUsername: {result['username']}")
        print(f"Checked: {result['total_checked']} platforms")
        print(f"Found on {result['total_found']} platforms:\n")
        for cat_key in CATEGORY_ORDER:
            platforms = result["categories"].get(cat_key, [])
            if not platforms:
                continue
            print(f"  {CATEGORY_DISPLAY[cat_key]} ({len(platforms)}):")
            for p in platforms:
                print(f"    [+] {p['platform']:20s}  {p['url']}")
        if result.get("error"):
            print(f"\nError: {result['error']}")

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
