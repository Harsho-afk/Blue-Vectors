"""
ARIA — Deterministic SOCMINT Report Builder.

Assembles a versioned report JSON from stored case data.
No external lookups, no LLM calls for structure — only deterministic assembly.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from .collector import load_case_data
from .references import build_references
from .confidence import build_confidence_notes, BAND_DEFINITIONS
from .limitations import build_limitations

log = logging.getLogger("aria.reporting")

METHODOLOGY_VERSION = "1.0"


def generate_report(case_id: int, user_id: int) -> dict:
    """
    Generate a complete SOCMINT report for a case.
    Returns the full report_json structure ready for storage.
    Raises ValueError if case not found or not owned by user.
    """
    case_data = load_case_data(case_id, user_id)
    if case_data is None:
        raise ValueError("Case not found or access denied")

    references = build_references(case_data)
    confidence_notes = build_confidence_notes(case_data["correlations"], references)
    limitations = build_limitations(case_data)

    now = datetime.now(timezone.utc).isoformat()

    report = {
        "report_metadata": _build_metadata(case_data, now),
        "quick_overview": _build_quick_overview(case_data, references),
        "scope_and_methodology": _build_scope(case_data),
        "executive_summary": _build_executive_summary(case_data, references),
        "identified_accounts": _build_accounts_section(case_data, references),
        "correlation_findings": _build_correlations_section(
            case_data, references, confidence_notes
        ),
        "open_source_references": references["sources"],
        "analytical_insights": _build_insights_section(case_data, references),
        "limitations": limitations,
        "confidence_notes": {
            "band_definitions": BAND_DEFINITIONS,
            "per_pair": confidence_notes,
            "disclaimer": (
                "Correlation does not prove common ownership. "
                "All findings represent analytical assessments of publicly "
                "available data convergence."
            ),
        },
        "intelligence_briefing": _build_intelligence_section(case_data),
        "appendix": _build_appendix(case_data, references, now),
    }

    return report


def compute_content_hash(report_json: dict) -> str:
    """SHA-256 of the canonical JSON for deduplication."""
    canonical = json.dumps(report_json, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def check_readiness(case_data: dict) -> list:
    """
    Return a list of readiness warnings (not hard failures).
    """
    warnings = []
    if not case_data["accounts"]:
        warnings.append("No accounts have been collected.")
    if not case_data["correlations"] and len(case_data["accounts"]) >= 2:
        warnings.append("Correlation has not been run.")
    if not case_data["insights"]:
        warnings.append("No analytical insights available.")
    if not case_data["lookups"]:
        warnings.append("No OSINT lookups have been performed.")
    if not case_data["intelligence"]:
        warnings.append("Intelligence briefing has not been generated.")
    return warnings


# ── Section builders ─────────────────────────────────────────────────────────


def _build_metadata(case_data: dict, generated_at: str) -> dict:
    case = case_data["case"]
    return {
        "case_id": case["id"],
        "case_title": case["title"],
        "case_status": case.get("status", "open"),
        "investigator": case.get("investigator_name", "Unknown"),
        "generated_at": generated_at,
        "methodology_version": METHODOLOGY_VERSION,
    }


def _build_scope(case_data: dict) -> dict:
    identifiers = case_data["identifiers"]
    lookups = case_data["lookups"]

    seed_summary = []
    for ident in identifiers:
        seed_summary.append({
            "type": ident["identifier_type"],
            "value": ident["value"],
            "platform_hint": ident.get("platform_hint"),
        })

    collection_methods = sorted(set(lk["lookup_type"] for lk in lookups))
    platforms_collected = sorted(set(a["platform"] for a in case_data["accounts"]))

    # Collection window
    all_timestamps = []
    for lk in lookups:
        if lk.get("created_at"):
            all_timestamps.append(lk["created_at"])
    for a in case_data["accounts"]:
        if a.get("created_at"):
            all_timestamps.append(a["created_at"])

    window = None
    if all_timestamps:
        ts_strings = [str(t) for t in all_timestamps]
        window = {"earliest": min(ts_strings), "latest": max(ts_strings)}

    return {
        "seed_identifiers": seed_summary,
        "collection_methods": collection_methods,
        "platforms_collected": platforms_collected,
        "collection_window": window,
        "public_source_statement": (
            "All data in this report was obtained from publicly accessible sources. "
            "No private accounts were accessed, no terms of service were violated, "
            "and no unauthorized access was performed."
        ),
    }


def _build_executive_summary(case_data: dict, references: dict) -> dict:
    accounts = case_data["accounts"]
    correlations = case_data["correlations"]
    insights = case_data["insights"]

    # Count by band
    band_counts = {"High": 0, "Medium": 0, "Low": 0}
    for cor in correlations:
        shap = cor.get("shap_json") or {}
        band = shap.get("band", "Low")
        band_counts[band] = band_counts.get(band, 0) + 1

    # Count insights by category
    insight_categories = {}
    for ins in insights:
        cat = ins.get("category", "unknown")
        insight_categories[cat] = insight_categories.get(cat, 0) + 1

    key_takeaways = []
    if accounts:
        platform_names = sorted(set(a["platform"] for a in accounts))
        key_takeaways.append(
            f"{len(accounts)} accounts were collected across {len(platform_names)} platforms."
        )
    else:
        key_takeaways.append("No accounts were collected for this case yet.")

    if correlations:
        high_count = band_counts.get("High", 0)
        medium_count = band_counts.get("Medium", 0)
        low_count = band_counts.get("Low", 0)
        key_takeaways.append(
            f"Correlation results are led by {high_count} high, {medium_count} medium, and {low_count} low confidence links."
        )
    else:
        key_takeaways.append("No correlations are available yet.")

    if insights:
        top_category = max(insight_categories.items(), key=lambda item: item[1])[0]
        key_takeaways.append(
            f"The strongest insight activity appears in the {top_category.replace('_', ' ')} category."
        )
    else:
        key_takeaways.append("No analytical insights are available yet.")

    return {
        "total_accounts_collected": len(accounts),
        "total_platforms": len(set(a["platform"] for a in accounts)),
        "total_correlations": len(correlations),
        "correlation_bands": band_counts,
        "total_insights": len(insights),
        "insight_categories": insight_categories,
        "total_sources": len(references["sources"]),
        "total_lookups": len(case_data["lookups"]),
        "key_takeaways": key_takeaways,
    }


def _build_quick_overview(case_data: dict, references: dict) -> dict:
    summary = _build_executive_summary(case_data, references)
    band_counts = summary.get("correlation_bands", {})
    total_correlations = max(summary.get("total_correlations", 0), 1)

    return {
        "headline": "At a glance summary for fast reading.",
        "bullet_points": summary.get("key_takeaways", []),
        "metrics": [
            {
                "label": "Accounts",
                "value": summary.get("total_accounts_collected", 0),
                "detail": f"Across {summary.get('total_platforms', 0)} platforms",
            },
            {
                "label": "Correlations",
                "value": summary.get("total_correlations", 0),
                "detail": "Links found between collected accounts",
            },
            {
                "label": "Sources",
                "value": summary.get("total_sources", 0),
                "detail": "Open-source references used",
            },
        ],
        "confidence_breakdown": [
            {
                "label": "High",
                "count": band_counts.get("High", 0),
                "percent": round((band_counts.get("High", 0) / total_correlations) * 100, 1),
            },
            {
                "label": "Medium",
                "count": band_counts.get("Medium", 0),
                "percent": round((band_counts.get("Medium", 0) / total_correlations) * 100, 1),
            },
            {
                "label": "Low",
                "count": band_counts.get("Low", 0),
                "percent": round((band_counts.get("Low", 0) / total_correlations) * 100, 1),
            },
        ],
        "priority_flags": [
            "High-confidence items should be reviewed first.",
            "Low-confidence items need supporting evidence before being treated as meaningful.",
            "Every conclusion remains an analytical assessment, not proof of identity.",
        ] if case_data.get("correlations") else [
            "Run collection and correlation to populate the report with evidence-backed findings.",
        ],
    }


def _build_accounts_section(case_data: dict, references: dict) -> dict:
    accounts = case_data["accounts"]
    lookups = case_data["lookups"]
    posts_meta = case_data["posts_meta"]
    account_refs = references["accounts"]

    # Collected accounts
    collected = []
    for acct in accounts:
        meta = posts_meta.get(acct["id"], {})
        collected.append({
            "reference_id": account_refs.get(acct["id"]),
            "platform": acct["platform"],
            "username": acct["username"],
            "display_name": acct.get("display_name"),
            "profile_url": _derive_profile_url(acct),
            "bio_excerpt": (acct.get("bio") or "")[:200] or None,
            "location": acct.get("location"),
            "follower_count": acct.get("follower_count"),
            "following_count": acct.get("following_count"),
            "post_count": meta.get("post_count", 0),
            "earliest_post": str(meta["earliest_post"]) if meta.get("earliest_post") else None,
            "latest_post": str(meta["latest_post"]) if meta.get("latest_post") else None,
            "collection_status": "collected",
        })

    # Discovered leads (from Maigret results not yet collected)
    collected_keys = {(a["platform"], a["username"].lower()) for a in accounts}
    discovered = []
    for lk in lookups:
        if lk["lookup_type"] != "maigret":
            continue
        result = lk.get("result_json")
        if not result:
            continue
        sites = result if isinstance(result, list) else result.get("sites", [])
        for site in sites:
            platform = (site.get("platform") or site.get("site_name", "")).lower()
            username = (site.get("username") or "").lower()
            if not platform or not username:
                continue
            if (platform, username) not in collected_keys:
                discovered.append({
                    "platform": site.get("site_name") or platform,
                    "username": site.get("username", ""),
                    "url": site.get("url") or site.get("url_user"),
                    "status": "discovered_lead",
                    "source_lookup": references["lookups"].get(lk["id"]),
                })

    return {
        "collected_accounts": collected,
        "discovered_leads": discovered[:50],  # Cap for report size
        "total_collected": len(collected),
        "total_leads": len(discovered),
    }


def _build_correlations_section(
    case_data: dict, references: dict, confidence_notes: list
) -> list:
    correlations = case_data["correlations"]
    accounts_by_id = {a["id"]: a for a in case_data["accounts"]}
    account_refs = references["accounts"]
    cor_refs = references["correlations"]

    results = []
    for i, cor in enumerate(correlations):
        acct_a = accounts_by_id.get(cor["account_a_id"], {})
        acct_b = accounts_by_id.get(cor["account_b_id"], {})
        shap = cor.get("shap_json") or {}
        note = confidence_notes[i] if i < len(confidence_notes) else {}

        results.append({
            "reference_id": cor_refs.get(cor["id"]),
            "account_a": {
                "ref": account_refs.get(cor["account_a_id"]),
                "platform": acct_a.get("platform"),
                "username": acct_a.get("username"),
            },
            "account_b": {
                "ref": account_refs.get(cor["account_b_id"]),
                "platform": acct_b.get("platform"),
                "username": acct_b.get("username"),
            },
            "confidence_pct": note.get("confidence_pct", cor.get("confidence", 0)),
            "band": note.get("band", "Low"),
            "evidence_type": note.get("evidence_type", "circumstantial_convergence"),
            "signals": note.get("signals_available", []),
            "signals_unavailable": note.get("signals_unavailable", []),
            "tier1_links": note.get("tier1_links", []),
            "conclusion": note.get("conclusion", ""),
            "renormalization_note": note.get("renormalization_note"),
        })

    return results


def _build_insights_section(case_data: dict, references: dict) -> dict:
    insights = case_data["insights"]
    accounts_by_id = {a["id"]: a for a in case_data["accounts"]}
    insight_refs = references["insights"]
    account_refs = references["accounts"]

    by_category = {}
    for ins in insights:
        cat = ins.get("category", "unknown")
        if cat not in by_category:
            by_category[cat] = []

        entry = {
            "reference_id": insight_refs.get(ins["id"]),
            "claim": ins["claim"],
            "confidence": ins["confidence"],
            "evidence_summary": _summarize_evidence(ins.get("evidence")),
        }
        if ins.get("account_id"):
            acct = accounts_by_id.get(ins["account_id"])
            entry["account_ref"] = account_refs.get(ins["account_id"])
            if acct:
                entry["account_label"] = f"{acct['platform']}/{acct['username']}"

        by_category[cat].append(entry)

    return by_category


def _build_intelligence_section(case_data: dict) -> dict | None:
    """Include the AI-generated briefing as an optional, clearly-labeled section."""
    intel = case_data.get("intelligence")
    if not intel:
        return None

    return {
        "label": intel.get("label", "AI-synthesized, citation-linked"),
        "narrative": intel.get("narrative", ""),
        "claims": intel.get("claims", []),
        "generated_at": str(intel.get("created_at", "")),
        "disclaimer": (
            "This narrative was generated by an AI language model and is provided "
            "as a supplementary analytical aid. All factual claims cite specific "
            "insight IDs. The investigator should independently verify conclusions."
        ),
    }


def _build_appendix(case_data: dict, references: dict, generated_at: str) -> dict:
    return {
        "seeds": [
            {"type": i["identifier_type"], "value": i["value"]}
            for i in case_data["identifiers"]
        ],
        "lookup_summary": [
            {
                "ref": references["lookups"].get(lk["id"]),
                "type": lk["lookup_type"],
                "input": lk["input_value"],
                "performed_at": str(lk.get("created_at", "")),
            }
            for lk in case_data["lookups"]
        ],
        "evidence_identifiers": {
            "accounts": len(references["accounts"]),
            "correlations": len(references["correlations"]),
            "insights": len(references["insights"]),
            "sources": len(references["sources"]),
            "lookups": len(references["lookups"]),
        },
        "generation_metadata": {
            "methodology_version": METHODOLOGY_VERSION,
            "generated_at": generated_at,
            "report_schema_version": "1.0",
        },
    }


def _summarize_evidence(evidence) -> str | None:
    """Produce a short textual summary of insight evidence."""
    if not evidence:
        return None
    if isinstance(evidence, str):
        return evidence[:200]
    if isinstance(evidence, dict):
        parts = []
        for k, v in list(evidence.items())[:3]:
            parts.append(f"{k}: {v}" if not isinstance(v, (dict, list)) else k)
        return "; ".join(parts)
    if isinstance(evidence, list):
        return f"{len(evidence)} evidence items"
    return str(evidence)[:200]


def _derive_profile_url(account: dict) -> str | None:
    platform = account.get("platform", "").lower()
    username = account.get("username", "")
    if not username:
        return None
    templates = {
        "reddit": f"https://www.reddit.com/user/{username}",
        "twitter": f"https://x.com/{username}",
        "github": f"https://github.com/{username}",
        "instagram": f"https://www.instagram.com/{username}",
    }
    return templates.get(platform)
