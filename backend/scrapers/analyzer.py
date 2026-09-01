import sqlite3
import re
import time
from typing import Dict, Any, List, Optional
from ..database import get_db_connection

def generate_ad_signature(title: str, year: int, mileage_km: int, district: str) -> str:
    """Creates a normalized fingerprint to detect reposted/relisted ads across portals"""
    clean_t = re.sub(r'[^a-zA-Z0-9]', '', (title or '').lower().replace('car', '').replace('forsale', ''))
    yr_s = str(year or '')
    km_s = str(mileage_km or '') if mileage_km and mileage_km > 0 else ''
    dist_s = re.sub(r'[^a-zA-Z]', '', (district or '').lower())
    return f"{clean_t}_{yr_s}_{km_s}_{dist_s}"

def extract_base_model(make: str, model: str, title: str = "") -> str:
    """
    Standardizes Sri Lankan vehicle models to core name (e.g. 'Sorento 1-12 Option SUV' -> 'Sorento',
    'Wagon R FX Hybrid' -> 'Wagon R', 'Aqua G Grade' -> 'Aqua', 'Prado TX L' -> 'Prado').
    """
    m_raw = f"{model or ''} {title or ''}".lower()
    
    known_models = [
        "wagon r", "wagonr", "alto", "celerio", "swift", "vitz", "aqua", "axio", "premio",
        "allion", "prius", "fit", "vezel", "civic", "grace", "cr-v", "crv", "prado", "hilux",
        "rush", "raize", "passo", "yaris", "harrier", "ch-r", "chr", "corolla", "sunny",
        "march", "dayz", "x-trail", "xtrail", "outlander", "pajero", "mira", "spacia",
        "hustler", "picanto", "sorento", "sportage", "tucson", "santa fe", "elantra",
        "panda", "viva elite", "axia", "bezza", "ranger", "d-max", "dmax", "belta", "ist",
        "land cruiser", "defender", "montero", "freed", "insight", "leaf",
        "terios", "s-presso", "spresso", "carina", "corona", "lancer"
    ]
    
    for km in known_models:
        pattern = r'\b' + re.escape(km) + r'\b'
        if re.search(pattern, m_raw):
            if km in ["wagonr"]: return "Wagon R"
            if km in ["crv"]: return "CR-V"
            if km in ["xtrail"]: return "X-Trail"
            if km in ["chr"]: return "CH-R"
            if km in ["dmax"]: return "D-Max"
            if km in ["spresso"]: return "S-Presso"
            return km.title()
            
    # Fallback to model first 2 words without noise
    clean = re.sub(r'\b(19\d\d|20\d\d|suv|car|hybrid|diesel|petrol|electric|ev|turbo|option|options|lkr|rs|automatic|manual)\b', '', (model or '').lower(), flags=re.IGNORECASE)
    clean = re.sub(r'[\s\-]+', ' ', clean).strip()
    return clean.title() if clean else (model or "General").title()

def compute_robust_mean(prices: List[float]) -> float:
    """
    Computes an outlier-resistant competitive market benchmark.
    Cuts the top 25% inflated dealer dream asks and bottom 10% placeholder down payments.
    """
    if not prices:
        return 0.0
    prices = sorted(prices)
    n = len(prices)
    if n < 4:
        return sum(prices) / n
    low_idx = max(0, int(n * 0.10))
    high_idx = min(n, int(n * 0.75))
    if high_idx <= low_idx:
        high_idx = n
    trimmed = prices[low_idx:high_idx]
    return sum(trimmed) / len(trimmed)

def _ad_word(n: int) -> str:
    """"1 ad" vs "2 ads" — confidence labels were showing "1 ads" for every
    single-comparable listing, which is extremely common (LOW confidence is
    exactly the 1-2 sample case)."""
    return "ad" if n == 1 else "ads"

def compute_liquidity_tier(make: str, model: str, body_type: str = "", year: int = None) -> Dict[str, Any]:
    """
    Computes real-world automotive dealer liquidity tier and turnaround velocity in Sri Lanka.
    """
    m_lower = ((make or '') + " " + (model or '')).lower()
    
    # Tier 1: Instant Cash (3-7 Days)
    tier_1_keywords = ["alto", "wagon r", "vitz", "aqua", "celerio", "axio", "premio", "prius", "mira"]
    if any(k in m_lower for k in tier_1_keywords):
        return {
            "tier": "Tier 1: Instant Cash",
            "turnaround_days": "3–7 Days",
            "velocity_score": 95,
            "badge_class": "liquidity-tier-1",
            "tag": "3–7d Turnover"
        }
        
    # Tier 2: High Demand (7-15 Days)
    tier_2_keywords = ["swift", "fit", "ist", "belta", "grace", "sunny", "corolla", "civic", "vezel", "march", "dayz", "spacia", "hustler", "passo", "yaris", "raize"]
    if any(k in m_lower for k in tier_2_keywords):
        return {
            "tier": "Tier 2: High Demand",
            "turnaround_days": "7–15 Days",
            "velocity_score": 80,
            "badge_class": "liquidity-tier-2",
            "tag": "7–15d Turnover"
        }
        
    # Tier 3: SUV & Utility (20-45 Days)
    tier_3_keywords = ["tucson", "sportage", "x-trail", "cr-v", "crv", "rush", "terios", "ranger", "hilux", "d-max", "dmax", "prado", "harrier", "ch-r", "chr", "outlander", "pajero", "santa fe", "sorento"]
    if any(k in m_lower for k in tier_3_keywords) or (body_type and body_type.lower() in ["suv", "pickup"]):
        return {
            "tier": "Tier 3: SUV / Niche",
            "turnaround_days": "20–45 Days",
            "velocity_score": 60,
            "badge_class": "liquidity-tier-3",
            "tag": "20–45d Turnover"
        }
        
    # Tier 4: Slower Liquidity (45+ Days)
    return {
        "tier": "Tier 4: Slow Turnover",
        "turnaround_days": "45–90+ Days",
        "velocity_score": 35,
        "badge_class": "liquidity-tier-4",
        "tag": "45+d Turnover"
    }

_benchmark_cache = None
_benchmark_cache_time = 0
BENCHMARK_CACHE_TTL = 30.0  # seconds

def calculate_market_benchmarks(force_refresh: bool = False) -> Dict[str, Any]:
    global _benchmark_cache, _benchmark_cache_time
    now = time.time()
    if not force_refresh and _benchmark_cache is not None and (now - _benchmark_cache_time < BENCHMARK_CACHE_TTL):
        return _benchmark_cache

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT make, model, title, year, fuel_type, price
    FROM cars
    WHERE price >= 400000 AND price <= 200000000 
      AND make != 'Other' AND make IS NOT NULL
      AND is_negotiable = 0
    """)
    rows = cursor.fetchall()
    conn.close()
    
    # Structure cohorts
    # 1. (make, base_model, year, fuel_type) -> prices
    # 2. (make, base_model, year) -> prices
    # 3. (make, base_model) -> list of (year, price)
    exact_fuel_cohorts = {}
    exact_year_cohorts = {}
    model_year_points = {} # (make, base_model) -> [(year, price)]
    
    for r in rows:
        make = (r["make"] or "Other").strip().title()
        model_str = r["model"] or ""
        title_str = r["title"] or ""
        base_model = extract_base_model(make, model_str, title_str)
        yr = r["year"]
        fuel = (r["fuel_type"] or "Petrol").strip().title()
        price = float(r["price"])
        
        m_key = make.lower()
        bm_key = base_model.lower()
        f_key = fuel.lower()
        
        if yr:
            # 1. Exact fuel + year
            k1 = f"{m_key}_{bm_key}_{yr}_{f_key}"
            exact_fuel_cohorts.setdefault(k1, []).append(price)
            
            # 2. Exact year
            k2 = f"{m_key}_{bm_key}_{yr}"
            exact_year_cohorts.setdefault(k2, []).append(price)
            
            # 3. Points for curve fitting / depreciation
            k3 = f"{m_key}_{bm_key}"
            model_year_points.setdefault(k3, []).append((yr, price))

    benchmarks_detailed = {}
    for k, prices in exact_fuel_cohorts.items():
        benchmarks_detailed[k] = {
            "avg_price": round(compute_robust_mean(prices), 0),
            "min_price": min(prices),
            "max_price": max(prices),
            "sample_size": len(prices)
        }
        
    benchmarks_year = {}
    for k, prices in exact_year_cohorts.items():
        benchmarks_year[k] = {
            "avg_price": round(compute_robust_mean(prices), 0),
            "min_price": min(prices),
            "max_price": max(prices),
            "sample_size": len(prices)
        }
        
    # Model year curves for depreciation fallback
    model_curves = {}
    for k, pts in model_year_points.items():
        # Group by year and compute robust mean per year
        yr_map = {}
        for y, p in pts:
            yr_map.setdefault(y, []).append(p)
        yearly_benchmarks = {y: compute_robust_mean(plist) for y, plist in yr_map.items()}
        model_curves[k] = {
            "yearly_benchmarks": yearly_benchmarks,
            "total_samples": len(pts)
        }

    _benchmark_cache = {
        "detailed_fuel": benchmarks_detailed,
        "detailed_year": benchmarks_year,
        "model_curves": model_curves
    }
    _benchmark_cache_time = now
    return _benchmark_cache

def enrich_car_with_valuation(car: Dict[str, Any], benchmarks: Dict[str, Any]) -> Dict[str, Any]:
    """Adds accurate, year-consistent market valuation, discount percentage, and deal classification to a car item"""
    price = car.get("price") or 0.0
    make = (car.get("make") or "").strip().lower()
    raw_model = (car.get("model") or "").strip()
    title = (car.get("title") or "").strip()
    base_model = extract_base_model(make, raw_model, title).lower()
    year = car.get("year")
    fuel = (car.get("fuel_type") or "Petrol").strip().lower()
    body_type = car.get("body_type") or ""
    
    # Compute real-world dealer liquidity metrics
    liq = compute_liquidity_tier(car.get("make") or "", base_model, body_type, year)
    car["liquidity_tier"] = liq["tier"]
    car["turnaround_days"] = liq["turnaround_days"]
    car["velocity_score"] = liq["velocity_score"]
    car["liquidity_tag"] = liq["tag"]
    car["liquidity_badge_class"] = liq["badge_class"]
    car["base_model"] = base_model.title()

    detailed_fuel_dict = benchmarks.get("detailed_fuel", {})
    detailed_year_dict = benchmarks.get("detailed_year", {})
    model_curves = benchmarks.get("model_curves", {})

    fuel_key = f"{make}_{base_model}_{year}_{fuel}"
    year_key = f"{make}_{base_model}_{year}"
    curve_key = f"{make}_{base_model}"

    avg_price = 0.0
    sample_size = 0
    confidence_level = "LOW"
    confidence_label = "No Benchmark Ads"

    # Hierarchy 1: Exact Base Model + Exact Year + Fuel Type (if sample >= 3)
    if fuel_key in detailed_fuel_dict and detailed_fuel_dict[fuel_key]["sample_size"] >= 3:
        b = detailed_fuel_dict[fuel_key]
        avg_price = b["avg_price"]
        sample_size = b["sample_size"]
        confidence_level = "HIGH" if sample_size >= 8 else "MEDIUM"
        confidence_label = f"{'High' if sample_size >= 8 else 'Medium'} Confidence ({sample_size} {fuel.title()} {_ad_word(sample_size)})"
        
    # Hierarchy 2: Exact Base Model + Exact Year
    elif year_key in detailed_year_dict:
        b = detailed_year_dict[year_key]
        avg_price = b["avg_price"]
        sample_size = b["sample_size"]
        if sample_size >= 8:
            confidence_level = "HIGH"
            confidence_label = f"High Confidence ({sample_size} {_ad_word(sample_size)})"
        elif sample_size >= 3:
            confidence_level = "MEDIUM"
            confidence_label = f"Medium Confidence ({sample_size} {_ad_word(sample_size)})"
        else:
            confidence_level = "LOW"
            confidence_label = f"Low Confidence ({sample_size} {_ad_word(sample_size)})"

    # Hierarchy 3: Nearest Year Cohort with Depreciation Adjustment (prevents mixing 2003 with 2025!)
    elif curve_key in model_curves and year:
        curve = model_curves[curve_key]
        yearly = curve["yearly_benchmarks"]
        if yearly:
            # Find closest year
            closest_yr = min(yearly.keys(), key=lambda y: abs(y - year))
            base_val = yearly[closest_yr]
            yr_diff = year - closest_yr
            # Realistic Sri Lankan annual depreciation scale: ~5.5% per year
            deprec_factor = (1.055 ** yr_diff)
            avg_price = round(base_val * deprec_factor, 0)
            sample_size = curve["total_samples"]
            confidence_level = "LOW"
            confidence_label = f"Estimated vs {closest_yr} cohort ({sample_size} comp {_ad_word(sample_size)})"

    car["deal_confidence"] = confidence_level
    car["deal_confidence_label"] = confidence_label

    # Handle unpriced/negotiable cars
    if car.get("is_negotiable") or price <= 0:
        car["valuation_rating"] = "UNPRICED"
        car["deal_score"] = 0
        car["market_avg_price"] = avg_price
        car["potential_profit_lkr"] = 0
        car["discount_pct"] = 0
        car["deal_tag"] = "Price on request"
        if not car.get("price_display") or car.get("price_display") in ["Negotiable", "Lease Down Payment"]:
            car["price_display"] = "Price on request"
        return car

    if avg_price <= 0:
        car["valuation_rating"] = "UNRATED"
        car["deal_score"] = 50
        car["market_avg_price"] = price
        car["potential_profit_lkr"] = 0
        car["discount_pct"] = 0
        car["deal_tag"] = "Market rate"
        return car
        
    diff_lkr = avg_price - price
    discount_pct = (diff_lkr / avg_price) * 100
    
    car["market_avg_price"] = avg_price
    car["discount_pct"] = round(discount_pct, 1)
    car["discount_percentage"] = car["discount_pct"]
    
    std_refurb_cost = 80000.0
    est_resale = avg_price * 0.97
    est_profit = est_resale - (price + std_refurb_cost)
    car["potential_profit_lkr"] = max(0, round(est_profit, 0))

    if discount_pct >= 15 and car["deal_confidence"] == "LOW":
        car["valuation_rating"] = "UNVERIFIED_DEAL"
        car["deal_score"] = 50
        car["deal_tag"] = f"{discount_pct:.0f}% below market (unverified)"
    elif discount_pct >= 15:
        car["valuation_rating"] = "HOT_DEAL"
        car["deal_score"] = min(99, int(75 + discount_pct))
        car["deal_tag"] = f"{discount_pct:.0f}% below market"
    elif discount_pct >= 5 and car["deal_confidence"] == "LOW":
        car["valuation_rating"] = "UNVERIFIED_DEAL"
        car["deal_score"] = 50
        car["deal_tag"] = f"{discount_pct:.0f}% below market (unverified)"
    elif discount_pct >= 5:
        car["valuation_rating"] = "GOOD_DEAL"
        car["deal_score"] = int(60 + discount_pct)
        car["deal_tag"] = f"{discount_pct:.0f}% below market"
    elif discount_pct >= -5:
        car["valuation_rating"] = "FAIR_PRICE"
        car["deal_score"] = 50
        car["deal_tag"] = "Market rate"
    else:
        car["valuation_rating"] = "OVERPRICED"
        car["deal_score"] = max(10, int(50 + discount_pct))
        car["deal_tag"] = f"{abs(discount_pct):.0f}% above market"

    return car

def get_market_trends_summary(limit: int = 20, offset: int = 0, query: str = "") -> Dict[str, Any]:
    """
    Returns robust year-specific market benchmarks in Sri Lanka grouped by (Make, Base Model, Year).
    Applies outlier trimming so averages reflect true street market prices rather than inflated dream asks.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT make, model, title, year, fuel_type, price
    FROM cars
    WHERE price >= 400000 AND price <= 200000000 
      AND make != 'Other' AND make IS NOT NULL
      AND year IS NOT NULL AND year >= 1990 AND year <= 2026
      AND is_negotiable = 0
    """)
    rows = cursor.fetchall()
    conn.close()
    
    # Group by (make, base_model, year)
    groups = {}
    for r in rows:
        make = (r["make"] or "Other").strip().title()
        model_str = r["model"] or ""
        title_str = r["title"] or ""
        base_model = extract_base_model(make, model_str, title_str)
        year = int(r["year"])
        price = float(r["price"])
        
        key = (make, base_model, year)
        if key not in groups:
            groups[key] = {
                "make": make,
                "model": base_model,
                "year": year,
                "prices": []
            }
        groups[key]["prices"].append(price)
        
    trends = []
    for (make, base_model, year), data in groups.items():
        prices = data["prices"]
        if not prices:
            continue
            
        if query:
            q_lower = query.lower()
            if q_lower not in make.lower() and q_lower not in base_model.lower() and q_lower != str(year):
                continue

        avg_p = compute_robust_mean(prices)
        min_p = min(prices)
        max_p = max(prices)
        total_ads = len(prices)
        
        liq = compute_liquidity_tier(make, base_model, year=year)
        
        trends.append({
            "make": make,
            "model": base_model,
            "year": year,
            "avg_year": year,
            "total_ads": total_ads,
            "avg_price": round(avg_p, 0),
            "min_price": min_p,
            "max_price": max_p,
            "liquidity_tier": liq["tier"],
            "turnaround_days": liq["turnaround_days"],
            "velocity_score": liq["velocity_score"],
            "liquidity_tag": liq["tag"],
            "liquidity_badge_class": liq["badge_class"]
        })
        
    # Sort by active inventory stock descending
    trends.sort(key=lambda x: (x["total_ads"], x["year"]), reverse=True)
    
    total = len(trends)
    paged = trends[offset : offset + limit]
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": paged
    }
