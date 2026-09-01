"""Periodic scrape run for the GitHub Actions scheduled workflow.

Pulls a modest, bounded number of pages from each source's full "cars"
category (no query filter) and upserts into whatever database
backend/database.py resolves to (D1, via D1_PROXY_URL/D1_PROXY_AUTH_TOKEN in
this workflow's case). Kept deliberately smaller than a one-off manual deep
scrape — this runs on a schedule (see .github/workflows/scrape.yml), so
coverage builds up gradually across many runs instead of one large burst,
which is both gentler on the source sites and self-healing: the now
cooldown-aware scrapers (backend/scrapers/rate_limit_state.py) will just skip
cleanly if a previous run left an active rate-limit cooldown.

Env vars (all optional):
  SCRAPE_PAGES_PER_SOURCE: pages to pull per source per run (default 15)
  SCRAPE_LIVENESS_BATCH: listings to liveness-check this run (default 300)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scrapers.riyasewana import RiyasewanaScraper
from backend.scrapers.ikman import IkmanScraper
from backend.scrapers.liveness import verify_active_listings_liveness
from backend.database import upsert_cars_batch, mark_stale_listings, init_db


def run_source(name, scraper, max_pages):
    total_upserted = 0
    total_scraped = 0
    for p in range(1, max_pages + 1):
        items = scraper.scrape_page(page_num=p)
        if not items:
            print(f"[{name}] page {p}: empty, stopping (end of results or blocked)", flush=True)
            break
        n = upsert_cars_batch(items)
        total_scraped += len(items)
        total_upserted += n
        print(f"[{name}] page {p}/{max_pages}: {len(items)} items, upserted {n}", flush=True)
        if getattr(scraper, "last_rate_limited", False):
            print(f"[{name}] rate-limit cooldown active — stopping this run early.", flush=True)
            break
    return total_scraped, total_upserted


def main():
    max_pages = int(os.environ.get("SCRAPE_PAGES_PER_SOURCE", "15"))
    liveness_batch = int(os.environ.get("SCRAPE_LIVENESS_BATCH", "300"))

    init_db()

    stale_count = mark_stale_listings()
    print(f"Time-based sweep: marked {stale_count} listings stale (not re-seen recently).", flush=True)

    liveness_result = verify_active_listings_liveness(batch_size=liveness_batch)
    print(f"Liveness check: {liveness_result}", flush=True)

    riya_scraped, riya_upserted = run_source("Riyasewana", RiyasewanaScraper(), max_pages)
    ikman_scraped, ikman_upserted = run_source("Ikman", IkmanScraper(), max_pages)

    print(
        f"DONE: riyasewana(scraped={riya_scraped}, upserted={riya_upserted}) "
        f"ikman(scraped={ikman_scraped}, upserted={ikman_upserted})",
        flush=True,
    )


if __name__ == "__main__":
    main()
