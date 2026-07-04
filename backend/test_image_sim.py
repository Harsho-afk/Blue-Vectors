"""
Quick test: compare two profile picture URLs and see the raw + calibrated CLIP scores.

Usage:
    python test_image_sim.py <url1> <url2>

Example:
    python test_image_sim.py "https://pbs.twimg.com/profile_images/abc/photo.jpg" "https://avatars.githubusercontent.com/u/12345"
"""

import sys
import io
import numpy as np
import httpx
from PIL import Image

CLIP_BASELINE = 0.60
CLIP_CEILING = 0.95


def download(url: str) -> Image.Image:
    resp = httpx.get(url, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    return Image.open(io.BytesIO(resp.content)).convert("RGB")


def calibrate(raw: float) -> float:
    if raw <= CLIP_BASELINE:
        return 0.0
    if raw >= CLIP_CEILING:
        return 1.0
    return (raw - CLIP_BASELINE) / (CLIP_CEILING - CLIP_BASELINE)


def compare(url_a: str, url_b: str):
    print(f"\nImage A: {url_a[:100]}")
    print(f"Image B: {url_b[:100]}")
    print()

    img_a = download(url_a)
    img_b = download(url_b)
    print(f"  A size: {img_a.size}   B size: {img_b.size}")
    print()

    print("  Loading CLIP model...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("clip-ViT-B-32")

    embeddings = model.encode([img_a, img_b], convert_to_numpy=True)
    raw = float(
        np.dot(embeddings[0], embeddings[1])
        / (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1]))
    )
    cal = calibrate(raw)

    print(f"  Raw CLIP cosine similarity : {raw:.4f}")
    print(f"  Calibrated score           : {cal:.4f} ({cal:.1%})")
    print(f"  Baseline (unrelated floor) : {CLIP_BASELINE}")
    print(f"  Ceiling  (identical)       : {CLIP_CEILING}")
    print()

    if cal > 0.70:
        print("  Verdict: HIGH MATCH — likely same person or same image")
    elif cal > 0.30:
        print("  Verdict: MODERATE — some visual similarity detected")
    elif cal > 0.0:
        print("  Verdict: LOW — minor similarity, probably different")
    else:
        print("  Verdict: NO MATCH — unrelated images")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_image_sim.py <url1> <url2>")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
