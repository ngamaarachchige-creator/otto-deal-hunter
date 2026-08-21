# 🚗 OTTO · The unfair advantage in the Lankan car market

Automated automotive arbitrage and vehicle deal acquisition intelligence platform for Sri Lanka. Scrapes and tracks real-time market data across **Riyasewana** and **Ikman.lk**, benchmarks statistical floor averages, flags underpriced deals (>15% below market), and manages an interactive 6-stage flip CRM pipeline.

## ✨ Features
- **Natural Language (NLU) Search**: Query naturally (e.g. `Toyota aqua 2019`, `2015 celerio in colombo under 5.5m`).
- **Live Market Valuation Benchmarks**: Statistical price curves across 550+ make/model/year combinations.
- **Turnover Velocity & Liquidity Ratings**: 4-tier dealer turnaround classification (3-7 day instant cash to 45+ day).
- **Ad Repost & Relisting Detection**: Identifies churned ads re-posted by tired sellers.
- **Acquisition CRM & Flip Calculator**: 6-stage Kanban board with profit/ROI calculators.
- **Dual-Mode Database**: SQLite local default with zero-config Supabase / Cloud PostgreSQL support.

## 🚀 Quick Start
```bash
# 1. Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Run the application
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
Open [http://localhost:8000](http://localhost:8000) in your browser.
