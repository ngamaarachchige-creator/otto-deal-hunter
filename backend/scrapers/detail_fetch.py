"""Fetches real vehicle spec fields (fuel type, transmission, body type, and the
seller's own description text) from each listing's own detail page.

The search-results cards on both sites only carry title/price/location/mileage —
they don't include fuel type, transmission, or the seller's description at all.
The scrapers used to guess transmission/fuel/body type from keyword hits in the
card text, which almost never contained "diesel"/"manual"/etc., so listings
silently defaulted to "Petrol"/"Unknown" most of the time regardless of what the
ad actually said. The description wasn't captured anywhere, even though it's the
main source of real condition detail (accessories, faults, service history) for
AI Inspect to reason over.

Uses plain `requests` with a normal browser User-Agent rather than scrapling's
Fetcher — Fetcher's request fingerprint is what has been getting flagged by these
sites' rate limiter. A plain request to the same ad pages held up through initial
testing, but under this session's total request volume Riyasewana rate-limited
plain requests too (confirmed 429 from two different devices on the same network,
so it's a network-level ban, not a per-fingerprint one) — treat "not rate-limited"
as "less likely to trip it sooner", not immunity.
"""
import html
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional
import requests

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Defensive cap — a normal seller description is a few sentences, but this keeps
# one pathological page from bloating a row or an AI prompt.
_MAX_DESCRIPTION_LEN = 3000


class DetailRateLimited(Exception):
    pass


def _clean_description(raw: str) -> str:
    text = html.unescape(raw.replace("\\n", "\n").replace("\\r", "")).strip()
    # Collapse runs of blank lines left over from the ad's own formatting.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text[:_MAX_DESCRIPTION_LEN]


def _extract_meta_description(html: str) -> Optional[str]:
    """Most listing sites (both of ours included) populate <meta name="description">
    with the seller's own ad text for SEO — this is the shared extraction path.
    Scans whole <meta> tags rather than assuming attribute order, since some pages
    put other attributes (e.g. data-rh="") before name="description"."""
    for tag_match in re.finditer(r'<meta\b[^>]*>', html):
        tag = tag_match.group(0)
        if 'name="description"' not in tag:
            continue
        content_match = re.search(r'content="([^"]*)"', tag)
        if content_match:
            text = _clean_description(content_match.group(1))
            return text or None
    return None


def fetch_riyasewana_specs(url: str, timeout: int = 12) -> Optional[Dict[str, str]]:
    """Parses the "Gear" / "Fuel Type" detail rows and seller description off a
    Riyasewana ad page."""
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    except requests.RequestException:
        return None
    if resp.status_code == 429:
        raise DetailRateLimited()
    if resp.status_code != 200:
        return None
    # Neither site declares a charset in Content-Type, so requests falls back to
    # ISO-8859-1 per the HTTP spec default — even though the actual pages are
    # UTF-8, which mangles Sinhala text and emoji in descriptions into mojibake.
    resp.encoding = "utf-8"

    pairs = dict(re.findall(
        r'<span class="detail-label">([^<]+)</span><span class="detail-value">([^<]*)</span>',
        resp.text
    ))
    out = {}
    if pairs.get("Gear", "").strip():
        out["transmission"] = pairs["Gear"].strip()
    if pairs.get("Fuel Type", "").strip():
        out["fuel_type"] = pairs["Fuel Type"].strip()
    description = _extract_meta_description(resp.text)
    if description:
        out["description"] = description
    return out or None


def fetch_ikman_specs(url: str, timeout: int = 12) -> Optional[Dict[str, str]]:
    """Parses the embedded {"label":"...","value":"..."} spec entries and seller
    description off an Ikman ad page."""
    try:
        resp = requests.get(url, timeout=timeout, headers=_HEADERS)
    except requests.RequestException:
        return None
    if resp.status_code == 429:
        raise DetailRateLimited()
    if resp.status_code != 200:
        return None
    resp.encoding = "utf-8"

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
    description = _extract_meta_description(text)
    if description:
        out["description"] = description
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
                # Tells upsert_cars_batch this item's transmission/fuel_type/body_type/
                # description came from the real ad page, not a keyword guess off the
                # search card — safe to overwrite whatever's already stored for this listing.
                item["_specs_verified"] = True

    return rate_limited
