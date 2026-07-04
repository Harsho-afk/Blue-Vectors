"""
ARIA — Tiered pairwise identity correlation engine.

Tier 1 (hard): bio cross-links, shared email/phone, Maigret linked_accounts
               -> confidence floor 80%
Tier 2 (conditional): username similarity x distinctiveness multiplier
Tier 3 (corroborating): bio cosine, temporal JSD, subreddit Jaccard,
                         char n-gram stylometry, geography agreement

evidence_type: "hard_link" (Tier 1 found) or "circumstantial_convergence"
"""

import json
import logging
import re
from itertools import combinations

from features import (
    username_similarity,
    bio_similarity,
    profile_image_similarity,
    temporal_similarity,
    community_overlap,
    stylometry_similarity,
)
from auth import get_db_conn

log = logging.getLogger("aria.correlator")

TIER1_FLOOR = 0.80

WEIGHTS = {
    "username": 0.22,
    "bio": 0.16,
    "profile_image": 0.15,
    "temporal": 0.13,
    "community": 0.12,
    "stylometry": 0.12,
    "geo": 0.10,
}

URL_RE = re.compile(r'https?://[^\s<>\'")\]]+', re.IGNORECASE)
HANDLE_RE = re.compile(r'(?:^|[\s(])@([A-Za-z0-9_.]{1,30})')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
TZ_CLAIM_RE = re.compile(r"UTC([+-]?\d+):00 to UTC([+-]?\d+):00")

PLATFORM_DOMAINS = {
    "twitter.com": "twitter", "x.com": "twitter",
    "instagram.com": "instagram", "github.com": "github",
    "reddit.com": "reddit", "linkedin.com": "linkedin",
    "facebook.com": "facebook", "t.me": "telegram",
    "youtube.com": "youtube", "tiktok.com": "tiktok",
    "twitch.tv": "twitch", "linktr.ee": "linktree",
    "threads.net": "threads", "bsky.app": "bluesky",
}


def _detect_platform(url: str) -> str | None:
    url_lower = url.lower()
    for domain, platform in PLATFORM_DOMAINS.items():
        if domain in url_lower:
            return platform
    return None


def _extract_handle_from_url(url: str) -> str | None:
    parts = url.rstrip("/").split("/")
    if len(parts) >= 4:
        candidate = parts[3].lstrip("@")
        if candidate and len(candidate) <= 30 and not candidate.startswith("?"):
            return candidate
    return None


# ── Tier 1: Hard link detection ──────────────────────────────────────────────

def _detect_hard_links(
    account_a: dict,
    account_b: dict,
    maigret_links: list[dict],
) -> list[str]:
    """Check for hard links between two specific accounts."""
    links: list[str] = []

    bio_a = (account_a.get("bio") or "").strip()
    bio_b = (account_b.get("bio") or "").strip()

    for bio, source_acc, target_acc in [
        (bio_a, account_a, account_b),
        (bio_b, account_b, account_a),
    ]:
        if not bio:
            continue

        target_platform = target_acc.get("platform", "").lower()
        target_user = target_acc.get("username", "").lower()

        for match in URL_RE.finditer(bio):
            url = match.group(0).rstrip(".,;:!?)")
            plat = _detect_platform(url)
            handle = _extract_handle_from_url(url)
            if (plat and handle
                    and plat == target_platform
                    and handle.lower() == target_user):
                src_label = f"{source_acc['platform']}:{source_acc['username']}"
                links.append(f"{src_label} bio links to {url}")

        for match in HANDLE_RE.finditer(bio):
            if match.group(1).lower() == target_user:
                src_label = f"{source_acc['platform']}:{source_acc['username']}"
                links.append(f"{src_label} bio mentions @{target_acc['username']}")

    emails_a = set(m.group(0).lower() for m in EMAIL_RE.finditer(bio_a))
    emails_b = set(m.group(0).lower() for m in EMAIL_RE.finditer(bio_b))
    for email in emails_a & emails_b:
        links.append(f"Shared email in bios: {email}")

    ua = account_a.get("username", "").lower()
    ub = account_b.get("username", "").lower()
    pa = account_a.get("platform", "").lower()
    pb = account_b.get("platform", "").lower()

    for ml in maigret_links:
        src = ml.get("source_username", "").lower()
        link_user = ml.get("linked_username", "").lower()
        link_plat = ml.get("linked_platform", "").lower()

        if src == ua and link_user == ub and link_plat == pb:
            links.append(f"Maigret: {account_a['username']} -> {account_b['username']} on {pb}")
        elif src == ub and link_user == ua and link_plat == pa:
            links.append(f"Maigret: {account_b['username']} -> {account_a['username']} on {pa}")

    return links


# ── Geography agreement ──────────────────────────────────────────────────────

def _check_geo_agreement(
    id_a: int,
    id_b: int,
    geo_insights: dict[int, list[tuple[int, int]]],
) -> float | None:
    """
    Check if two accounts' timezone estimates overlap.
    Returns 1.0 (overlap), 0.5 (adjacent), 0.0 (conflict), or None.
    """
    ranges_a = geo_insights.get(id_a)
    ranges_b = geo_insights.get(id_b)

    if not ranges_a or not ranges_b:
        return None

    best = 0.0
    for low_a, high_a in ranges_a:
        for low_b, high_b in ranges_b:
            if low_a <= high_b and low_b <= high_a:
                return 1.0
            gap = min(abs(low_a - high_b), abs(low_b - high_a))
            if gap <= 1:
                best = max(best, 0.5)
    return best


# ── Pre-fetch helpers ────────────────────────────────────────────────────────

def _load_maigret_links(conn, case_id: int) -> list[dict]:
    """Load Maigret linked_accounts into a flat list."""
    cur = conn.cursor()
    cur.execute(
        "SELECT input_value, result_json FROM osint_lookups "
        "WHERE case_id = %s AND lookup_type = 'maigret'",
        (case_id,),
    )
    links: list[dict] = []
    for row in cur.fetchall():
        raw = row["result_json"]
        if isinstance(raw, str):
            raw = json.loads(raw)

        src_user = raw.get("username", "")
        for la in raw.get("linked_accounts", []):
            links.append({
                "source_username": src_user,
                "linked_username": la.get("username", ""),
                "linked_platform": la.get("source_platform", ""),
            })
    return links


def _load_geo_insights(conn, case_id: int) -> dict[int, list[tuple[int, int]]]:
    """Load timezone insights keyed by account_id."""
    cur = conn.cursor()
    cur.execute(
        "SELECT account_id, claim FROM insights "
        "WHERE case_id = %s AND category = 'geography' AND account_id IS NOT NULL",
        (case_id,),
    )
    result: dict[int, list[tuple[int, int]]] = {}
    for row in cur.fetchall():
        m = TZ_CLAIM_RE.search(row["claim"])
        if not m:
            continue
        tz_range = (int(m.group(1)), int(m.group(2)))
        result.setdefault(row["account_id"], []).append(tz_range)
    return result


# ── Core pair correlation ────────────────────────────────────────────────────

def correlate_pair(
    account_a: dict,
    posts_a: list[dict],
    account_b: dict,
    posts_b: list[dict],
    maigret_links: list[dict],
    distinctiveness: dict[str, float],
    geo_insights: dict[int, list[tuple[int, int]]],
) -> dict:
    """Compare two accounts using the tiered scoring model."""

    # ── Tier 1: Hard links ──
    tier1_links = _detect_hard_links(account_a, account_b, maigret_links)
    has_hard_link = len(tier1_links) > 0

    # ── Tier 2: Username similarity x distinctiveness ──
    u_raw = username_similarity(
        account_a.get("username", ""),
        account_a.get("display_name"),
        account_b.get("username", ""),
        account_b.get("display_name"),
    )

    dist_a = distinctiveness.get(account_a.get("username", "").lower(), 0.5)
    dist_b = distinctiveness.get(account_b.get("username", "").lower(), 0.5)
    avg_dist = (dist_a + dist_b) / 2.0
    u_score = u_raw * avg_dist

    # ── Tier 3: Corroborating signals ──
    b_score = bio_similarity(
        account_a.get("bio"),
        account_b.get("bio"),
    )

    emb_a = account_a.get("image_embedding")
    emb_b = account_b.get("image_embedding")
    if isinstance(emb_a, str):
        emb_a = json.loads(emb_a)
    if isinstance(emb_b, str):
        emb_b = json.loads(emb_b)

    pi_score = profile_image_similarity(
        account_a.get("profile_image_url"),
        account_b.get("profile_image_url"),
        embedding_a=emb_a,
        embedding_b=emb_b,
    )

    t_score = temporal_similarity(posts_a, posts_b)
    c_score = community_overlap(posts_a, posts_b)
    s_score = stylometry_similarity(posts_a, posts_b)
    g_score = _check_geo_agreement(
        account_a["id"], account_b["id"], geo_insights,
    )

    # ── Weighted combination ──
    signals: dict[str, float | None] = {
        "username": round(u_score, 4),
        "bio": round(b_score, 4) if b_score is not None else None,
        "profile_image": round(pi_score, 4) if pi_score is not None else None,
        "temporal": round(t_score, 4) if t_score is not None else None,
        "community": round(c_score, 4) if c_score is not None else None,
        "stylometry": round(s_score, 4) if s_score is not None else None,
        "geo": round(g_score, 4) if g_score is not None else None,
    }

    available: dict[str, float] = {}
    notes: list[str] = []

    for key, weight in WEIGHTS.items():
        if signals[key] is not None:
            available[key] = weight
        else:
            notes.append(f"{key} score unavailable - excluded, weights renormalized")

    if not available:
        confidence = 0.0
    else:
        total_weight = sum(available.values())
        confidence = sum(
            (available[k] / total_weight) * signals[k]
            for k in available
        )

    if has_hard_link:
        if confidence < TIER1_FLOOR:
            notes.append(
                f"Hard link found - confidence raised from "
                f"{confidence*100:.1f}% to {TIER1_FLOOR*100:.0f}% floor"
            )
        confidence = max(confidence, TIER1_FLOOR)

    confidence = round(confidence, 4)
    confidence_pct = round(confidence * 100, 1)

    if confidence_pct <= 40:
        band = "Low"
    elif confidence_pct <= 70:
        band = "Medium"
    else:
        band = "High"

    evidence_type = "hard_link" if has_hard_link else "circumstantial_convergence"

    a_id = account_a["id"]
    b_id = account_b["id"]
    if a_id > b_id:
        a_id, b_id = b_id, a_id

    return {
        "account_a_id": a_id,
        "account_b_id": b_id,
        "account_a_platform": account_a.get("platform", ""),
        "account_a_username": account_a.get("username", ""),
        "account_b_platform": account_b.get("platform", ""),
        "account_b_username": account_b.get("username", ""),
        "username_score": signals["username"],
        "username_raw": round(u_raw, 4),
        "username_distinctiveness": round(avg_dist, 4),
        "bio_score": signals["bio"],
        "profile_image_score": signals["profile_image"],
        "temporal_score": signals["temporal"],
        "community_score": signals["community"],
        "stylometry_score": signals["stylometry"],
        "geo_agreement": signals["geo"],
        "confidence": confidence,
        "confidence_pct": confidence_pct,
        "band": band,
        "evidence_type": evidence_type,
        "tier1_links": tier1_links,
        "notes": notes,
    }


# ── Case-level orchestration ────────────────────────────────────────────────

def _build_shap_data(result: dict) -> dict:
    """Extract the subset of fields stored in shap_json."""
    return {
        "username_score": result["username_score"],
        "username_raw": result["username_raw"],
        "username_distinctiveness": result["username_distinctiveness"],
        "bio_score": result["bio_score"],
        "profile_image_score": result["profile_image_score"],
        "temporal_score": result["temporal_score"],
        "community_score": result["community_score"],
        "stylometry_score": result["stylometry_score"],
        "geo_agreement": result["geo_agreement"],
        "confidence": result["confidence"],
        "confidence_pct": result["confidence_pct"],
        "band": result["band"],
        "evidence_type": result["evidence_type"],
        "tier1_links": result["tier1_links"],
        "notes": result["notes"],
    }


def _load_accounts_and_posts(cur, case_id: int, account_ids: list[int] | None = None):
    """Load accounts and their posts. If account_ids given, load only those."""
    if account_ids:
        placeholders = ",".join(["%s"] * len(account_ids))
        cur.execute(
            f"SELECT id, case_id, platform, username, display_name, bio, location, profile_image_url, image_embedding "
            f"FROM accounts WHERE case_id = %s AND id IN ({placeholders})",
            (case_id, *account_ids),
        )
    else:
        cur.execute(
            "SELECT id, case_id, platform, username, display_name, bio, location, profile_image_url, image_embedding "
            "FROM accounts WHERE case_id = %s",
            (case_id,),
        )
    accounts = [dict(row) for row in cur.fetchall()]

    account_posts: dict[int, list[dict]] = {}
    for acc in accounts:
        cur.execute(
            "SELECT text, timestamp, metadata FROM posts WHERE account_id = %s",
            (acc["id"],),
        )
        posts = []
        for row in cur.fetchall():
            row_dict = dict(row)
            md = row_dict.get("metadata")
            if isinstance(md, str):
                try:
                    row_dict["metadata"] = json.loads(md)
                except (json.JSONDecodeError, TypeError):
                    row_dict["metadata"] = {}
            posts.append(row_dict)
        account_posts[acc["id"]] = posts

    return accounts, account_posts


def _upsert_result(cur, case_id: int, result: dict):
    """Insert or replace a single linkage result."""
    shap_data = _build_shap_data(result)
    cur.execute(
        "DELETE FROM linkage_results "
        "WHERE case_id = %s AND account_a_id = %s AND account_b_id = %s",
        (case_id, result["account_a_id"], result["account_b_id"]),
    )
    cur.execute(
        """
        INSERT INTO linkage_results
            (case_id, account_a_id, account_b_id, confidence, shap_json)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            case_id,
            result["account_a_id"],
            result["account_b_id"],
            result["confidence_pct"],
            json.dumps(shap_data),
        ),
    )


def correlate_case(case_id: int) -> list[dict]:
    """
    Run pairwise correlation on all accounts in a case.
    Deletes previous results and replaces them.
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        accounts, account_posts = _load_accounts_and_posts(cur, case_id)

        if len(accounts) < 2:
            log.info("Case %d has fewer than 2 accounts - nothing to correlate", case_id)
            return []

        maigret_links = _load_maigret_links(conn, case_id)
        geo_insights = _load_geo_insights(conn, case_id)

        try:
            from insights.distinctiveness import get_case_distinctiveness
            distinctiveness = get_case_distinctiveness(conn, case_id)
        except Exception:
            log.warning("Could not load distinctiveness scores, using defaults")
            distinctiveness = {}

        log.info(
            "Case %d: correlating %d accounts (%d pairs), %d Maigret links, %d geo insights",
            case_id, len(accounts), len(accounts) * (len(accounts) - 1) // 2,
            len(maigret_links), len(geo_insights),
        )

        cur.execute("DELETE FROM linkage_results WHERE case_id = %s", (case_id,))

        results = []
        for acc_a, acc_b in combinations(accounts, 2):
            result = correlate_pair(
                acc_a, account_posts.get(acc_a["id"], []),
                acc_b, account_posts.get(acc_b["id"], []),
                maigret_links, distinctiveness, geo_insights,
            )
            result["case_id"] = case_id
            _upsert_result(cur, case_id, result)
            results.append(result)

        conn.commit()
        log.info("Case %d: correlation complete - %d pairs scored", case_id, len(results))

    finally:
        conn.close()

    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


def correlate_single_pair(case_id: int, account_a_id: int, account_b_id: int) -> dict:
    """
    Run correlation on a specific pair of accounts.
    Replaces only that pair's existing result (if any).
    """
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        accounts, account_posts = _load_accounts_and_posts(
            cur, case_id, [account_a_id, account_b_id],
        )

        acc_map = {a["id"]: a for a in accounts}
        if account_a_id not in acc_map:
            raise ValueError(f"Account {account_a_id} not found in case {case_id}")
        if account_b_id not in acc_map:
            raise ValueError(f"Account {account_b_id} not found in case {case_id}")

        acc_a = acc_map[account_a_id]
        acc_b = acc_map[account_b_id]

        maigret_links = _load_maigret_links(conn, case_id)
        geo_insights = _load_geo_insights(conn, case_id)

        try:
            from insights.distinctiveness import get_case_distinctiveness
            distinctiveness = get_case_distinctiveness(conn, case_id)
        except Exception:
            distinctiveness = {}

        result = correlate_pair(
            acc_a, account_posts.get(acc_a["id"], []),
            acc_b, account_posts.get(acc_b["id"], []),
            maigret_links, distinctiveness, geo_insights,
        )
        result["case_id"] = case_id
        _upsert_result(cur, case_id, result)

        conn.commit()
        log.info(
            "Case %d: pair correlation %d↔%d complete — %.1f%%",
            case_id, account_a_id, account_b_id, result["confidence_pct"],
        )

    finally:
        conn.close()

    return result
