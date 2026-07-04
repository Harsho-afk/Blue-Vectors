"""
Stage 2A Orchestrator

Runs all Pass 1 insight functions (independent, parallel-safe),
then Pass 2 (depends on Pass 1 output), persists results to the
insights table, and returns the full list.

Execution order:
  Pass 1 (independent): timezone, network_geo, cross_link, pattern_of_life,
                         coordination, risk, keywords
  Pass 2 (depends on Pass 1): identity consistency checker
"""

import logging
from .models import save_insights, clear_insights
from . import cross_link, pattern_of_life, risk, timezone, network_geo, coordination, keywords, consistency

log = logging.getLogger("aria.insights.orchestrator")


def run_pass1(conn, case_id: int) -> list:
    """Run all independent Pass 1 insight functions and persist results."""
    from .models import InsightResult

    clear_insights(conn, case_id)

    all_results: list[InsightResult] = []

    functions = [
        ("cross_link", cross_link.run),
        ("timezone", timezone.run),
        ("network_geo", network_geo.run),
        ("pattern_of_life", pattern_of_life.run),
        ("coordination", coordination.run),
        ("risk", risk.run),
        ("keywords", keywords.run),
    ]

    for name, func in functions:
        try:
            results = func(conn, case_id)
            all_results.extend(results)
            log.info("  [%s] -> %d insights", name, len(results))
        except Exception:
            log.exception("  [%s] FAILED", name)

    saved = save_insights(conn, case_id, all_results)
    log.info("Case %d: Pass 1 complete - %d insights saved", case_id, saved)

    return [r.to_dict() for r in all_results]


def run_pass2(conn, case_id: int) -> list:
    """Run Pass 2 functions that depend on Pass 1 insights."""
    from .models import InsightResult

    all_results: list[InsightResult] = []

    functions = [
        ("consistency", consistency.run),
    ]

    for name, func in functions:
        try:
            results = func(conn, case_id)
            all_results.extend(results)
            log.info("  [%s] -> %d insights", name, len(results))
        except Exception:
            log.exception("  [%s] FAILED", name)

    if all_results:
        saved = save_insights(conn, case_id, all_results)
        log.info("Case %d: Pass 2 complete - %d insights saved", case_id, saved)
    else:
        log.info("Case %d: Pass 2 complete - no additional insights", case_id)

    return [r.to_dict() for r in all_results]


def run_all(conn, case_id: int) -> list:
    """Run both passes in order and return combined results."""
    pass1 = run_pass1(conn, case_id)
    pass2 = run_pass2(conn, case_id)
    return pass1 + pass2
