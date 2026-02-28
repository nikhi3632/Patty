import math
import sys
import os

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.config import get


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Compute distance in miles between two lat/lng points."""
    R = 3959  # Earth radius in miles
    lat1, lng1, lat2, lng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def geocode(query: str) -> tuple[float, float] | None:
    """Geocode an address or business name using Google Geocoding API.

    Returns (lat, lng) or None if not found.
    """
    result = geocode_full(query)
    if result:
        return result[0], result[1]
    return None


def geocode_full(query: str) -> tuple[float, float, str] | None:
    """Geocode and return (lat, lng, formatted_address) or None."""
    api_key = get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return None
    try:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": query, "key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                loc = results[0]["geometry"]["location"]
                addr = results[0].get("formatted_address", "")
                return loc["lat"], loc["lng"], addr
    except Exception:
        return None
    return None
