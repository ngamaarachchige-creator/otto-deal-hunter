import os
import re
import json
import sqlite3
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.scrapers.analyzer import calculate_market_benchmarks, enrich_car_with_valuation, get_db_connection
from backend.scrapers import RiyasewanaScraper, IkmanScraper
from backend.database import upsert_cars_batch, get_pipeline_stages_summary

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.23:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-vl:8b")

COPILOT_SYSTEM_PROMPT = """You are OTTO, an autonomous vehicle acquisition and deal intelligence agent operating in Sri Lanka.
You are in a continuous conversation with a car buyer/flipper. Remember the conversation context and maintain topic continuity across turns.

Capabilities & Tools:
1. `search_market_deals`: Searches 1,981+ active Sri Lankan listings. Use this when the user mentions any car brand, model, price, or asks to search/find/check cars.
2. `trigger_live_market_scrape`: Triggers live web scraping on Riyasewana & Ikman to fetch fresh listings.
3. `get_pipeline_summary`: Inspects CRM flip pipeline metrics.

Behavior & Reasoning Guidelines:
- Contextual Awareness: If the user refers to a car mentioned in previous messages (e.g. 'i want a low price', 'make it 50 million', 'show me that one'), retain the make/model from prior messages!
- If the user asks for 'low price' or 'cheapest' without a numeric budget, do NOT invent a fake cap like 5M. Search with sort_by='price_asc' or search the brand directly.
- Tone: Sharp, conversational, authentic Sri Lankan market expert.
- Never use em dashes ("—") or en dashes ("-"). Use colons, commas, or clean sentences.

Training Examples (Few-Shot Prompting):
User: "yo wht good boi, chilling?"
Assistant: "Chillin' all day, bro! Ready to hunt some fresh deals. What model or budget are we looking to flip today?"

User: "no cap find me a cheap wagon r under 7m"
Assistant: <tool_call>{"name": "search_market_deals", "arguments": {"query": "Wagon R", "max_price": 7000000, "sort_by": "price_asc"}}</tool_call>

User: "do a live scrape on Vitz fr fr"
Assistant: <tool_call>{"name": "trigger_live_market_scrape", "arguments": {"query": "Vitz"}}</tool_call>

User: "find cheap Celerio"
Assistant: <tool_call>{"name": "search_market_deals", "arguments": {"query": "Celerio", "sort_by": "price_asc"}}</tool_call>
User: "make it under 4 million lkr"
Assistant: <tool_call>{"name": "search_market_deals", "arguments": {"query": "Celerio", "max_price": 4000000, "sort_by": "price_asc"}}</tool_call>"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_market_deals",
            "description": "Searches the database of active Sri Lankan vehicle ads for specific makes, models, years, price ranges, and flip deals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Vehicle make, model, or search terms (e.g. 'Lexus', 'Toyota Prado', 'Aqua', 'Celerio')"
                    },
                    "year": {
                        "type": "integer",
                        "description": "Optional manufacture/registration year (e.g. 2011, 2026)"
                    },
                    "min_price": {
                        "type": "integer",
                        "description": "Optional minimum price in LKR"
                    },
                    "max_price": {
                        "type": "integer",
                        "description": "Optional maximum price in LKR (e.g. 50000000 for 50M)"
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["discount_desc", "price_asc", "price_desc", "year_desc"],
                        "description": "Sort order: discount_desc for highest flip margin, price_asc for cheapest"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_live_market_scrape",
            "description": "Triggers live web scrapers on Riyasewana and Ikman to fetch fresh vehicle listings into the database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Vehicle make, model, or keyword to scrape (e.g. 'Lexus', 'Prado 2026')"
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pipeline_summary",
            "description": "Retrieves the user's current Flip Pipeline CRM status, active leads, invested capital, and potential profits.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

def log_copilot_turn(user_msg: str, tool_calls: list, thought_steps: list, response_text: str):
    try:
        log_entry = {
            "timestamp": str(datetime.now()),
            "user_message": user_msg,
            "tool_calls": tool_calls,
            "thought_steps": thought_steps,
            "response_text": response_text
        }
        log_dir = "/Users/nethukagamaarachcige/Documents/otto-deal-hunter/data"
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "copilot_chats.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        print("Chat log error:", e)

def execute_search_deals(
    query: str = "",
    year: Optional[int] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort_by: str = "discount_desc",
    limit: int = 6
) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    sql = "SELECT * FROM cars WHERE price > 0"
    params = {}
    
    # Extract year from query if present
    if not year and query:
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', query)
        if year_match:
            year = int(year_match.group(1))
            
    if year:
        sql += " AND year = :year"
        params["year"] = year
        
    if query and query.lower() not in ["all", "any", "cars", "deals", "cheap", "car"]:
        cleaned_words = [w for w in query.lower().split() if w != str(year) and len(w) > 1]
        for i, w in enumerate(cleaned_words):
            param_key = f"w_{i}"
            sql += f" AND (LOWER(make) LIKE :{param_key} OR LOWER(model) LIKE :{param_key} OR LOWER(title) LIKE :{param_key})"
            params[param_key] = f"%{w}%"
            
    if min_price:
        sql += " AND price >= :min_price"
        params["min_price"] = min_price
        
    if max_price:
        sql += " AND price <= :max_price"
        params["max_price"] = max_price
        
    sql += " ORDER BY updated_at DESC LIMIT 120"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    conn.close()
    
    cars = [dict(r) for r in rows]
    benchmarks = calculate_market_benchmarks()
    enriched = [enrich_car_with_valuation(c, benchmarks) for c in cars]
    
    if sort_by == "price_asc":
        enriched.sort(key=lambda x: x.get("price", 0) or 0)
    elif sort_by == "price_desc":
        enriched.sort(key=lambda x: x.get("price", 0) or 0, reverse=True)
    elif sort_by == "year_desc":
        enriched.sort(key=lambda x: x.get("year", 0) or 0, reverse=True)
    else:
        enriched.sort(key=lambda x: x.get("discount_pct", 0) or 0, reverse=True)
        
    return enriched[:limit]

COPILOT_SCRAPE_LOGS = []

def execute_live_scrape(query: str = "") -> Dict[str, Any]:
    global COPILOT_SCRAPE_LOGS
    COPILOT_SCRAPE_LOGS.clear()
    
    query_desc = query or "All Recent Ads"
    COPILOT_SCRAPE_LOGS.append(f"Initiating live search on Riyasewana for '{query_desc}'...")
    
    riya = RiyasewanaScraper()
    def riya_prog(msg, cur, total):
        COPILOT_SCRAPE_LOGS.append(msg)
        
    riya_items = riya.scrape_multi_pages(max_pages=1, progress_callback=riya_prog, query=query)
    riya_count = len(riya_items)
    if riya_items:
        upsert_cars_batch(riya_items)
    COPILOT_SCRAPE_LOGS.append(f"Completed Riyasewana. Found {riya_count} listings.")
    
    COPILOT_SCRAPE_LOGS.append(f"Connecting to Ikman.lk for '{query_desc}'...")
    ikman = IkmanScraper()
    def ikman_prog(msg, cur, total):
        COPILOT_SCRAPE_LOGS.append(msg)
        
    ikman_items = ikman.scrape_multi_pages(max_pages=1, progress_callback=ikman_prog, query=query)
    ikman_count = len(ikman_items)
    if ikman_items:
        upsert_cars_batch(ikman_items)
    COPILOT_SCRAPE_LOGS.append(f"Completed Ikman.lk. Found {ikman_count} listings.")
    
    total_count = riya_count + ikman_count
    COPILOT_SCRAPE_LOGS.append(f"Finished live scrape. {total_count} total listings indexed.")
    
    return {
        "status": "completed",
        "new_listings_count": total_count,
        "source": "Riyasewana & Ikman Live Feed",
        "query": query_desc
    }

def execute_pipeline_summary() -> Dict[str, Any]:
    summary = get_pipeline_stages_summary()
    return {
        "pipeline_stages": summary,
        "active_stages": [s for s in summary if s.get("count", 0) > 0]
    }

def run_copilot_agent(user_message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    thought_steps = []
    thought_steps.append("Processing conversation context with OTTO agent...")

    # Build full conversation history
    messages = [{"role": "system", "content": COPILOT_SYSTEM_PROMPT}]
    if history and isinstance(history, list):
        for msg in history[-8:]:  # keep last 8 turns of context
            if msg.get("role") in ["user", "assistant"] and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})
                
    # Append current turn
    messages.append({"role": "user", "content": user_message})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "tools": TOOLS_SCHEMA,
        "stream": False
    }

    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        err_msg = f"Couldn't reach OTTO agent: {str(e)}"
        log_copilot_turn(user_message, [], ["Error communicating with model"], err_msg)
        return {
            "thought_steps": ["Error communicating with local AI model"],
            "response_text": err_msg,
            "recommended_cars": []
        }

    assistant_msg = data.get("message", {})
    tool_calls = assistant_msg.get("tool_calls", [])
    raw_content = assistant_msg.get("content", "").strip()

    # Case 1: Model responded conversationally without tools
    if not tool_calls:
        clean_response = raw_content.replace("—", ": ").replace("–", ": ")
        clean_response = re.sub(r"\n*\*?\(?\s*\d+\s*words?\s*\)?\*?\s*$", "", clean_response, flags=re.IGNORECASE).strip()
        clean_response = re.sub(r"\n*\*?\(?\s*word count:?\s*\d+\s*\w*\s*\)?\*?\s*$", "", clean_response, flags=re.IGNORECASE).strip()
        
        # If content is empty (e.g. model output only thinking trace), generate fallback from thinking or prompt
        if not clean_response:
            thinking = assistant_msg.get("thinking", "")
            if thinking:
                clean_response = thinking.split("\n")[-1].strip()
            if not clean_response:
                clean_response = "Got it! Let me know if you want me to search specific models or trigger a live scrape."
                
        log_copilot_turn(user_message, [], ["Conversation response generated."], clean_response)
        return {
            "thought_steps": ["Conversation response generated."],
            "response_text": clean_response,
            "recommended_cars": []
        }

    # Case 2: Model chose to call tools
    tool_call = tool_calls[0]
    func_name = tool_call.get("function", {}).get("name")
    raw_args = tool_call.get("function", {}).get("arguments", {})
    args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}")

    recommended_cars = []

    if func_name == "search_market_deals":
        query_val = args.get("query", "")
        year_val = args.get("year")
        min_p = args.get("min_price")
        max_p = args.get("max_price")
        sort_by_val = args.get("sort_by", "discount_desc")
        
        thought_steps.append(f"Invoking tool `search_market_deals` (query='{query_val}', min_price={min_p}, max_price={max_p}, sort={sort_by_val})...")
        thought_steps.append("Querying local index of 1,981+ listings & calculating valuation spreads...")
        
        deals = execute_search_deals(
            query=query_val,
            year=year_val,
            min_price=min_p,
            max_price=max_p,
            sort_by=sort_by_val,
            limit=5
        )
        
        # If no deals found, keep deals empty so we don't display unrelated cars
        # The model will explain that 0 matches were found and suggest a live scrape.
            
        deals_context = ""
        for d in deals[:4]:
            deals_context += (
                f"Car #{d.get('id')}: {d.get('year')} {d.get('make')} {d.get('model')} | "
                f"Price: Rs. {d.get('price'):,} | Market Avg: Rs. {d.get('market_avg_price', 0):,} | "
                f"Discount: {d.get('discount_pct', 0)}% | Mileage: {d.get('mileage_display', 'N/A')} | "
                f"Location: {d.get('district') or d.get('location')}\n"
            )
            
        thought_steps.append("Synthesizing actionable recommendations...")
        
        second_payload = {
            "model": OLLAMA_MODEL,
            "messages": messages + [
                assistant_msg,
                {
                    "role": "tool",
                    "content": json.dumps({"deals_found": len(deals), "listings": deals_context})
                }
            ],
            "stream": False
        }
        try:
            synth_resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=second_payload, timeout=60).json()
            final_text = synth_resp.get("message", {}).get("content", "").strip()
        except Exception:
            final_text = f"Found {len(deals)} top matching deals in the market:"
            
        for c in deals[:3]:
            recommended_cars.append({
                "id": c.get("id"),
                "title": c.get("title"),
                "make": c.get("make"),
                "model": c.get("model"),
                "year": c.get("year"),
                "price": c.get("price"),
                "price_display": c.get("price_display"),
                "market_avg_price": c.get("market_avg_price"),
                "discount_pct": c.get("discount_pct"),
                "mileage": c.get("mileage_display") or f"{c.get('mileage', '')} km",
                "transmission": c.get("transmission"),
                "location": c.get("district") or c.get("location"),
                "image_url": c.get("image_url"),
                "url": c.get("url"),
                "liquidity_tier": c.get("liquidity_tier", "B")
            })

    elif func_name == "trigger_live_market_scrape":
        query_val = args.get("query", "")
        thought_steps.append(f"Invoking tool `trigger_live_market_scrape` (query='{query_val or 'All Recent Ads'}')...")
        thought_steps.append("Connecting to live marketplace endpoints on Riyasewana...")
        scrape_result = execute_live_scrape(query=query_val)
        thought_steps.append(f"Ingested {scrape_result['new_listings_count']} fresh ads. Deduplicating and writing to SQLite index...")
        thought_steps.append(f"Querying freshly updated market index for '{query_val or 'latest'}' opportunities...")
        
        deals = execute_search_deals(query=query_val, limit=5)
            
        thought_steps.append(f"Found {len(deals)} matching listings. Synthesizing market intelligence...")
        
        deals_context = ""
        for d in deals[:4]:
            deals_context += (
                f"Car #{d.get('id')}: {d.get('year')} {d.get('make')} {d.get('model')} | "
                f"Price: Rs. {d.get('price'):,} | Market Avg: Rs. {d.get('market_avg_price', 0):,} | "
                f"Discount: {d.get('discount_pct', 0)}% | Mileage: {d.get('mileage_display', 'N/A')} | "
                f"Location: {d.get('district') or d.get('location')}\n"
            )
            
        second_payload = {
            "model": OLLAMA_MODEL,
            "messages": messages + [
                assistant_msg,
                {
                    "role": "tool",
                    "content": json.dumps({"status": "scraped", "new_listings": scrape_result['new_listings_count'], "deals": deals_context})
                }
            ],
            "stream": False
        }
        try:
            synth_resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=second_payload, timeout=60).json()
            final_text = synth_resp.get("message", {}).get("content", "").strip()
        except Exception:
            final_text = f"Live scrape completed! Ingested {scrape_result['new_listings_count']} listings. Here are the top results:"
            
        for c in deals[:3]:
            recommended_cars.append({
                "id": c.get("id"),
                "title": c.get("title"),
                "make": c.get("make"),
                "model": c.get("model"),
                "year": c.get("year"),
                "price": c.get("price"),
                "price_display": c.get("price_display"),
                "market_avg_price": c.get("market_avg_price"),
                "discount_pct": c.get("discount_pct"),
                "mileage": c.get("mileage_display") or f"{c.get('mileage', '')} km",
                "transmission": c.get("transmission"),
                "location": c.get("district") or c.get("location"),
                "image_url": c.get("image_url"),
                "url": c.get("url"),
                "liquidity_tier": c.get("liquidity_tier", "B")
            })

    elif func_name == "get_pipeline_summary":
        thought_steps.append("Invoking tool `get_pipeline_summary`...")
        summary = execute_pipeline_summary()
        thought_steps.append("Analyzed active CRM stages and profit projections.")
        active = summary.get("active_stages", [])
        total_leads = sum(s.get("count", 0) for s in active)
        final_text = f"You currently have **{total_leads} active leads** in your Flip Pipeline across stages. Review your Kanban board for details."

    else:
        final_text = raw_content or "Done."

    clean_final = final_text.replace("—", ": ").replace("–", ": ")
    # Strip raw JSON tool declarations sometimes leaked by local models
    clean_final = re.sub(r'\{?\s*"name"\s*:\s*"[A-Za-z0-9_]+",\s*"arguments"\s*:\s*\{.*?\}\s*\}?', "", clean_final, flags=re.DOTALL)
    clean_final = re.sub(r"\n*\*?\(?\s*\d+\s*words?\s*\)?\*?\s*$", "", clean_final, flags=re.IGNORECASE).strip()
    clean_final = re.sub(r"\n*\*?\(?\s*word count:?\s*\d+\s*\w*\s*\)?\*?\s*$", "", clean_final, flags=re.IGNORECASE).strip()

    log_copilot_turn(user_message, tool_calls, thought_steps, clean_final)

    return {
        "thought_steps": thought_steps,
        "response_text": clean_final,
        "recommended_cars": recommended_cars
    }
