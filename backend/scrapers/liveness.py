"""Actively verifies whether 'active' listings are still live on the source site.

Unlike the time-based mark_stale_listings() sweep (which only catches ads not
re-seen in a scrape for a while), this hits each listing's own URL directly.
Both Riyasewana and Ikman return HTTP 410 with an "ad no longer available"
page once a listing is removed or sold, which is what we check for.
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
from scrapling import Fetcher

from backend.database import get_db_connection, IS_POSTGRES

DEAD_STATUS_CODES = {404, 410}
RATE_LIMITED_STATUS_CODES = {429}


def _is_dead(url: str, fetcher: Fetcher, retries: int = 2) -> bool:
    for attempt in range(retries + 1):
        try:
            resp = fetcher.get(url, timeout=15)
        except Exception:
            # Network hiccup / timeout isn't proof the ad is gone; leave it alone.
            return False
        if resp.status in DEAD_STATUS_CODES:
            return True
        if resp.status in RATE_LIMITED_STATUS_CODES and attempt < retries:
            time.sleep(3 * (attempt + 1))
            continue
        return False
    return False


def verify_active_listings_liveness(
    max_workers: int = 5,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Checks every 'active' listing's URL and flips dead ones to 'stale'.

    Returns {"checked": n, "marked_stale": n}.
    """
    conn = get_db_connection()
    if IS_POSTGRES:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cursor = conn.cursor()
    cursor.execute("SELECT id, url FROM cars WHERE status = 'active' AND url IS NOT NULL AND url != ''")
    rows = [(r["id"], r["url"]) for r in cursor.fetchall()]
    conn.close()

    total = len(rows)
    dead_ids = []
    fetcher = Fetcher()
    checked = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {pool.submit(_is_dead, url, fetcher): car_id for car_id, url in rows}
        for future in as_completed(future_to_id):
            car_id = future_to_id[future]
            checked += 1
            try:
                if future.result():
                    dead_ids.append(car_id)
            except Exception:
                pass
            if progress_callback:
                progress_callback(checked, total)

    if dead_ids:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if IS_POSTGRES else "?"
        chunk = 500  # keep IN() clauses reasonably sized
        for i in range(0, len(dead_ids), chunk):
            batch = dead_ids[i:i + chunk]
            in_clause = ",".join([placeholder] * len(batch))
            cursor.execute(f"UPDATE cars SET status = 'stale' WHERE id IN ({in_clause})", batch)
        conn.commit()
        conn.close()

    return {"checked": total, "marked_stale": len(dead_ids)}
