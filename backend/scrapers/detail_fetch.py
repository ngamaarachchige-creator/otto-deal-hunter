"""Fetches real vehicle spec fields (fuel type, transmission, body type) from each
listing's own detail page.

The search-results cards on both sites only carry title/price/location/mileage —
they don't include fuel type or transmission at all. The scrapers used to guess
those fields from keyword hits in the card text, which almost never contained
"diesel"/"manual"/etc., so listings silently defaulted to "Petrol"/"Unknown" most
of the time regardless of what the ad actually said.

Uses plain `requests` with a normal browser User-Agent rather than scrapling's
Fetcher — Fetcher's request fingerprint is what has been getting flagged by these
sites' rate limiter; a plain request to the same ad pages was not rate-limited in
testing.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


class DetailRateLimited(Exception):
    pass


def fetch_riyasewana_specs(url: str, timeout: int = 12) -> Optional[Dict[str, str]]:
    """Parses the "Gear" / "Fuel Type" detail rows off a Riyasewana ad page."""
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    except requests.RequestException:
        return None
    if resp.status_code == 429:
        raise DetailRateLimited()
    if resp.status_code != 200:
        return None

    pairs = dict(re.findall(
        r'<span class="detail-label">([^<]+)</span><span class="detail-value">([^<]*)</span>',
        resp.text
    ))
    out = {}
    if pairs.get("Gear", "").strip():
        out["transmission"] = pairs["Gear"].strip()
    if pairs.get("Fuel Type", "").strip():
        out["fuel_type"] = pairs["Fuel Type"].strip()
    return out or None


def fetch_ikman_specs(url: str, timeout: int = 12) -> Optional[Dict[str, str]]:
    """Parses the embedded {"label":"...","value":"..."} spec entries off an Ikman ad page."""
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    except requests.RequestException:
        return None
    if resp.status_code == 429:
        raise DetailRateLimited()
    if resp.status_code != 200:
        return None

    text = resp.text
    out = {}
    m = re.search(r'"label":"Transmission","value":"([^"]+)"', text)
    if m:
        out["transmission"] = m.group(1)
    m = re.search(r'"label":"Fuel type","value":"([^"]+)"', text)
    if m:
        out["fuel_type"] = m.group(1)
    m = re.search(r'"label":"Body type","value":"([^"]+)"', text)
    if m:
        out["body_type"] = m.group(1).split(" / ")[0].strip()
    return out or None


def enrich_with_detail_specs(
    items: List[Dict],
    fetch_fn: Callable[[str], Optional[Dict[str, str]]],
    max_workers: int = 3,
    delay: float = 0.3,
) -> bool:
    """Fetches real specs for each item's detail page and overwrites the card-level
    guesses in place with whatever the ad page actually says. Stops early (leaving
    remaining items on their card-text guesses) if the source site starts rate
    limiting, rather than hammering it further.

    Returns True if rate limiting was hit.
    """
    if not items:
        return False

    def worker(item):
        time.sleep(delay)
        return fetch_fn(item["url"])

    rate_limited = False
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_item = {pool.submit(worker, item): item for item in items if item.get("url")}
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            try:
                specs = future.result()
            except DetailRateLimited:
                rate_limited = True
                for f in future_to_item:
                    f.cancel()
                break
            except Exception:
                specs = None
            if specs:
                item.update(specs)
                # Tells upsert_cars_batch this item's transmission/fuel_type/body_type
                # came from the real ad page, not a keyword guess off the search card —
                # safe to overwrite whatever's already stored for this listing.
                item["_specs_verified"] = True

    return rate_limited
