"""
Shared data structures for Stage 2A insight functions.

Every insight function returns list[InsightResult].
The evidence list links each claim back to source rows so the
Analyst LLM and investigator can trace every assertion.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger("aria.insights")

VALID_CATEGORIES = frozenset([
    "geography",
    "pattern_of_life",
    "identity_consistency",
    "coordination",
    "risk",
    "cross_reference",
    "content",
])

VALID_CONFIDENCES = frozenset(["high", "medium", "low"])


@dataclass
class EvidenceItem:
    method: str
    detail: str
    source_table: str
    source_id: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class InsightResult:
    category: str
    claim: str
    confidence: str
    evidence: list[EvidenceItem] = field(default_factory=list)
    account_id: Optional[int] = None

    def __post_init__(self):
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {self.category}")
        if self.confidence not in VALID_CONFIDENCES:
            raise ValueError(f"Invalid confidence: {self.confidence}")

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "claim": self.claim,
            "confidence": self.confidence,
            "account_id": self.account_id,
            "evidence": [e.to_dict() for e in self.evidence],
        }


def save_insights(conn, case_id: int, insights: list[InsightResult]) -> int:
    """Persist a batch of InsightResults to the insights table. Returns count saved."""
    if not insights:
        return 0

    cur = conn.cursor()
    saved = 0

    for ins in insights:
        cur.execute(
            """
            INSERT INTO insights (case_id, account_id, category, claim, confidence, evidence)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                case_id,
                ins.account_id,
                ins.category,
                ins.claim,
                ins.confidence,
                json.dumps([e.to_dict() for e in ins.evidence]),
            ),
        )
        saved += 1

    conn.commit()
    log.info("Saved %d insights for case %d", saved, case_id)
    return saved


def clear_insights(conn, case_id: int, category: Optional[str] = None) -> int:
    """Delete existing insights for a case (optionally filtered by category). Returns count deleted."""
    cur = conn.cursor()

    if category:
        cur.execute(
            "DELETE FROM insights WHERE case_id = %s AND category = %s",
            (case_id, category),
        )
    else:
        cur.execute(
            "DELETE FROM insights WHERE case_id = %s",
            (case_id,),
        )

    deleted = cur.rowcount
    conn.commit()
    log.info("Cleared %d insights for case %d (category=%s)", deleted, case_id, category or "all")
    return deleted
