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
- **Dual-Mode Database**: SQLite local default with zero-config Supabase / Cloud PostgreSQL support.

## 🚀 Quick Start

```bash
./run.sh
```

This creates a local virtualenv (if one doesn't already exist), installs dependencies, and starts the server. Open [http://localhost:8000](http://localhost:8000) in your browser.
