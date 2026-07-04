# ARIA — Adaptive Resolution of Identity Across Platforms

**SOCMINT-based cross-platform identity resolution system**  
Hackathon deadline: **July 4, 2026** | Team: 3 members

---

## What ARIA Does

Given a seed account (username + platform), ARIA determines whether accounts on other platforms belong to the same real-world person — and explains *why*, signal by signal.

Design principle: **AI recommends, investigator decides.** ARIA never claims two accounts ARE the same person. It surfaces evidence, assigns confidence, and decomposes reasoning via SHAP. The human investigator makes the final call.

---

## System Architecture: 5-Layer Pipeline

```
Layer 1  Data Collection      Seed username → raw posts, profile, social graph
Layer 2  Feature Extraction   Raw data per account → 5 feature vectors
Layer 3  Correlation Engine   Feature vectors (account pair) → confidence score 0–1
Layer 4  Graph Intelligence   Social graph edges → GNN node embeddings
Layer 5  Explainability       Fusion model + SHAP → per-signal evidence breakdown
```

End-to-end flow:
1. Investigator enters seed account (e.g. `u/johndoe` on Reddit)
2. Layer 1 fetches public posts, bio, timestamps, profile image, follower list
3. Layer 2 computes profile similarity, stylometric fingerprint, temporal rhythm, graph neighbourhood, image embedding for each candidate pair
4. Layer 3 fuses feature vectors → ranked candidate matches with confidence scores
5. Layer 4 runs GAT on the social graph; feeds node embeddings back into fusion model
6. Layer 5 runs SHAP; decomposes each prediction into per-signal evidence
7. Frontend displays ranked matches with evidence panel, confidence breakdown, and graph visualisation

---

## Tech Stack

| Domain | Technology | Notes |
|---|---|---|
| ML Framework | PyTorch 2.x | Siamese net, GNN training |
| Graph ML | PyTorch Geometric | GAT / GraphSAGE |
| NLP | spaCy + NLTK | Stylometric features, rule-based |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Bio / profile text similarity |
| Image | OpenAI CLIP | Profile image similarity — frozen, do NOT retrain |
| Image Captioning | BLIP (Salesforce) | Generate captions from profile images |
| String Similarity | rapidfuzz | Username / display name matching |
| XAI | SHAP (TreeExplainer) | Explain fusion model predictions |
| ML Training Env | Google Colab / Kaggle | T4 GPU, free tier |
| Backend | FastAPI (Python 3.11) | Async API server |
| Primary DB | PostgreSQL | Profiles, posts, feature vectors |
| Cache / Queue | Redis | Rate limiting, job queuing |
| Reddit Scraping | Redlib (no-key scraping) | See Layer 1 details |
| Twitter Scraping | twikit (browser cookies) | See Layer 1 details |
| LinkedIn | Mock data / Proxycurl | No stable public API |
| Frontend | React + Tailwind CSS | Dark theme (Palantir aesthetic) |
| Graph Viz | React Flow + D3.js | Social graph, identity links |
| Charts | Recharts | SHAP breakdown bar charts |
| Containers | Docker Compose | One-command startup |

---

## Layer 1: Data Collection (BUILT ✅)

Layer 1 is the foundation. All other layers depend on data quality.
**Collect only public data — no authentication bypass, no private endpoints.**

### Files

```
collector.py      Core collection logic — RedditCollector, TwitterCollector, save_to_db
app.py            FastAPI server exposing GET /collect/{platform}/{username}
schema.sql        PostgreSQL schema (accounts + posts tables)
ARIACollector.jsx React UI for triggering collection and displaying results
requirements.txt  Python dependencies
```

### AccountProfile schema (shared contract between all layers)

```
platform           str          "reddit" | "twitter"
username           str
display_name       str
bio                str
location           str
profile_image_url  str          URL — 400×400 for Twitter, Redlib-proxied for Reddit
created_utc        float|None   Unix epoch UTC
posts              list[Post]   submissions + comments combined, sorted newest first
subreddits         list[str]    Reddit only — derived from post/comment history
karma              int|None     Reddit only
follower_count     int|None     Twitter only
following_count    int|None     Twitter only
```

```
Post.text              str    full text
Post.timestamp         float  Unix epoch UTC
Post.metadata.type     str    "submission" | "comment" | "tweet"
Post.metadata.subreddit str   Reddit only
Post.metadata.score    int    Reddit upvotes (submissions and comments)
Post.metadata.tweet_id str    Twitter only
Post.metadata.retweet_count   int  Twitter only
Post.metadata.favorite_count  int  Twitter only
Post.metadata.reply_count     int  Twitter only
Post.metadata.lang     str    Twitter only
```

### Reddit Collector

Scrapes via **Redlib** (public frontend — no credentials, no API key).
Tries multiple public instances in order until one responds.

Collects from two endpoints per user:
- `/user/{username}/submitted` — posts (title + body text, subreddit, score, timestamp)
- `/user/{username}/comments` — comments (body text, subreddit, score, timestamp)

Both are paginated and fully exhausted up to `limit`. The `limit` applies independently to submissions and comments — e.g. `--limit 500` fetches up to 500 submissions and up to 500 comments (up to 1000 total posts).

Also collects from the profile page: display name, bio (`#user_description`), karma, account creation date, profile image URL.

**Redlib HTML structure (verified June 2026 against v0.36.0):**
- Profile: `#user_title`, `#user_description`, `#user_details` (CSS grid: `<label>` + `<div>` pairs for Karma/Created), `#user_icon`
- Submissions: `.post` items, `.post_title a:last` for title, `.created[title]` for timestamp, `.post_subreddit` for subreddit, `.post_score[title]` for score
- Comments: `.comment` items, `.comment_body` for text, `.created[title]` for timestamp, `.comment_subreddit` for subreddit, `.comment_score[title]` for score
- Submissions pagination: `<a rel="next">` with `?after=` query param
- Comments pagination: `<a>NEXT</a>` (no rel attribute) with `?after=` query param

**Redlib instances tried (in order):**
```
https://redlib.catsarch.com
https://redlib.perennialte.ch
https://rl.bloat.cat
https://redlib.privacyredirect.com
https://redlib.seasi.dev
```

### Twitter Collector

Uses **twikit** with browser-extracted cookies. No login flow, no Cloudflare issues.
Contains two monkey patches (documented in code) for upstream twikit bugs active as of March 2026:
- `ClientTransaction` regex patch (Twitter changed `ondemand.s.js` structure)
- `User.__init__` crash patch (bio with no URLs)

Collects: username, display name, bio, location, profile image URL (`_400x400`), creation date, follower/following counts, up to `limit` original tweets (retweets filtered), per-tweet metadata.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Twitter cookies (required for Twitter collection)

twikit uses browser session cookies instead of an API key.

```
1. Log into x.com in your browser
2. DevTools (F12) → Application → Cookies → https://x.com
3. Copy values for 'ct0' and 'auth_token'
```

Create a `.env` file in the project root:

```env
TWITTER_CT0=your_ct0_value_here
TWITTER_AUTH_TOKEN=your_auth_token_here
```

Cookies expire after a few weeks. Re-extract from browser when they do.

### 3. Database (optional for CLI, required for save_to_db)

```bash
psql -d aria -f schema.sql
```

### 4. Frontend

The React component (`ARIACollector.jsx`) is a Vite project. The FastAPI server must be running on `http://localhost:8000`.

```bash
uvicorn app:app --reload
# Then in your Vite project, import ARIACollector from ./ARIACollector.jsx
```

---

## Usage

### CLI

```bash
# Collect submissions + comments, print JSON
python collector.py collect reddit spez
python collector.py collect twitter jack --limit 100

# Save to file (recommended for large collections)
python collector.py collect reddit spez --limit 10000 --out spez.json
python collector.py collect twitter jack --out jack.json
```

`--limit` defaults to 100. Pass a large number like `10000` to exhaust all available posts.

### Python module (synchronous)

```python
from collector import collect, save_to_db
import psycopg2

reddit_profile  = collect("reddit", "spez", limit=10000)
twitter_profile = collect("twitter", "jack", limit=100)

print(reddit_profile.karma)
print(reddit_profile.subreddits)
for post in reddit_profile.posts:
    print(post.metadata["type"], post.timestamp, post.text[:80])

conn = psycopg2.connect("postgresql://localhost/aria")
account_id = save_to_db(reddit_profile, conn)
```

### Python module (async — inside FastAPI)

```python
from collector import collect_async

profile = await collect_async("reddit", "spez", limit=10000)
```

Use `collect_async` when inside an already-running event loop. Reddit collection is offloaded to a thread via `run_in_executor` so it doesn't block FastAPI's event loop.

### REST API

```
GET /collect/{platform}/{username}?limit=50
```

Returns `AccountProfile.to_dict()` JSON. Raises HTTP 404 if user not found.

---

## PostgreSQL Schema (Layer 1 tables)

```sql
accounts(id, platform, username, display_name, bio, location, created_at, profile_image_url)
posts(id, account_id, text, timestamp, metadata JSONB,
      UNIQUE(account_id, timestamp, text))   -- deduplication on re-collection
```

Future layers will add:
```sql
graph_edges(source_account_id, target_account_id, edge_type, weight)
feature_vectors(id, account_id, profile_vec, style_vec, temporal_vec, graph_vec, image_vec)
linkage_results(id, account_a_id, account_b_id, confidence, shap_json, created_at)
```

---

## Layer 1 → Layer 2 Handoff

`AccountProfile` is the shared data contract between all ARIA layers.

```python
from collector import collect   # Layer 1
from features  import extract   # Layer 2 (not yet built)

profile  = collect("reddit", "johndoe", limit=10000)
features = extract(profile)
```

---

## Layer 2: Feature Extraction (NOT YET BUILT)

Five sub-modules, each producing a scalar similarity score (0–1) for a given account pair.

### 2.1 Profile Similarity Module

| Field | Method | Library | Weight |
|---|---|---|---|
| Username | Levenshtein + Jaro-Winkler + LCS | rapidfuzz | 0.25 |
| Display Name | Token sort ratio | rapidfuzz | 0.15 |
| Bio | Cosine similarity of sentence embeddings | sentence-transformers | 0.25 |
| Location | Exact + fuzzy match | rapidfuzz | 0.10 |
| Education / Work | Token overlap + embedding similarity | rapidfuzz + ST | 0.15 |
| Profile Image | CLIP embedding cosine similarity | openai/clip | 0.10 |

### 2.2 Stylometric Module (core ML contribution)

Train a Siamese network taking two sets of posts as input. Features: writing style fingerprint, vocabulary richness, sentence length distribution, punctuation patterns, function word frequency, part-of-speech tag ratios.

Use `post.text` from all `AccountProfile.posts` regardless of type — submissions, comments, and tweets all feed into this. Training environment: Google Colab / Kaggle (T4 GPU free tier).

### 2.3 Temporal Module

Posting cadence analysis: hour-of-day distribution, day-of-week distribution, inter-post intervals, activity burst patterns. Use `post.timestamp` (Unix epoch UTC). Compare two accounts' temporal fingerprints using histogram similarity (Jensen-Shannon divergence).

### 2.4 Graph Intelligence Module (Layer 4 feeds into this)

Graph Attention Network (GAT) on the follower/following social graph. Node embeddings feed back into the fusion model. Library: PyTorch Geometric.

### 2.5 Image Module

CLIP embeddings for profile images + BLIP-generated captions. Use `profile.profile_image_url` — already 400×400 for Twitter; Redlib-proxied URL for Reddit. Frozen pretrained models — do NOT retrain.

---

## Layer 3: Correlation Engine (NOT YET BUILT)

Fusion model (XGBoost or MLP) that takes the 5 feature scores as input and outputs a linkage confidence score (0–1). Training target: labelled account pairs (same person vs. different person).

---

## Layer 5: Explainability (NOT YET BUILT)

SHAP `TreeExplainer` on the fusion model. Output: per-signal contribution breakdown displayed as bar charts in the frontend (Recharts).

Research gap closed by ARIA: StyleLink (ICWSM 2025) does stylometry + GNN but has zero XAI component. ARIA adds full SHAP explainability to the pipeline.

---

## Frontend (ARIACollector.jsx — Layer 1 UI, BUILT)

Dark-themed React component. Features:
- Platform selector (Reddit / Twitter)
- Username input + post limit selector
- Collection log with typewriter effect
- Profile card (avatar, display name, platform badge, bio, location)
- Stat pills (karma, followers, following, post count)
- Post feed with type filters (submission / comment / tweet)
- Subreddit tag cloud (Reddit only)
- Mock data mode for UI development without a live backend

The component calls `GET http://localhost:8000/collect/{platform}/{username}?limit={n}`. Falls back to `generateMockProfile()` silently if the backend is unreachable — for production, surface this error explicitly so investigators know they're seeing mock data.

Future layers will extend this UI with: ranked candidate matches panel, SHAP evidence breakdown (Recharts bar chart), and social graph visualisation (React Flow + D3.js).

---

## Known Issues / Notes for Next Claude Session

1. **twikit monkey patches** — Two patches in `collector.py` for twikit bugs active as of March 2026. Check twikit changelog before removing; they may be fixed in a later release.

2. **Redlib instances go offline** — If all 5 fail, add fresh instances from the [Redlib instance list](https://github.com/redlib-org/redlib-instances). The `INSTANCES` list is at the top of `RedditCollector`.

3. **Twitter cookie expiry** — Cookies expire after ~2–3 weeks. Re-extract `ct0` and `auth_token` from browser DevTools when collection returns auth errors.

4. **LinkedIn** — No stable public API. For the demo, use pre-crawled mock data stored directly in the DB, or Proxycurl API (paid, has free trial credits). Fields needed: name, headline, location, education (school/degree/year), work experience (company/role/years), skills.

5. **Reddit Redlib vs PRAW** — The implementation plan mentions PRAW, but the current collector uses Redlib (no credentials needed). Redlib HTML structure has been verified against v0.36.0 (June 2026). If Redlib's HTML changes, re-run `diagnose_redlib.py` and `diagnose_comments.py` to inspect current structure and update selectors in `RedditCollector.collect()`.

6. **`limit` is per-endpoint for Reddit** — `--limit 500` fetches up to 500 submissions AND up to 500 comments separately, so the total `posts` list can be up to 1000 entries. Adjust if you need a strict total cap.

7. **Profile image is Redlib-proxied for Reddit** — `profile_image_url` for Reddit accounts points to the responding Redlib instance, not Reddit's CDN directly. This URL may break if that instance goes offline. For Layer 2 image processing, fetch and cache the image bytes immediately after collection.

---

## Project Status

| Layer | Status | Owner |
|---|---|---|
| 1 — Data Collection | ✅ Built | Backend |
| 2 — Feature Extraction | 🔲 Not started | ML + Backend |
| 3 — Correlation Engine | 🔲 Not started | ML |
| 4 — Graph Intelligence | 🔲 Not started | ML |
| 5 — Explainability | 🔲 Not started | Backend |
| Auth / Case management | 🔲 Not started | Backend |
| Full investigator UI | 🟡 Layer 1 UI done | Frontend |
