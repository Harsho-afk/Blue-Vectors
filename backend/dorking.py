"""
ARIA — Dorking Survey Agent

Given identifiers, generates safe public-web search queries, runs them via
DuckDuckGo, extracts entities from results, and scores each result as a lead.

Two query sources:
  1. Deterministic templates — safe, predictable, covers common patterns
  2. LLM query planner — Groq/Gemini generates creative queries for edge cases

The LLM is NOT the evidence source. It only suggests queries.
Evidence comes from actual search results with source URLs and timestamps.
"""

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import unquote

import httpx

log = logging.getLogger("aria.dorking")


# ── Regex patterns for entity extraction (borrowed from insights/cross_link) ──

URL_RE = re.compile(r'https?://[^\s<>\'")\]]+', re.IGNORECASE)
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
HANDLE_RE = re.compile(r'(?:^|[\s(])@([A-Za-z0-9_.]{1,30})')
PHONE_RE = re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}')

PLATFORM_DOMAINS = {
    "twitter.com": "twitter", "x.com": "twitter",
    "instagram.com": "instagram", "github.com": "github",
    "reddit.com": "reddit", "linkedin.com": "linkedin",
    "facebook.com": "facebook", "t.me": "telegram",
    "youtube.com": "youtube", "tiktok.com": "tiktok",
    "twitch.tv": "twitch", "discord.gg": "discord",
    "linktr.ee": "linktree", "mastodon.social": "mastodon",
    "threads.net": "threads", "bsky.app": "bluesky",
    "medium.com": "medium", "dev.to": "devto",
    "stackoverflow.com": "stackoverflow", "keybase.io": "keybase",
    "gitlab.com": "gitlab", "bitbucket.org": "bitbucket",
    "pinterest.com": "pinterest", "tumblr.com": "tumblr",
    "flickr.com": "flickr", "vimeo.com": "vimeo",
    "soundcloud.com": "soundcloud", "spotify.com": "spotify",
    "behance.net": "behance", "dribbble.com": "dribbble",
}

# ── Safety: blocked terms that must never appear in search queries ────────────

BLOCKED_TERMS = [
    "password", "passwd", "credential", "secret", "token",
    "dump", "leak", "exploit", "hack", "crack", "breach dump",
    "private key", "ssh key", "api key", "access key",
    "dark web", "darknet", "onion", "tor hidden",
    "bypass", "captcha", "scrape private",
    "dox", "doxx", "swat",
]


# ═════════════════════════════════════════════════════════════════════════════
# 1. DETERMINISTIC QUERY TEMPLATES
# ═════════════════════════════════════════════════════════════════════════════

def _templates_for_username(username: str) -> list[dict]:
    return [
        {"query": f'"{username}"', "purpose": "Exact username mentions across the web"},
        {"query": f'"{username}" site:github.com', "purpose": "GitHub profile or references"},
        {"query": f'"{username}" site:reddit.com', "purpose": "Reddit profile or posts"},
        {"query": f'"{username}" site:twitter.com OR site:x.com', "purpose": "Twitter/X references"},
        {"query": f'"{username}" site:instagram.com', "purpose": "Instagram references"},
        {"query": f'"{username}" site:linkedin.com', "purpose": "LinkedIn profile references"},
        {"query": f'"{username}" email', "purpose": "Pages associating username with an email"},
        {"query": f'"{username}" profile', "purpose": "Profile pages mentioning this username"},
        {"query": f'"{username}" blog OR portfolio OR website', "purpose": "Personal sites or blogs"},
        {"query": f'"{username}" forum OR community', "purpose": "Forum or community activity"},
    ]


def _templates_for_email(email: str) -> list[dict]:
    local_part = email.split("@")[0]
    domain = email.split("@")[1] if "@" in email else ""
    return [
        {"query": f'"{email}"', "purpose": "Exact email mentions across the web"},
        {"query": f'"{email}" profile', "purpose": "Profile pages listing this email"},
        {"query": f'"{email}" site:github.com', "purpose": "GitHub references to this email"},
        {"query": f'"{email}" site:reddit.com', "purpose": "Reddit references to this email"},
        {"query": f'"{local_part}" "{domain}" profile', "purpose": "Username + domain co-occurrence"},
        {"query": f'"{local_part}" site:github.com', "purpose": "Local part as username on GitHub"},
        {"query": f'"{email}" contact OR about', "purpose": "Contact/about pages listing this email"},
        {"query": f'"{local_part}" blog OR portfolio', "purpose": "Personal sites using this username part"},
    ]


def _templates_for_phone(phone: str) -> list[dict]:
    digits_only = re.sub(r'\D', '', phone)
    return [
        {"query": f'"{phone}"', "purpose": "Exact phone number mentions"},
        {"query": f'"{digits_only}"', "purpose": "Digits-only format mentions"},
        {"query": f'"{phone}" profile OR contact', "purpose": "Profile or contact pages"},
        {"query": f'"{phone}" whatsapp OR telegram', "purpose": "Messenger references"},
        {"query": f'"{digits_only}" site:facebook.com OR site:linkedin.com', "purpose": "Social media references"},
    ]


def _templates_for_profile_url(url: str) -> list[dict]:
    username = url.rstrip("/").split("/")[-1] if "/" in url else url
    return [
        {"query": f'"{url}"', "purpose": "Pages linking to this exact profile URL"},
        {"query": f'"{username}" profile', "purpose": "Username from URL on other platforms"},
        {"query": f'"{username}" site:github.com', "purpose": "GitHub references for this username"},
        {"query": f'"{username}" site:reddit.com', "purpose": "Reddit references for this username"},
        {"query": f'"{username}" email OR contact', "purpose": "Contact info associated with this user"},
        {"query": f'"{username}" blog OR portfolio OR website', "purpose": "Personal sites"},
    ]


def generate_deterministic_queries(identifier_type: str, value: str) -> list[dict]:
    generators = {
        "username": _templates_for_username,
        "email": _templates_for_email,
        "phone": _templates_for_phone,
        "profile_url": _templates_for_profile_url,
    }
    gen = generators.get(identifier_type)
    if not gen:
        return [{"query": f'"{value}"', "purpose": "Exact match search"}]
    return gen(value)


# ═════════════════════════════════════════════════════════════════════════════
# 2. LLM QUERY PLANNER
# ═════════════════════════════════════════════════════════════════════════════

_PLANNER_SYSTEM = """\
You are an OSINT search query planner. Given an identifier (username, email, phone, or URL), \
generate additional public-web search queries that an investigator would use to find \
related accounts, mentions, documents, and digital footprints.

RULES:
1. Generate 5-8 creative queries that go BEYOND obvious exact-match searches.
2. Think about variations: nicknames, partial matches, associated domains, platform-specific searches.
3. Each query must search only PUBLIC, indexed web pages.
4. NEVER generate queries that search for: passwords, credentials, private keys, exploits, dark web, breaches, dumps, or any private/illegal content.
5. Each query should have a clear investigative purpose.

Respond with ONLY valid JSON:
{
    "queries": [
        {
            "query": "the search query string",
            "purpose": "why this query is useful for the investigation"
        }
    ]
}
"""


def _build_planner_prompt(identifier_type: str, value: str, platform_hint: Optional[str] = None) -> str:
    context = f"Identifier type: {identifier_type}\nValue: {value}"
    if platform_hint:
        context += f"\nPlatform hint: {platform_hint}"
    if identifier_type == "email":
        local = value.split("@")[0]
        domain = value.split("@")[1] if "@" in value else ""
        context += f"\nLocal part: {local}\nDomain: {domain}"
    context += (
        "\n\nGenerate creative search queries to discover this person's digital footprint. "
        "Think about username variations, platform-specific searches, document/blog mentions, "
        "and cross-references that deterministic templates would miss."
    )
    return context


def _call_groq_planner(api_key: str, prompt: str) -> list[dict]:
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": _PLANNER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return parsed.get("queries", [])


def _call_gemini_planner(api_key: str, prompt: str) -> list[dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_PLANNER_SYSTEM,
            response_mime_type="application/json",
            temperature=0.4,
            max_output_tokens=1024,
        ),
    )
    parsed = json.loads(response.text)
    return parsed.get("queries", [])


def generate_llm_queries(
    identifier_type: str, value: str, platform_hint: Optional[str] = None,
) -> list[dict]:
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not groq_key and not gemini_key:
        log.warning("Dorking: no LLM API key — skipping AI query expansion")
        return []

    prompt = _build_planner_prompt(identifier_type, value, platform_hint)
    queries = []

    if groq_key:
        try:
            queries = _call_groq_planner(groq_key, prompt)
            log.info("Dorking: Groq generated %d queries", len(queries))
        except Exception as e:
            log.warning("Dorking: Groq planner failed: %s", e)
            if not gemini_key:
                return []

    if not queries and gemini_key:
        try:
            queries = _call_gemini_planner(gemini_key, prompt)
            log.info("Dorking: Gemini generated %d queries", len(queries))
        except Exception as e:
            log.warning("Dorking: Gemini planner failed: %s", e)
            return []

    return queries


# ═════════════════════════════════════════════════════════════════════════════
# 3. SAFETY FILTER
# ═════════════════════════════════════════════════════════════════════════════

def is_query_safe(query: str) -> bool:
    q_lower = query.lower()
    return not any(term in q_lower for term in BLOCKED_TERMS)


# ═════════════════════════════════════════════════════════════════════════════
# 4. SEARCH EXECUTION (Serper.dev — real Google results)
#
# Requires: SERPER_API_KEY in .env
# Free tier: 2,500 queries on signup.  https://serper.dev
# ═════════════════════════════════════════════════════════════════════════════

_SERPER_URL = "https://google.serper.dev/search"
_SEARCH_CONCURRENCY = max(
    1, int(os.environ.get("DORKING_SEARCH_CONCURRENCY", "4"))
)


def execute_search(query: str, max_results: int = 8) -> list[dict]:
    api_key = os.environ.get("SERPER_API_KEY", "").strip()

    if not api_key:
        log.error("Dorking: SERPER_API_KEY not set")
        return []

    try:
        resp = httpx.post(
            _SERPER_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json={"q": query, "num": min(max_results, 10)},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("Dorking: Serper search failed for query '%s': %s", query, exc)
        return []

    now = datetime.now(timezone.utc).isoformat()
    results = []

    for item in data.get("organic", []):
        if item.get("link"):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
                "source": "google",
                "query": query,
                "retrieved_at": now,
            })

    return results


# ═════════════════════════════════════════════════════════════════════════════
# 5. ENTITY EXTRACTION
# ═════════════════════════════════════════════════════════════════════════════

def _detect_platform(url: str) -> Optional[str]:
    url_lower = url.lower()
    for domain, platform in PLATFORM_DOMAINS.items():
        if domain in url_lower:
            return platform
    return None


def _extract_username_from_url(url: str) -> Optional[str]:
    parts = url.rstrip("/").split("/")
    if len(parts) >= 4:
        candidate = parts[3].lstrip("@")
        if candidate and len(candidate) <= 30 and not candidate.startswith("?"):
            return candidate
    return None


def extract_entities(results: list[dict]) -> list[dict]:
    entities = []
    seen = set()

    for r in results:
        text = f"{r.get('title', '')} {r.get('snippet', '')} {r.get('url', '')}"

        # Profile URLs
        url = r.get("url", "")
        platform = _detect_platform(url)
        if platform:
            username = _extract_username_from_url(url)
            key = f"profile:{platform}:{username or url}"
            if key not in seen:
                seen.add(key)
                entities.append({
                    "type": "profile_url",
                    "value": url,
                    "platform": platform,
                    "username": username,
                    "source_url": url,
                })

        # Emails in snippets/titles
        for m in EMAIL_RE.finditer(text):
            email = m.group(0)
            if email not in seen:
                seen.add(email)
                entities.append({
                    "type": "email",
                    "value": email,
                    "source_url": url,
                })

        # Handles in snippets/titles
        for m in HANDLE_RE.finditer(text):
            handle = m.group(1)
            if handle.lower() in ("gmail", "yahoo", "hotmail", "outlook"):
                continue
            hkey = f"handle:{handle}"
            if hkey not in seen:
                seen.add(hkey)
                entities.append({
                    "type": "handle",
                    "value": f"@{handle}",
                    "source_url": url,
                })

        # URLs in snippets (secondary profile links)
        for m in URL_RE.finditer(r.get("snippet", "")):
            found_url = m.group(0).rstrip(".,;:!?)")
            found_platform = _detect_platform(found_url)
            if found_platform:
                fuser = _extract_username_from_url(found_url)
                fkey = f"profile:{found_platform}:{fuser or found_url}"
                if fkey not in seen:
                    seen.add(fkey)
                    entities.append({
                        "type": "profile_url",
                        "value": found_url,
                        "platform": found_platform,
                        "username": fuser,
                        "source_url": url,
                    })

    return entities


# ═════════════════════════════════════════════════════════════════════════════
# 6. LEAD SCORING
# ═════════════════════════════════════════════════════════════════════════════

def score_result(
    result: dict,
    identifier_value: str,
    identifier_type: Optional[str] = None,
) -> dict:
    score = 0
    signals = []

    # Serper may return HTML entities in text and percent-encoded identifiers in
    # URLs (for example, user%40example.com). Decode before matching so the
    # score reflects what Google actually found.
    title = unescape(result.get("title", "")).casefold()
    snippet = unescape(result.get("snippet", "")).casefold()
    url = unquote(unescape(result.get("url", ""))).casefold()
    ident_lower = identifier_value.strip().casefold()

    title_match = bool(ident_lower and ident_lower in title)
    snippet_match = bool(ident_lower and ident_lower in snippet)
    url_match = bool(ident_lower and ident_lower in url)
    is_email = identifier_type == "email" or bool(EMAIL_RE.fullmatch(identifier_value.strip()))

    # An exact email on an indexed page is strong direct evidence. The old
    # additive weights gave a snippet-only exact match just 15/100 ("low").
    # Use the strongest occurrence as the evidence score, then add contextual
    # platform/profile support without double-counting repeated occurrences.
    if is_email and (title_match or snippet_match or url_match):
        evidence_scores = []
        if title_match:
            evidence_scores.append(65)
            signals.append("exact_match_in_title")
        if snippet_match:
            evidence_scores.append(60)
            signals.append("exact_match_in_snippet")
        if url_match:
            evidence_scores.append(70)
            signals.append("identifier_in_url")
        score = max(evidence_scores)
        signals.append("exact_email_match")
    else:
        if title_match:
            score += 25
            signals.append("exact_match_in_title")

        if snippet_match:
            score += 15
            signals.append("exact_match_in_snippet")

        if url_match:
            score += 20
            signals.append("identifier_in_url")

    platform = _detect_platform(url)
    if platform:
        score += 20
        signals.append(f"known_platform:{platform}")

    if any(kw in url for kw in ["/user/", "/profile/", "/u/", "/people/", "/@"]):
        score += 10
        signals.append("profile_url_pattern")

    if not signals:
        score = 5
        signals.append("weak_mention")

    score = min(score, 100)

    if score >= 60:
        band = "high"
    elif score >= 30:
        band = "medium"
    else:
        band = "low"

    return {
        **result,
        "lead_score": score,
        "lead_band": band,
        "signals": signals,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 7. MAIN ORCHESTRATOR
# ═════════════════════════════════════════════════════════════════════════════

def run_dorking(
    identifier_type: str,
    value: str,
    platform_hint: Optional[str] = None,
    use_llm: bool = True,
) -> dict:
    """
    Run the full dorking survey for a single identifier.

    Returns a dict with:
      - queries_executed: list of {query, purpose, source, result_count}
      - results: list of scored search results
      - entities: list of extracted entities
      - summary: {total_queries, total_results, high_leads, medium_leads, low_leads}
    """
    log.info("Dorking: starting survey for %s = '%s'", identifier_type, value)

    # Step 1: Generate queries
    deterministic = generate_deterministic_queries(identifier_type, value)
    for q in deterministic:
        q["source"] = "template"

    llm_queries = []
    if use_llm:
        raw_llm = generate_llm_queries(identifier_type, value, platform_hint)
        for q in raw_llm:
            q["source"] = "llm"
        llm_queries = raw_llm

    all_queries = deterministic + llm_queries

    # Step 2: Safety filter
    safe_queries = []
    blocked_count = 0
    for q in all_queries:
        if is_query_safe(q["query"]):
            safe_queries.append(q)
        else:
            blocked_count += 1
            log.warning("Dorking: blocked unsafe query: '%s'", q["query"])

    log.info(
        "Dorking: %d queries (%d template, %d LLM, %d blocked)",
        len(safe_queries), len(deterministic), len(llm_queries), blocked_count,
    )

    # Step 3: Execute searches
    all_results = []
    seen_urls = set()
    queries_executed = []

    # Serper queries are independent network calls. Execute a small bounded
    # batch concurrently; executor.map preserves query order, keeping output
    # and URL deduplication deterministic for the UI and saved evidence.
    with ThreadPoolExecutor(
        max_workers=min(_SEARCH_CONCURRENCY, len(safe_queries) or 1)
    ) as executor:
        search_results = executor.map(
            lambda q: execute_search(q["query"], max_results=8),
            safe_queries,
        )

        for q, results in zip(safe_queries, search_results):

            # Deduplicate by URL
            deduped = []
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    deduped.append(r)

            queries_executed.append({
                "query": q["query"],
                "purpose": q.get("purpose", ""),
                "source": q.get("source", "template"),
                "result_count": len(deduped),
            })

            all_results.extend(deduped)

    # Step 4: Score results
    scored = [score_result(r, value, identifier_type) for r in all_results]
    scored.sort(key=lambda x: x["lead_score"], reverse=True)

    # Step 5: Extract entities
    entities = extract_entities(all_results)

    # Step 6: Build summary
    high = sum(1 for r in scored if r["lead_band"] == "high")
    medium = sum(1 for r in scored if r["lead_band"] == "medium")
    low = sum(1 for r in scored if r["lead_band"] == "low")

    summary = {
        "total_queries": len(safe_queries),
        "template_queries": len(deterministic),
        "llm_queries": len(llm_queries),
        "blocked_queries": blocked_count,
        "total_results": len(scored),
        "high_leads": high,
        "medium_leads": medium,
        "low_leads": low,
        "entities_found": len(entities),
    }

    log.info(
        "Dorking: complete — %d results (%d high, %d medium, %d low), %d entities",
        len(scored), high, medium, low, len(entities),
    )

    return {
        "identifier_type": identifier_type,
        "identifier_value": value,
        "queries_executed": queries_executed,
        "results": scored,
        "entities": entities,
        "summary": summary,
    }
