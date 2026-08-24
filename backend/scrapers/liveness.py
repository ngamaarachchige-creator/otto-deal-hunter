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
    # Small per-request delay spreads out the batch so it doesn't read as a burst
    # to the source site's anti-bot/rate-limiting.
    time.sleep(0.4)
    for attempt in range(retries + 1):
        try:
            resp = fetcher.get(url, timeout=15)
        except Exception:
            # Network hiccup / timeout isn't proof the ad is gone; leave it alone.
            return False
        if resp.status in DEAD_STATUS_CODES:
            return True
        if resp.status in RATE_LIMITED_STATUS_CODES:
            # Getting rate-limited at all means we're going too fast for this site
            # right now — bail out of the whole batch instead of hammering it further.
            raise RateLimited()
        return False
    return False


class RateLimited(Exception):
    pass


def verify_active_listings_liveness(
    max_workers: int = 2,
    batch_size: Optional[int] = 40,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Checks 'active' listings' URLs and flips dead ones to 'stale'.

    With batch_size set, only the batch_size listings least-recently actively
    verified are checked (oldest/never-verified first), so this can run as a
    quick step on every scrape without re-checking the whole table (which is
    slow and risks tripping the source site's rate limiter) — the full active
    set just gets cycled through gradually across scrapes instead.

    Returns {"checked": n, "marked_stale": n}.
    """
    conn = get_db_connection()
    if IS_POSTGRES:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cursor = conn.cursor()
    query = (
        "SELECT id, url FROM cars WHERE status = 'active' AND url IS NOT NULL AND url != '' "
        "ORDER BY last_verified_at ASC NULLS FIRST"
    )
    if batch_size:
        query += f" LIMIT {int(batch_size)}"
    cursor.execute(query)
    rows = [(r["id"], r["url"]) for r in cursor.fetchall()]
    conn.close()

    total = len(rows)
    dead_ids = []
    checked_ids = []
    fetcher = Fetcher()
    checked = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {pool.submit(_is_dead, url, fetcher): car_id for car_id, url in rows}
        rate_limited = False
        for future in as_completed(future_to_id):
            car_id = future_to_id[future]
            try:
                result = future.result()
            except RateLimited:
                # We're going too fast for this site right now — stop checking
                # more listings this run rather than risk a longer ban.
                rate_limited = True
                for f in future_to_id:
                    f.cancel()
                break
            except Exception:
                result = False
            checked += 1
            checked_ids.append(car_id)
            if result:
                dead_ids.append(car_id)
            if progress_callback:
                progress_callback(checked, total)

    if checked_ids:
        conn = get_db_connection()
        cursor = conn.cursor()
        placeholder = "%s" if IS_POSTGRES else "?"
        now_expr = "NOW()" if IS_POSTGRES else "CURRENT_TIMESTAMP"
        chunk = 500  # keep IN() clauses reasonably sized
        for i in range(0, len(checked_ids), chunk):
            batch = checked_ids[i:i + chunk]
            in_clause = ",".join([placeholder] * len(batch))
            cursor.execute(f"UPDATE cars SET last_verified_at = {now_expr} WHERE id IN ({in_clause})", batch)
        for i in range(0, len(dead_ids), chunk):
            batch = dead_ids[i:i + chunk]
            in_clause = ",".join([placeholder] * len(batch))
            cursor.execute(f"UPDATE cars SET status = 'stale' WHERE id IN ({in_clause})", batch)
        conn.commit()
        conn.close()

    return {"checked": checked, "marked_stale": len(dead_ids), "rate_limited": rate_limited}
