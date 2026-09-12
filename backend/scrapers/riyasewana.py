import re
import time
import urllib.parse
from datetime import datetime
from typing import List, Dict, Any, Optional
import curl_cffi.requests
from bs4 import BeautifulSoup
from .rate_limit_state import is_cooling_down, record_rate_limit, execute_with_backoff

# Common Sri Lankan districts for normalization
SRI_LANKA_DISTRICTS = [
    "Colombo", "Gampaha", "Kalutara", "Kandy", "Matale", "Nuwara Eliya",
    "Galle", "Matara", "Hambantota", "Jaffna", "Kilinochchi", "Mannar",
    "Vavuniya", "Mullaitivu", "Batticaloa", "Ampara", "Trincomalee",
    "Kurunegala", "Puttalam", "Anuradhapura", "Polonnaruwa", "Badulla",
    "Monaragala", "Ratnapura", "Kegalle"
]

POPULAR_MAKES = [
    "Toyota", "Suzuki", "Honda", "Nissan", "Daihatsu", "Mitsubishi", 
    "Mazda", "Hyundai", "Kia", "Mercedes-Benz", "BMW", "Audi", "Land Rover",
    "Micro", "Perodua", "Peugeot", "DFSK", "Chery", "MG", "Subaru", "Volkswagen", "Renault", "Ford"
]

def clean_price(price_str: str, full_card_text: str = "") -> tuple[float, str, bool]:
    """
    Robust price parser for Sri Lankan vehicle listings.
    Returns (numeric_lkr, display_str, is_negotiable).
    
    Rules:
    - Minimum genuine car price in Sri Lanka is Rs. 200,000.
    - Placeholder/dummy prices (e.g. Rs. 1, Rs. 10, Rs. 100, Rs. 1,000, Rs. 50,000) or 'Negotiable'
      are strictly classified as 'Price on request' with price = 0.0 and is_negotiable = True.
    - Lease down payments ('hand to hand', 'down payment') without full price are flagged.
    """
    # Check for lease balance / down payment indicators
    text_lower = (full_card_text + " " + price_str).lower()
    is_lease_downpayment = any(k in text_lower for k in ["hand to hand", "down payment", "advance only", "to hand", "hand 1"])

    candidates = []
    
    # 1. Search in price_str and full_card_text for currency patterns: Rs. 5,250,000 / Rs 26,000,000 / LKR 4,800,000
    for src in [price_str, full_card_text]:
        if not src:
            continue
        matches = re.findall(r'(?:Rs\.?|LKR)\s*([\d,]+)', src, re.IGNORECASE)
        for m in matches:
            digits = re.sub(r'[^\d]', '', m)
            if digits:
                val = float(digits)
                candidates.append(val)
                
    # Filter candidates: genuine vehicle prices in Sri Lanka are >= 200,000 LKR and <= 350,000,000 LKR
    genuine_prices = [c for c in candidates if 200000 <= c <= 350000000]
    if genuine_prices:
        # If lease downpayment was detected and the price is unusually small (< 2.5M for modern car), flag it
        price_val = genuine_prices[0]
        if is_lease_downpayment and price_val < 2500000:
            return 0.0, "Lease Down Payment", True
        return price_val, f"Rs. {int(price_val):,}", False
        
    # Check if there are raw digits in price_str alone (e.g. '5250000')
    if price_str:
        p_lower = price_str.lower().strip()
        if "negotiable" not in p_lower and "call" not in p_lower:
            digits = re.sub(r'[^\d]', '', price_str)
            if digits:
                val = float(digits)
                if 200000 <= val <= 350000000:
                    return val, f"Rs. {int(val):,}", False

    # Any unstated or dummy placeholder (Rs. 1, Rs. 10, Negotiable) is treated as Price on request
    return 0.0, "Price on request", True

def clean_mileage(mileage_str: str, year: Optional[int] = None) -> tuple[Optional[int], str]:
    """
    Parse mileage string into (km_int, display_str).
    Discards dummy placeholders like 1 km, 10 km, 1234 km on used cars.
    """
    if not mileage_str:
        return None, ""
    cleaned = re.sub(r'[^\d]', '', mileage_str)
    if cleaned:
        try:
            km = int(cleaned)
            # Filter dummy placeholder mileages
            if km < 500 or km in [1, 10, 100, 1000, 1234, 12345, 123456, 999999]:
                return None, ""
            if 500 <= km <= 800000:
                return km, f"{km:,} km"
        except Exception:
            pass
    return None, ""

def detect_make_and_model(title: str, url: str) -> tuple[str, str]:
    """Extract standard Make and Model from title or URL"""
    cleaned_title = title.replace("Car", "").replace("for sale", "").strip()
    detected_make = "Other"
    
    for make in POPULAR_MAKES:
        if re.search(r'\b' + re.escape(make) + r'\b', cleaned_title, re.IGNORECASE):
            detected_make = make
            break
            
    # Extract model by stripping make and common year/modifiers
    model = cleaned_title
    if detected_make != "Other":
        model = re.sub(r'\b' + re.escape(detected_make) + r'\b', '', model, flags=re.IGNORECASE).strip()
    # Remove year if present in title
    model = re.sub(r'\b(19\d{2}|20\d{2})\b', '', model).strip()
    # Clean redundant punctuation
    model = re.sub(r'[\s\-]+', ' ', model).strip()
    
    return detected_make, model if model else "General"

def normalize_district(location: str) -> str:
    """Map town/city to Sri Lankan District"""
    if not location:
        return "All Island"
    loc_clean = location.strip()
    for d in SRI_LANKA_DISTRICTS:
        if d.lower() in loc_clean.lower():
            return d
    return loc_clean

class RiyasewanaScraper:
    def __init__(self):
        self.base_url = "https://riyasewana.com"

    def _fetch_with_backoff(self, url: str):
        return execute_with_backoff(curl_cffi.requests.get, "riyasewana.com", url=url, impersonate="chrome120", timeout=10, verify=False)

    def build_search_url(self, query: str = "", make: str = "", model: str = "", 
                         min_price: float = None, max_price: float = None, 
                         page: int = 1) -> str:
        if make and model:
            path = f"/cars/{make.lower().strip()}/{model.lower().strip()}"
        elif make:
            path = f"/cars/{make.lower().strip()}"
        elif query:
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', query.strip().lower()).strip('-')
            path = f"/{slug}" if slug else "/cars"
        else:
            path = "/cars"

        url = self.base_url + path
        params = []
        if page > 1:
            params.append(f"page={page}")
        if min_price and min_price >= 200000:
            params.append(f"price_min={int(min_price)}")
        if max_price:
            params.append(f"price_max={int(max_price)}")

        if params:
            url += "?" + "&".join(params)
        return url

    def scrape_page(self, page_num: int = 1, query: str = "", make: str = "", 
                     model: str = "", min_price: float = None, max_price: float = None) -> List[Dict[str, Any]]:
        url = self.build_search_url(query=query, make=make, model=model,
                                     min_price=min_price, max_price=max_price, page=page_num)

        results = []
        from .rate_limit_state import is_cooling_down, record_rate_limit
        if is_cooling_down("riyasewana.com"):
            self.last_rate_limited = True
            return results
        try:
            resp = self._fetch_with_backoff(url)
            
            soup = BeautifulSoup(resp.content, "html.parser")
            ad_anchors = soup.select('a[href*="/buy/"]')
            seen_urls = set()

            for a in ad_anchors:
                item_url = a.get('href', '')
                if not item_url or item_url in seen_urls:
                    continue

                container = a.parent
                for _ in range(4):
                    if container and len(container.get_text(separator=' ', strip=True)) > 30:
                        break
                    if container:
                        container = container.parent
                        
                if not container:
                    continue

                card_text = container.get_text(separator=' ', strip=True)
                if 'km' not in card_text and 'Rs.' not in card_text and 'Negotiable' not in card_text:
                    continue

                seen_urls.add(item_url)
                
                # External ID from URL
                id_match = re.search(r'-(\d+)$', item_url)
                external_id = f"riya_{id_match.group(1)}" if id_match else f"riya_{abs(hash(item_url))}"
                
                # Title
                lines = [line.strip() for line in card_text.split('\n') if line.strip() and line.strip() != '·' and line.strip() != 'TOP AD']
                title = a.text.strip() if a.text and len(a.text.strip()) > 3 else (lines[0] if lines else "Car Ad")
                title = title.replace("for sale", "").strip()

                # Year Extraction
                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', card_text)
                year_num = int(year_match.group(1)) if year_match else None

                # Price Extraction with Robust Fallbacks
                price_match = re.search(r'Rs\.?\s*([\d,]+)', card_text)
                raw_price = price_match.group(0) if price_match else ("Negotiable" if "negotiable" in card_text.lower() else "")
                price_num, price_display, is_neg = clean_price(raw_price, card_text)

                # Mileage Extraction (Filtered for fake 1 km / 10 km placeholders)
                km_match = re.search(r'([\d,]+)\s*km', card_text, re.IGNORECASE)
                mileage_num, mileage_display = clean_mileage(km_match.group(0) if km_match else "", year_num)

                # Location & District Extraction
                location = ""
                for line in lines:
                    for d in SRI_LANKA_DISTRICTS:
                        if d.lower() in line.lower():
                            location = line
                            break
                    if location:
                        break
                district = normalize_district(location)

                # Image Extraction
                img_el = container.select('img')
                img_url = ""
                if img_el:
                    raw_src = img_el[0].get('src', '')
                    if raw_src.startswith('//'):
                        img_url = 'https:' + raw_src
                    elif raw_src.startswith('http'):
                        img_url = raw_src

                detected_make, detected_model = detect_make_and_model(title, item_url)

                results.append({
                    "source": "riyasewana",
                    "external_id": external_id,
                    "title": title,
                    "make": detected_make,
                    "model": detected_model,
                    "year": year_num,
                    "price": price_num,
                    "price_display": price_display,
                    "is_negotiable": is_neg,
                    "location": location,
                    "district": district,
                    "mileage_km": mileage_num,
                    "mileage_display": mileage_display,
                    "transmission": "Automatic" if "auto" in card_text.lower() else "Manual" if "manual" in card_text.lower() else "Unknown",
                    "fuel_type": "Hybrid" if "hybrid" in card_text.lower() else "Electric" if "electric" in card_text.lower() or "ev" in card_text.lower() else "Diesel" if "diesel" in card_text.lower() else "Petrol",
                    "body_type": "Hatchback" if any(x in title.lower() for x in ["alto", "wagon r", "vitz", "mira", "fit", "aqua", "march", "dayz"]) else "Sedan" if any(x in title.lower() for x in ["premio", "axio", "civic", "grace", "corolla", "fb15"]) else "SUV" if any(x in title.lower() for x in ["vezel", "crv", "chr", "raize", "defender", "tucson", "harrier"]) else "Car",
                    "image_url": img_url,
                    "url": item_url,
                    "date_posted": "Recent",
                })
        except Exception as e:
            print(f"[Riyasewana] Error scraping page {page_num}: {e}")

        # The card-level transmission/fuel_type/body_type above are just keyword
        # guesses off the search-card text, which almost never mentions them —
        # overwrite with the real values off each ad's own detail page.
        # Tracked on self rather than returned, since scrape_page's return type
        # (the item list) is relied on elsewhere — scrape_multi_pages checks this
        # after each page so a rate limit actually stops the whole run instead of
        # silently re-hitting a blocked endpoint on every remaining page.
        self.last_rate_limited = False
        if results:
            from .detail_fetch import enrich_with_detail_specs, fetch_riyasewana_specs
            self.last_rate_limited = enrich_with_detail_specs(results, fetch_riyasewana_specs)

        return results

    def scrape_multi_pages(self, max_pages: int = 3, progress_callback=None, **filter_kwargs) -> List[Dict[str, Any]]:
        all_items = []
        for p in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(f"Fetching Riyasewana page {p} of {max_pages}", p, max_pages)
            items = self.scrape_page(page_num=p, **filter_kwargs)
            if not items:
                break
            all_items.extend(items)
            if getattr(self, "last_rate_limited", False):
                if progress_callback:
                    progress_callback("Riyasewana is rate-limiting detail requests — stopping early to cool down.", p, max_pages)
                break
            time.sleep(0.5)
        return all_items
