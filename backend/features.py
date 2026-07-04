"""
ARIA — Feature extraction for identity correlation.

Three independent similarity signals, each returns 0.0-1.0 (or None if unavailable).
"""

import logging
from typing import Optional
from datetime import datetime, timezone

import numpy as np
from rapidfuzz import fuzz
from rapidfuzz.distance import JaroWinkler
from scipy.spatial.distance import jensenshannon

log = logging.getLogger("aria.features")

# ──────────────────────────────────────────────
# Signal 1: Username / display-name similarity
# ──────────────────────────────────────────────

def username_similarity(
    username_a: str,
    display_a: str | None,
    username_b: str,
    display_b: str | None,
) -> float:
    """
    Compare usernames and display names across two accounts.
    Uses Levenshtein ratio, Jaro-Winkler, and partial ratio; takes best score.
    """
    scores: list[float] = []

    ua = (username_a or "").lower().strip()
    ub = (username_b or "").lower().strip()
    da = (display_a or "").lower().strip()
    db = (display_b or "").lower().strip()

    if ua and ub:
        scores.append(fuzz.ratio(ua, ub) / 100.0)
        scores.append(JaroWinkler.similarity(ua, ub))
        scores.append(fuzz.partial_ratio(ua, ub) / 100.0)

    if da and db:
        scores.append(fuzz.ratio(da, db) / 100.0)
        scores.append(JaroWinkler.similarity(da, db))
        scores.append(fuzz.partial_ratio(da, db) / 100.0)

    if ua and db:
        scores.append(fuzz.ratio(ua, db) / 100.0)
        scores.append(fuzz.partial_ratio(ua, db) / 100.0)
    if da and ub:
        scores.append(fuzz.ratio(da, ub) / 100.0)
        scores.append(fuzz.partial_ratio(da, ub) / 100.0)

    return max(scores) if scores else 0.0


# ──────────────────────────────────────────────
# Signal 2: Bio / description semantic similarity
# ──────────────────────────────────────────────

_st_model = None


def _get_st_model():
    global _st_model
    if _st_model is None:
        log.info("Loading sentence-transformers model (first call)...")
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("all-MiniLM-L6-v2")
        log.info("Sentence-transformers model loaded.")
    return _st_model


def bio_similarity(bio_a: str | None, bio_b: str | None) -> Optional[float]:
    """
    Cosine similarity of sentence embeddings for two bio texts.
    Returns None if either bio is too short (< 5 chars).
    """
    a = (bio_a or "").strip()
    b = (bio_b or "").strip()

    if len(a) < 5 or len(b) < 5:
        return None

    try:
        model = _get_st_model()
        embeddings = model.encode([a, b], convert_to_numpy=True)
        cos_sim = float(
            np.dot(embeddings[0], embeddings[1])
            / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
        )
        return max(0.0, min(1.0, cos_sim))
    except Exception as e:
        log.warning("Bio similarity failed: %s", e)
        return None


# ──────────────────────────────────────────────
# Signal 3: Temporal posting-pattern similarity
# ──────────────────────────────────────────────

def temporal_similarity(
    posts_a: list[dict],
    posts_b: list[dict],
) -> Optional[float]:
    """
    Compare hour-of-day posting distributions via Jensen-Shannon divergence.
    Returns None if either account has < 5 posts with valid timestamps.
    """
    if len(posts_a) < 5 or len(posts_b) < 5:
        return None

    def extract_hours(posts: list[dict]) -> list[int]:
        hours: list[int] = []
        for p in posts:
            ts = p.get("timestamp") if isinstance(p, dict) else getattr(p, "timestamp", None)
            if ts is None:
                continue

            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            elif isinstance(ts, str):
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    except ValueError:
                        continue
            elif isinstance(ts, datetime):
                dt = ts
            else:
                continue

            hours.append(dt.hour)
        return hours

    hours_a = extract_hours(posts_a)
    hours_b = extract_hours(posts_b)

    if len(hours_a) < 5 or len(hours_b) < 5:
        return None

    hist_a = np.zeros(24)
    hist_b = np.zeros(24)
    for h in hours_a:
        hist_a[h] += 1
    for h in hours_b:
        hist_b[h] += 1

    hist_a = hist_a / hist_a.sum()
    hist_b = hist_b / hist_b.sum()

    epsilon = 1e-10
    hist_a = (hist_a + epsilon)
    hist_a = hist_a / hist_a.sum()
    hist_b = (hist_b + epsilon)
    hist_b = hist_b / hist_b.sum()

    jsd = jensenshannon(hist_a, hist_b)
    similarity = 1.0 - float(jsd)
    return max(0.0, min(1.0, similarity))
