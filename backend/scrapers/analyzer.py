import sqlite3
import re
from typing import Dict, Any, List
from ..database import get_db_connection

def generate_ad_signature(title: str, year: int, mileage_km: int, district: str) -> str:
    """Creates a normalized fingerprint to detect reposted/relisted ads across portals"""
    clean_t = re.sub(r'[^a-zA-Z0-9]', '', (title or '').lower().replace('car', '').replace('forsale', ''))
    yr_s = str(year or '')
    km_s = str(mileage_km or '') if mileage_km and mileage_km > 0 else ''
    dist_s = re.sub(r'[^a-zA-Z]', '', (district or '').lower())
    return f"{clean_t}_{yr_s}_{km_s}_{dist_s}"

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
    tier_3_keywords = ["tucson", "sportage", "x-trail", "cr-v", "crv", "rush", "terios", "ranger", "hilux", "d-max", "dmax", "prado", "harrier", "ch-r", "chr", "outlander", "pajero", "santa fe"]
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
BENCHMARK_CACHE_TTL = 45.0  # seconds

def calculate_market_benchmarks(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    global _benchmark_cache, _benchmark_cache_time
    import time
    now = time.time()
    if not force_refresh and _benchmark_cache is not None and (now - _benchmark_cache_time < BENCHMARK_CACHE_TTL):
        return _benchmark_cache

    """
    Computes statistical benchmarks (average, min, max, count) grouped by (Make, Model, Year)
    and (Make, Model) across the database. Excludes unpriced/zero-price records.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Group by make, model, year
    cursor.execute("""
    SELECT make, model, year, 
           AVG(price) as avg_price,
           MIN(price) as min_price,
           MAX(price) as max_price,
           COUNT(*) as sample_size
    FROM cars
    WHERE price >= 400000 AND price <= 200000000 
      AND make != 'Other' AND make IS NOT NULL
      AND is_negotiable = 0
    GROUP BY make, model, year
    HAVING COUNT(*) >= 1
    """)
    rows = cursor.fetchall()
    
    benchmarks_detailed = {}
    for r in rows:
        key = f"{r['make'].lower()}_{r['model'].lower()}_{r['year']}"
        benchmarks_detailed[key] = {
            "avg_price": round(r["avg_price"], 0),
            "min_price": r["min_price"],
            "max_price": r["max_price"],
            "sample_size": r["sample_size"]
        }
        
    # Group by make, model general fallback
    cursor.execute("""
    SELECT make, model,
           AVG(price) as avg_price,
           MIN(price) as min_price,
           MAX(price) as max_price,
           COUNT(*) as sample_size
    FROM cars
    WHERE price >= 400000 AND price <= 200000000 
      AND make != 'Other' AND make IS NOT NULL
      AND is_negotiable = 0
    GROUP BY make, model
    HAVING COUNT(*) >= 1
    """)
    gen_rows = cursor.fetchall()
    
    benchmarks_general = {}
    for r in gen_rows:
        key = f"{r['make'].lower()}_{r['model'].lower()}"
        benchmarks_general[key] = {
            "avg_price": round(r["avg_price"], 0),
            "min_price": r["min_price"],
            "max_price": r["max_price"],
            "sample_size": r["sample_size"]
        }
        
    conn.close()
    return {"detailed": benchmarks_detailed, "general": benchmarks_general}

def enrich_car_with_valuation(car: Dict[str, Any], benchmarks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Adds market valuation, discount percentage, and deal classification to a car item"""
    price = car.get("price") or 0.0
    make = (car.get("make") or "").lower()
    model = (car.get("model") or "").lower()
    year = car.get("year")
    body_type = car.get("body_type") or ""
    
    # Compute real-world dealer liquidity metrics
    liq = compute_liquidity_tier(car.get("make") or "", car.get("model") or "", body_type, year)
    car["liquidity_tier"] = liq["tier"]
    car["turnaround_days"] = liq["turnaround_days"]
    car["velocity_score"] = liq["velocity_score"]
    car["liquidity_tag"] = liq["tag"]
    car["liquidity_badge_class"] = liq["badge_class"]

    detailed_key = f"{make}_{model}_{year}"
    general_key = f"{make}_{model}"
    
    is_detailed = False
    sample_size = 0
    if detailed_key in benchmarks["detailed"]:
        benchmark = benchmarks["detailed"][detailed_key]
        is_detailed = True
        sample_size = benchmark.get("sample_size", 0)
    elif general_key in benchmarks["general"]:
        benchmark = benchmarks["general"][general_key]
        sample_size = benchmark.get("sample_size", 0)
    else:
        benchmark = None

    avg_price = benchmark["avg_price"] if benchmark else 0.0

    # Assign confidence labels based on benchmark sample size
    if not benchmark:
        car["deal_confidence"] = "LOW"
        car["deal_confidence_label"] = "No Benchmark Ads"
    elif is_detailed and sample_size >= 8:
        car["deal_confidence"] = "HIGH"
        car["deal_confidence_label"] = f"High Confidence ({sample_size} ads)"
    elif is_detailed and sample_size >= 3:
        car["deal_confidence"] = "MEDIUM"
        car["deal_confidence_label"] = f"Medium Confidence ({sample_size} ads)"
    else:
        car["deal_confidence"] = "LOW"
        car["deal_confidence_label"] = f"Low Confidence ({sample_size} fallback ads)"

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

    if not benchmark or avg_price <= 0:
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

    # A discount computed off only 1-2 loosely-matched comparable ads (LOW confidence)
    # isn't a trustworthy signal — don't let it surface as a hot/good deal.
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

def get_market_trends_summary(limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """Returns paginated market benchmarks in Sri Lanka with average market prices, active listings and liquidity score"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total distinct models
    cursor.execute("""
    SELECT COUNT(*) FROM (
        SELECT make, model 
        FROM cars 
        WHERE price >= 400000 AND make != 'Other' AND make IS NOT NULL AND is_negotiable = 0
        GROUP BY make, model
    )
    """)
    row = cursor.fetchone()
    total = row[0] if row else 0
    
    cursor.execute("""
    SELECT make, model, 
           COUNT(*) as total_ads,
           ROUND(AVG(price), 0) as avg_price,
           MIN(price) as min_price,
           MAX(price) as max_price,
           ROUND(AVG(year), 0) as avg_year
    FROM cars
    WHERE price >= 400000 AND make != 'Other' AND make IS NOT NULL AND is_negotiable = 0
    GROUP BY make, model
    ORDER BY total_ads DESC
    LIMIT :limit OFFSET :offset
    """, {"limit": limit, "offset": offset})
    
    rows = cursor.fetchall()
    trends = []
    for r in rows:
        d = dict(r)
        liq = compute_liquidity_tier(d.get('make', ''), d.get('model', ''))
        d['liquidity_tier'] = liq['tier']
        d['turnaround_days'] = liq['turnaround_days']
        d['velocity_score'] = liq['velocity_score']
        d['liquidity_tag'] = liq['tag']
        d['liquidity_badge_class'] = liq['badge_class']
        trends.append(d)
        
    conn.close()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": trends
    }
