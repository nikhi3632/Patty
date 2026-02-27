import sys
import os
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.core.pricing.market_selector import haversine

# Coordinates of MARS terminal markets actually present in wholesale_prices.
# Only ~9 active cities. Used for fallback when restaurant's nearest_market
# doesn't exactly match a MARS market name (e.g., "New York" → "Bronx").
MARS_MARKET_COORDS = {
    "Atlanta": (33.749, -84.388),
    "Baltimore": (39.290, -76.612),
    "Bronx": (40.837, -73.865),
    "Chicago": (41.878, -87.630),
    "Detroit": (42.331, -83.046),
    "Everett": (47.979, -122.202),
    "Los Angeles": (34.052, -118.244),
    "Miami": (25.762, -80.192),
    "Philadelphia": (39.953, -75.164),
}


def resolve_mars_market(nearest_market: str, lat: float, lng: float) -> str:
    """Resolve a restaurant's nearest_market to an actual MARS terminal market.

    Tries exact match first, falls back to nearest by haversine.
    """
    if nearest_market in MARS_MARKET_COORDS:
        return nearest_market

    return min(
        MARS_MARKET_COORDS,
        key=lambda m: haversine(lat, lng, *MARS_MARKET_COORDS[m]),
    )


def compute_mars_trend(supabase_client, parent: str, market: str) -> dict | None:
    """Compute MARS wholesale trend for a parent category at a terminal market.

    Compares average mid-price of recent 5 market days vs prior 15 market days.
    """
    commodities = (
        supabase_client.table("commodities")
        .select("raw_name")
        .eq("source", "MARS")
        .eq("parent", parent)
        .execute()
    )
    raw_names = [c["raw_name"] for c in commodities.data]
    if not raw_names:
        return None

    prices = (
        supabase_client.table("wholesale_prices")
        .select("commodity, report_date, low_price, high_price")
        .in_("commodity", raw_names)
        .eq("terminal_market", market)
        .order("report_date", desc=True)
        .limit(500)
        .execute()
    )

    if not prices.data:
        return None

    # Average mid-price per date across all varieties
    date_mids = defaultdict(list)
    for p in prices.data:
        low = p["low_price"] or 0
        high = p["high_price"] or low
        mid = (low + high) / 2
        date_mids[p["report_date"]].append(mid)

    dates = sorted(date_mids.keys(), reverse=True)
    if len(dates) < 3:
        return None

    recent_dates = dates[:5]
    earlier_dates = dates[5:20]
    if not earlier_dates:
        return None

    recent_avg = sum(sum(date_mids[d]) / len(date_mids[d]) for d in recent_dates) / len(
        recent_dates
    )
    earlier_avg = sum(
        sum(date_mids[d]) / len(date_mids[d]) for d in earlier_dates
    ) / len(earlier_dates)

    if earlier_avg == 0:
        return None

    change_pct = (recent_avg - earlier_avg) / earlier_avg * 100

    return {
        "current": round(recent_avg, 2),
        "previous": round(earlier_avg, 2),
        "change_pct": round(change_pct, 2),
        "market": market,
        "commodity": raw_names[0],
        "date_range": f"{earlier_dates[-1]} to {recent_dates[0]}",
    }


def compute_nass_trend(supabase_client, parent: str) -> dict | None:
    """Compute NASS commodity trend for a parent category (national level).

    Compares average price of recent 2 months vs prior 4 months.
    """
    commodities = (
        supabase_client.table("commodities")
        .select("raw_name")
        .eq("source", "NASS")
        .eq("parent", parent)
        .execute()
    )
    raw_names = [c["raw_name"] for c in commodities.data]
    if not raw_names:
        return None

    prices = (
        supabase_client.table("commodity_prices")
        .select("commodity, price, unit, year, month, state")
        .in_("commodity", raw_names)
        .eq("agg_level", "NATIONAL")
        .order("year", desc=True)
        .order("month", desc=True)
        .limit(12)
        .execute()
    )

    if not prices.data:
        return None

    # Sort by (year, month) descending
    sorted_prices = sorted(
        prices.data, key=lambda p: (p["year"], p["month"]), reverse=True
    )

    if len(sorted_prices) < 3:
        return None

    recent = sorted_prices[:2]
    earlier = sorted_prices[2:6]
    if not earlier:
        return None

    recent_avg = sum(p["price"] for p in recent) / len(recent)
    earlier_avg = sum(p["price"] for p in earlier) / len(earlier)

    if earlier_avg == 0:
        return None

    change_pct = (recent_avg - earlier_avg) / earlier_avg * 100

    recent_label = f"{recent[-1]['year']}-{recent[-1]['month']:02d}"
    earlier_label = f"{earlier[-1]['year']}-{earlier[-1]['month']:02d}"

    return {
        "current": round(recent_avg, 2),
        "previous": round(earlier_avg, 2),
        "change_pct": round(change_pct, 2),
        "unit": sorted_prices[0]["unit"],
        "state": sorted_prices[0].get("state", "US"),
        "date_range": f"{earlier_label} to {recent_label}",
    }


def classify_signal(mars_pct: float | None, nass_pct: float | None) -> str:
    """Classify trend signal based on MARS and NASS change percentages.

    Returns: strong_up, strong_down, moderate_up, moderate_down, stable, mixed
    """
    threshold = 5.0

    mars_dir = None
    if mars_pct is not None:
        if mars_pct > threshold:
            mars_dir = "up"
        elif mars_pct < -threshold:
            mars_dir = "down"
        else:
            mars_dir = "flat"

    nass_dir = None
    if nass_pct is not None:
        if nass_pct > threshold:
            nass_dir = "up"
        elif nass_pct < -threshold:
            nass_dir = "down"
        else:
            nass_dir = "flat"

    # Both present and agree
    if mars_dir and nass_dir:
        if mars_dir == nass_dir == "up":
            return "strong_up"
        if mars_dir == nass_dir == "down":
            return "strong_down"
        if mars_dir == nass_dir == "flat":
            return "stable"
        if "up" in (mars_dir, nass_dir) and "down" in (mars_dir, nass_dir):
            return "mixed"
        if "up" in (mars_dir, nass_dir):
            return "moderate_up"
        if "down" in (mars_dir, nass_dir):
            return "moderate_down"
        return "stable"

    # Only one layer
    direction = mars_dir or nass_dir
    if direction == "up":
        return "moderate_up"
    if direction == "down":
        return "moderate_down"
    return "stable"


def compute_trends(supabase_client, restaurant_id: str) -> dict:
    """Compute price trends for all tracked commodities of a restaurant.

    Stores results in the trends table. Returns summary.
    """
    restaurant = (
        supabase_client.table("restaurants")
        .select("nearest_market, lat, lng")
        .eq("id", restaurant_id)
        .single()
        .execute()
    )
    nearest_market = restaurant.data["nearest_market"]
    lat = float(restaurant.data["lat"])
    lng = float(restaurant.data["lng"])
    mars_market = resolve_mars_market(nearest_market, lat, lng)

    tracked = (
        supabase_client.table("restaurant_commodities")
        .select("commodity_id, raw_ingredient_name, commodities(id, parent)")
        .eq("restaurant_id", restaurant_id)
        .eq("status", "tracked")
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()
    computed = 0
    results = []

    for item in tracked.data:
        commodity = item.get("commodities")
        if not commodity:
            continue

        parent = commodity["parent"]
        commodity_id = commodity["id"]

        mars = compute_mars_trend(supabase_client, parent, mars_market)
        nass = compute_nass_trend(supabase_client, parent)

        if not mars and not nass:
            continue

        signal = classify_signal(
            mars["change_pct"] if mars else None,
            nass["change_pct"] if nass else None,
        )

        row = {
            "restaurant_id": restaurant_id,
            "commodity_id": commodity_id,
            "parent": parent,
            "nass_current": nass["current"] if nass else None,
            "nass_previous": nass["previous"] if nass else None,
            "nass_change_pct": nass["change_pct"] if nass else None,
            "nass_unit": nass["unit"] if nass else None,
            "nass_state": nass["state"] if nass else None,
            "nass_date_range": nass["date_range"] if nass else None,
            "mars_commodity": mars["commodity"] if mars else None,
            "mars_market": mars["market"] if mars else None,
            "mars_current": mars["current"] if mars else None,
            "mars_previous": mars["previous"] if mars else None,
            "mars_change_pct": mars["change_pct"] if mars else None,
            "mars_date_range": mars["date_range"] if mars else None,
            "signal": signal,
            "computed_at": now,
        }

        supabase_client.table("trends").upsert(
            row, on_conflict="restaurant_id,commodity_id"
        ).execute()
        computed += 1
        results.append({"parent": parent, "signal": signal, "mars": mars, "nass": nass})

    return {
        "restaurant_id": restaurant_id,
        "mars_market": mars_market,
        "computed": computed,
        "trends": results,
    }
