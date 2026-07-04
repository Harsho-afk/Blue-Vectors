"""
Stage 2B: Analyst LLM

Receives ONLY the insights table rows + account summaries (no raw posts).
Produces a structured intelligence briefing with every claim cited to
specific insight IDs.

Supports two providers (checked in order):
  1. Groq  (GROQ_API_KEY)  — free tier, 30 req/min
  2. Gemini (GEMINI_API_KEY) — needs billing or free quota
"""

import json
import logging
import os

import httpx

log = logging.getLogger("aria.llm.analyst")

SYSTEM_PROMPT = """\
You are an OSINT intelligence analyst reviewing digital footprint evidence.

RULES - follow these exactly:
1. ONLY reference facts present in the INSIGHTS below. Never introduce external knowledge or speculation beyond what the data supports.
2. Every claim you make MUST cite the insight_id(s) that support it using the cited_insight_ids array.
3. Use hedging language: "suggests", "indicates", "is consistent with", "points to" - never make definitive identity claims.
4. If insights corroborate each other (e.g. timezone and location agree), explicitly note the convergence.
5. If insights contradict each other, explicitly flag the contradiction.
6. Group related findings into coherent themes (geography, behavior, identity links, risk).
7. The narrative should be 2-4 paragraphs, written for a law enforcement investigator who needs actionable intelligence.
8. Do NOT reference raw post content - only reference the computed insights provided.

Respond with ONLY valid JSON matching this exact schema:
{
    "narrative": "A 2-4 paragraph intelligence summary written in professional analyst tone...",
    "claims": [
        {
            "narrative_claim": "A single factual statement derived from the insights...",
            "cited_insight_ids": [1, 5]
        }
    ]
}

The claims array should contain 5-15 discrete claims, each citing at least one insight_id.
"""


def _build_insights_payload(conn, case_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT id, account_id, category, claim, confidence, evidence "
        "FROM insights WHERE case_id = %s ORDER BY id",
        (case_id,),
    )
    rows = []
    for row in cur.fetchall():
        r = dict(row)
        if isinstance(r["evidence"], str):
            r["evidence"] = json.loads(r["evidence"])
        rows.append(r)
    return rows


def _build_accounts_summary(conn, case_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT a.id, a.platform, a.username, a.display_name, a.bio, a.location, "
        "  (SELECT COUNT(*) FROM posts p WHERE p.account_id = a.id) as post_count "
        "FROM accounts a WHERE a.case_id = %s",
        (case_id,),
    )
    return [dict(row) for row in cur.fetchall()]


def _build_correlation_summary(conn, case_id: int) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        "SELECT lr.account_a_id, lr.account_b_id, lr.confidence, lr.shap_json "
        "FROM linkage_results lr WHERE lr.case_id = %s ORDER BY lr.confidence DESC",
        (case_id,),
    )
    results = []
    for row in cur.fetchall():
        r = dict(row)
        if isinstance(r["shap_json"], str):
            r["shap_json"] = json.loads(r["shap_json"])
        results.append({
            "account_a_id": r["account_a_id"],
            "account_b_id": r["account_b_id"],
            "confidence_pct": r["confidence"],
            "evidence_type": r["shap_json"].get("evidence_type", "unknown") if r["shap_json"] else "unknown",
            "band": r["shap_json"].get("band", "Unknown") if r["shap_json"] else "Unknown",
        })
    return results


def _build_user_prompt(insights, accounts, correlations) -> str:
    return (
        f"CASE INSIGHTS ({len(insights)} total):\n"
        f"{json.dumps(insights, default=str, indent=2)}\n\n"
        f"ACCOUNTS IN THIS CASE ({len(accounts)} total):\n"
        f"{json.dumps(accounts, default=str, indent=2)}\n\n"
        f"CORRELATION RESULTS ({len(correlations)} pairs):\n"
        f"{json.dumps(correlations, default=str, indent=2)}\n\n"
        "Generate the intelligence briefing now."
    )


def _call_groq(api_key: str, user_prompt: str) -> tuple[dict, str]:
    """Call Groq API (OpenAI-compatible). Returns (parsed_json, model_name)."""
    model = "llama-3.3-70b-versatile"
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content), model


def _call_gemini(api_key: str, user_prompt: str) -> tuple[dict, str]:
    """Call Gemini via google-genai SDK. Returns (parsed_json, model_name)."""
    from google import genai
    from google.genai import types

    model = "gemini-2.0-flash"
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            temperature=0.3,
            max_output_tokens=4096,
        ),
    )
    return json.loads(response.text), model


def generate_briefing(conn, case_id: int) -> dict:
    """
    Generate an intelligence briefing from the case's insights.
    Tries Groq first (free), then Gemini as fallback.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if not groq_key and not gemini_key:
        raise RuntimeError(
            "No LLM API key configured. Set GROQ_API_KEY (free) or GEMINI_API_KEY in .env."
        )

    insights = _build_insights_payload(conn, case_id)
    if not insights:
        raise ValueError("No insights found for this case. Run the insights pipeline first.")

    accounts = _build_accounts_summary(conn, case_id)
    correlations = _build_correlation_summary(conn, case_id)
    user_prompt = _build_user_prompt(insights, accounts, correlations)

    log.info(
        "Case %d: sending %d insights + %d accounts + %d correlations to Analyst LLM",
        case_id, len(insights), len(accounts), len(correlations),
    )

    result = None
    model_used = None
    errors = []

    if groq_key:
        try:
            result, model_used = _call_groq(groq_key, user_prompt)
            log.info("Case %d: used Groq (%s)", case_id, model_used)
        except Exception as e:
            log.warning("Groq call failed for case %d: %s", case_id, e)
            errors.append(("Groq", e))

    if result is None and gemini_key:
        try:
            result, model_used = _call_gemini(gemini_key, user_prompt)
            log.info("Case %d: used Gemini (%s)", case_id, model_used)
        except Exception as e:
            log.warning("Gemini call failed for case %d: %s", case_id, e)
            errors.append(("Gemini", e))

    if result is None:
        providers_tried = [name for name, _ in errors]
        is_rate_limit = any(
            "429" in str(err) or "rate" in str(err).lower()
            for _, err in errors
        )
        if is_rate_limit:
            msg = "Intelligence generation temporarily unavailable — LLM rate limits exceeded. Please try again in a few minutes."
        elif not providers_tried:
            msg = "No LLM provider available. Please configure GROQ_API_KEY or GEMINI_API_KEY."
        else:
            msg = f"Intelligence generation failed — could not reach LLM providers ({', '.join(providers_tried)}). Please try again shortly."
        raise RuntimeError(msg)

    if "narrative" not in result or "claims" not in result:
        raise RuntimeError(
            f"LLM response missing required fields. Got keys: {list(result.keys())}"
        )

    log.info(
        "Case %d: Analyst LLM produced %d claims in briefing",
        case_id, len(result.get("claims", [])),
    )

    return {
        "narrative": result["narrative"],
        "claims": result["claims"],
        "input_insight_count": len(insights),
        "model": model_used,
    }
