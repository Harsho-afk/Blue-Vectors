# ARIA — Adaptive Resolution of Identity Across Platforms

**Cross-platform identity resolution and SOCMINT case management system.**

## Project Overview

ARIA is a case-centric OSINT (Open Source Intelligence) investigation platform. An investigator creates a case, attaches seed identifiers (username, email, phone, profile URL), and ARIA collects public digital footprints, correlates accounts across platforms, generates analytical insights, and produces structured intelligence reports — all from a single-click investigation runner with real-time progress streaming over Server-Sent Events (SSE).

> **Design principle: AI recommends, investigator decides.** ARIA never claims two accounts ARE the same person. Every correlation comes with a confidence score (0–100%), a per-signal breakdown, and evidence citations.

### Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                     Frontend (React 19 + Vite, nginx)             │
│  Dashboard · Investigation Runner · Case Detail · Graph · Timeline│
│  Evidence Panel · Reports · Monitoring · Alerts                   │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ REST (/api) + SSE
┌───────────────────────────────▼───────────────────────────────────┐
│                       Backend (FastAPI, Python 3.12)               │
│  Collection: Reddit · Twitter/X · GitHub · Instagram                │
│  OSINT: Maigret · breach lookup · Holehe · dorking · phone · Gravatar│
│  Features: username/bio(NLP)/image(CLIP)/temporal/community/stylo   │
│  Correlator: tiered hard-link + circumstantial scoring               │
│  Insights: timezone · geo · cross-link · pattern-of-life ·           │
│            coordination · risk · keywords · consistency ·           │
│            distinctiveness                                          │
│  LLM Analyst (Groq / Gemini) · Report Builder (JSON/HTML/PDF) ·      │
│  Monitoring Engine (background scheduler, 30s sweep)                 │
└───────────────────────────────┬───────────────────────────────────┘
                                 │
┌───────────────────────────────▼───────────────────────────────────┐
│  PostgreSQL 17 (14 tables) · Redlib (Reddit proxy) · WA sidecar    │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **Data collection** from Reddit (self-hosted Redlib → Reddit JSON API → public Redlib fallback), Twitter/X (via `twikit` with browser cookies), GitHub, and Instagram (via `instagrapi`)
- **OSINT lookups**: Maigret username enumeration, breach lookup (XposedOrNot / HIBP), Holehe email discovery, Serper.dev-backed web dorking, phone OSINT (phonenumbers, Telegram, WhatsApp, Twilio Lookup), Gravatar
- **Correlation engine** combining multiple similarity signals (username, bio/NLP, profile image via CLIP, temporal patterns, community overlap, stylometry) into a tiered hard-link + circumstantial confidence score
- **9 analytical insight modules**: timezone, network geography, cross-link detection, pattern-of-life, coordination detection, risk assessment, keyword extraction, identity consistency, distinctiveness
- **LLM-powered intelligence briefings** (Groq first, Gemini fallback) — every claim is cited to specific insight IDs, no external knowledge is introduced
- **SOCMINT report builder**: JSON, HTML preview, and PDF export
- **Monitoring/watchlist**: background scheduler (30-second sweep) with baseline snapshots, change detection, and investigator alerts
- **One-click investigation runner** that orchestrates the full pipeline and streams progress live via SSE

### Tech Stack

| Layer          | Technology                                                                                                    |
| -------------- | --------------------------------------------------------------------------------------------------------------- |
| Frontend       | React 19, Vite, TypeScript, TanStack Router/Table/Query, Zustand, Tailwind CSS 4, Radix UI, Recharts, react-force-graph-2d |
| Backend        | FastAPI, Uvicorn, Python 3.12                                                                                 |
| Database       | PostgreSQL 17 (14 tables, auto-migrated on startup)                                                           |
| Auth           | JWT via `python-jose`, httpOnly cookie, `bcrypt` password hashing                                             |
| Collection     | httpx, aiohttp, twikit, instagrapi, socid-extractor, Maigret, Holehe                                          |
| NLP / ML       | sentence-transformers, scikit-learn, rapidfuzz, imagehash, Pillow, scipy, numpy                               |
| LLM            | Groq (`llama-3.3-70b-versatile`, via raw HTTPX) and/or `google-genai` (`gemini-2.0-flash`)                     |
| Reporting      | ReportLab (PDF), Jinja2 (HTML)                                                                                |
| Phone OSINT    | phonenumbers, Telethon (Telegram), whatsapp-web.js sidecar, Twilio Lookup v2, duckduckgo-search                |
| Web search     | Serper.dev (Google results)                                                                                  |
| Infrastructure | Docker Compose (postgres, redlib, wa-sidecar, backend, frontend)                                              |

---

## Prerequisites

- **Docker** and **Docker Compose** v2+
- A `.env` file in the project root (next to `docker-compose.yml`) — see [Step 2](#step-2-create-your-env-file) below

### Credentials you'll want on hand
Only `DATABASE_URL` and `JWT_SECRET` are strictly required to boot the app. Everything else unlocks a specific collector/feature and is optional until you need it:

| Variable(s) | Unlocks | How to get it |
| --- | --- | --- |
| `DATABASE_URL` | App boot | PostgreSQL connection string |
| `JWT_SECRET` | Secure auth | Any random string (defaults to an insecure dev value if unset) |
| `TWITTER_CT0`, `TWITTER_AUTH_TOKEN` | Twitter/X collection | Log into x.com → DevTools → Application → Cookies → copy `ct0` and `auth_token` |
| `INSTAGRAM_SESSION_ID`, `INSTAGRAM_USERNAME` | Instagram collection | Log into instagram.com → DevTools → Application → Cookies → copy `sessionid` |
| `GITHUB_TOKEN` | Higher GitHub rate limit (60/hr → 5000/hr) | Personal access token, no scopes needed |
| `GROQ_API_KEY` and/or `GEMINI_API_KEY` | Intelligence briefings | Groq console (free tier) and/or Google AI Studio |
| `SERPER_API_KEY` | Web dorking | serper.dev (2,500 free queries on signup) |
| `HIBP_API_KEY` | Breach lookup upgrade (falls back to free XposedOrNot if unset) | haveibeenpwned.com API |
| `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION` | Telegram phone OSINT | my.telegram.org → API development tools, then generate a session with Telethon |
| `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` or `TWILIO_API_KEY`/`TWILIO_API_KEY_SECRET` | Twilio phone Lookup (carrier, line type, caller name) | Twilio console |
| `WHATSAPP_SIDECAR_URL` | WhatsApp phone OSINT | Runs automatically as the `wa-sidecar` Docker service (needs a one-time QR scan) |

---

## Step-by-Step Setup and Installation Guide

### Step 1: Clone the repository

```bash
git clone https://github.com/Harsho-afk/Blue-Vectors.git
cd Blue-Vectors
```

### Step 2: Create your `.env` file

Create a `.env` file in the project root, next to `docker-compose.yml`:

```env
# Required
DATABASE_URL=postgresql://aria:aria_password@localhost:5432/aria
JWT_SECRET=replace-with-a-long-random-string

# Optional — auth cookie tuning (defaults shown)
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
COOKIE_SECURE=false

# Optional — Twitter/X collection
TWITTER_CT0=
TWITTER_AUTH_TOKEN=

# Optional — Instagram collection
INSTAGRAM_SESSION_ID=
INSTAGRAM_USERNAME=
INSTAGRAM_PROXY=

# Optional — GitHub rate limit boost
GITHUB_TOKEN=

# Optional — LLM intelligence briefings (at least one recommended)
GROQ_API_KEY=
GEMINI_API_KEY=

# Optional — web dorking
SERPER_API_KEY=
DORKING_SEARCH_CONCURRENCY=4

# Optional — breach lookup upgrade
HIBP_API_KEY=

# Optional — Telegram phone OSINT
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION=

# Optional — Twilio phone Lookup
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_API_KEY=
TWILIO_API_KEY_SECRET=
```

Leave `WHATSAPP_SIDECAR_URL` and `DATABASE_URL`'s host alone — `docker-compose.yml` injects the container-network values below on top of your `.env` automatically at runtime, so you don't need to set them yourself:

```
REDLIB_URL=http://aria-redlib:8080
REDLIB_PUBLIC_URL=http://localhost:8080
WHATSAPP_SIDECAR_URL=http://aria-wa-sidecar:3333
```

---

## Docker Setup and Execution Steps

Docker Compose brings up all 5 services together: `postgres`, `redlib` (Reddit proxy), `wa-sidecar` (WhatsApp lookups), `backend`, and `frontend`.

### 1. Build and start all services

```bash
docker compose up --build
```

Run detached with `-d`:

```bash
docker compose up --build -d
```

The `backend` service waits for `postgres` to report healthy (via `pg_isready`) before starting, and the Postgres container automatically applies `backend/schema.sql` on first initialization.

### 2. Services and ports

| Service      | Container name    | Port(s)   | Purpose                                              |
| ------------ | ------------------ | --------- | ----------------------------------------------------- |
| `postgres`   | `aria-postgres`    | 5432      | PostgreSQL 17, schema auto-applied on first init       |
| `redlib`     | `aria-redlib`      | 8080      | Self-hosted Reddit frontend (privacy-preserving proxy) |
| `wa-sidecar` | `aria-wa-sidecar`  | 3333      | WhatsApp Web lookup service (needs a one-time QR scan) |
| `backend`    | `aria-backend`     | 8000      | FastAPI application                                    |
| `frontend`   | `aria-frontend`    | 80        | nginx serving the built React app, proxies `/api` and `/collect` to the backend |

### 3. Link WhatsApp (first run only)

The `wa-sidecar` service authenticates via a QR code the first time it starts, the same way WhatsApp Web does:

```bash
docker compose logs -f wa-sidecar
```

Scan the printed QR code from **WhatsApp → Linked Devices → Link a Device**. The session is persisted in the `wa_auth` Docker volume, so this is only needed once.

### 4. Access the application

Once containers report healthy, open `http://localhost` (port 80) for the frontend. The backend API is reachable directly at `http://localhost:8000`, and Redlib at `http://localhost:8080`.

### 5. View logs

```bash
docker compose logs -f            # all services
docker compose logs -f backend    # a single service
```

### 6. Stop the services

```bash
docker compose down
```

Add `-v` to also remove the `postgres_data` and `wa_auth` volumes (this deletes all stored case data and the WhatsApp session):

```bash
docker compose down -v
```

### 7. Rebuild after code changes

```bash
docker compose up --build
```

Compose only rebuilds the images whose build context changed.

---

## Usage

### Web application

1. **Register / log in** — create an investigator account
2. **New investigation** — create a case with a title and one or more seed identifiers (username, email, phone, or profile URL)
3. **Run investigation** (`POST /api/cases/{id}/run`) — one click runs the full pipeline (collection → Maigret enumeration → breach/phone lookups → correlation → insights → intelligence briefing), streamed live via SSE
4. **Case detail** — view collected accounts, posts, OSINT results, correlation matches with evidence breakdowns, and the investigation graph
5. **Reports** — generate versioned SOCMINT reports (JSON, HTML preview, or PDF)
6. **Monitoring** — enroll targets for continuous watchlist monitoring; the background scheduler sweeps every 30 seconds and raises alerts on detected changes

### REST API reference

All endpoints below require authentication via the `aria_token` JWT cookie set on login.

**Auth** (`/api/auth`)
```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me
PUT    /api/auth/profile
```

**Cases** (`/api/cases`)
```
POST   /api/cases                              Create case
GET    /api/cases                              List cases
GET    /api/cases/{case_id}                    Case detail
DELETE /api/cases/{case_id}                     Delete case
PATCH  /api/cases/{case_id}/title
PATCH  /api/cases/{case_id}/status
POST   /api/cases/{case_id}/identifiers         Add identifier
PUT    /api/cases/{case_id}/identifiers/{id}
DELETE /api/cases/{case_id}/identifiers/{id}
POST   /api/cases/{case_id}/correlate           Run correlation
GET    /api/cases/{case_id}/results
POST   /api/cases/{case_id}/intelligence        Generate LLM briefing
GET    /api/cases/{case_id}/intelligence
POST   /api/cases/{case_id}/collect             Collect from a single platform
POST   /api/cases/{case_id}/run                 One-click full investigation (SSE)
```

**OSINT** (`/api/cases/{case_id}/osint`)
```
POST   /api/cases/{case_id}/osint/username-search    Maigret enumeration
POST   /api/cases/{case_id}/osint/breach-lookup
POST   /api/cases/{case_id}/osint/holehe-lookup
POST   /api/cases/{case_id}/osint/phone-lookup
POST   /api/cases/{case_id}/osint/dorking
POST   /api/cases/{case_id}/osint/import-account
GET    /api/cases/{case_id}/osint                    List all lookups for a case
```

**Analysis**
```
GET    /api/cases/{case_id}/graph               Investigation graph (nodes + edges)
GET    /api/cases/{case_id}/timeline            Chronological event timeline
```

**Reports** (`/api/cases/{case_id}/reports`)
```
GET    /api/cases/{case_id}/reports/readiness
POST   /api/cases/{case_id}/reports             Generate a new report version
GET    /api/cases/{case_id}/reports             List report versions
GET    /api/cases/{case_id}/reports/{report_id}
GET    /api/cases/{case_id}/reports/{report_id}/html
GET    /api/cases/{case_id}/reports/{report_id}/pdf
```

**Monitoring** (`/api`)
```
POST   /api/cases/{case_id}/monitor-targets
GET    /api/cases/{case_id}/monitor-targets
GET    /api/monitor-targets/{target_id}
PATCH  /api/monitor-targets/{target_id}
POST   /api/monitor-targets/{target_id}/pause
POST   /api/monitor-targets/{target_id}/resume
DELETE /api/monitor-targets/{target_id}
POST   /api/monitor-targets/{target_id}/check
POST   /api/monitor-targets/{target_id}/reset-baseline
GET    /api/monitor-targets/{target_id}/events
GET    /api/alerts
PATCH  /api/alerts/{alert_id}
GET    /api/alerts/dashboard
POST   /api/alerts/mark-all-read
```

---

## Confidence Scoring

Correlation scores from `correlator.py` are mapped to bands:

| Band   | Range   | Meaning                                   |
| ------ | ------- | -------------------------------------------|
| Low    | 0–40%   | Weak or coincidental similarity            |
| Medium | 41–70%  | Possible match, needs manual review        |
| High   | 71–100% | Strong convergence across multiple signals |

A detected hard link (e.g. an explicit cross-reference between accounts) raises the confidence floor to 80% regardless of the circumstantial score. Every result includes a per-signal breakdown of which evidence contributed.

---

## Ethical Constraints

- **Public data only** — no authentication bypass, no private endpoints, no credential stuffing
- **AI recommends, investigator decides** — the system surfaces evidence and confidence scores; it never asserts a definitive identity match
- **All LLM output is citation-linked** — every claim in an intelligence briefing references specific insight IDs; the model is only given computed insights, never raw posts, and is instructed never to introduce outside knowledge
- **Monitoring requires explicit enrollment** — each watchlist target needs a stated reason and expiration date; there is no blanket surveillance
