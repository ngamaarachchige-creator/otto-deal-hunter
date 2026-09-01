import os
import uuid
import threading
import io
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, BackgroundTasks, Query, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .database import (
    init_db, upsert_car, upsert_cars_batch, get_cars, get_car_count,
    update_pipeline_item, delete_pipeline_item, get_pipeline_stages_summary,
    get_db_connection, mark_stale_listings
)
from .scrapers.liveness import verify_active_listings_liveness
from .scrapers import (
    RiyasewanaScraper, IkmanScraper,
    calculate_market_benchmarks, enrich_car_with_valuation, get_market_trends_summary
)
from .ai_assistant import inspect_car
from .copilot import run_copilot_agent

app = FastAPI(title="Lanka Car Hunter API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")

scraping_jobs: Dict[str, Dict[str, Any]] = {}

class ScrapeRequest(BaseModel):
    sources: List[str] = ["riyasewana", "ikman"]
    pages_per_source: int = 3
    query: Optional[str] = ""
    make: Optional[str] = ""
    model: Optional[str] = ""
    min_price: Optional[float] = None
    max_price: Optional[float] = None

class PipelineUpdateRequest(BaseModel):
    stage: str = "saved"
    seller_phone: Optional[str] = ""
    seller_name: Optional[str] = ""
    offer_price: Optional[float] = 0.0
    purchase_price: Optional[float] = 0.0
    estimated_repair_cost: Optional[float] = 0.0
    target_resale_price: Optional[float] = 0.0
    actual_sold_price: Optional[float] = 0.0
    notes: Optional[str] = ""

def run_scraping_worker(job_id: str, req: ScrapeRequest):
    job = scraping_jobs[job_id]
    job["status"] = "running"
    query_desc = req.query or f"{req.make} {req.model}".strip() or "All Cars"
    job["logs"].append(f"Initiated search on [{', '.join(req.sources)}] for '{query_desc}'")

    stale_count = mark_stale_listings()
    if stale_count:
        job["logs"].append(f"Hid {stale_count} listing(s) not re-seen recently (likely sold/removed).")

    job["logs"].append("Verifying a batch of existing listings are still live on-site...")
    liveness_result = verify_active_listings_liveness()
    if liveness_result["marked_stale"]:
        job["logs"].append(
            f"Confirmed {liveness_result['marked_stale']} of {liveness_result['checked']} checked "
            f"listings are actually removed/sold; hid them."
        )
    if liveness_result.get("rate_limited"):
        job["logs"].append("Source site started rate-limiting the liveness check; stopped early to avoid a ban.")

    total_scraped = 0
    riya_count = 0
    ikman_count = 0

    riya_scraper = RiyasewanaScraper()
    ikman_scraper = IkmanScraper()

    try:
        if "riyasewana" in req.sources:
            job["logs"].append(f"Fetching up to {req.pages_per_source} pages from Riyasewana...")
            def riya_prog(msg, cur, total):
                job["current_step"] = f"Riyasewana page {cur}/{total}"
                job["logs"].append(msg)

            riya_items = riya_scraper.scrape_multi_pages(
                max_pages=req.pages_per_source,
                progress_callback=riya_prog,
                query=req.query,
                make=req.make,
                model=req.model,
                min_price=req.min_price,
                max_price=req.max_price
            )
            riya_count = len(riya_items)
            total_scraped += riya_count
            if riya_items:
                upsert_cars_batch(riya_items)
            job["logs"].append(f"Found {riya_count} listings on Riyasewana.")

        if "ikman" in req.sources:
            job["logs"].append(f"Fetching up to {req.pages_per_source} pages from Ikman.lk...")
            def ikman_prog(msg, cur, total):
                job["current_step"] = f"Ikman.lk page {cur}/{total}"
                job["logs"].append(msg)

            ikman_items = ikman_scraper.scrape_multi_pages(
                max_pages=req.pages_per_source,
                progress_callback=ikman_prog,
                query=req.query,
                make=req.make,
                model=req.model,
                min_price=req.min_price,
                max_price=req.max_price
            )
            ikman_count = len(ikman_items)
            total_scraped += ikman_count
            if ikman_items:
                upsert_cars_batch(ikman_items)
            job["logs"].append(f"Found {ikman_count} listings on Ikman.lk.")

        job["status"] = "completed"
        job["total_scraped"] = total_scraped
        job["riya_count"] = riya_count
        job["ikman_count"] = ikman_count
        job["is_empty"] = (total_scraped == 0)
        
        if total_scraped == 0:
            job["logs"].append(f"No listings found for the specified filters.")
        else:
            job["logs"].append(f"Completed. {total_scraped} total listings indexed.")
            
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["logs"].append(f"Scraper error: {e}")

@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/api/cars")
def list_cars(
    query: Optional[str] = None,
    source: Optional[str] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    district: Optional[str] = None,
    fuel_type: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    max_mileage: Optional[int] = None,
    pipeline_stage: Optional[str] = None,
    is_negotiable: Optional[bool] = None,
    deal_filter: Optional[str] = None,
    sort_by: str = "date_desc",
    limit: int = 20,
    offset: int = 0
):
    filters = {
        "query": query,
        "source": source,
        "make": make,
        "model": model,
        "district": district,
        "fuel_type": fuel_type,
        "min_price": min_price,
        "max_price": max_price,
        "min_year": min_year,
        "max_year": max_year,
        "max_mileage": max_mileage,
        "pipeline_stage": pipeline_stage,
        "is_negotiable": is_negotiable,
        "deal_filter": deal_filter,
    }
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    
    benchmarks = calculate_market_benchmarks()

    if deal_filter in ["hot", "good"]:
        all_candidates = get_cars(filters, sort_by=sort_by, limit=None)
        enriched = [enrich_car_with_valuation(c, benchmarks) for c in all_candidates]
        if deal_filter == "hot":
            filtered = [c for c in enriched if c.get("valuation_rating") == "HOT_DEAL"]
        else:
            filtered = [c for c in enriched if c.get("valuation_rating") in ["HOT_DEAL", "GOOD_DEAL"]]
        total = len(filtered)
        paged_items = filtered[offset:offset+limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": paged_items
        }

    total = get_car_count(filters)
    raw_cars = get_cars(filters, sort_by=sort_by, limit=limit, offset=offset)
    enriched = [enrich_car_with_valuation(c, benchmarks) for c in raw_cars]

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": enriched
    }

@app.post("/api/scrape")
def trigger_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    scraping_jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "current_step": "Initializing...",
        "total_scraped": 0,
        "query_used": req.query or f"{req.make} {req.model}".strip() or "All Cars",
        "sources": req.sources,
        "is_empty": False,
        "logs": [],
        "error": None
    }
    background_tasks.add_task(run_scraping_worker, job_id, req)
    return {"job_id": job_id, "status": "started"}

@app.get("/api/scrape-status/{job_id}")
def get_scrape_status(job_id: str):
    if job_id not in scraping_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return scraping_jobs[job_id]

@app.get("/api/stats")
def get_dashboard_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT 
        COUNT(*) as total_cars,
        SUM(CASE WHEN source = 'riyasewana' THEN 1 ELSE 0 END) as riyasewana_count,
        SUM(CASE WHEN source = 'ikman' THEN 1 ELSE 0 END) as ikman_count
    FROM cars
    """)
    car_stats = cursor.fetchone()
    total_cars = car_stats['total_cars'] or 0
    riyasewana_count = car_stats['riyasewana_count'] or 0
    ikman_count = car_stats['ikman_count'] or 0

    cursor.execute("""
    SELECT 
        SUM(CASE WHEN stage NOT IN ('archived', 'sold') THEN 1 ELSE 0 END) as active_leads,
        SUM(CASE WHEN stage = 'sold' THEN 1 ELSE 0 END) as sold_count
    FROM pipeline
    """)
    pipe_stats = cursor.fetchone()
    active_leads = pipe_stats['active_leads'] or 0
    sold_count = pipe_stats['sold_count'] or 0
    
    conn.close()

    benchmarks = calculate_market_benchmarks()
    all_cars = get_cars({}, limit=None)
    enriched = [enrich_car_with_valuation(c, benchmarks) for c in all_cars]
    hot_deals_count = len([c for c in enriched if c.get("valuation_rating") == "HOT_DEAL"])
    total_potential_profit = sum(c.get("potential_profit_lkr", 0) for c in enriched if c.get("valuation_rating") == "HOT_DEAL")

    return {
        "total_cars": total_cars,
        "riyasewana_count": riyasewana_count,
        "ikman_count": ikman_count,
        "active_leads": active_leads,
        "sold_count": sold_count,
        "hot_deals_count": hot_deals_count,
        "total_potential_profit": round(total_potential_profit, 0),
        "pipeline_summary": get_pipeline_stages_summary()
    }

@app.get("/api/market-trends")
def market_trends(limit: int = 20, offset: int = 0, query: Optional[str] = None):
    return get_market_trends_summary(limit=limit, offset=offset, query=query or "")

@app.get("/api/pipeline")
def list_pipeline_leads(stage: Optional[str] = None, limit: int = 100, offset: int = 0):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    where_clause = ""
    params = {}
    if stage:
        where_clause = "WHERE p.stage = :stage"
        params["stage"] = stage

    cursor.execute(f"SELECT COUNT(*) FROM pipeline p {where_clause}", params)
    total = cursor.fetchone()[0]

    query = f"""
    SELECT c.*, p.stage, p.seller_phone, p.seller_name, p.offer_price,
           p.purchase_price, p.estimated_repair_cost, p.target_resale_price,
           p.actual_sold_price, p.notes as pipeline_notes, p.updated_at as stage_updated_at
    FROM pipeline p
    JOIN cars c ON p.car_id = c.id
    {where_clause}
    ORDER BY p.updated_at DESC
    LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset
    cursor.execute(query, params)
    rows = cursor.fetchall()
    leads = [dict(r) for r in rows]
    conn.close()
    
    benchmarks = calculate_market_benchmarks()
    enriched_leads = [enrich_car_with_valuation(c, benchmarks) for c in leads]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": enriched_leads
    }

@app.post("/api/pipeline/{car_id}")
def update_pipeline(car_id: int, req: PipelineUpdateRequest):
    res = update_pipeline_item(
        car_id=car_id,
        stage=req.stage,
        seller_phone=req.seller_phone or "",
        seller_name=req.seller_name or "",
        offer_price=req.offer_price or 0.0,
        purchase_price=req.purchase_price or 0.0,
        estimated_repair_cost=req.estimated_repair_cost or 0.0,
        target_resale_price=req.target_resale_price or 0.0,
        actual_sold_price=req.actual_sold_price or 0.0,
        notes=req.notes or ""
    )
    return res

@app.delete("/api/pipeline/{car_id}")
def remove_from_pipeline(car_id: int):
    return delete_pipeline_item(car_id)

@app.post("/api/verify-ad-liveness")
def verify_ad_liveness(limit: int = 50):
    """
    Checks active listings, marks removed/404 ads as status='removed',
    while retaining all historical memory, price drops, and seller records.
    """
    from scrapling import Fetcher
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, url FROM cars WHERE status = 'active' OR status IS NULL LIMIT :limit", {"limit": limit})
    rows = cursor.fetchall()
    
    fetcher = Fetcher()
    checked = 0
    removed = 0
    now = datetime.utcnow().isoformat()
    
    for r in rows:
        car_id = r["id"]
        url = r["url"]
        checked += 1
        try:
            resp = fetcher.get(url)
            if resp.status in [404, 410, 301, 302] or ("this ad has been removed" in resp.text.lower()) or ("no longer available" in resp.text.lower()):
                cursor.execute("UPDATE cars SET status = 'removed', last_seen_at = :now WHERE id = :id", {"now": now, "id": car_id})
                removed += 1
        except Exception:
            pass
            
    conn.commit()
    conn.close()
    return {"checked": checked, "marked_removed": removed, "status": "completed"}


class CopilotChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, str]]] = None

@app.post("/api/copilot/chat")
def copilot_chat(req: CopilotChatRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    try:
        return run_copilot_agent(req.message.strip(), history=req.history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Copilot agent error: {str(e)}")

@app.post("/api/ai/inspect/{car_id}")
def ai_inspect_car(car_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM cars WHERE id = :id", {"id": car_id})
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Car not found")

    car = dict(row)
    benchmarks = calculate_market_benchmarks()
    car = enrich_car_with_valuation(car, benchmarks)

    try:
        analysis = inspect_car(car)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI assistant unreachable: {e}")

    return {"car_id": car_id, "analysis": analysis}

@app.get("/api/export")
def export_deals_csv(
    query: Optional[str] = None,
    source: Optional[str] = None,
    make: Optional[str] = None,
    district: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
):
    filters = {
        "query": query,
        "source": source,
        "make": make,
        "district": district,
        "min_price": min_price,
        "max_price": max_price,
    }
    filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    cars = get_cars(filters, limit=1000)
    benchmarks = calculate_market_benchmarks()
    enriched = [enrich_car_with_valuation(c, benchmarks) for c in cars]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Source", "Title", "Make", "Model", "Year", "Price (LKR)",
        "Price Status", "District", "Location", "Mileage (KM)", "Transmission",
        "Fuel Type", "Market Average (LKR)", "Discount %", "Valuation Rating", "Potential Flip Profit (LKR)", "URL"
    ])
    
    for c in enriched:
        writer.writerow([
            c.get("id"),
            c.get("source"),
            c.get("title"),
            c.get("make"),
            c.get("model"),
            c.get("year"),
            c.get("price"),
            "Price on request" if c.get("is_negotiable") or c.get("price") == 0 else "Stated Price",
            c.get("district"),
            c.get("location"),
            c.get("mileage_km"),
            c.get("transmission"),
            c.get("fuel_type"),
            c.get("market_avg_price"),
            c.get("discount_pct"),
            c.get("valuation_rating"),
            c.get("potential_profit_lkr"),
            c.get("url")
        ])

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lanka_car_deals.csv"}
    )

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("frontend/assets/favicon.svg", media_type="image/svg+xml")

@app.get("/")
def serve_root():
    index_file = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Lanka Car Hunter Backend API is running."}


@app.get("/api/copilot/status")
def get_copilot_status():
    from .copilot import resolve_ollama_host, OLLAMA_MODEL
    import requests
    host = resolve_ollama_host()
    try:
        resp = requests.get(host, timeout=2)
        if resp.status_code == 200:
            return {"active": True, "model": OLLAMA_MODEL, "host": host}
    except Exception:
        pass
    return {"active": False, "model": OLLAMA_MODEL, "host": host}

@app.get("/api/copilot/scrape-logs")
def get_copilot_scrape_logs():
    from .copilot import COPILOT_SCRAPE_LOGS
    return {"logs": COPILOT_SCRAPE_LOGS}
