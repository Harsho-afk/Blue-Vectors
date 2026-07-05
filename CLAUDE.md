# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Project: ARIA — Social Media Intelligence & OSINT Platform

Hackathon submission. A lawful SOCMINT/OSINT platform that discovers, correlates, analyzes, and visualizes publicly available digital footprints across multiple online platforms. Investigators create cases, input identifiers, and ARIA discovers accounts, correlates identities with explainable confidence scores, and generates intelligence reports.

## Commit Rules

Do not add any `Co-Authored-By` trailer to commit messages.

## Development Commands

### Full stack (Docker)
```bash
docker compose up --build        # Start all services (postgres, redlib, wa-sidecar, backend, frontend)
docker compose up --build -d     # Detached mode
docker compose down              # Stop all
```
Services: postgres:5432, redlib:8080, wa-sidecar:3333, backend:8000, frontend:80

### Backend only (local dev)
```bash
cd backend
pip install -r requirements.txt
# Also need: pip install torch --index-url https://download.pytorch.org/whl/cpu
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```
Requires `DATABASE_URL` env var pointing to a PostgreSQL instance with schema applied (`psql -d aria -f schema.sql`).

### Frontend only (local dev)
```bash
cd frontend
npm install
npm run dev                      # Vite dev server on :5173
npm run build                    # tsc + vite build
npm run lint                     # ESLint
npm run test                     # Vitest with Playwright browser (headless)
npm run test:watch               # Watch mode
npm run test:coverage            # Coverage report
npm run test:browser:install     # Install Playwright Chromium (first time)
```
Set `VITE_API_URL=http://localhost:8000` for local backend.

### Database
```bash
psql -d aria -f backend/schema.sql   # Initialize schema
```
Docker auto-applies schema via `docker-entrypoint-initdb.d`.

## Architecture

### Backend (FastAPI, Python 3.12)

Single FastAPI app (`backend/app.py`) with routers:

| Router | File | Purpose |
|--------|------|---------|
| Auth | `routes_auth.py` | Register, login, JWT via HttpOnly cookie (`aria_token`) |
| Cases | `routes_cases.py` | CRUD cases + case_identifiers |
| OSINT | `routes_osint.py` | Maigret enumeration, breach lookups, dorking |
| Run | `routes_run.py` | One-click investigation runner (SSE streaming) |
| Graph | `routes_graph.py` | Force-graph data for visualization |
| Timeline | `routes_timeline.py` | Chronological activity feed |
| Reports | `routes_reports.py` | SOCMINT report generation/retrieval |

**Investigation pipeline** (`routes_run.py` — `POST /api/cases/{case_id}/run`):
Seeds run concurrently → Maigret + deep-collect (per platform) + breach + phone OSINT → then correlation + insights run concurrently → then LLM analyst (depends on both). Progress streams via SSE.

**Collectors** (`backend/collector/`):
- `reddit.py` — Redlib scraping (self-hosted → public fallback) + Reddit JSON API
- `twitter.py` — twikit library with browser cookies
- `github.py` — GitHub REST API v3 (unauthenticated or with token)
- `instagram.py` — instagrapi (mobile API)
- `phone.py` — phonenumbers + Telegram + WhatsApp sidecar + DuckDuckGo + Twilio
- `base.py` — `collect_async()` dispatcher, `save_to_db()` persists to accounts/posts tables

**Correlation engine** (`backend/correlator.py`):
Three-tiered scoring: Tier 1 hard links (bio cross-links, shared email/phone → floor 80%), Tier 2 username×distinctiveness, Tier 3 weighted signals (username 0.22, bio 0.16, profile_image 0.15, temporal 0.13, community 0.12, stylometry 0.12, geo 0.10). Outputs confidence 0-100 + SHAP-style breakdown.

**Feature extractors** (`backend/features.py`):
Username similarity (rapidfuzz), bio similarity (sentence-transformers all-MiniLM-L6-v2), profile image (CLIP cosine), temporal patterns (Jensen-Shannon divergence), community overlap (Jaccard), stylometry (char n-gram TF-IDF).

**Insights** (`backend/insights/`):
Pass 1 (parallel): cross_link, timezone, network_geo, pattern_of_life, coordination, risk, keywords.
Pass 2 (sequential): consistency (depends on timezone output).
Orchestrated by `insights/orchestrator.py`.

**LLM Analyst** (`backend/llm/analyst.py`):
Groq (llama-3.3-70b) primary, Gemini 2.0 Flash fallback. Generates structured intelligence briefing from insights + correlations.

**Dorking** (`backend/dorking.py`):
Deterministic query templates + LLM query planner → Serper.dev (Google search) → entity extraction + lead scoring.

**Reporting** (`backend/reporting/`):
Multi-section report builder: collector → references → confidence → limitations → render_html.

### Frontend (React 19, TypeScript, Vite)

Uses TanStack Router (file-based routes in `src/routes/`) + TanStack Query + Zustand + Tailwind CSS v4 + shadcn/ui components.

**Route structure:**
- `(auth)/` — sign-in, sign-up, forgot-password, OTP
- `_authenticated/` — guarded by `AuthContext` (checks `aria_token` cookie)
  - `cases/index` — case list
  - `cases/$id` — case detail (accounts, identifiers, investigation runner, graph, timeline, reports)
  - `investigate/index` — quick investigate page
  - `settings/` — profile, account, appearance, notifications, display

**Key patterns:**
- API base URL from `VITE_API_URL` env var (`src/lib/aria-api.ts`)
- Auth via HttpOnly cookie, context in `src/context/auth-context.tsx`
- Path alias `@/` → `src/`
- UI components in `src/components/ui/` (shadcn)
- Feature components in `src/components/` (correlation-results, dorking-results, intelligence-briefing, investigation-runner, etc.)

### Database (PostgreSQL 17)

Schema in `backend/schema.sql`. Key tables: users, cases, case_identifiers, osint_lookups (JSONB), accounts (with image_embedding JSONB for CLIP vectors), posts (with metadata JSONB), linkage_results (confidence + shap_json), insights, intelligence_reports, socmint_reports.

All accounts are scoped to a case (`case_id` FK). Linkage results enforce `account_a_id < account_b_id` ordering.

### Docker Services

| Service | Image/Build | Port | Purpose |
|---------|-------------|------|---------|
| postgres | postgres:17 | 5432 | Database |
| redlib | tagliasteel/redlib | 8080 | Reddit scraping proxy |
| wa-sidecar | ./wa_sidecar | 3333 | WhatsApp Web.js bridge |
| backend | ./backend | 8000 | FastAPI |
| frontend | ./frontend | 80 | Nginx serving built React |

## Critical Rules

**MVP First.** Priority: Auth → Cases → OSINT Collection → Correlation → Dashboard → Graph → Reports → Advanced AI.

**Explainability.** Every correlation must show per-signal breakdown with confidence bands (Low/Medium/High). Never make absolute identity claims.

**Never assume data availability.** Platforms restrict access. Verify API availability, rate limits, ToS. If inaccessible legally, propose alternatives.

**Prevent scope creep.** Before implementing: Is it required for demo? Can judges see it? Can it be completed in time?

**Hackathon judging focus:** Innovation, technical depth, demonstration quality, practical relevance, UI/UX, scalability potential.

## Environment Variables

Required in `.env` (loaded by backend and docker-compose):
- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET` — HMAC key for JWT tokens
- `TWITTER_CT0`, `TWITTER_AUTH_TOKEN` — Twitter cookies
- `INSTAGRAM_SESSION_ID`, `INSTAGRAM_USERNAME`
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_SESSION`
- `SERPER_API_KEY` — Google search for dorking
- `GROQ_API_KEY` — LLM (primary)
- `GEMINI_API_KEY` — LLM (fallback)
- `TWILIO_API_KEY`, `TWILIO_API_KEY_SECRET` — Phone lookup

Optional: `GITHUB_TOKEN` (higher rate limits), `HIBP_API_KEY` (premium breach), `INSTAGRAM_CSRFTOKEN`, `INSTAGRAM_DS_USER_ID`, `INSTAGRAM_REQUEST_DELAY`, `INSTAGRAM_PROXY`.

## Auth Pattern

JWT stored as HttpOnly cookie named `aria_token`. Backend reads it via `Cookie(default=None)` dependency. Frontend never touches the token directly — just sends credentials, backend sets/clears the cookie.
