import math
import sys
import os
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

# Cache: populated once on first call
terminal_markets_cache = None  # {city: {"lat": float, "lng": float, "slugs": [str]}}


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 3959  # miles
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def geocode(city: str) -> tuple[float, float]:
    resp = httpx.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": city, "key": get("GOOGLE_PLACES_API_KEY")},
    )
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Could not geocode: {city}")
    loc = results[0]["geometry"]["location"]
    return loc["lat"], loc["lng"]


def fetch_terminal_markets() -> dict:
    resp = httpx.get(
        f"{get('MYMARKET_NEWS_BASE_URL')}/reports",
        auth=(get("MYMARKET_NEWS_API_KEY"), ""),
    )
    reports = resp.json()

    markets = {}
    for r in reports:
        title = r.get("report_title", "") or ""
        if "Terminal" not in title or "Market" not in title or "Discontinued" in title:
            continue

        city = title.split(" Terminal Market")[0].strip()
        slug = r.get("slug_id", "")

        if city not in markets:
            markets[city] = {"slugs": []}
        markets[city]["slugs"].append(str(slug))

    for city in markets:
        lat, lng = geocode(city)
        markets[city]["lat"] = lat
        markets[city]["lng"] = lng

    return markets


def get_markets() -> dict:
    global terminal_markets_cache
    if terminal_markets_cache is None:
        terminal_markets_cache = fetch_terminal_markets()
    return terminal_markets_cache


def find_nearest_market(lat: float, lng: float) -> str:
    markets = get_markets()
    return min(
        markets, key=lambda m: haversine(lat, lng, markets[m]["lat"], markets[m]["lng"])
    )


def get_market_slugs(market_name: str) -> list[str]:
    markets = get_markets()
    return markets.get(market_name, {}).get("slugs", [])
