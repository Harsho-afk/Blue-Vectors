"""
Deterministically derive report limitations from actual case conditions.
"""


def build_limitations(case_data: dict) -> list:
    """
    Generate limitations based on what data is missing or incomplete.
    Returns a list of limitation strings.
    """
    limitations = []
    accounts = case_data["accounts"]
    correlations = case_data["correlations"]
    lookups = case_data["lookups"]
    insights = case_data["insights"]
    posts_meta = case_data["posts_meta"]

    # Platform restrictions
    platforms_collected = {a["platform"] for a in accounts}
    limitations.append(
        "This report is based exclusively on publicly available information. "
        "Private, deleted, or access-restricted content was not accessible."
    )

    # Missing profile data
    accounts_missing_bio = [a for a in accounts if not a.get("bio")]
    accounts_missing_image = [a for a in accounts if not a.get("profile_image_url")]
    if accounts_missing_bio:
        limitations.append(
            f"{len(accounts_missing_bio)} account(s) had no biography available, "
            f"limiting bio-based correlation signals."
        )
    if accounts_missing_image:
        limitations.append(
            f"{len(accounts_missing_image)} account(s) had no profile image available, "
            f"limiting image-based similarity analysis."
        )

    # Small content samples
    low_post_accounts = []
    for acct in accounts:
        meta = posts_meta.get(acct["id"])
        if not meta or meta.get("post_count", 0) < 10:
            low_post_accounts.append(acct)
    if low_post_accounts:
        limitations.append(
            f"{len(low_post_accounts)} account(s) had fewer than 10 posts, "
            f"reducing reliability of temporal, stylometric, and content analysis."
        )

    # Unavailable correlation signals
    if correlations:
        all_unavailable = set()
        for cor in correlations:
            shap = cor.get("shap_json") or {}
            from .confidence import SIGNAL_LABELS, SHAP_KEY_MAP
            for signal_key in SIGNAL_LABELS:
                shap_key = SHAP_KEY_MAP.get(signal_key, signal_key)
                if shap.get(shap_key) is None and shap.get(signal_key) is None:
                    all_unavailable.add(signal_key)
        if all_unavailable:
            labels = [SIGNAL_LABELS[k] for k in all_unavailable]
            limitations.append(
                f"The following correlation signals were unavailable for one or more pairs: "
                f"{', '.join(labels)}. Weights were renormalized across available signals."
            )

    # Rate-limited or failed lookups
    failed_lookups = [
        lk for lk in lookups
        if not lk.get("result_json")
        or (isinstance(lk.get("result_json"), dict) and lk["result_json"].get("error"))
    ]
    if failed_lookups:
        types = set(lk["lookup_type"] for lk in failed_lookups)
        limitations.append(
            f"{len(failed_lookups)} OSINT lookup(s) returned errors or empty results "
            f"(types: {', '.join(sorted(types))}). Some leads may be missing."
        )

    # Search results disclaimer
    dorking_lookups = [lk for lk in lookups if lk.get("lookup_type") == "dorking"]
    if dorking_lookups:
        limitations.append(
            "Web search (dorking) results are subject to search engine indexing. "
            "Results may be incomplete, stale, or reflect cached content."
        )

    # Maigret discovery disclaimer
    maigret_lookups = [lk for lk in lookups if lk.get("lookup_type") == "maigret"]
    if maigret_lookups:
        limitations.append(
            "Username enumeration results indicate leads (username matches on platforms), "
            "not verified account ownership. False positives are common for non-distinctive usernames."
        )

    # Collection timestamp spread
    if len(accounts) > 1:
        timestamps = [a["created_at"] for a in accounts if a.get("created_at")]
        if len(timestamps) > 1:
            limitations.append(
                "Collection timestamps differ across sources. "
                "Account state may have changed between collection times."
            )

    # No correlation run
    if not correlations and len(accounts) >= 2:
        limitations.append(
            "Correlation analysis has not been run for this case. "
            "No identity-linkage conclusions can be drawn."
        )

    # Confidence disclaimer (always present)
    limitations.append(
        "Confidence scores are analytical estimates based on available signal convergence. "
        "They do not represent probabilities of identity, guilt, or account ownership."
    )

    return limitations
