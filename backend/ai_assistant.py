import os
import base64
import requests
from typing import Dict, Any, Optional

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.23:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5vl:7b")

SYSTEM_PROMPT = """You are OTTO, an in-house vehicle acquisition assistant for a used-car flipper operating in Sri Lanka (Riyasewana / Ikman.lk listings).

When given a listing, give a short, practical pre-purchase assessment:
1. Search Full Price Spectrum mindset: judge the price against the stated market average, not a padded one.
2. Disaggregate specs: flag if it's Manual vs Automatic, and Japanese vs Indian/Regional spec if inferable from the title/description.
3. Sri Lanka-specific inspection checklist for this make/model: coastal rust points, gearbox/CVT health, suspension bushings, AC coil, common local failure points for that engine family.
4. If a photo is attached, actually look at it: comment on visible condition, paint/panel mismatches, tyre wear, interior condition, odometer photo if visible.
5. A one-line verdict: BUY / NEGOTIATE / PASS, with the single biggest reason why.

Keep the whole answer under 180 words. Be direct and practical, not generic. Do not repeat the input data back verbatim."""


def _fetch_image_b64(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode("utf-8")
    except Exception:
        return None


def inspect_car(car: Dict[str, Any]) -> str:
    details = (
        f"Title: {car.get('title')}\n"
        f"Make/Model/Year: {car.get('make')} {car.get('model')} {car.get('year')}\n"
        f"Price: {car.get('price_display') or car.get('price')}\n"
        f"Market Avg (this make/model/year): {car.get('market_avg_price')}\n"
        f"Discount vs Market: {car.get('discount_pct')}%\n"
        f"Mileage: {car.get('mileage_display')}\n"
        f"Transmission: {car.get('transmission')}\n"
        f"Fuel: {car.get('fuel_type')}\n"
        f"Location: {car.get('district') or car.get('location')}\n"
        f"Liquidity Tier: {car.get('liquidity_tier')}\n"
    )

    user_message: Dict[str, Any] = {"role": "user", "content": f"Assess this listing:\n\n{details}"}

    image_b64 = _fetch_image_b64(car["image_url"]) if car.get("image_url") else None
    if image_b64:
        user_message["images"] = [image_b64]

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            user_message,
        ],
        "stream": False,
    }

    resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content", "").strip()
