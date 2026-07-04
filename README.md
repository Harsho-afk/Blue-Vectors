# ARIA — Adaptive Resolution of Identity Across Platforms

**SOCMINT-based cross-platform identity resolution & case management system**
Hackathon deadline: **July 4, 2026** | Today: June 12 (22 days) | Team: 3 members

---

## What ARIA Does

ARIA is a case-centric OSINT investigation platform. An investigator creates a **case**, attaches one or more **seed identifiers** (username, email, phone, profile URL), and ARIA:

1. Collects public digital footprints across platforms (Reddit, Twitter, username enumeration via Sherlock, breach data via HaveIBeenPwned)
2. Extracts features for each discovered account (profile similarity, stylometry, temporal behaviour, content/sentiment)
3. Correlates accounts that may belong to the same real-world person, with a **confidence score (0–100%)** and a **per-signal explanation**
4. Visualises results: ranked candidates, evidence breakdown, social graph, unified timeline
5. Exports a structured SOCMINT report (JSON + PDF)

Design principle: **AI recommends, investigator decides.** ARIA never claims two accounts ARE the same person. Confidence bands are:

| Band | Range |
|---|---|
| Low | 0–40% |
| Medium | 41–70% |
| High | 71–100% |

Every score must be accompanied by a per-signal explanation of *why* it was assigned.

---

## System Architecture: 7-Layer Pipeline

```
Layer 0  Auth + Case Management   Login, case creation, multi-identifier input (NEW)
Layer 1  Data Collection          Identifiers → raw posts, profiles, OSINT lookups
Layer 2  Feature Extraction       Raw data per account → similarity feature scores
Layer 3  Correlation Engine       Feature scores (account pair) → confidence score 0–1
Layer 4  Graph Intelligence       Social graph edges → GNN node embeddings (STRETCH)
Layer 5  Explainability           Fusion model → per-signal evidence breakdown
Layer 6  Profiling + Report       Suspect profile aggregation → exportable SOCMINT report (NEW)
```

End-to-end flow:
1. Investigator registers/logs in, creates a case with a title and one or more identifiers
2. Layer 0 routes each identifier by type (username → Reddit/Twitter/Sherlock, email → HIBP, profile_url → direct scrape)
3. Layer 1 collects public posts, bios, timestamps, profile images, OSINT lookup results — all scoped to `case_id`
4. Layer 2 computes per-account feature scores: profile similarity, stylometric fingerprint, temporal rhythm, content/sentiment, (image similarity — stretch)
5. Layer 3 fuses feature scores → ranked candidate matches with confidence scores
6. Layer 4 (stretch) runs GAT on the social graph; feeds node embeddings back into fusion
7. Layer 5 decomposes each prediction into per-signal evidence (SHAP if trained model exists, otherwise weighted-component breakdown)
8. Layer 6 aggregates everything into a suspect profile and generates a SOCMINT report
9. Frontend displays ranked matches, evidence panel, graph view, timeline, and report export

---

## MVP vs. Stretch — what's demo-guaranteed

Given the 22-day timeline, the correlation engine ships as a **rule-based weighted MVP first**. ML components (Siamese LSTM, GAT, trained XGBoost+SHAP) are stretch goals attempted only if Phases 1–3 land early. The frontend and report always display real evidence — MVP or ML-based, the *interface* doesn't change, only what powers the score does.

| Component | MVP (guaranteed) | Stretch (if time allows) |
|---|---|---|
| Username similarity | rapidfuzz (Levenshtein/Jaro-Winkler) | — |
| Bio similarity | sentence-transformers cosine | — |
| Temporal similarity | histogram comparison (Jensen-Shannon) | — |
| Image similarity | skipped, neutral value | CLIP cosine similarity |
| Stylometry | TF-IDF cosine similarity fallback | Siamese LSTM (PAN 2020, target AUC > 0.75) |
| Graph reasoning | skipped | GAT on Foursquare-Twitter, 128-dim embeddings |
| Fusion | weighted sum of available signals | XGBoost on 6 features |
| Explainability | per-component score breakdown ("why") | SHAP TreeExplainer |

### MVP Correlation Scoring Spec (Layer 2/3)

For a candidate account pair, compute up to 3 component scores, each 0–1:

```
username_score  = rapidfuzz weighted ratio (Levenshtein + Jaro-Winkler + LCS) on username/display_name
bio_score       = cosine similarity of sentence-transformers (all-MiniLM-L6-v2) embeddings of bio text
temporal_score  = 1 - Jensen-Shannon divergence of hour-of-day posting histograms
```

If a component is unavailable (e.g. empty bio), exclude it and renormalize remaining weights. Default weights:

```
username_score : 0.40
bio_score       : 0.35
temporal_score  : 0.25
```

```
confidence = Σ (weight_i × score_i) / Σ (weight_i for available signals)
```

Map `confidence` (0–1) to 0–100% and to Low/Medium/High bands above.

**Explanation output** (feeds Evidence Panel + report, replaces SHAP until/unless a trained model exists):

```json
{
  "username_score": 0.82,
  "bio_score": 0.61,
  "temporal_score": 0.74,
  "confidence": 0.72,
  "band": "High",
  "notes": ["Image score unavailable — excluded, weights renormalized"]
}
```

This JSON shape is stored in `linkage_results.shap_json` (field name kept for schema/frontend compatibility — it holds either the SHAP breakdown or this weighted breakdown, both shaped as per-signal contributions).

---

## Tech Stack

| Domain | Technology | Notes |
|---|---|---|
| Auth | fastapi-users, JWT (httpOnly cookie), bcrypt | Layer 0 |
| Routing (frontend) | react-router-dom | Protected routes: Login → Dashboard → Case views |
| ML Framework | PyTorch 2.x | Stretch: Siamese net, GNN training |
| Graph ML | PyTorch Geometric | Stretch: GAT / GraphSAGE |
| NLP | spaCy + NLTK + VADER | Stylometry (stretch), sentiment/tone (MVP) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Bio / profile text similarity (MVP) |
| Image | OpenAI CLIP | Stretch — frozen, do NOT retrain |
| Image Captioning | BLIP (Salesforce) | Stretch |
| String Similarity | rapidfuzz | Username / display name matching (MVP) |
| XAI | SHAP (TreeExplainer) | Stretch — MVP uses weighted-component breakdown instead |
| OSINT — username enum | Sherlock | New, Layer 1 |
| OSINT — breach lookup | HaveIBeenPwned API | New, Layer 1 |
| ML Training Env | Google Colab / Kaggle | T4 GPU, free tier — stretch only |
| Backend | FastAPI (Python 3.11) | Async API server |
| Primary DB | PostgreSQL | Case-centric schema (see below) |
| Cache / Queue | Redis | Rate limiting, job queuing, demo result caching |
| Reddit Scraping | Redlib (no-key scraping) | See Layer 1 details |
| Twitter Scraping | twikit (browser cookies) | See Layer 1 details |
| LinkedIn | Mock/pre-loaded data | Labelled "Pre-loaded OSINT data" in UI |
| Frontend | React + Tailwind CSS | Dark theme (Palantir aesthetic) |
| Graph Viz | React Flow + D3.js | Social graph, identity links |
| Timeline Viz | react-chrono or custom CSS scroll list | D3 optional — simplicity over polish |
| Charts | Recharts | Evidence breakdown bar charts |
| Report | WeasyPrint (PDF) | Fallback: browser print-to-PDF from JSON |
| Containers | Docker Compose | postgres + redis + fastapi |

---

## Layer 0: Auth + Case Management (🔲 Not started)

The entry gate. Every action in ARIA is scoped to a case; every case is owned by an authenticated investigator.

### Auth

- JWT-based registration and login via **fastapi-users**
- Passwords hashed with bcrypt
- Tokens stored in **httpOnly cookies** — requires `credentials: include` on frontend fetches and CORS `allow_credentials=True` on backend
- Access control: investigators can only view/modify their own cases (`WHERE investigator_id = current_user.id` on every case query) — no shared case access in v1

### Endpoints

```
POST /api/auth/register   { email, password, full_name } → JWT
POST /api/auth/login      { email, password }            → JWT
POST /api/auth/logout     → clears cookie
```

### Case Management

```
POST   /api/cases               { title, identifiers[] } → case_id
GET    /api/cases                list cases for logged-in investigator
GET    /api/cases/{case_id}      case details, status, linked accounts, results
DELETE /api/cases/{case_id}      delete case + all associated data
```

Each identifier in `identifiers[]` is one of:

```
{ identifier_type: "username" | "email" | "phone" | "profile_url", value: "...", platform_hint?: "reddit"|"twitter"|... }
```

Identifier routing:
- `username` → Reddit + Twitter collectors, Sherlock
- `email` → HaveIBeenPwned breach lookup
- `profile_url` → direct scrape (httpx + BeautifulSoup)
- `phone` → reserved, no lookup source defined yet

---

## Layer 1: Data Collection (✅ Built, case-scoped)

Layer 1 is the foundation. All other layers depend on data quality.
**Collect only public data — no authentication bypass, no private endpoints.**

### Files

```
collector.py      Core collection logic — RedditCollector, TwitterCollector, save_to_db
app.py            FastAPI server exposing GET /collect/{platform}/{username}
schema.sql        PostgreSQL schema (case-centric, 10 tables)
migration_001.sql Migration from original 2-table schema to case-centric schema
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
spike_flag             bool   set by Layer 2 spike/gap detector (stretch), default false
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

### OSINT Lookups (🔲 Not started — Phase 1, days 4–5)

```
POST /api/osint/username-search   { username } → Sherlock results: platforms where handle exists
POST /api/osint/breach-lookup     { email }    → HIBP results: breach list + exposed data types
```

Results stored in `osint_lookups` (raw JSON in `result_json`). Pre-run all lookups before demo day; demo shows stored results, not live calls (live OSINT lookups can be slow/rate-limited).

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
JWT_SECRET=your_jwt_signing_secret_here
```

Cookies expire after a few weeks. Re-extract from browser when they do.

### 3. Database

Fresh install:
```bash
psql -d aria -f schema.sql
```

Upgrading an existing Layer-1-only database:
```bash
psql -d aria -f migration_001.sql
```

Both produce an identical case-centric schema (see below).

### 4. Frontend

The React app (Vite + react-router-dom) requires the FastAPI server running on `http://localhost:8000`.

```bash
uvicorn app:app --reload
# Then: npm install && npm run dev
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
account_id = save_to_db(reddit_profile, conn, case_id=1)  # case_id now required
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

## PostgreSQL Schema (case-centric, 10 tables)

```sql
-- Layer 0: Auth + Case Management
users(id, email, password_hash, full_name, role, created_at)
cases(id, investigator_id→users, title, status, created_at, closed_at)
case_identifiers(id, case_id→cases, identifier_type, value, platform_hint, created_at)

-- Layer 1: Data Collection + OSINT
accounts(id, case_id→cases, platform, username, display_name, bio, location,
         created_at, profile_image_url, UNIQUE(case_id, platform, username))
posts(id, account_id→accounts, text, timestamp, metadata JSONB, spike_flag BOOLEAN DEFAULT false,
      UNIQUE(account_id, timestamp, text))
osint_lookups(id, case_id→cases, lookup_type, input_value, result_json JSONB, created_at)

-- Layer 2/3/5: Features + Correlation + Explainability
linkage_results(id, case_id→cases, account_a_id→accounts, account_b_id→accounts,
                 confidence NUMERIC(5,2), shap_json JSONB, created_at,
                 CHECK (account_a_id < account_b_id))

-- Stretch — not created until the corresponding layer is built
graph_edges(source_account_id, target_account_id, edge_type, weight)
feature_vectors(id, account_id, profile_vec, style_vec, temporal_vec, graph_vec, image_vec)
content_analysis(id, account_id→accounts, top_keywords_json, hashtags_json,
                  sentiment_compound, tone_label, cross_post_fingerprint, created_at)
```

`accounts` is **per-case**: the same real account collected for two different cases produces two rows. This avoids merge/dedup logic at the cost of re-collection if a suspect reappears — acceptable tradeoff for the hackathon timeline, documented as a known limitation.

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

## Layer 2: Feature Extraction (🔲 Not started)

### 2.1 Profile Similarity Module (MVP)

| Field | Method | Library | Weight |
|---|---|---|---|
| Username | Levenshtein + Jaro-Winkler + LCS | rapidfuzz | 0.40 |
| Bio | Cosine similarity of sentence embeddings | sentence-transformers | 0.35 |
| Temporal | 1 − Jensen-Shannon divergence of posting-hour histograms | scipy | 0.25 |

See **MVP Correlation Scoring Spec** above for the exact formula and output JSON shape.

### 2.2 Content Analysis Module (MVP, new)

- Top-20 keywords per account (TF-IDF)
- Hashtag frequency vector, frequent bigrams
- Cross-post fingerprinting (cosine sim of full post text across platforms)
- Sentiment: VADER compound score + tone label (neutral / positive / aggressive / promotional), computed per account

Endpoints:
```
GET /api/accounts/{id}/keywords    top keywords, hashtags, bigrams
GET /api/accounts/{id}/sentiment   sentiment score + tone label
```

### 2.3 Behaviour / Spike-Gap Module (MVP, new)

Rolling 7-day post count per account; flag windows with 3σ deviation from baseline as activity spikes or gaps. Writes `spike_flag` on `posts`.

```
GET /api/accounts/{id}/timeline       chronological post events with spike/gap flags
GET /api/cases/{case_id}/timeline     merged timeline across all linked accounts in a case
```

### 2.4 Stylometric Module (STRETCH)

Siamese network on post text. Features: vocabulary richness, sentence length distribution, punctuation patterns, function word frequency, POS tag ratios. Train on PAN 2020 via Colab/Kaggle T4, target AUC > 0.75. **Fallback if not trained in time:** TF-IDF cosine similarity as the stylometric score.

### 2.5 Image Module (STRETCH)

CLIP embeddings for profile images + BLIP captions. Frozen pretrained models — do NOT retrain. If not built, image signal is omitted and weights renormalize (see MVP spec).

### 2.6 Graph Intelligence Module (STRETCH — Layer 4)

GAT on follower/following social graph (Foursquare-Twitter dataset, 496-node subset, trained once and checkpointed — never retrained during demo). Node embeddings feed back into fusion as a 6th feature.

---

## Layer 3: Correlation Engine

**MVP**: weighted sum of available Layer 2 component scores → confidence 0–1 → band (Low/Medium/High). See spec above.

**STRETCH**: XGBoost trained on 6 features (5 component scores + GAT embedding) → linkage probability 0–1.

Candidate generation (both modes): rapidfuzz username filter (>0.40) + bio embedding threshold (>0.35) → top-10 candidates per seed account.

```
GET /api/cases/{case_id}/candidates   ranked candidate matches with confidence scores
GET /api/evidence/{pair_id}           per-signal breakdown for a candidate pair
GET /api/graph/{case_id}              social graph nodes + edges for React Flow (stretch — empty until Layer 4 built)
```

---

## Layer 5: Explainability

**MVP**: per-component score breakdown (see JSON shape in MVP spec) — same shape SHAP would produce, displayed as a horizontal bar chart with plain-English labels (e.g. "Writing Style Match: 91%").

**STRETCH**: SHAP `TreeExplainer` on the trained XGBoost fusion model, same output shape, stored in `linkage_results.shap_json`.

Research gap closed by ARIA: StyleLink (ICWSM 2025) does stylometry + GNN but has zero XAI component. ARIA adds explainability to the pipeline regardless of MVP/stretch path.

---

## Layer 6: Profiling + Report Generation (🔲 Not started, new)

Aggregates all layer outputs into a suspect profile and generates an exportable SOCMINT report.

- Suspect profile: aggregated bio, all linked accounts with confidence, top keywords, sentiment summary, posting behaviour summary, network cluster summary (if Layer 4 built)
- Report sections: case metadata, seed identifiers, discovered accounts, correlation logic per link, evidence breakdown, open-source references, confidence notes, limitations disclaimer
- Confidence note auto-added if any signal is missing (e.g. "Image score unavailable — excluded, weights renormalized")

Endpoints:
```
GET /api/cases/{case_id}/report       structured SOCMINT report as JSON
GET /api/cases/{case_id}/report/pdf   report as PDF (WeasyPrint)
```

**Fallback** if WeasyPrint dependency issues arise: serve JSON only, browser print-to-PDF. The JSON + investigator notes field is sufficient to demonstrate the feature.

---

## Frontend — 9 Screens

| # | Screen | Status |
|---|---|---|
| 1 | Login / Register | 🔲 Not started |
| 2 | Case Dashboard | 🔲 Not started |
| 3 | New Case / Input (multi-identifier) | 🔲 Not started |
| 4 | Processing Screen (7-layer progress) | 🔲 Not started |
| 5 | Results Screen (ranked candidates) | 🔲 Not started |
| 6 | Evidence Panel (score breakdown, keywords, tone, hashtags) | 🔲 Not started |
| 7 | Graph View (React Flow) | 🔲 Not started |
| 8 | Timeline View | 🔲 Not started |
| 9 | Report Export Screen | 🔲 Not started |

Screens 1–7 are mandatory. Screens 8–9 are high priority but may be simplified to static-render if time runs short.

Current Layer 1 UI (`ARIACollector.jsx`) — platform selector, username input, collection log with typewriter effect, profile card, stat pills, post feed with type filters, subreddit tag cloud, mock data mode — will be integrated as a sub-view of the case detail screen rather than the primary entry point.

**Note**: mock data mode currently fails silently if the backend is unreachable. For the case-centric version, surface this explicitly (e.g. a visible "Showing mock data — backend unreachable" banner) so investigators aren't misled during a live demo.

---

## Known Issues / Notes for Next Claude Session

1. **twikit monkey patches** — Two patches in `collector.py` for twikit bugs active as of March 2026. Check twikit changelog before removing; they may be fixed in a later release.

2. **Redlib instances go offline** — If all 5 fail, add fresh instances from the [Redlib instance list](https://github.com/redlib-org/redlib-instances). The `INSTANCES` list is at the top of `RedditCollector`.

3. **Twitter cookie expiry** — Cookies expire after ~2–3 weeks. Re-extract `ct0` and `auth_token` from browser DevTools when collection returns auth errors.

4. **LinkedIn** — No stable public API. For the demo, use pre-crawled mock data stored directly in the DB, labelled clearly in the UI as "Pre-loaded OSINT data". Fields needed: name, headline, location, education (school/degree/year), work experience (company/role/years), skills.

5. **Reddit Redlib vs PRAW** — Current collector uses Redlib (no credentials needed). Redlib HTML structure verified against v0.36.0 (June 2026). If Redlib's HTML changes, re-run `diagnose_redlib.py` and `diagnose_comments.py` to inspect current structure and update selectors in `RedditCollector.collect()`.

6. **`limit` is per-endpoint for Reddit** — `--limit 500` fetches up to 500 submissions AND up to 500 comments separately, so the total `posts` list can be up to 1000 entries. Adjust if you need a strict total cap.

7. **Profile image is Redlib-proxied for Reddit** — `profile_image_url` for Reddit accounts points to the responding Redlib instance, not Reddit's CDN directly. This URL may break if that instance goes offline. For Layer 2 image processing (stretch), fetch and cache image bytes immediately after collection.

8. **`accounts` is per-case** — same real-world account collected in two different cases creates two separate rows (see schema note above). `save_to_db()` now requires `case_id`; `ON CONFLICT` target is `(case_id, platform, username)`.

9. **`linkage_results.shap_json` is dual-purpose** — holds either the MVP weighted-breakdown JSON or a real SHAP breakdown, both in the same per-signal shape. Frontend/report code should not assume SHAP-specific fields exist.

10. **Sherlock/HIBP should be pre-run before demo** — store results in `osint_lookups`, demo from stored results rather than live calls (rate limits / latency risk).

---

## Project Status

| Layer | Status | Owner |
|---|---|---|
| 0 — Auth + Case Management | 🔲 Not started | Backend |
| 1 — Data Collection (incl. OSINT lookups) | ✅ Core built, case-scoped; OSINT lookups not started | Backend |
| 2 — Feature Extraction (MVP: profile/content/behaviour) | 🔲 Not started | ML + Backend |
| 2 — Feature Extraction (stretch: stylometry, image) | 🔲 Not started | ML |
| 3 — Correlation Engine | 🔲 Not started | ML + Backend |
| 4 — Graph Intelligence (stretch) | 🔲 Not started | ML |
| 5 — Explainability | 🔲 Not started | Backend |
| 6 — Profiling + Report | 🔲 Not started | Backend |
| Frontend — Screens 1–7 (mandatory) | 🟡 Layer 1 sub-view only | Frontend |
| Frontend — Screens 8–9 (timeline, report) | 🔲 Not started | Frontend |

**Build schedule**: Phase 1 (Foundation, Jun 12–17) → Phase 2 (ML/Correlation Core, Jun 18–24) → Phase 3 (Frontend + Viz, Jun 25–Jul 1) → Phase 4 (Polish + Demo Prep, Jul 2–3).