# ARIA — Adaptive Resolution of Identity Across Platforms

**Cross-platform identity resolution and SOCMINT case management system.**

ARIA is a case-centric OSINT investigation platform. An investigator creates a case, attaches seed identifiers (username, email, phone, profile URL), and ARIA collects public digital footprints, correlates accounts across platforms, generates analytical insights, and produces structured intelligence reports — all from a single-click investigation runner with real-time progress streaming.

> **Design principle: AI recommends, investigator decides.** ARIA never claims two accounts ARE the same person. Every correlation comes with a confidence score (0–100%), a per-signal breakdown, and evidence citations.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Frontend (React 19 + Vite)                   │
│   Dashboard · Investigation Runner · Case Detail · Graph · Timeline │
│   Evidence Panel · Reports · Monitoring · Settings                  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ REST + SSE
┌────────────────────────────────▼────────────────────────────────────┐
│                        Backend (FastAPI)                             │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌──────────┐ │
│  │Collection│ │  OSINT   │ │ Features  │ │Correlat.│ │ Insights │ │
│  │ Reddit   │ │ Maigret  │ │ Username  │ │ Tiered  │ │ Timezone │ │
│  │ Twitter  │ │ Breach   │ │ Bio (NLP) │ │ Hard    │ │ Geo      │ │
│  │ GitHub   │ │ Holehe   │ │ Image     │ │ links + │ │ Patterns │ │
│  │Instagram │ │ Dorking  │ │ (CLIP)    │ │ Circum- │ │ Risk     │ │
│  │          │ │ Phone    │ │ Temporal  │ │ stantial│ │ Keywords │ │
│  │          │ │ Gravatar │ │ Community │ │         │ │ Coordin. │ │
│  │          │ │          │ │ Stylometry│ │         │ │ Cross-ref│ │
│  └──────────┘ └──────────┘ └───────────┘ └─────────┘ └──────────┘ │
│                                                                     │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────────┐   │
│  │ LLM Analyst  │  │ Report Builder│  │ Monitoring Engine      │   │
│  │ (Groq/Gemini)│  │ (JSON + PDF)  │  │ (Background scheduler) │   │
│  └──────────────┘  └───────────────┘  └────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│  PostgreSQL (14 tables) · Redlib (Reddit proxy) · WA Sidecar       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### Data Collection
- **Reddit** — 3-source waterfall: self-hosted Redlib → Reddit JSON API → public Redlib instances
- **Twitter/X** — via twikit with browser-extracted cookies
- **GitHub** — REST API v3 (repos, events, follower/following network)
- **Instagram** — instaloader, fully anonymous, public-only (no login, no Stories)

### OSINT Lookups
- **Maigret** — username enumeration across 500+ platforms with structured profile extraction and category tagging
- **Breach lookup** — XposedOrNot (free, no key) with HIBP v3 fallback
- **Holehe** — email-to-account discovery (100+ sites via password reset probing)
- **Dorking** — DuckDuckGo-powered web search with deterministic templates + LLM query planning
- **Phone OSINT** — phonenumbers (carrier/country), Telegram (Telethon), WhatsApp (sidecar service)
- **Gravatar** — email-to-avatar/profile lookup
- **Lead scoring** — each Maigret hit scored 0–100 to separate strong leads from noise

### Identity Correlation (7 Signals)
| Signal | Method | Library |
|--------|--------|---------|
| Username similarity | Levenshtein + Jaro-Winkler + partial ratio | rapidfuzz |
| Bio similarity | Cosine similarity of sentence embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Profile image | CLIP cosine similarity with baseline calibration | CLIP (clip-ViT-B-32) |
| Temporal patterns | 1 - Jensen-Shannon divergence of posting-hour histograms | scipy |
| Community overlap | Jaccard similarity of subreddit/topic sets | — |
| Stylometry | Cosine similarity of character n-gram TF-IDF vectors | scikit-learn |
| Geography | Timezone and location agreement across accounts | — |

**Tiered correlation engine:**
- **Tier 1 (hard links)** — bio cross-links, shared email/phone, Maigret linked accounts → confidence floor 80%
- **Tier 2 (conditional)** — username similarity weighted by distinctiveness
- **Tier 3 (corroborating)** — bio, temporal, community, stylometry, geography signals

### Analytical Insights (8 Modules)
- **Timezone estimation** — inferred from posting patterns
- **Network geography** — subreddit and location-based geo signals
- **Cross-link detection** — URLs, handles, emails found in bios/posts linking to other platforms
- **Pattern of life** — activity rhythms, posting frequency, spike/gap detection
- **Coordination detection** — synchronized activity across accounts
- **Risk assessment** — behavioral risk indicators
- **Keyword extraction** — TF-IDF top keywords per account
- **Identity consistency** — cross-checks insights from Pass 1 for contradictions/corroboration

### Intelligence Briefing
LLM-powered analyst (Groq or Gemini) synthesizes insights into a structured intelligence briefing with every claim cited to specific insight IDs. The LLM only sees computed insights, never raw posts.

### SOCMINT Reports
Deterministic report builder assembling versioned report snapshots from case data. Includes methodology notes, confidence assessments, limitations, and open-source references. Available as JSON, rendered HTML preview, or PDF export (via ReportLab).

### Monitoring / Watchlist
Background scheduler that continuously monitors enrolled targets:
- Captures periodic snapshots (profile re-collection, Maigret, dorking, breach)
- Diffs against baseline to detect profile changes, new posts, network changes, new breaches
- Creates events and investigator-facing alerts with priority levels
- Triggers correlation recomputation on identity-affecting changes

### One-Click Investigation Runner
`POST /api/cases/{case_id}/run` orchestrates the full pipeline via SSE streaming:

```
Maigret (username enum) ──┐
Deep collectors (platform) ├── concurrent ──→ Correlation ──┐
Breach lookup (email) ─────┤                  Insights ─────├── concurrent ──→ Intelligence Briefing
Phone OSINT ───────────────┘                                │
Holehe (email) ────────────┘                                └── sequential after both finish
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, Vite, TypeScript, TanStack Router/Table/Query, shadcn/ui, Tailwind CSS 4, Zustand, Recharts, react-force-graph-2d |
| **Backend** | FastAPI (Python 3.12), Uvicorn |
| **Database** | PostgreSQL 17 (14 tables) |
| **Auth** | JWT (httpOnly cookies), bcrypt |
| **Collection** | httpx, twikit, instaloader, Maigret, Holehe |
| **NLP/ML** | sentence-transformers, CLIP (clip-ViT-B-32), scikit-learn, rapidfuzz, scipy, numpy |
| **LLM** | Google Generative AI (Gemini), Groq |
| **Reporting** | ReportLab (PDF), Jinja2 (HTML) |
| **Phone OSINT** | phonenumbers, Telethon (Telegram), whatsapp-web.js (sidecar) |
| **Web Search** | duckduckgo-search |
| **Infrastructure** | Docker Compose (5 services) |

---

## Quick Start

### Prerequisites
- Docker and Docker Compose
- A `.env` file at the project root

### 1. Configure environment

Create a `.env` file in the project root:

```env
DATABASE_URL=postgresql://aria:aria_password@localhost:5432/aria
JWT_SECRET=your_jwt_signing_secret_here
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440
COOKIE_SECURE=false

# Twitter (required for Twitter collection)
TWITTER_CT0=your_ct0_value
TWITTER_AUTH_TOKEN=your_auth_token

# GitHub (optional — raises rate limit from 60/hr to 5000/hr)
GITHUB_TOKEN=

# Instagram (optional — tune anonymous request pacing, default 1.5s + jitter)
INSTAGRAM_REQUEST_DELAY=1.5

# LLM Analyst (at least one required for intelligence briefings)
GROQ_API_KEY=
GEMINI_API_KEY=

# Breach lookup (optional — defaults to XposedOrNot if unset)
HIBP_API_KEY=

# Telegram phone OSINT (optional)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_SESSION=
```

**Twitter cookies:** log into x.com → DevTools (F12) → Application → Cookies → copy `ct0` and `auth_token`. Cookies expire after ~2–3 weeks.

**GitHub token:** create at github.com/settings/tokens — no scopes needed for public data reads.

### 2. Run with Docker Compose

```bash
docker compose up --build
```

This starts 5 services:
| Service | Port | Description |
|---------|------|-------------|
| `postgres` | 5432 | PostgreSQL with schema auto-applied on first init |
| `redlib` | 8080 | Self-hosted Reddit frontend (privacy proxy) |
| `wa-sidecar` | 3333 | WhatsApp Web lookup service |
| `backend` | 8000 | FastAPI application |
| `frontend` | 80 | nginx-served React build |

### 3. Run locally without Docker

**Database:**
```bash
psql -d aria -f backend/schema.sql
```

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL` in `frontend/.env` to point at the backend (e.g. `http://localhost:8000`).

---

## Usage

### Web Application

1. **Register / Log in** — create an investigator account
2. **New Investigation** — create a case with a title and one or more seed identifiers (username, email, phone, or profile URL)
3. **Run Investigation** — one-click runs the full pipeline: Maigret enumeration → deep platform collection → breach/phone lookups → correlation → insights → intelligence briefing, all streamed live via SSE
4. **Case Detail** — view collected accounts, posts, OSINT results, correlation matches, evidence breakdowns, and the investigation graph
5. **Reports** — generate versioned SOCMINT reports (JSON / HTML preview / PDF)
6. **Monitoring** — enroll targets for continuous watchlist monitoring with automated change detection and alerts

### REST API

All endpoints require authentication via JWT cookie.

**Auth:**
```
POST   /api/auth/register
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/me
```

**Cases:**
```
POST   /api/cases                           Create case with identifiers
GET    /api/cases                           List cases
GET    /api/cases/{id}                      Case detail with all associated data
DELETE /api/cases/{id}                      Delete case (cascade)
POST   /api/cases/{id}/identifiers          Add identifiers to case
POST   /api/cases/{id}/collect              Collect from a single platform
POST   /api/cases/{id}/run                  One-click full investigation (SSE)
```

**OSINT:**
```
POST   /api/cases/{id}/osint/username-search     Maigret username enumeration
POST   /api/cases/{id}/osint/breach-lookup        Breach lookup
POST   /api/cases/{id}/osint/phone-lookup         Phone OSINT
POST   /api/cases/{id}/osint/dorking              Web dorking search
POST   /api/cases/{id}/osint/holehe               Email-to-account discovery
GET    /api/cases/{id}/osint                      List all OSINT lookups for case
```

**Analysis:**
```
GET    /api/cases/{id}/graph                Investigation graph (nodes + edges)
GET    /api/cases/{id}/timeline             Chronological event timeline
```

**Reports:**
```
POST   /api/cases/{id}/reports              Generate new report version
GET    /api/cases/{id}/reports              List report versions
GET    /api/cases/{id}/reports/{rid}        Retrieve report JSON
GET    /api/cases/{id}/reports/{rid}/html   Rendered HTML preview
GET    /api/cases/{id}/reports/readiness    Check report generation readiness
```

**Monitoring:**
```
POST   /api/cases/{id}/monitor-targets      Enroll target for monitoring
GET    /api/cases/{id}/monitor-targets      List monitored targets
PATCH  /api/monitor-targets/{id}            Update monitoring config
DELETE /api/monitor-targets/{id}            Remove from watchlist
GET    /api/alerts                          List investigator alerts
PATCH  /api/alerts/{id}                     Update alert status
```

---

## Database Schema (14 Tables)

```
── Auth & Case Management ──────────────────────
users               Investigator accounts
cases               Investigation cases (owned by investigator)
case_identifiers    Seed identifiers per case (username/email/phone/URL)

── Data Collection & OSINT ─────────────────────
accounts            Collected platform profiles (per-case)
posts               Individual posts/events per account
osint_lookups       Maigret, breach, holehe, phone, dorking results

── Correlation & Analysis ──────────────────────
linkage_results     Pairwise account correlations with confidence scores
insights            Deterministic analytical insights (7 categories)
intelligence_reports  LLM-synthesized intelligence briefings
socmint_reports     Versioned SOCMINT report snapshots

── Monitoring System ───────────────────────────
monitor_targets     Profiles under active monitoring
monitor_snapshots   Point-in-time state captures for diffing
monitor_events      Detected changes between snapshots
alerts              Investigator-facing notifications
```

---

## Project Structure

```
Blue-Vectors/
├── docker-compose.yml              5-service orchestration
├── .env                            Environment variables (not committed)
│
├── backend/
│   ├── app.py                      FastAPI application + CORS + lifespan
│   ├── auth.py                     JWT, bcrypt, DB helpers
│   ├── schema.sql                  PostgreSQL schema (14 tables)
│   ├── routes_auth.py              Auth endpoints
│   ├── routes_cases.py             Case CRUD + per-case collection
│   ├── routes_osint.py             OSINT lookup endpoints
│   ├── routes_run.py               One-click investigation runner (SSE)
│   ├── routes_graph.py             Investigation graph assembly
│   ├── routes_timeline.py          Chronological timeline assembly
│   ├── routes_reports.py           SOCMINT report generation
│   ├── routes_monitor.py           Watchlist monitoring API
│   ├── features.py                 7-signal feature extraction
│   ├── correlator.py               Tiered pairwise correlation engine
│   ├── lead_scorer.py              Maigret lead scoring (0-100)
│   ├── dorking.py                  Web dorking survey agent
│   ├── osint.py                    Maigret + breach lookup
│   ├── monitor_engine.py           Background monitoring scheduler
│   ├── collect_stream.py           Streaming collection helper
│   ├── collector/
│   │   ├── base.py                 Collection entrypoints + DB save
│   │   ├── models.py               AccountProfile / Post dataclasses
│   │   ├── reddit.py               Reddit collector (3-source waterfall)
│   │   ├── twitter.py              Twitter collector (twikit)
│   │   ├── github.py               GitHub collector (REST API v3)
│   │   ├── instagram.py            Instagram collector (instaloader)
│   │   ├── phone.py                Phone OSINT (phonenumbers + Telegram + WhatsApp)
│   │   ├── gravatar.py             Gravatar email lookup
│   │   └── holehe_lookup.py        Email-to-account discovery
│   ├── insights/
│   │   ├── orchestrator.py         Pass 1 + Pass 2 insight pipeline
│   │   ├── timezone.py             Timezone estimation
│   │   ├── network_geo.py          Geographic inference
│   │   ├── cross_link.py           Cross-platform link detection
│   │   ├── pattern_of_life.py      Activity pattern analysis
│   │   ├── coordination.py         Coordination detection
│   │   ├── risk.py                 Risk assessment
│   │   ├── keywords.py             Keyword extraction
│   │   ├── consistency.py          Identity consistency (Pass 2)
│   │   └── distinctiveness.py      Username distinctiveness scoring
│   ├── llm/
│   │   ├── analyst.py              LLM intelligence analyst (Groq/Gemini)
│   │   └── citation_check.py       Citation validation
│   ├── reporting/
│   │   ├── builder.py              Deterministic report assembly
│   │   ├── collector.py            Case data loader for reports
│   │   ├── confidence.py           Confidence band notes
│   │   ├── limitations.py          Methodology limitations
│   │   ├── references.py           Open-source reference builder
│   │   ├── render_html.py          HTML report renderer
│   │   └── render_pdf.py           PDF report renderer (ReportLab)
│   └── validation/
│       └── split_half_test.py      Split-half reliability testing
│
├── frontend/
│   ├── src/
│   │   ├── routes/                 TanStack Router file-based routes
│   │   ├── features/               Auth, Dashboard, Settings, Errors
│   │   ├── components/             Investigation graph, evidence panel,
│   │   │                           timeline, reports, monitoring, OSINT,
│   │   │                           correlation results, dorking, breach,
│   │   │                           phone results, comment search, etc.
│   │   ├── context/                Auth, theme, layout, search providers
│   │   ├── stores/                 Zustand auth store
│   │   └── lib/                    API client, utilities
│   └── Dockerfile                  Multi-stage build (Node → nginx)
│
└── wa_sidecar/
    ├── wa_sidecar.js               WhatsApp Web lookup service
    └── Dockerfile                  Puppeteer + Chromium container
```

---

## Confidence Scoring

Correlation scores are mapped to confidence bands:

| Band | Range | Meaning |
|------|-------|---------|
| Low | 0–40% | Weak or coincidental similarity |
| Medium | 41–70% | Possible match, needs manual review |
| High | 71–100% | Strong convergence across multiple signals |

Every score includes a per-signal breakdown explaining which signals contributed and which were unavailable (with weights renormalized accordingly).

---

## Ethical Constraints

- **Public data only** — no authentication bypass, no private endpoints, no credential stuffing
- **Instagram Stories permanently out of scope** — requires authenticated following relationship; no anonymous path exists
- **AI recommends, investigator decides** — system surfaces evidence and confidence, never makes definitive identity claims
- **All LLM output is citation-linked** — every claim references specific insight IDs; the LLM never introduces external knowledge
- **Monitoring requires explicit enrollment** — no blanket surveillance; each target needs a stated reason and expiration date
