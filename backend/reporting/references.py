"""
Generate stable, deduplicated reference labels for report evidence.
"""

from datetime import datetime


def build_references(case_data: dict) -> dict:
    """
    Build a reference register from case data.
    Returns:
        {
            "accounts": { account_id: "ACC-001", ... },
            "correlations": { correlation_id: "COR-001", ... },
            "insights": { insight_id: "INS-001", ... },
            "sources": [ { reference_id, url, title, source_type, ... }, ... ],
            "lookups": { lookup_id: "LOOK-001", ... },
        }
    """
    refs = {
        "accounts": {},
        "correlations": {},
        "insights": {},
        "sources": [],
        "lookups": {},
    }

    # ACC references
    for i, acct in enumerate(case_data["accounts"], 1):
        refs["accounts"][acct["id"]] = f"ACC-{i:03d}"

    # COR references
    for i, cor in enumerate(case_data["correlations"], 1):
        refs["correlations"][cor["id"]] = f"COR-{i:03d}"

    # INS references
    for i, ins in enumerate(case_data["insights"], 1):
        refs["insights"][ins["id"]] = f"INS-{i:03d}"

    # LOOK references + source extraction
    seen_urls = set()
    src_counter = 0

    for i, lookup in enumerate(case_data["lookups"], 1):
        refs["lookups"][lookup["id"]] = f"LOOK-{i:03d}"

        # Extract URLs from lookup results for source register
        urls = _extract_urls_from_lookup(lookup)
        for url_info in urls:
            if url_info["url"] in seen_urls:
                continue
            seen_urls.add(url_info["url"])
            src_counter += 1
            refs["sources"].append({
                "reference_id": f"SRC-{src_counter:03d}",
                "url": url_info["url"],
                "title": url_info.get("title", "Public source"),
                "source_type": url_info.get("source_type", "lookup_result"),
                "retrieved_at": _fmt_time(lookup.get("created_at")),
                "lookup_id": lookup["id"],
                "account_ids": url_info.get("account_ids", []),
            })

    # Profile URLs from collected accounts
    for acct in case_data["accounts"]:
        profile_url = _derive_profile_url(acct)
        if profile_url and profile_url not in seen_urls:
            seen_urls.add(profile_url)
            src_counter += 1
            refs["sources"].append({
                "reference_id": f"SRC-{src_counter:03d}",
                "url": profile_url,
                "title": f"{acct['platform']} profile: {acct['username']}",
                "source_type": "profile",
                "retrieved_at": _fmt_time(acct.get("created_at")),
                "lookup_id": None,
                "account_ids": [acct["id"]],
            })

    return refs


def _extract_urls_from_lookup(lookup: dict) -> list:
    """Extract source URLs from an OSINT lookup result."""
    urls = []
    result = lookup.get("result_json")
    if not result:
        return urls

    lookup_type = lookup.get("lookup_type", "")

    if lookup_type == "maigret":
        sites = result if isinstance(result, list) else result.get("sites", [])
        for site in sites[:50]:  # Cap to avoid huge lists
            url = site.get("url") or site.get("url_user")
            if url:
                urls.append({
                    "url": url,
                    "title": site.get("site_name", "Discovered profile"),
                    "source_type": "discovered_profile",
                })

    elif lookup_type == "dorking":
        results_list = result.get("results", [])
        for item in results_list[:30]:
            url = item.get("link") or item.get("url")
            if url:
                urls.append({
                    "url": url,
                    "title": item.get("title", "Search result"),
                    "source_type": "search_result",
                })

    elif lookup_type in ("hibp", "xposedornot"):
        # No direct URLs to extract
        pass

    return urls


def _derive_profile_url(account: dict) -> str | None:
    """Construct a canonical profile URL for a collected account."""
    platform = account.get("platform", "").lower()
    username = account.get("username", "")
    if not username:
        return None

    url_templates = {
        "reddit": f"https://www.reddit.com/user/{username}",
        "twitter": f"https://x.com/{username}",
        "github": f"https://github.com/{username}",
        "instagram": f"https://www.instagram.com/{username}",
    }
    return url_templates.get(platform)


def _fmt_time(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)
