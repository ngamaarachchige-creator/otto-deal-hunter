# 🚗 OTTO · The unfair advantage in the Lankan car market

Automated automotive arbitrage and vehicle deal acquisition intelligence platform for Sri Lanka. Scrapes and tracks real-time market data across **Riyasewana** and **Ikman.lk**, benchmarks statistical floor averages, flags underpriced deals, and manages an interactive 6-stage flip CRM pipeline — with an on-device AI copilot to search, inspect, and run scrapes for you.

## ✨ Features

- **OTTO Copilot**: A local Ollama-powered chat agent (sidebar + mascot trigger) that can search listings, explain deals, and kick off live scrapes through natural conversation and tool calling.
- **AI Photo Inspection**: Per-listing AI inspection using a vision model (`qwen3-vl:8b` by default) — flags condition issues and colour-arbitrage opportunities straight from the ad photos.
- **Natural Language (NLU) Search**: Query naturally (e.g. `Toyota aqua 2019`, `2015 celerio in colombo under 5.5m`), plus a Raycast-style `Cmd+K` command bar.
- **Live Market Valuation Benchmarks**: Statistical price curves grouped by make/model/year (with a make/model fallback), refreshed on a short in-memory cache.
- **Confidence-Gated Hot Opportunities**: Deals only surface as HOT/GOOD when backed by enough comparable ads (MEDIUM+ confidence); thin-sample discounts are labeled "unverified" instead of shown as trustworthy deals.
- **Active Listing Liveness Checks**: Beyond time-based staleness, OTTO actively re-checks each listing's own URL (HTTP 404/410) to catch sold/delisted ads — throttled and rate-limit-aware so it doesn't get the scraper banned by source sites.
- **Turnover Velocity & Liquidity Ratings**: 4-tier dealer turnaround classification (3–7 day instant cash to 45+ day slow movers).
- **Ad Repost & Relisting Detection**: Identifies churned ads re-posted by tired sellers.
- **Acquisition CRM & Flip Calculator**: 6-stage Kanban board with profit/ROI calculators.
- **Multi-Mode Database**: Cloudflare D1 in production (via an authenticated Worker proxy), local SQLite by default for development, with zero-config Supabase / Cloud PostgreSQL also supported.
- **Self-Driving Scraper**: An hourly Cloudflare Worker Cron Trigger dispatches a GitHub Actions job that rotates through a 24-make list across both sources, so coverage advances toward each site's real inventory instead of re-skimming the same newest-listings page every run. Cooldown-aware rate-limit handling (escalating backoff, durable cross-run history) keeps it from hammering a source that's actively blocking it, and a daily D1 write-budget guard stops scraping early if it's nearing the free-tier `rows_written` cap.

## 🚀 Quick Start

```bash
./run.sh
```

This creates a local virtualenv (if one doesn't already exist), installs dependencies, and starts the server. Open [http://localhost:8000](http://localhost:8000) in your browser.

The production deployment (Vercel + Cloudflare D1) is live at **otto-deal-hunter.vercel.app** — the app works the same locally, just against a local SQLite DB by default instead of the shared D1 instance.

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in what you need:

- **`D1_PROXY_URL`** / **`D1_PROXY_AUTH_TOKEN`** — production path. Points at the `cf-worker/` Cloudflare Worker that proxies D1 (see below); takes priority over `DATABASE_URL` when set.
- **`DATABASE_URL`** — optional. Leave blank (and `D1_PROXY_URL` unset) to use local SQLite (`data/cars.db`); set to a Postgres/Supabase connection string to run against that instead.
- **`OLLAMA_HOST`** / **`OLLAMA_MODEL`** — required for the OTTO Copilot and AI Inspection features. Point this at wherever Ollama is running (localhost, LAN IP, or Tailscale IP) with a vision-capable model pulled (default `qwen3-vl:8b`).

Without Ollama configured, the core scraping/valuation/CRM dashboard still works — only the AI copilot and photo inspection features are disabled.

## 🤖 Automated Scraping Infrastructure

Production scraping runs unattended, independent of any local machine being on:

- **`cf-worker/`** — a Cloudflare Worker that does two jobs: proxies D1 for the live app (D1 has no direct connection string, only a Workers binding), and carries an hourly Cron Trigger that calls GitHub's `workflow_dispatch` API directly to kick off the scrape.
- **`.github/workflows/scrape.yml`** + **`scripts/scheduled_scrape.py`** — the actual scrape job. Rotates through makes deterministically by wall-clock time (no persisted cursor needed), so each hourly run covers different ground.
- **`backend/scrapers/rate_limit_state.py`** — persistent, cross-run cooldown tracking per host, with a durable event log (`rate_limit_events` table) for auditing how often and when each source blocks the scraper.
- **`scripts/rate_limit_report.py`** — summarizes that history (by host, time of day, cooldown length) to sanity-check the scraping cadence against what each source actually tolerates.

If scraping ever stalls, check (in order): GitHub Actions run history for the `Scheduled scrape` workflow (billing/spending-limit issues surface here as instant failures), the Cloudflare Worker's Cron Trigger status, and `rate_limit_events` for a source-side block outlasting its expected cooldown.

## 🧠 Agent Guidelines

See [AGENTS.md](AGENTS.md) for the deal-scouting protocol OTTO's copilot follows (price-floor discipline, spec disaggregation, colour arbitrage, and flip math transparency).
