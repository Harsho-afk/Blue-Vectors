"""
Stage 2C: Citation Check (Verifier)

Purely structural validation: does every cited_insight_id in the Analyst
output actually exist in this case's insights table?

Claims with invalid citations are stripped.
The output is labeled "AI-synthesized, citation-linked" - not "verified."
This is a sanitizer, not a truth check.
"""

import json
import logging

log = logging.getLogger("aria.llm.citation_check")

LABEL = "AI-synthesized, citation-linked"


def validate_citations(conn, case_id: int, analyst_output: dict) -> dict:
    """
    Validate and sanitize the analyst's briefing.

    1. Check every cited_insight_id exists in this case's insights table.
    2. Strip claims that cite nonexistent insights.
    3. Label the output appropriately.

    Returns: {
        "narrative": str,
        "claims": [{"narrative_claim": str, "cited_insight_ids": [int]}],
        "label": "AI-synthesized, citation-linked",
        "citation_stats": {
            "total_claims": int,
            "valid_claims": int,
            "stripped_claims": int,
            "total_citations": int,
            "valid_citations": int,
            "invalid_citation_ids": [int],
        }
    }
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM insights WHERE case_id = %s",
        (case_id,),
    )
    valid_ids = {row["id"] for row in cur.fetchall()}

    claims = analyst_output.get("claims", [])
    narrative = analyst_output.get("narrative", "")

    valid_claims = []
    stripped_claims = []
    all_citations = 0
    valid_citation_count = 0
    invalid_ids: set[int] = set()

    for claim in claims:
        cited_ids = claim.get("cited_insight_ids", [])

        if not isinstance(cited_ids, list):
            cited_ids = []

        int_ids = []
        for cid in cited_ids:
            try:
                int_ids.append(int(cid))
            except (ValueError, TypeError):
                pass

        all_citations += len(int_ids)

        good_ids = [cid for cid in int_ids if cid in valid_ids]
        bad_ids = [cid for cid in int_ids if cid not in valid_ids]

        valid_citation_count += len(good_ids)
        invalid_ids.update(bad_ids)

        if good_ids:
            valid_claims.append({
                "narrative_claim": claim.get("narrative_claim", ""),
                "cited_insight_ids": good_ids,
            })
        else:
            stripped_claims.append({
                "narrative_claim": claim.get("narrative_claim", ""),
                "original_cited_ids": int_ids,
                "reason": "no valid citations",
            })

    stats = {
        "total_claims": len(claims),
        "valid_claims": len(valid_claims),
        "stripped_claims": len(stripped_claims),
        "total_citations": all_citations,
        "valid_citations": valid_citation_count,
        "invalid_citation_ids": sorted(invalid_ids),
    }

    if stripped_claims:
        log.warning(
            "Case %d: stripped %d claim(s) with invalid citations: %s",
            case_id, len(stripped_claims),
            [s["narrative_claim"][:60] for s in stripped_claims],
        )

    log.info(
        "Case %d: citation check passed %d/%d claims (%d/%d citations valid)",
        case_id, stats["valid_claims"], stats["total_claims"],
        stats["valid_citations"], stats["total_citations"],
    )

    return {
        "narrative": narrative,
        "claims": valid_claims,
        "label": LABEL,
        "citation_stats": stats,
    }


def save_report(conn, case_id: int, checked_output: dict) -> int:
    """Persist the validated intelligence report. Returns the report ID."""
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM intelligence_reports WHERE case_id = %s",
        (case_id,),
    )

    cur.execute(
        """
        INSERT INTO intelligence_reports (case_id, narrative, claims, label)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (
            case_id,
            checked_output["narrative"],
            json.dumps(checked_output["claims"]),
            checked_output["label"],
        ),
    )
    report_id = cur.fetchone()["id"]
    conn.commit()

    log.info("Case %d: intelligence report saved (id=%d)", case_id, report_id)
    return report_id
