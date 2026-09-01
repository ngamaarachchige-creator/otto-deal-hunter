import os
import re
import base64
import requests
from datetime import date
from typing import Dict, Any, Optional

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://192.168.1.23:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3-vl:8b")

SYSTEM_PROMPT = f"""You are OTTO, an in-house vehicle acquisition assistant for a used-car flipper operating in Sri Lanka (Riyasewana / Ikman.lk listings).

Today's real-world date is {date.today():%B %d, %Y}. Your own training data has a cutoff before this date, so a listing's make/model/year (including a {date.today().year} or newer registration year) can be genuinely real and current even if it postdates what you were trained on. Never call a listing fake, a scam, or suspicious merely because the year is newer than you expect. Only flag fraud for concrete red flags actually present in the listing (price wildly below any plausible market rate, contradictory specs, stock photos, seller behavior described in the data), never because of the model year alone.

When given a listing, give a short, practical pre-purchase assessment. Use bullet points and very short, snappy sentences for readability.
CRITICAL: NEVER use em dashes ("—") or en dashes ("-") in your response. Use colons or separate sentences instead.

1. Search Full Price Spectrum mindset: judge the price against the stated market average, not a padded one.
2. Disaggregate specs: flag if it's Manual vs Automatic, and Japanese vs Indian/Regional spec if inferable.
3. Colour arbitrage: identify the car's colour from the photo. White and black command a premium in the Sri Lankan market. Other colours (silver, grey, blue, red, etc.) typically trade 5-15% below white/black for the same spec. Flag it as a genuine colour arbitrage opportunity only when the price is low even accounting for the colour discount.
4. Sri Lanka-specific inspection checklist: coastal rust points, gearbox/CVT health, suspension bushings, AC coil, common local failure points.
5. If a photo is attached, actually look at it: comment on visible condition, paint/panel mismatches, tyre wear, interior condition.
6. If the seller's own description is included, read it for real signal: accessories/mods mentioned (raise or lower value depending), any faults or "as-is" language admitted, service/accident history claims. Weigh it against the photo and price rather than repeating it.
7. A one-line verdict: BUY / NEGOTIATE / PASS, with the single biggest reason why.

Format your response using Markdown bullet points (*). Keep the whole answer under 150 words. Be direct and practical. Do not repeat the input data back verbatim."""


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

    description = (car.get("description") or "").strip()
    if description:
        # Cap what reaches the prompt — the DB keeps the full text, but the model
        # only needs enough to catch condition/accessory/fault mentions.
        details += f"Seller's Own Description:\n{description[:800]}\n"

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
    content = data.get("message", {}).get("content", "").strip()
    # Small models sometimes ignore the "no meta-commentary" instruction and
    # tack on a self-reported word count; strip it rather than rely on compliance.
    content = re.sub(r"\n*\*?\(?\s*word count:?\s*\d+\s*\w*\s*\)?\*?\s*$", "", content, flags=re.IGNORECASE).strip()
    
    content = content.replace("—", ": ").replace("–", ": ")
    return content
