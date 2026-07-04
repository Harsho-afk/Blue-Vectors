"""
Convert stored correlation scores into explanatory confidence notes.
"""

BAND_DEFINITIONS = {
    "High": "Strong evidence convergence or an explainable hard link",
    "Medium": "Multiple supporting indicators with meaningful uncertainty",
    "Low": "Weak, incomplete, or largely circumstantial evidence",
}

SIGNAL_LABELS = {
    "username": "Username similarity",
    "bio": "Biography/bio similarity",
    "profile_image": "Profile image similarity",
    "temporal": "Temporal posting pattern",
    "community": "Community/subreddit overlap",
    "stylometry": "Writing style (stylometry)",
    "geo": "Geographic agreement",
}

# Maps our canonical signal keys to the actual keys stored in shap_json
SHAP_KEY_MAP = {
    "username": "username_score",
    "bio": "bio_score",
    "profile_image": "profile_image_score",
    "temporal": "temporal_score",
    "community": "community_score",
    "stylometry": "stylometry_score",
    "geo": "geo_agreement",
}


def build_confidence_notes(correlations: list, references: dict) -> list:
    """
    For each correlation, produce an explanatory confidence section.
    """
    notes = []
    account_refs = references["accounts"]
    cor_refs = references["correlations"]

    for cor in correlations:
        shap = cor.get("shap_json") or {}
        confidence_pct = shap.get("confidence_pct", cor.get("confidence", 0))
        band = shap.get("band", _derive_band(confidence_pct))
        evidence_type = shap.get("evidence_type", "circumstantial_convergence")

        # Separate available vs unavailable signals
        signals_available = []
        signals_unavailable = []

        for signal_key, label in SIGNAL_LABELS.items():
            shap_key = SHAP_KEY_MAP.get(signal_key, signal_key)
            score = shap.get(shap_key)
            if score is None:
                score = shap.get(signal_key)
            if score is not None:
                signals_available.append({
                    "signal": signal_key,
                    "label": label,
                    "score": round(score, 3),
                })
            else:
                signals_unavailable.append({
                    "signal": signal_key,
                    "label": label,
                })

        # Renormalization note
        total_available = len(signals_available)
        total_signals = len(SIGNAL_LABELS)
        renorm_note = None
        if total_available < total_signals:
            renorm_note = (
                f"Weights renormalized across {total_available}/{total_signals} "
                f"available signals. {total_signals - total_available} signal(s) "
                f"were unavailable and excluded from scoring."
            )

        # Hard link details
        tier1_links = shap.get("tier1_links", [])

        # Calibrated conclusion
        conclusion = _build_conclusion(
            band, confidence_pct, evidence_type,
            signals_available, signals_unavailable
        )

        notes.append({
            "correlation_ref": cor_refs.get(cor["id"], f"COR-{cor['id']}"),
            "account_a_ref": account_refs.get(cor["account_a_id"], f"ACC-{cor['account_a_id']}"),
            "account_b_ref": account_refs.get(cor["account_b_id"], f"ACC-{cor['account_b_id']}"),
            "confidence_pct": round(confidence_pct, 1),
            "band": band,
            "band_definition": BAND_DEFINITIONS.get(band, ""),
            "evidence_type": evidence_type,
            "signals_available": signals_available,
            "signals_unavailable": signals_unavailable,
            "renormalization_note": renorm_note,
            "tier1_links": tier1_links,
            "conclusion": conclusion,
            "notes": shap.get("notes", ""),
        })

    return notes


def _derive_band(confidence_pct: float) -> str:
    if confidence_pct >= 70:
        return "High"
    elif confidence_pct >= 40:
        return "Medium"
    return "Low"


def _build_conclusion(
    band: str,
    confidence_pct: float,
    evidence_type: str,
    signals_available: list,
    signals_unavailable: list,
) -> str:
    """Generate a calibrated natural-language conclusion."""
    strength = {
        "High": "strong",
        "Medium": "moderate",
        "Low": "weak",
    }.get(band, "limited")

    if evidence_type == "hard_link":
        basis = "A direct link was identified between these accounts"
    else:
        top_signals = sorted(signals_available, key=lambda s: s["score"], reverse=True)[:3]
        signal_names = [s["label"].lower() for s in top_signals]
        if signal_names:
            basis = f"{', '.join(signal_names[:-1])} and {signal_names[-1]} support the relationship" if len(signal_names) > 1 else f"{signal_names[0]} supports the relationship"
        else:
            basis = "Limited evidence is available"

    unavail_note = ""
    if signals_unavailable:
        unavail_names = [s["label"].lower() for s in signals_unavailable[:3]]
        unavail_note = f", but {' and '.join(unavail_names)} evidence was unavailable"

    qualifier = {
        "High": "This result indicates a likely association",
        "Medium": "This result suggests a possible association",
        "Low": "This result provides only tentative indication",
    }.get(band, "This result is inconclusive")

    return (
        f"{band}-confidence association ({confidence_pct:.0f}%). "
        f"{basis}{unavail_note}. "
        f"{qualifier} and does not establish common ownership."
    )
