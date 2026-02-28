import sys
import os
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get
from src.core.http import safe_request
from src.core.geo import haversine, geocode

# Cache: populated once on first call
terminal_markets_cache = None  # {city: {"lat": float, "lng": float, "slugs": [str]}}


def fetch_terminal_markets() -> dict:
    with safe_request():
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

    for city in list(markets):
        coords = geocode(city)
        if coords:
            markets[city]["lat"] = coords[0]
            markets[city]["lng"] = coords[1]
        else:
            del markets[city]

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
