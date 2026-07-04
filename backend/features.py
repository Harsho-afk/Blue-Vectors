"""
ARIA — Feature extraction for identity correlation.

Seven independent similarity signals, each returns 0.0-1.0 (or None if unavailable).
"""

import io
import json
import logging
from typing import Optional
from datetime import datetime, timezone

import numpy as np
import httpx
from PIL import Image
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
# Signal 3: Profile image similarity (CLIP)
# ──────────────────────────────────────────────

_clip_model = None

# CLIP cosine similarity for unrelated images clusters around 0.55-0.65.
# Rescale so that baseline → 0.0 and near-perfect → 1.0.
_CLIP_BASELINE = 0.60
_CLIP_CEILING = 0.95


def _get_clip_model():
    global _clip_model
    if _clip_model is None:
        log.info("Loading CLIP model (first call)...")
        from sentence_transformers import SentenceTransformer
        _clip_model = SentenceTransformer("clip-ViT-B-32")
        log.info("CLIP model loaded.")
    return _clip_model


def _calibrate_clip_score(raw: float) -> float:
    """Rescale raw CLIP cosine similarity to a meaningful 0.0–1.0 range."""
    if raw <= _CLIP_BASELINE:
        return 0.0
    if raw >= _CLIP_CEILING:
        return 1.0
    return (raw - _CLIP_BASELINE) / (_CLIP_CEILING - _CLIP_BASELINE)


def _download_image(url: str) -> Optional[Image.Image]:
    """Download an image from URL and return as PIL Image, or None on failure."""
    if not url or not url.startswith("http"):
        return None
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        log.debug("Image download failed for %s: %s", url[:80], e)
        return None


def compute_image_embedding(url: str | None) -> Optional[list[float]]:
    """Download a profile image and return its CLIP embedding as a list of floats."""
    if not url:
        return None
    img = _download_image(url)
    if img is None:
        return None
    try:
        model = _get_clip_model()
        emb = model.encode([img], convert_to_numpy=True)[0]
        return emb.tolist()
    except Exception as e:
        log.warning("CLIP embedding computation failed: %s", e)
        return None


def profile_image_similarity(
    url_a: str | None,
    url_b: str | None,
    embedding_a: list[float] | None = None,
    embedding_b: list[float] | None = None,
) -> Optional[float]:
    """
    CLIP-based semantic similarity between two profile pictures.
    Uses pre-computed embeddings if available, otherwise downloads and embeds.
    Raw cosine similarity is calibrated so unrelated images → 0.0.
    Returns None if either image is missing or download fails.
    """
    try:
        if embedding_a is not None and embedding_b is not None:
            vec_a = np.array(embedding_a)
            vec_b = np.array(embedding_b)
        else:
            if not url_a or not url_b:
                return None
            img_a = _download_image(url_a)
            img_b = _download_image(url_b)
            if img_a is None or img_b is None:
                return None
            model = _get_clip_model()
            vecs = model.encode([img_a, img_b], convert_to_numpy=True)
            vec_a, vec_b = vecs[0], vecs[1]

        raw = float(
            np.dot(vec_a, vec_b)
            / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))
        )
        calibrated = _calibrate_clip_score(raw)

        log.info(
            "Image similarity: raw_cosine=%.4f → calibrated=%.4f (%.1f%%)",
            raw, calibrated, calibrated * 100,
        )

        return round(calibrated, 4)

    except Exception as e:
        log.warning("Profile image similarity failed: %s", e)
        return None


# ──────────────────────────────────────────────
# Signal 4: Temporal posting-pattern similarity
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


# ──────────────────────────────────────────────
# Signal 5: Community/subreddit Jaccard overlap
# ──────────────────────────────────────────────

def _extract_subreddits(posts: list[dict]) -> set[str]:
    """Extract unique subreddit names from post metadata."""
    subs: set[str] = set()
    for p in posts:
        md = p.get("metadata")
        if isinstance(md, str):
            try:
                md = json.loads(md)
            except (json.JSONDecodeError, TypeError):
                md = {}
        if not isinstance(md, dict):
            continue
        sub = (md.get("subreddit") or "").strip().lower()
        if sub:
            subs.add(sub)
    return subs


def community_overlap(
    posts_a: list[dict],
    posts_b: list[dict],
) -> Optional[float]:
    """
    Jaccard similarity of subreddit sets between two accounts.
    Returns None if either account has no subreddit activity.
    """
    subs_a = _extract_subreddits(posts_a)
    subs_b = _extract_subreddits(posts_b)

    if not subs_a or not subs_b:
        return None

    intersection = len(subs_a & subs_b)
    union = len(subs_a | subs_b)

    return intersection / union if union > 0 else 0.0


# ──────────────────────────────────────────────
# Signal 6: Character n-gram stylometry
# ──────────────────────────────────────────────

MIN_STYLOMETRY_CHARS = 200


def stylometry_similarity(
    posts_a: list[dict],
    posts_b: list[dict],
) -> Optional[float]:
    """
    Cosine similarity of character n-gram TF-IDF vectors.
    Returns None if either account has insufficient text (< 200 chars).
    """
    def concat_texts(posts: list[dict]) -> str:
        return " ".join(
            p.get("text", "") for p in posts if p.get("text")
        )

    text_a = concat_texts(posts_a)
    text_b = concat_texts(posts_b)

    if len(text_a) < MIN_STYLOMETRY_CHARS or len(text_b) < MIN_STYLOMETRY_CHARS:
        return None

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as cos_sim

        vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 4),
            max_features=5000,
        )
        tfidf = vectorizer.fit_transform([text_a, text_b])
        sim = float(cos_sim(tfidf[0:1], tfidf[1:2])[0][0])
        return max(0.0, min(1.0, sim))
    except Exception as e:
        log.warning("Stylometry similarity failed: %s", e)
        return None
