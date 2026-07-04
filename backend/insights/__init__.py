"""
ARIA — Stage 2A deterministic insight functions.

Every function in this package returns list[InsightResult].
The orchestrator persists them to the `insights` table.
"""

from .models import InsightResult, EvidenceItem, save_insights, clear_insights

__all__ = ["InsightResult", "EvidenceItem", "save_insights", "clear_insights"]
