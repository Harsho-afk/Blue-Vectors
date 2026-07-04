# ARIA — Adaptive Resolution of Identity Across Platforms

**SOCMINT-based cross-platform identity resolution & case management system**
Hackathon deadline: **July 4, 2026** | Team: 3 members

---

## What ARIA Does

ARIA is a case-centric OSINT investigation platform. An investigator creates a **case**, attaches one or more **seed identifiers** (username, email, phone, profile URL), and ARIA:

1. Collects public digital footprints across platforms (Reddit, Twitter, GitHub, Instagram, username enumeration via Sherlock, breach data via XposedOrNot/HaveIBeenPwned)
2. Extracts features for each discovered account (profile similarity, stylometry, temporal behaviour, content/sentiment) — _not yet built_
3. Correlates accounts that may belong to the same real-world person, with a **confidence score (0–100%)** and a **per-signal explanation** — _not yet built_
4. Visualises results: ranked candidates, evidence breakdown, social graph, unified timeline — _not yet built_
5. Exports a structured SOCMINT report (JSON + PDF) — _not yet built_

Design principle: **AI recommends, investigator decides.** ARIA never claims two accounts ARE the same person. Confidence bands are:

| Band   | Range   |
| ------ | ------- |
| Low    | 0–40%   |
| Medium | 41–70%  |
| High   | 71–100% |

Every score must be accompanied by a per-signal explanation of _why_ it was assigned.

---

## System Architecture: 7-Layer Pipeline

```
Layer 0  Auth + Case Management   Login, case creation, multi-identifier input        ✅ Built
Layer 1  Data Collection          Identifiers → raw posts, profiles, OSINT lookups     ✅ Built
Layer 2  Feature Extraction       Raw data per account → similarity feature scores     🔲 Not started
Layer 3  Correlation Engine       Feature scores (account pair) → confidence score 0–1 🔲 Not started
Layer 4  Graph Intelligence       Social graph edges → GNN node embeddings (STRETCH)    🔲 Not started
Layer 5  Explainability           Fusion model → per-signal evidence breakdown         🔲 Not started
Layer 6  Profiling + Report       Suspect profile aggregation → SOCMINT report         🔲 Not started
```

End-to-end flow (target):

1. Investigator registers/logs in, creates a case with a title and one or more identifiers ✅
2. Layer 0 routes each identifier by type (username → Reddit/Twitter/GitHub/Instagram, email → breach lookup) ✅
3. Layer 1 collects public posts, bios, timestamps, profile images, OSINT lookup results — all scoped to `case_id` ✅
4. Layer 2 computes per-account feature scores: profile similarity, stylometric fingerprint, temporal rhythm, content/sentiment, (image similarity — stretch) 🔲
5. Layer 3 fuses feature scores → ranked candidate matches with confidence scores 🔲
6. Layer 4 (stretch) runs GAT on the social graph; feeds node embeddings back into fusion 🔲
7. Layer 5 decomposes each prediction into per-signal evidence (SHAP if trained model exists, otherwise weighted-component breakdown) 🔲
8. Layer 6 aggregates everything into a suspect profile and generates a SOCMINT report 🔲
9. Frontend displays ranked matches, evidence panel, graph view, timeline, and report export — only case CRUD + collection + OSINT views exist today

---

## MVP vs. Stretch — what's demo-guaranteed

Given the remaining timeline, the correlation engine ships as a **rule-based weighted MVP first**. ML components (Siamese LSTM, GAT, trained XGBoost+SHAP) are stretch goals attempted only if Phases 1–3 land early. The frontend and report always display real evidence — MVP or ML-based, the _interface_ doesn't change, only what powers the score does.

| Component           | MVP (guaranteed)                      | Stretch (if time allows)                      |
| -------------------- | -------------------------------------- | ----------------------------------------------- |
| Username similarity  | rapidfuzz (Levenshtein/Jaro-Winkler)  | —                                               |
| Bio similarity       | sentence-transformers cosine          | —                                               |
| Temporal similarity  | histogram comparison (Jensen-Shannon) | —                                               |
| Image similarity     | skipped, neutral value                | CLIP cosine similarity                          |
| Stylometry           | TF-IDF cosine similarity fallback     | Siamese LSTM (PAN 2020, target AUC > 0.75)      |
| Graph reasoning      | skipped                               | GAT on Foursquare-Twitter, 128-dim embeddings   |
| Fusion               | weighted sum of available signals     | XGBoost on 6 features                           |
| Explainability       | per-component score breakdown ("why") | SHAP TreeExplainer                              |

### MVP Correlation Scoring Spec (Layer 2/3 — design target, not yet implemented)

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

This JSON shape will be stored in `linkage_results.shap_json` (field name kept for schema/frontend compatibility — it holds either the SHAP breakdown or this weighted breakdown, both shaped as per-signal contributions). The `linkage_results` table already exists in `schema.sql`; nothing writes to it yet.

---

## Tech Stack

| Domain                | Technology                                                                       | Status                                                            |
| ---------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Auth                  | JWT (httpOnly cookie), bcrypt, custom routes (`routes_auth.py`)                 | ✅ Built                                                          |
| Routing (frontend)    | react-router-dom                                                                | ✅ Built                                                          |
| Backend               | FastAPI (Python 3.12)                                                           | ✅ Built                                                          |
| Primary DB            | PostgreSQL                                                                      | ✅ Built — case-centric schema (see below)                       |
| OSINT — username enum | Sherlock (`sherlock-project` site DB + custom async checker)                    | ✅ Built                                                          |
| OSINT — breach lookup | XposedOrNot (free, no key) — falls back to HIBP v3 if `HIBP_API_KEY` is set     | ✅ Built                                                          |
| Reddit Scraping       | Self-hosted Redlib container → Reddit public JSON API → public Redlib fallbacks | ✅ Built                                                          |
| Twitter Scraping      | twikit (browser cookies)                                                        | ✅ Built                                                          |
| GitHub Scraping       | GitHub public REST API v3 (optional `GITHUB_TOKEN` for higher rate limit)       | ✅ Built                                                          |
| Instagram Scraping    | instaloader, anonymous/public-only (no login, no Stories)                       | ✅ Built                                                          |
| Frontend              | React 19 + Vite                                                                 | ✅ Built — auth, dashboard, case detail, collection, OSINT views |
| ML Framework          | PyTorch 2.x                                                                     | 🔲 Not started — stretch only                                    |
| Graph ML              | PyTorch Geometric                                                               | 🔲 Not started — stretch only                                    |
| NLP                   | spaCy + NLTK + VADER                                                            | 🔲 Not started                                                   |
| Embeddings            | sentence-transformers (all-MiniLM-L6-v2)                                        | 🔲 Not started                                                   |
| Image                 | OpenAI CLIP                                                                     | 🔲 Not started — stretch                                         |
| String Similarity     | rapidfuzz                                                                       | 🔲 Not started                                                   |
| XAI                   | SHAP (TreeExplainer)                                                            | 🔲 Not started — stretch                                         |
| Graph Viz             | React Flow + D3.js                                                              | 🔲 Not started                                                   |
| Timeline Viz          | react-chrono or custom CSS scroll list                                          | 🔲 Not started                                                   |
| Charts                | Recharts                                                                        | 🔲 Not started                                                   |
| Report                | WeasyPrint (PDF)                                                                | 🔲 Not started                                                   |
| Cache / Queue         | Redis                                                                           | 🔲 Not wired up (no service in docker-compose yet)               |
| Containers            | Docker Compose                                                                  | ✅ postgres + redlib + backend + frontend                        |
| Deployment            | Vercel (frontend) / Railway, Render, or AWS (backend)                           | Planned, not yet deployed                                        |

---

## Layer 0: Auth + Case Management (✅ Built)

The entry gate. Every action in ARIA is scoped to a case; every case is owned by an authenticated investigator.

### Auth

- JWT-based registration and login, hand-rolled in `routes_auth.py` / `auth.py` (no fastapi-users dependency)
- Passwords hashed with bcrypt (`auth.hash_password` / `verify_password`), capped at 72 bytes per bcrypt's limit
- Tokens stored in an **httpOnly cookie** named `aria_token` — requires `credentials: "include"` on frontend fetches and CORS `allow_credentials=True` on backend
- Access control: investigators can only view/modify their own cases (`check_case_ownership` on every case-scoped route) — no shared case access in v1

### Endpoints

```
POST /api/auth/register   { email, password, full_name? } → user object, sets cookie
POST /api/auth/login      { email, password }              → user object, sets cookie
POST /api/auth/logout     → clears cookie
GET  /api/auth/me         → current user, 401 if not authenticated
```

### Case Management

```
POST   /api/cases                       { title, identifiers[] } → { case_id }
GET    /api/cases                        list cases for logged-in investigator
GET    /api/cases/{case_id}              case + identifiers + accounts (with posts) + linkage results + OSINT lookups
DELETE /api/cases/{case_id}              delete case + all associated data (cascade)
POST   /api/cases/{case_id}/identifiers  add identifier(s) to an existing case
POST   /api/cases/{case_id}/collect      { platform, username, limit? } → triggers Layer 1 collection, persists to DB
```

Each identifier in `identifiers[]` is one of:

```
{ identifier_type: "username" | "email" | "phone" | "profile_url", value: "...", platform_hint?: "reddit"|"twitter"|"github"|"instagram" }
```

Identifier routing today: `username` identifiers can be collected (Reddit/Twitter/GitHub/Instagram) or run through Sherlock from the case detail screen; `email` identifiers can be run through breach lookup. `phone` and `profile_url` are stored but have no lookup source wired up yet.

### Frontend

Built: `Login.jsx`, `Register.jsx`, `AuthContext.jsx` (session restore via `/api/auth/me`), `ProtectedRoute.jsx`, `CaseDashboard.jsx` (list + create), `NewCase.jsx` (multi-identifier form), `CaseDetail.jsx` (identifiers, add-identifier form, per-identifier Collect/Sherlock/breach-check actions, OSINT results display, collected account + post feed display, GitHub follower/following panel).

---

## Layer 1: Data Collection (✅ Built, case-scoped)

Layer 1 is the foundation. All other layers depend on data quality.
**Collect only public data — no authentication bypass, no private endpoints.**

### Files

```
backend/collector/
  __init__.py
  base.py         collect() / collect_async() entrypoints, save_to_db()
  models.py       AccountProfile / Post dataclasses, shared logger
  reddit.py       RedditCollector waterfall (self-hosted Redlib → JSON API → public Redlib)
  twitter.py      TwitterCollector (twikit + monkey patches)
  github.py       GitHubCollector (REST API v3 — repos, events, follower/following lists)
  instagram.py    InstagramCollector (instaloader, anonymous, public-only, no Stories)
backend/osint.py            Sherlock username search + XposedOrNot/HIBP breach lookup
backend/app.py              FastAPI app, CORS, router includes, legacy /collect/{platform}/{username}
backend/routes_cases.py     Case CRUD + per-case /collect
backend/routes_osint.py     Per-case OSINT routes
backend/routes_auth.py      Auth routes
backend/auth.py             JWT, bcrypt, DB connection helper, get_current_user dependency
backend/schema.sql          PostgreSQL schema (case-centric, 7 tables)
backend/requirements.txt    Python dependencies
```

The original monolithic `collector.py` has been split into the `collector/` package above, with a shared `AccountProfile`/`Post` schema in `models.py`. `ARIACollector.jsx` (the old standalone collector UI) has been retired — collection is now triggered from `CaseDetail.jsx`.

Supported `platform` values across `SUPPORTED_PLATFORMS` (`collector/base.py`), `CollectRequest` (`routes_cases.py`), and the frontend platform selects: `"reddit"`, `"twitter"`, `"github"`, `"instagram"`.

### AccountProfile schema (shared contract between all layers)

```
platform           str          "reddit" | "twitter" | "github" | "instagram"
username           str
display_name       str
bio                str
location           str
profile_image_url  str          URL — 400×400 for Twitter, Redlib-proxied for Reddit, GitHub avatar, Instagram CDN URL
created_utc        float|None   Unix epoch UTC — null for Instagram (not exposed publicly)
posts              list[Post]   platform-specific items, sorted newest first
subreddits         list[str]    Reddit only — derived from post/comment history
karma              int|None     Reddit only
follower_count     int|None     Twitter, GitHub, Instagram
following_count    int|None     Twitter, GitHub, Instagram
```

```
Post.external_id        str    platform-native ID (t3_xxx / t1_xxx for Reddit, tweet ID for Twitter,
                                repo:id / event:id / network:... for GitHub, shortcode for Instagram)
                                — used for DB dedup
Post.text                str    full text (caption for Instagram)
Post.timestamp           float  Unix epoch UTC
Post.metadata.type       str    "submission" | "comment" | "tweet" | "repo" | "push" | "pr" | "issue" |
                                "fork" | "star" | "create" | "release" | "event" | "network" |
                                "post" | "reel" | "carousel"
Post.metadata.subreddit  str    Reddit only
Post.metadata.score      int    Reddit upvotes (submissions and comments)
Post.metadata.url        str    permalink to the original post/comment/tweet/repo/event/Instagram post
Post.metadata.images     list   extracted image URLs
Post.metadata.tweet_id   str    Twitter only
Post.metadata.retweet_count   int  Twitter only
Post.metadata.favorite_count  int  Twitter only
Post.metadata.reply_count     int  Twitter only
Post.metadata.lang       str    Twitter only
Post.metadata.language   str    GitHub repos only — primary language
Post.metadata.topics     list   GitHub repos only
Post.metadata.stars      int    GitHub repos only
Post.metadata.forks      int    GitHub repos only
Post.metadata.logins     list   GitHub network posts only — follower/following usernames
Post.metadata.direction  str    GitHub network posts only — "followers" | "following"
Post.metadata.is_video         bool  Instagram only
Post.metadata.like_count       int|None  Instagram only — null if hidden by poster
Post.metadata.comment_count    int|None  Instagram only
Post.metadata.video_view_count int|None  Instagram only — videos/reels only
```

### Reddit Collector — 3-source waterfall

`RedditCollector.collect()` (`backend/collector/reddit.py`) tries sources in this order, falling through on failure:

1. **Self-hosted Redlib** (`RedlibCollector` against `REDLIB_URL`, default `http://aria-redlib:8080`) — probed first via a lightweight `GET /`; used if reachable and not serving a bot-challenge page
2. **Reddit's public JSON API** (`RedditJSONCollector` against `www.reddit.com/user/<username>/{about,submitted,comments}.json`) — no credentials needed, paginated via `after` cursors
3. **Public Redlib instances** (`PUBLIC_REDLIB_INSTANCES` list, currently empty by default — populate with known-good public instances as a fallback)

Each source collects from two endpoints per user — submissions and comments — fully paginated up to `limit` (applied independently per endpoint, so total posts can be up to `2 × limit`). Profile metadata (display name, bio, karma, account creation date, avatar) is parsed alongside.

Image extraction is handled per-source: the JSON collector pulls from post `url`, `preview.images`, and `media_metadata` (galleries); the Redlib collector parses thumbnails, markdown-embedded images, and SVG-rendered media blocks from HTML.

**Redlib HTML structure (verified June 2026):**

- Profile: `#user_title`, `#user_description`, `#user_details` (CSS grid: `<label>` + `<div>` pairs for Karma/Created), `#user_icon`
- Submissions: `.post` items, `.post_title a` (last match) for title, `.created[title]` for timestamp, `.post_subreddit` for subreddit, `.post_score[title]` for score
- Comments: `.comment` items, `.comment_body` for text, `.created[title]` for timestamp, `.comment_subreddit` for subreddit, `.comment_score[title]` for score
- Submissions pagination: `<a rel="next">` with `?after=` query param
- Comments pagination: `<a>NEXT</a>` (no rel attribute) with `?after=` query param

### Twitter Collector

Uses **twikit** with browser-extracted cookies. No login flow, no Cloudflare issues.
Contains two monkey patches (documented in `backend/collector/twitter.py`) for upstream twikit bugs active as of March 2026:

- `ClientTransaction` regex patch (Twitter changed `ondemand.s.js` structure)
- `User.__init__` crash patch (bio with no URLs)

Collects: username, display name, bio, location, profile image URL (`_400x400`), creation date, follower/following counts, up to `limit` original tweets (retweets filtered), per-tweet metadata.

### GitHub Collector

Uses the **GitHub public REST API v3** (`backend/collector/github.py`) — no authentication required for public profiles, but rate-limited to 60 requests/hour per IP unless `GITHUB_TOKEN` is set in `.env` (raises the limit to 5,000/hour).

Collects:
- **Profile**: name, bio, location, avatar, follower/following counts, account creation date, public repo count
- **Repos**: up to `limit // 2` most-recently-pushed public repos, each treated as a `"repo"`-type post (name, description, language, topics, stars, forks)
- **Events**: up to 300 public events (pushes, PR opens, issue opens, comments, forks, stars, branch/tag creation, releases) — gives temporal signal for Layer 2 behavioral analysis
- **Followers / Following**: up to 100 usernames each (`NETWORK_LIMIT`), stored as two synthetic `"network"`-type posts rather than individual rows, so they persist in the DB and are visible to Layer 2 without per-user account rows. Surfaced in the frontend via `NetworkPanel.jsx` (tabbed, searchable username grid below the profile card).

If follower/following counts exceed the 100-username cap, the frontend shows a truncation note suggesting `GITHUB_TOKEN` to raise it (the 100-cap itself is a sane default to limit API calls, not a hard platform limit — each 100 usernames costs one paginated call).

### Instagram Collector

Uses **instaloader** in fully anonymous mode (`backend/collector/instagram.py`) — **no login, no session cookies, no Stories.** This is a deliberate, permanent scope decision rather than a missing feature:

- **No login**: ARIA only reads what Instagram serves a logged-out visitor. Private profiles correctly fail with a clear error (`PrivateProfileNotFollowedException` → `ValueError`) rather than being bypassed, consistent with the public-data-only constraint in `CLAUDE.md`.
- **No Stories**: Stories are never public on any platform under any tooling — they require an authenticated, following relationship and expire after 24h. There is no anonymous path to them, so they are out of scope permanently, not pending.
- **Reels and carousel posts fold into the regular post stream** with a `metadata.type` tag (`"post"` | `"reel"` | `"carousel"`), mirroring how the Reddit collector tags submissions vs. comments rather than maintaining separate feeds. A video post in the main public feed is classified as a reel; `GraphSidecar` (carousel) posts expose every child image URL via `metadata.images`.
- **Reliability**: anonymous scraping is the least reliable of the four collectors — there's no fallback tier the way Reddit has. Instagram can rate-limit (`TooManyRequestsException`) or start requiring login mid-pagination (`LoginRequiredException`); the collector catches both and returns whatever posts it gathered rather than failing the whole request, but a thin or empty result is possible. A delay between paginated requests (`INSTAGRAM_REQUEST_DELAY`, default 1.5s + random jitter) reduces — does not eliminate — the chance of being throttled.
- Collects: username, display name, bio, avatar, follower/following counts, and posts (caption, timestamp, like/comment counts where the poster hasn't hidden them, media URLs). Account creation date and a structured location field are not exposed by Instagram's public surface, so they're left `null`/empty respectively.

No credentials are required — there's nothing Instagram-specific to add to `.env` beyond the optional `INSTAGRAM_REQUEST_DELAY` tuning knob.

### OSINT Lookups (✅ Built)

```
POST /api/cases/{case_id}/osint/username-search   { username } → Sherlock results: platforms where handle exists
POST /api/cases/{case_id}/osint/breach-lookup      { email }    → breach list + exposed data types
GET  /api/cases/{case_id}/osint                    list all OSINT lookups for a case
```

**Username enumeration** (`backend/osint.py`) loads site definitions from the installed `sherlock-project` package's `data.json` (400+ platforms) and runs its own concurrent `httpx`-based checker (semaphore-limited, default 30 concurrent) against Sherlock's detection rules (`status_code`, `message`, `response_url` error types). NSFW-flagged sites are filtered out.

**Breach lookup** defaults to **XposedOrNot** (`api.xposedornot.com`, free, no API key, real data). If `HIBP_API_KEY` is set in the environment, it uses HaveIBeenPwned v3 instead (and falls back to XposedOrNot on a 401 from HIBP). Results are stored in `osint_lookups.result_json` regardless of source.

Pre-run all lookups before demo day where possible; demo should favor stored results over live calls for predictability (live OSINT lookups can be slow or rate-limited).

---

## Setup

### 1. Install dependencies

```bash
cd backend
pip install -r requirements.txt
```

`requirements.txt` includes `instaloader` for the Instagram collector alongside the existing `httpx`, `twikit`, `sherlock-project`, etc.

### 2. Environment variables

Create a `.env` file at the project root (used by `docker-compose.yml` and loaded via `python-dotenv` in the backend):

```env
DATABASE_URL=postgresql://aria:aria_password@localhost:5432/aria
JWT_SECRET=your_jwt_signing_secret_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
COOKIE_SECURE=false

# Twitter (required for Twitter collection)
TWITTER_CT0=your_ct0_value_here
TWITTER_AUTH_TOKEN=your_auth_token_here

# GitHub (optional — raises rate limit from 60/hr to 5000/hr per IP)
GITHUB_TOKEN=

# Instagram (optional — tune anonymous request pacing; default is 1.5s + jitter)
INSTAGRAM_REQUEST_DELAY=1.5

# Optional — breach lookup defaults to XposedOrNot if unset
HIBP_API_KEY=
```

To get Twitter cookies:

```
1. Log into x.com in your browser
2. DevTools (F12) → Application → Cookies → https://x.com
3. Copy values for 'ct0' and 'auth_token'
```

Cookies expire after a few weeks. Re-extract from browser when collection starts returning auth errors.

To get a GitHub token (optional, raises rate limit): create a fine-grained or classic personal access token at github.com/settings/tokens — no scopes are required for public-data reads, but GitHub still requires a token to grant the higher rate limit tier.

Instagram requires no credentials at all — collection is fully anonymous.

### 3. Run with Docker Compose (recommended)

```bash
docker compose up --build
```

This starts four services: `postgres` (schema auto-applied from `backend/schema.sql` on first init), `redlib` (self-hosted Reddit frontend), `backend` (FastAPI on port 8000), `frontend` (nginx-served React build on port 80, proxying `/api/` and `/collect/` to the backend container).

### 4. Run locally without Docker

Database:

```bash
psql -d aria -f backend/schema.sql
```

Backend:

```bash
cd backend
uvicorn app:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` in `frontend/.env` to point at the backend (e.g. `http://localhost:8000`).

---

## Usage

### Via the web app

Register → log in → create a case with one or more identifiers → from the case detail screen, trigger **Collect** (Reddit/Twitter/GitHub/Instagram), **Sherlock** (username enumeration), or **Check Breaches** (email) per identifier. Results persist to the case and reload on refresh.

### Python module (synchronous)

```python
from collector.base import collect, save_to_db
import psycopg2

reddit_profile    = collect("reddit", "spez", limit=10000)
twitter_profile   = collect("twitter", "jack", limit=100)
github_profile    = collect("github", "torvalds", limit=100)
instagram_profile = collect("instagram", "natgeo", limit=50)

print(reddit_profile.karma)
print(reddit_profile.subreddits)
for post in reddit_profile.posts:
    print(post.metadata["type"], post.timestamp, post.text[:80])

conn = psycopg2.connect("postgresql://localhost/aria")
account_id = save_to_db(reddit_profile, conn, case_id=1)  # case_id is required
```

### Python module (async — inside FastAPI)

```python
from collector.base import collect_async

profile = await collect_async("instagram", "natgeo", limit=50)
```

Use `collect_async` when inside an already-running event loop. Reddit, GitHub, and Instagram collection are each offloaded to a thread via `run_in_executor` so they don't block FastAPI's event loop; Twitter (twikit) is natively async.

### REST API

```
GET /collect/{platform}/{username}?limit=50
```

Legacy, case-less endpoint — requires authentication (`get_current_user`), returns `AccountProfile.to_dict()` JSON, 404 if user not found. Prefer `POST /api/cases/{case_id}/collect` for anything that should be attached to a case.

### OSINT CLI (standalone testing)

```bash
python osint.py username spez
python osint.py breach someone@example.com
```

---

## PostgreSQL Schema (case-centric, 7 tables — `backend/schema.sql`)

```sql
-- Layer 0: Auth + Case Management
users(id, email, password_hash, full_name, role, created_at)
cases(id, investigator_id→users, title, status, created_at, closed_at)
case_identifiers(id, case_id→cases, identifier_type, value, platform_hint, created_at)

-- Layer 1: Data Collection + OSINT
osint_lookups(id, case_id→cases, lookup_type, input_value, result_json JSONB, created_at)
accounts(id, case_id→cases, platform, username, display_name, bio, location,
         created_at, profile_image_url, karma, follower_count, following_count,
         UNIQUE(case_id, platform, username))
posts(id, account_id→accounts, external_id, text, timestamp, metadata JSONB,
      spike_flag BOOLEAN DEFAULT false,
      UNIQUE(account_id, external_id))

-- Layer 2/3/5: Correlation + Explainability (table exists, nothing writes to it yet)
linkage_results(id, case_id→cases, account_a_id→accounts, account_b_id→accounts,
                 confidence NUMERIC(5,2), shap_json JSONB, created_at,
                 CHECK (account_a_id < account_b_id))

-- Stretch — not created until the corresponding layer is built
graph_edges(source_account_id, target_account_id, edge_type, weight)
feature_vectors(id, account_id, profile_vec, style_vec, temporal_vec, graph_vec, image_vec)
content_analysis(id, account_id→accounts, top_keywords_json, hashtags_json,
                  sentiment_compound, tone_label, cross_post_fingerprint, created_at)
```

`platform` has no DB-level CHECK constraint — any string is accepted, so adding a new collector (as with GitHub and Instagram) never requires a migration. The frontend and `CollectRequest` Pydantic model are what actually constrain which platforms can be triggered from the UI/API.

`accounts` is **per-case**: the same real account collected for two different cases produces two rows. This avoids merge/dedup logic at the cost of re-collection if a suspect reappears — acceptable tradeoff for the hackathon timeline, documented as a known limitation.

`posts.external_id` (platform-native ID) is the dedup key, not `(timestamp, text)` — this is more robust to edited posts and avoids false-duplicate collisions. GitHub network posts use a synthetic ID (`network:followers:<username>`, `network:following:<username>`) since they aren't really individual posts.

---

## Layer 1 → Layer 2 Handoff

`AccountProfile` is the shared data contract between all ARIA layers.

```python
from collector.base import collect   # Layer 1 — built
from features      import extract    # Layer 2 — not yet built

profile  = collect("reddit", "johndoe", limit=10000)
features = extract(profile)
```

---

## Layer 2: Feature Extraction (🔲 Not started)

### 2.1 Profile Similarity Module (MVP)

| Field    | Method                                                    | Library                | Weight |
| -------- | ---------------------------------------------------------- | ------------------------ | ------ |
| Username | Levenshtein + Jaro-Winkler + LCS                          | rapidfuzz               | 0.40   |
| Bio      | Cosine similarity of sentence embeddings                  | sentence-transformers   | 0.35   |
| Temporal | 1 − Jensen-Shannon divergence of posting-hour histograms  | scipy                   | 0.25   |

See **MVP Correlation Scoring Spec** above for the exact formula and output JSON shape.

### 2.2 Content Analysis Module (MVP, new)

- Top-20 keywords per account (TF-IDF)
- Hashtag frequency vector, frequent bigrams
- Cross-post fingerprinting (cosine sim of full post text across platforms)
- Sentiment: VADER compound score + tone label (neutral / positive / aggressive / promotional), computed per account

Planned endpoints:

```
GET /api/accounts/{id}/keywords    top keywords, hashtags, bigrams
GET /api/accounts/{id}/sentiment   sentiment score + tone label
```

### 2.3 Behaviour / Spike-Gap Module (MVP, new)

Rolling 7-day post count per account; flag windows with 3σ deviation from baseline as activity spikes or gaps. Writes `spike_flag` on `posts` (column already exists in schema). GitHub's event stream and Instagram's post timestamps both feed this the same way Reddit/Twitter posts do — no platform-specific logic needed here.

Planned endpoints:

```
GET /api/accounts/{id}/timeline       chronological post events with spike/gap flags
GET /api/cases/{case_id}/timeline     merged timeline across all linked accounts in a case
```

### 2.4 Stylometric Module (STRETCH)

Siamese network on post text. Features: vocabulary richness, sentence length distribution, punctuation patterns, function word frequency, POS tag ratios. Train on PAN 2020 via Colab/Kaggle T4, target AUC > 0.75. **Fallback if not trained in time:** TF-IDF cosine similarity as the stylometric score. Note: Instagram captions tend to be short relative to Reddit/Twitter text, which may weaken this signal for Instagram accounts specifically — worth flagging in the Layer 5 evidence notes if it becomes relevant.

### 2.5 Image Module (STRETCH)

CLIP embeddings for profile images + BLIP captions. Frozen pretrained models — do NOT retrain. If not built, image signal is omitted and weights renormalize (see MVP spec). Instagram and Reddit both supply rich `metadata.images` arrays on individual posts (not just profile images) that could extend this beyond just avatar comparison, if time allows.

### 2.6 Graph Intelligence Module (STRETCH — Layer 4)

GAT on follower/following social graph (Foursquare-Twitter dataset, 496-node subset, trained once and checkpointed — never retrained during demo). Node embeddings feed back into fusion as a 6th feature. GitHub's collected follower/following username lists (`NetworkPanel.jsx` data) are a natural real-data substitute for the Foursquare-Twitter dataset if there's time to wire it in — Instagram and Twitter's friend graphs aren't collected at this depth currently.

---

## Layer 3: Correlation Engine (🔲 Not started)

**MVP**: weighted sum of available Layer 2 component scores → confidence 0–1 → band (Low/Medium/High). See spec above.

**STRETCH**: XGBoost trained on 6 features (5 component scores + GAT embedding) → linkage probability 0–1.

Candidate generation (both modes): rapidfuzz username filter (>0.40) + bio embedding threshold (>0.35) → top-10 candidates per seed account.

Planned endpoints:

```
GET /api/cases/{case_id}/candidates   ranked candidate matches with confidence scores
GET /api/evidence/{pair_id}           per-signal breakdown for a candidate pair
GET /api/graph/{case_id}              social graph nodes + edges for React Flow (stretch — empty until Layer 4 built)
```

---

## Layer 5: Explainability (🔲 Not started)

**MVP**: per-component score breakdown (see JSON shape in MVP spec) — same shape SHAP would produce, displayed as a horizontal bar chart with plain-English labels (e.g. "Writing Style Match: 91%").

**STRETCH**: SHAP `TreeExplainer` on the trained XGBoost fusion model, same output shape, stored in `linkage_results.shap_json`.

Research gap closed by ARIA: StyleLink (ICWSM 2025) does stylometry + GNN but has zero XAI component. ARIA adds explainability to the pipeline regardless of MVP/stretch path.

---

## Layer 6: Profiling + Report Generation (🔲 Not started)

Aggregates all layer outputs into a suspect profile and generates an exportable SOCMINT report.

- Suspect profile: aggregated bio, all linked accounts with confidence, top keywords, sentiment summary, posting behaviour summary, network cluster summary (if Layer 4 built)
- Report sections: case metadata, seed identifiers, discovered accounts, correlation logic per link, evidence breakdown, open-source references, confidence notes, limitations disclaimer
- Confidence note auto-added if any signal is missing (e.g. "Image score unavailable — excluded, weights renormalized") — should also surface platform-specific caveats, e.g. "Instagram collection used anonymous access; result set may be incomplete" when relevant

Planned endpoints:

```
GET /api/cases/{case_id}/report       structured SOCMINT report as JSON
GET /api/cases/{case_id}/report/pdf   report as PDF (WeasyPrint)
```

**Fallback** if WeasyPrint dependency issues arise: serve JSON only, browser print-to-PDF. The JSON + investigator notes field is sufficient to demonstrate the feature.

---

## Frontend — Screens

| #   | Screen                                                                    | Status         |
| --- | ---------------------------------------------------------------------------| -------------- |
| 1   | Login / Register                                                          | ✅ Built       |
| 2   | Case Dashboard                                                            | ✅ Built       |
| 3   | New Case / Input (multi-identifier)                                       | ✅ Built       |
| 4   | Case Detail (identifiers, collect, OSINT, collected accounts + post feed, GitHub network panel) | ✅ Built |
| 5   | Processing Screen (7-layer progress)                                      | 🔲 Not started |
| 6   | Results Screen (ranked candidates)                                        | 🔲 Not started |
| 7   | Evidence Panel (score breakdown, keywords, tone, hashtags)                | 🔲 Not started |
| 8   | Graph View (React Flow)                                                   | 🔲 Not started |
| 9   | Timeline View                                                             | 🔲 Not started |
| 10  | Report Export Screen                                                      | 🔲 Not started |

Screens 1–4 cover everything Layer 0 and Layer 1 currently support. Screens 5–10 depend on Layers 2–6 and haven't been started. The old standalone `ARIACollector.jsx` (mock-data demo mode, typewriter log effect) has been removed in favor of the integrated `CaseDetail.jsx` flow — there is currently no mock-data fallback UI; if the backend is unreachable, requests simply fail and surface an error banner.

`NetworkPanel.jsx` is GitHub-specific (renders the two synthetic follower/following posts as a tabbed, searchable username grid) and only mounts when `acc.platform === "github"`. Instagram doesn't currently collect a follower/following username list (only counts), so it has no equivalent panel.

---

## Known Issues / Notes for Next Claude Session

1. **twikit monkey patches** — Two patches in `backend/collector/twitter.py` for twikit bugs active as of March 2026. Check twikit changelog before removing; they may be fixed in a later release.

2. **`PUBLIC_REDLIB_INSTANCES` is empty** — the third tier of the Reddit waterfall (public Redlib fallbacks) currently has no instances configured in `backend/collector/reddit.py`. Populate from the [Redlib instance list](https://github.com/redlib-org/redlib-instances) before relying on it as a real fallback; right now Reddit collection effectively only has two tiers (self-hosted → JSON API) in practice.

3. **Twitter cookie expiry** — Cookies expire after ~2–3 weeks. Re-extract `ct0` and `auth_token` from browser DevTools when collection returns auth errors.

4. **LinkedIn** — not implemented at all yet (no collector, no mock data path). If needed for the demo, plan for pre-crawled/mock data labelled clearly in the UI as "Pre-loaded OSINT data."

5. **Reddit waterfall priority order** — Self-hosted Redlib is tried first (fastest, most reliable when the container is healthy), then Reddit's own JSON API, then public Redlib instances. If Redlib's HTML structure changes, re-inspect and update selectors in `RedlibCollector` (`backend/collector/reddit.py`).

6. **`limit` is per-endpoint for Reddit** — `limit=500` fetches up to 500 submissions AND up to 500 comments separately, so the total `posts` list can be up to 1000 entries. Adjust if a strict total cap is needed.

7. **Profile image is Redlib-proxied for Reddit** — `profile_image_url` for Reddit accounts collected via Redlib points at the responding instance, not Reddit's CDN directly (resolved via `resolve_url`, substituting `REDLIB_PUBLIC_URL` when behind Docker). This URL may break if that instance goes offline. For Layer 2 image processing (stretch), fetch and cache image bytes immediately after collection.

8. **`accounts` is per-case** — the same real-world account collected in two different cases creates two separate rows (see schema note above). `save_to_db()` requires `case_id`; `ON CONFLICT` target is `(case_id, platform, username)`.

9. **`linkage_results.shap_json` is dual-purpose** — will hold either the MVP weighted-breakdown JSON or a real SHAP breakdown, both in the same per-signal shape, once Layer 3/5 is built. Frontend/report code should not assume SHAP-specific fields exist.

10. **Sherlock/breach lookups should be pre-run before demo** — results are stored in `osint_lookups`; prefer demoing from stored results rather than live calls (rate limits / latency risk), especially for Sherlock's 400+ site sweep.

11. **No mock-data fallback exists anymore** — the old `frontend/src/lib/mockData.js` generator is unused dead code since `ARIACollector.jsx` was retired. Either wire it into `CaseDetail.jsx` as an explicit "demo mode" fallback (with a visible banner, as previously planned) or remove it. It currently only knows Reddit/Twitter shapes anyway — would need GitHub/Instagram sample data added if revived.

12. **Redis is in the tech-stack table but not in `docker-compose.yml`** — no caching/rate-limiting/job-queue service is actually running. Add the service if Layer 2/3 background jobs need it.

13. **GitHub unauthenticated rate limit is low** — 60 requests/hour per IP without `GITHUB_TOKEN`, and each page of 100 followers/following costs one call on top of the profile/repo/event calls. A profile with many followers collected without a token will exhaust the limit quickly. Set `GITHUB_TOKEN` before any demo involving GitHub collection, and don't re-collect the same account repeatedly while testing.

14. **Instagram collection is the least reliable of the four collectors** — anonymous-only scraping has no fallback tier the way Reddit's waterfall does. Instagram may rate-limit (`TooManyRequestsException`) or demand login mid-pagination (`LoginRequiredException`); the collector returns a partial result rather than erroring out completely, but a thin or empty post list is a real possibility, especially for high-follower accounts. Pre-run and cache Instagram collection before a demo rather than relying on it live — same guidance as Sherlock/breach lookups.

15. **Instagram Stories are permanently out of scope, not a future item** — Stories require an authenticated, following relationship with the target and expire in 24h; there is no anonymous, public path to them under any tooling. Building Stories collection would mean operating a logged-in session against a target's privacy boundary, which conflicts with the public-data-only constraint in `CLAUDE.md`. Don't pick this up as a "nice to have" without first reopening that constraint with the team.

16. **`platform` has no DB CHECK constraint** — unlike `case_identifiers.identifier_type` or `osint_lookups.lookup_type`, the `accounts.platform` column accepts any string. This is why GitHub and Instagram needed no migration to add, but also means a typo'd platform string (e.g. `"instagran"`) would silently create a new, separate platform bucket rather than erroring. Worth adding a CHECK constraint once the platform list stabilizes.

---

## Project Status

| Layer                                                                            | Status                | Owner        |
| ----------------------------------------------------------------------------------| ------------------------| --------------|
| 0 — Auth + Case Management                                                       | ✅ Built              | Backend      |
| 1 — Data Collection (Reddit, Twitter, GitHub, Instagram, incl. OSINT lookups)    | ✅ Built, case-scoped | Backend      |
| 2 — Feature Extraction (MVP: profile/content/behaviour)                          | 🔲 Not started        | ML + Backend |
| 2 — Feature Extraction (stretch: stylometry, image)                              | 🔲 Not started        | ML           |
| 3 — Correlation Engine                                                           | 🔲 Not started        | ML + Backend |
| 4 — Graph Intelligence (stretch)                                                 | 🔲 Not started        | ML           |
| 5 — Explainability                                                               | 🔲 Not started        | Backend      |
| 6 — Profiling + Report                                                           | 🔲 Not started        | Backend      |
| Frontend — Screens 1–4 (auth, dashboard, new case, case detail)                  | ✅ Built              | Frontend     |
| Frontend — Screens 5–10 (processing, results, evidence, graph, timeline, report) | 🔲 Not started        | Frontend     |

**Build schedule**: Phase 1 (Foundation) — done → Phase 2 (ML/Correlation Core, collectors expanded with GitHub + Instagram) — in progress → Phase 3 (Frontend + Viz) → Phase 4 (Polish + Demo Prep).
