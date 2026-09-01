"""Actively verifies whether 'active' listings are still live on the source site.

Unlike the time-based mark_stale_listings() sweep (which only catches ads not
re-seen in a scrape for a while), this hits each listing directly. The primary
signal is the listing's own thumbnail image going missing (404) — both source
sites drop the photo as soon as an ad is delisted/sold, and checking an image
URL is far cheaper than rendering the full ad page. Only when there's no image
on record, or the image check is inconclusive, do we fall back to fetching the
ad page itself and checking for the "no longer available" HTTP 404/410.
"""
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
from urllib.parse import urlparse
from scrapling import Fetcher

from backend.database import get_db_connection, IS_POSTGRES
from .rate_limit_state import is_cooling_down, record_rate_limit

DEAD_STATUS_CODES = {404, 410}
# 403 included alongside 429: Riyasewana escalated from a soft 429 to a hard 403
# block under this session's sustained volume, so both need to trigger the same
# cooldown — treating only 429 as "rate limited" left the harder block invisible
# to this whole mechanism.
RATE_LIMITED_STATUS_CODES = {429, 403}


class RateLimited(Exception):
    pass


def _image_dead(image_url: str) -> Optional[bool]:
    """Returns True if the image is confirmed gone, False if confirmed present,
    or None if inconclusive (network hiccup, unexpected status) — caller should
    fall back to checking the ad page itself in that case."""
    if is_cooling_down(urlparse(image_url).netloc):
        return None
    try:
        # stream=True + immediate close: we only need the status line, not the
        # image bytes, so this stays cheap even though HEAD isn't supported by
        # every static file host.
        resp = requests.get(image_url, timeout=10, stream=True)
        resp.close()
        if resp.status_code in DEAD_STATUS_CODES:
            return True
        if resp.status_code in RATE_LIMITED_STATUS_CODES:
            record_rate_limit(urlparse(image_url).netloc, resp.status_code)
            raise RateLimited()
        if resp.status_code == 200:
            return False
        return None
    except RateLimited:
        raise
    except requests.RequestException:
        return None


def _is_dead(url: str, image_url: Optional[str], fetcher: Fetcher, retries: int = 2) -> bool:
    # Small per-request delay spreads out the batch so it doesn't read as a burst
    # to the source site's anti-bot/rate-limiting.
    time.sleep(0.4)

    if image_url:
        img_result = _image_dead(image_url)
        if img_result is True:
            return True
        if img_result is False:
            return False
        # None (inconclusive) falls through to the ad-page check below.

    host = urlparse(url).netloc
    if is_cooling_down(host):
        return False

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
            record_rate_limit(host, resp.status)
            raise RateLimited()
        return False
    return False


def verify_active_listings_liveness(
    max_workers: int = 2,
    batch_size: Optional[int] = 150,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> dict:
    """Checks 'active' listings and flips dead ones to 'stale'.

    With batch_size set, only the batch_size listings least-recently actively
    verified are checked (oldest/never-verified first), so this can run as a
    quick step on every scrape without re-checking the whole table (which is
    slow and risks tripping the source site's rate limiter) — the full active
    set just gets cycled through gradually across scrapes instead. Since the
    image-first check is much cheaper than a full page render, this can afford
    a bigger batch per run than the old page-only version could.

    Returns {"checked": n, "marked_stale": n}.
    """
    conn = get_db_connection()
    if IS_POSTGRES:
        import psycopg2.extras
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cursor = conn.cursor()
    query = (
        "SELECT id, url, image_url FROM cars WHERE status = 'active' AND url IS NOT NULL AND url != '' "
        "ORDER BY last_verified_at ASC NULLS FIRST"
    )
    if batch_size:
        query += f" LIMIT {int(batch_size)}"
    cursor.execute(query)
    rows = [(r["id"], r["url"], r["image_url"]) for r in cursor.fetchall()]
    conn.close()

    total = len(rows)
    dead_ids = []
    checked_ids = []
    fetcher = Fetcher()
    checked = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_id = {pool.submit(_is_dead, url, image_url, fetcher): car_id for car_id, url, image_url in rows}
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
        # D1 caps bound parameters at 100 per statement (confirmed empirically —
        # 300 threw "too many SQL variables"); 100 stays comfortably under
        # SQLite's much higher default (999) and Postgres too, so one number
        # works safely across every backend this file might run against.
        chunk = 100
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
