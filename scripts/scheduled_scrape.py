"""Periodic scrape run for the GitHub Actions scheduled workflow.

IMPORTANT: earlier versions of this script always hit each source's
unfiltered "cars" category, page 1..N, every single run. That endpoint is
sorted newest-first, so successive runs re-fetch almost the same newest
listings over and over — the vast majority of each run's "upserted" count
was just re-touching cars already in the DB, not discovering new ones. That
is why the total barely moved run over run despite scraping "working".

Fix: rotate through a fixed list of makes, one (or a few) per run, using the
site's own make-filtered search (both scrapers already support `make=`).
Each run then covers a different slice of each site's full inventory instead
of re-skimming the same newest-listings page, so coverage actually grows
toward the full catalog (~10k+ on ikman alone) over successive scheduled
runs. Rotation index is derived from wall-clock time (no persisted state
needed) so it advances deterministically run to run.

Env vars (all optional):
  SCRAPE_PAGES_PER_SOURCE: pages to pull per make per source per run (default 15)
  SCRAPE_LIVENESS_BATCH: listings to liveness-check this run (default 300)
  SCRAPE_MAKES_PER_RUN: how many makes to rotate through per run (default 2)
  SCRAPE_INTERVAL_HOURS: hours between scheduled runs, for rotation math (default 12)
  D1_DAILY_WRITE_CAP: safety ceiling on rows_written/UTC day before this run
    stops scraping early (default 90000, leaving headroom under D1's 100k
    free-tier cap -- see backend/database.py get_write_budget_today()).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.scrapers.riyasewana import RiyasewanaScraper
from backend.scrapers.ikman import IkmanScraper
from backend.scrapers.liveness import verify_active_listings_liveness
from backend.database import (
    upsert_cars_batch, mark_stale_listings, init_db,
    get_write_budget_today, record_write_budget,
)

# Rough coverage of the SL used-car market, roughly ordered by listing volume.
MAKES = [
    "toyota", "honda", "nissan", "suzuki", "micro", "mitsubishi",
    "kia", "hyundai", "mazda", "perodua", "daihatsu", "isuzu",
    "bmw", "mercedes-benz", "audi", "land-rover", "jeep", "ford",
    "peugeot", "renault", "mg", "tata", "jaguar", "volkswagen",
]


def run_source(name, scraper, max_pages, make="", write_cap=90000):
    total_upserted = 0
    total_scraped = 0
    label = f"{name}/{make or 'unfiltered'}"
    for p in range(1, max_pages + 1):
        spent = get_write_budget_today()
        if spent >= write_cap:
            print(f"[{label}] D1 write budget hit ({spent}/{write_cap} today) — stopping to avoid the 100k free-tier cap.", flush=True)
            break
        items = scraper.scrape_page(page_num=p, make=make)
        if not items:
            print(f"[{label}] page {p}: empty, stopping (end of results or blocked)", flush=True)
            break
        n = upsert_cars_batch(items)
        record_write_budget(n)
        total_scraped += len(items)
        total_upserted += n
        print(f"[{label}] page {p}/{max_pages}: {len(items)} items, {n} actually written (rest unchanged)", flush=True)
        if getattr(scraper, "last_rate_limited", False):
            print(f"[{label}] rate-limit cooldown active — stopping this run early.", flush=True)
            break
    return total_scraped, total_upserted


def pick_makes_for_this_run(n):
    """Deterministic rotation through MAKES based on wall-clock time, so no
    state needs to be persisted between runs (each GH Actions run is a fresh
    checkout)."""
    interval_hours = int(os.environ.get("SCRAPE_INTERVAL_HOURS", "12"))
    slot = int(time.time() // (interval_hours * 3600))
    start = (slot * n) % len(MAKES)
    return [MAKES[(start + i) % len(MAKES)] for i in range(n)]


def main():
    max_pages = int(os.environ.get("SCRAPE_PAGES_PER_SOURCE", "15"))
    liveness_batch = int(os.environ.get("SCRAPE_LIVENESS_BATCH", "300"))
    makes_per_run = int(os.environ.get("SCRAPE_MAKES_PER_RUN", "2"))
    write_cap = int(os.environ.get("D1_DAILY_WRITE_CAP", "90000"))

    init_db()

    spent = get_write_budget_today()
    print(f"D1 write budget so far today (UTC): {spent}/{write_cap}", flush=True)
    if spent >= write_cap:
        print("Already at today's D1 write budget — skipping this run entirely (stale sweep, liveness, and scraping all write rows).", flush=True)
        return

    stale_count = mark_stale_listings()
    record_write_budget(stale_count)
    print(f"Time-based sweep: marked {stale_count} listings stale (not re-seen recently).", flush=True)

    liveness_result = verify_active_listings_liveness(batch_size=liveness_batch)
    record_write_budget(liveness_result.get("checked", 0))
    print(f"Liveness check: {liveness_result}", flush=True)

    makes = pick_makes_for_this_run(makes_per_run)
    print(f"This run's make rotation: {makes}", flush=True)

    riya = RiyasewanaScraper()
    ikman = IkmanScraper()
    riya_scraped = riya_upserted = ikman_scraped = ikman_upserted = 0

    for make in makes:
        if get_write_budget_today() >= write_cap:
            break
        rs, ru = run_source("Riyasewana", riya, max_pages, make=make, write_cap=write_cap)
        riya_scraped += rs
        riya_upserted += ru
        if getattr(riya, "last_rate_limited", False):
            break  # cooldown active, no point trying the next make on this source

    for make in makes:
        if get_write_budget_today() >= write_cap:
            break
        is_, iu = run_source("Ikman", ikman, max_pages, make=make, write_cap=write_cap)
        ikman_scraped += is_
        ikman_upserted += iu
        if getattr(ikman, "last_rate_limited", False):
            break

    print(
        f"DONE: riyasewana(scraped={riya_scraped}, upserted={riya_upserted}) "
        f"ikman(scraped={ikman_scraped}, upserted={ikman_upserted}) "
        f"| D1 write budget now: {get_write_budget_today()}/{write_cap}",
        flush=True,
    )


if __name__ == "__main__":
    main()
