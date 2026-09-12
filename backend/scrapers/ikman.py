import re
import time
import json
from typing import List, Dict, Any, Optional
import curl_cffi.requests
from bs4 import BeautifulSoup
from .riyasewana import clean_price, clean_mileage, detect_make_and_model, normalize_district
from .rate_limit_state import is_cooling_down, record_rate_limit, execute_with_backoff

class IkmanScraper:
    def __init__(self):
        self.base_url = "https://ikman.lk/en/ads/sri-lanka/cars"

    def _fetch_with_backoff(self, url: str):
        return execute_with_backoff(curl_cffi.requests.get, "ikman.lk", url=url, impersonate="chrome120", timeout=10, verify=False)

    def build_search_url(self, query: str = "", make: str = "", model: str = "",
                         min_price: float = None, max_price: float = None,
                         page: int = 1) -> str:
        url = self.base_url
        if make:
            url += f"/{make.lower().strip()}"
            
        params = []
        if page > 1:
            params.append(f"page={page}")
        if query and not make:
            params.append(f"query={query.strip()}")
        elif model:
            params.append(f"query={model.strip()}")
            
        if min_price and min_price >= 200000:
            params.append(f"money_min={int(min_price)}")
        if max_price:
            params.append(f"money_max={int(max_price)}")

        if params:
            url += "?" + "&".join(params)
        return url

    def scrape_page(self, page_num: int = 1, query: str = "", make: str = "",
                     model: str = "", min_price: float = None, max_price: float = None) -> List[Dict[str, Any]]:
        url = self.build_search_url(query=query, make=make, model=model,
                                     min_price=min_price, max_price=max_price, page=page_num)
        results = []
        if is_cooling_down("ikman.lk"):
            self.last_rate_limited = True
            return results
        try:
            resp = self._fetch_with_backoff(url)
            
            soup = BeautifulSoup(resp.content, "html.parser")
            ad_links = soup.select('a[href*="/en/ad/"]')
            seen_urls = set()

            for link_el in ad_links:
                href = link_el.get('href', '')
                if not href or href in seen_urls or "/ads/" in href:
                    continue
                seen_urls.add(href)
                
                full_url = f"https://ikman.lk{href}" if href.startswith('/') else href
                
                slug_match = re.search(r'/en/ad/([^/?]+)', href)
                external_id = f"ikman_{slug_match.group(1)}" if slug_match else f"ikman_{abs(hash(href))}"
                
                title = link_el.get('title', '')
                card_text = link_el.get_text(separator=' ', strip=True).replace('\n', ' ')
                
                if not title:
                    title_match = re.search(r'([A-Za-z0-9\s\-]+(19\d{2}|20\d{2}))', card_text)
                    if title_match:
                        title = title_match.group(1).strip()
                    else:
                        title = slug_match.group(1).replace('-', ' ').title() if slug_match else "Car Ad"
                
                title = title.replace("for sale", "").strip()

                year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title + " " + card_text)
                year_num = int(year_match.group(1)) if year_match else None

                price_match = re.search(r'Rs\.?\s*([\d,]+)', card_text)
                raw_price = price_match.group(0) if price_match else ("Negotiable" if "negotiable" in card_text.lower() else "")
                price_num, price_display, is_neg = clean_price(raw_price, card_text)

                mileage_match = re.search(r'([\d,]+)\s*km', card_text, re.IGNORECASE)
                mileage_num, mileage_display = clean_mileage(mileage_match.group(0) if mileage_match else "", year_num)

                loc_match = re.search(r'([A-Za-z\s]+),\s*Cars', card_text)
                if loc_match:
                    location = loc_match.group(1).strip()
                else:
                    location = "Colombo"
                    for d in ["colombo", "gampaha", "kandy", "kurunegala", "kalutara", "galle", "matara", "negombo"]:
                        if d in href.lower():
                            location = d.title()
                            break

                district = normalize_district(location)

                img_el = link_el.select_one('img')
                img_url = ""
                if img_el:
                    img_url = img_el.get('src', '')

                detected_make, detected_model = detect_make_and_model(title, full_url)

                results.append({
                    "source": "ikman",
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
                    "fuel_type": "Hybrid" if "hybrid" in card_text.lower() else "Electric" if "electric" in card_text.lower() else "Diesel" if "diesel" in card_text.lower() else "Petrol",
                    "body_type": "Hatchback" if "hatchback" in card_text.lower() else "Sedan" if "sedan" in card_text.lower() or "saloon" in card_text.lower() else "SUV" if "suv" in card_text.lower() else "Car",
                    "image_url": img_url,
                    "url": full_url,
                    "date_posted": "Recent",
                })
        except Exception as e:
            print(f"[Ikman] Error scraping page {page_num}: {e}")
            if "Max retries" in str(e):
                self.last_rate_limited = True

        self.last_rate_limited = getattr(self, "last_rate_limited", False)
        if results:
            from .detail_fetch import enrich_with_detail_specs, fetch_ikman_specs
            self.last_rate_limited = enrich_with_detail_specs(results, fetch_ikman_specs)

        return results

    def scrape_multi_pages(self, max_pages: int = 2, progress_callback=None, **filter_kwargs) -> List[Dict[str, Any]]:
        all_items = []
        for p in range(1, max_pages + 1):
            if progress_callback:
                progress_callback(f"Scraping Ikman.lk page {p} of {max_pages}...", p, max_pages)
            items = self.scrape_page(page_num=p, **filter_kwargs)
            if not items:
                break
            all_items.extend(items)
            if getattr(self, "last_rate_limited", False):
                if progress_callback:
                    progress_callback("Ikman is rate-limiting detail requests — stopping early to cool down.", p, max_pages)
                break
            time.sleep(0.6)
        return all_items
