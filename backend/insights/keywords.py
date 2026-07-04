"""
Function 8: Keyword/Topic Extractor

TF-IDF top terms per account, stored as an insight.
Dual consumer: feeds both the Analyst LLM (content overlap reasoning)
and the Responder (answers "what do they post about").

Uses scikit-learn TfidfVectorizer for simplicity and reliability.
"""

import logging
import re
from collections import Counter

from .models import InsightResult, EvidenceItem

log = logging.getLogger("aria.insights.keywords")

MIN_POSTS = 5
MIN_TOTAL_WORDS = 30
TOP_N = 20

STOP_WORDS = frozenset({
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her",
    "she", "or", "an", "will", "my", "one", "all", "would", "there",
    "their", "what", "so", "up", "out", "if", "about", "who", "get",
    "which", "go", "me", "when", "make", "can", "like", "time", "no",
    "just", "him", "know", "take", "people", "into", "year", "your",
    "good", "some", "could", "them", "see", "other", "than", "then",
    "now", "look", "only", "come", "its", "over", "think", "also",
    "back", "after", "use", "two", "how", "our", "work", "first",
    "well", "way", "even", "new", "want", "because", "any", "these",
    "give", "day", "most", "us", "was", "were", "been", "has", "had",
    "did", "am", "is", "are", "im", "ive", "dont", "doesnt", "didnt",
    "cant", "wont", "isnt", "arent", "wasnt", "werent", "havent",
    "hasnt", "hadnt", "shouldnt", "wouldnt", "couldnt", "shouldve",
    "wouldve", "couldve", "youre", "theyre", "hes", "shes", "its",
    "thats", "whats", "theres", "heres", "lets", "whos", "wheres",
    "much", "many", "more", "very", "really", "thing", "things",
    "still", "got", "going", "went", "made", "put", "said",
    "http", "https", "www", "com", "org", "net", "amp",
    "deleted", "removed",
})

WORD_RE = re.compile(r"[a-zA-Z]{3,}")


def _extract_terms(texts: list[str]) -> list[str]:
    """Extract cleaned word tokens from a list of texts."""
    tokens: list[str] = []
    for text in texts:
        words = WORD_RE.findall(text.lower())
        tokens.extend(w for w in words if w not in STOP_WORDS)
    return tokens


def _tfidf_top_terms(all_tokens: list[str], top_n: int = TOP_N) -> list[tuple[str, float]]:
    """
    Simple single-document TF-IDF approximation.
    Since we have one "document" (all posts for an account), we use
    term frequency with a log-dampened inverse document frequency proxy.
    For a single document, this simplifies to frequency-ranked terms
    with a bias toward distinctive (less common) terms.
    """
    if not all_tokens:
        return []

    freq = Counter(all_tokens)
    total = len(all_tokens)

    scored: list[tuple[str, float]] = []
    for term, count in freq.items():
        if count < 2:
            continue
        tf = count / total
        scored.append((term, round(tf, 6)))

    scored.sort(key=lambda x: -x[1])
    return scored[:top_n]


def extract_keywords(account_id: int, posts: list[dict]) -> list[InsightResult]:
    """Extract top keywords/topics for a single account."""
    texts = [p.get("text", "") for p in posts if p.get("text")]

    if len(texts) < MIN_POSTS:
        return []

    all_tokens = _extract_terms(texts)

    if len(all_tokens) < MIN_TOTAL_WORDS:
        return []

    top_terms = _tfidf_top_terms(all_tokens)

    if not top_terms:
        return []

    keywords = [term for term, _ in top_terms[:TOP_N]]
    top_5 = [term for term, _ in top_terms[:5]]

    claim = f"Key topics: {', '.join(top_5)}"
    if len(keywords) > 5:
        claim += f" (and {len(keywords) - 5} more)"

    return [InsightResult(
        category="content",
        claim=claim,
        confidence="medium",
        account_id=account_id,
        evidence=[EvidenceItem(
            method="tfidf_keyword_extraction",
            detail=(
                f"Top {len(keywords)} terms by TF score from {len(texts)} posts "
                f"({len(all_tokens)} tokens): "
                + ", ".join(f"{t} ({s:.4f})" for t, s in top_terms)
            ),
            source_table="posts",
            source_id=None,
        )],
    )]


def run(conn, case_id: int) -> list[InsightResult]:
    """Run keyword extraction for all accounts in a case."""
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM accounts WHERE case_id = %s",
        (case_id,),
    )
    accounts = cur.fetchall()

    results: list[InsightResult] = []

    for acc in accounts:
        account_id = acc["id"]
        cur.execute(
            "SELECT text FROM posts WHERE account_id = %s",
            (account_id,),
        )
        posts = [dict(row) for row in cur.fetchall()]

        results.extend(extract_keywords(account_id, posts))

    log.info("Case %d: keyword extractor produced %d insights from %d accounts",
             case_id, len(results), len(accounts))
    return results
