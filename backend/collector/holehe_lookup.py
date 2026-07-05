"""
Email-to-account discovery using Holehe.

Holehe checks 100+ websites to see if an email is registered
(via password reset / signup endpoint probing). This is the
email equivalent of Maigret for usernames.

Holehe uses trio internally, so we run it in a thread to stay
compatible with our asyncio-based backend.
"""

import trio
import httpx
import logging

log = logging.getLogger("aria.collector")


def _run_holehe_sync(email: str, timeout: int = 10) -> list[dict]:
    """Run holehe synchronously (trio event loop). Returns the raw results list."""
    from holehe.core import import_submodules, get_functions, launch_module

    modules = import_submodules("holehe.modules")
    websites = get_functions(modules)

    out: list = []

    async def _run():
        client = httpx.AsyncClient(timeout=timeout)
        try:
            async with trio.open_nursery() as nursery:
                for website in websites:
                    nursery.start_soon(launch_module, website, email, client, out)
        finally:
            await client.aclose()

    trio.run(_run)
    return sorted(out, key=lambda i: i.get("name", ""))


def holehe_search(email: str, timeout: int = 10) -> dict:
    """
    Run Holehe and return structured results.

    Returns:
        {
            "email": "...",
            "total_checked": N,
            "total_found": N,
            "sites": [
                {"name": "...", "domain": "...", "exists": True, "emailrecovery": "...", "phoneNumber": "..."},
                ...
            ]
        }
    """
    email = email.strip().lower()
    log.info("Holehe: checking email %s across 100+ sites", email)

    try:
        raw = _run_holehe_sync(email, timeout=timeout)
    except Exception as exc:
        log.error("Holehe search failed: %s", exc)
        return {
            "email": email,
            "total_checked": 0,
            "total_found": 0,
            "sites": [],
            "error": str(exc),
        }

    found = []
    for entry in raw:
        if entry.get("exists"):
            domain = entry.get("domain", "")
            found.append({
                "name": entry.get("name", ""),
                "domain": domain,
                "url": f"https://{domain}" if domain else None,
                "method": entry.get("method"),
                "exists": True,
                "emailrecovery": entry.get("emailrecovery"),
                "phoneNumber": entry.get("phoneNumber"),
            })

    log.info(
        "Holehe: %s — checked %d sites, found on %d",
        email, len(raw), len(found),
    )

    return {
        "email": email,
        "total_checked": len(raw),
        "total_found": len(found),
        "sites": found,
    }
