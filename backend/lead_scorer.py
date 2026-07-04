"""
ARIA — Maigret Lead Scorer

Scores each Maigret platform hit to separate strong leads from noise.
Each platform gets a 0-100 lead score and a confidence band.

Signals:
  +0-20  username distinctiveness (rare username = higher score)
  +15    platform has a deep collector (github, reddit, twitter, instagram)
  +12    display name found in profile
  +15    bio text available
  +10    profile image / avatar found
  +5     location data present
  +5     follower count > 0
  +10    linked accounts discovered from this platform
  +5     high-value platform category
  -15    platform known for weak username validation
  -10    no parsed metadata at all
"""

import logging

log = logging.getLogger("aria.lead_scorer")

DEEP_COLLECTABLE = {"reddit", "twitter", "github", "instagram", "x"}

WEAK_PLATFORMS = {
    "pinterest", "chess.com", "fiverr", "shutterstock", "ask.fm",
    "buzzfeed", "issuu", "slides", "myspace", "about.me",
    "slideshare", "last.fm", "4pda", "hubpages", "metacritic",
}

HIGH_VALUE_TAGS = {"social", "coding", "microblogging", "hacking", "career"}


def score_lead(
    platform_entry: dict,
    username: str,
    total_found: int,
    total_checked: int,
    linked_platforms: set,
) -> dict:
    score = 0
    reasons = []
    platform_name = platform_entry.get("platform", "").lower()
    parsed = platform_entry.get("parsed_data") or {}

    if total_checked > 0:
        distinctiveness = 1.0 - (total_found / total_checked)
        dist_points = int(distinctiveness * 20)
        score += dist_points
        if distinctiveness >= 0.9:
            reasons.append("Rare username")
        elif distinctiveness < 0.6:
            reasons.append("Common username")

    if platform_name in DEEP_COLLECTABLE:
        score += 15
        reasons.append("Deep collection available")

    if parsed.get("display_name"):
        score += 12
        reasons.append("Display name found")
    if parsed.get("bio"):
        score += 15
        reasons.append("Bio available")
    if parsed.get("avatar_url"):
        score += 10
        reasons.append("Profile image found")
    if parsed.get("location"):
        score += 5
        reasons.append("Location data")
    if parsed.get("followers") and int(parsed["followers"]) > 0:
        score += 5
        reasons.append(f"{parsed['followers']} followers")

    if platform_name in linked_platforms:
        score += 10
        reasons.append("Linked accounts discovered")

    tags = platform_entry.get("tags", [])
    if any(t in HIGH_VALUE_TAGS for t in tags):
        score += 5
        reasons.append("High-value category")

    if platform_name in WEAK_PLATFORMS:
        score -= 15
        reasons.append("Weak-validation platform")

    if not parsed:
        score -= 10
        reasons.append("No profile metadata")

    score = max(0, min(100, score))

    if score >= 65:
        band = "high"
    elif score >= 35:
        band = "medium"
    elif score >= 15:
        band = "low"
    else:
        band = "noise"

    return {
        "lead_score": score,
        "lead_band": band,
        "lead_reasons": reasons,
    }


def score_maigret_results(maigret_result: dict) -> dict:
    """
    Enrich a Maigret result dict by scoring all platform entries.
    Adds lead_score, lead_band, lead_reasons to each platform entry
    and a top-level lead_summary with counts per band.
    Mutates and returns the same dict.
    """
    total_found = maigret_result.get("total_found", 0)
    total_checked = maigret_result.get("total_checked", 0)
    username = maigret_result.get("username", "")

    linked_platforms: set = set()
    for la in maigret_result.get("linked_accounts", []):
        linked_platforms.add(la.get("source_platform", "").lower())

    summary = {"high": 0, "medium": 0, "low": 0, "noise": 0}

    for platforms in maigret_result.get("categories", {}).values():
        for entry in platforms:
            scores = score_lead(
                entry, username, total_found, total_checked, linked_platforms,
            )
            entry.update(scores)
            summary[scores["lead_band"]] += 1

    maigret_result["lead_summary"] = summary

    log.info(
        "Lead scoring for '%s': %d high, %d medium, %d low, %d noise",
        username, summary["high"], summary["medium"],
        summary["low"], summary["noise"],
    )
    return maigret_result
