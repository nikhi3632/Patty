import sys
import os
import math
import hashlib
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.core.geo import haversine, geocode

# Cache: {terminal_market_name: (lat, lng)}
db_market_coords_cache: dict[str, tuple[float, float]] | None = None


def get_db_market_coords(supabase_client) -> dict[str, tuple[float, float]]:
    """Get geocoded coordinates for all terminal markets in the DB.

    Cached after first call to avoid repeated queries and geocoding.
    """
    global db_market_coords_cache
    if db_market_coords_cache is not None:
        return db_market_coords_cache

    rows = (
        supabase_client.table("wholesale_prices")
        .select("terminal_market")
        .limit(1000)
        .execute()
    )
    names = {r["terminal_market"] for r in rows.data if r["terminal_market"]}

    coords = {}
    for name in names:
        result = geocode(name)
        if result:
            coords[name] = result

    db_market_coords_cache = coords
    return coords


def resolve_mars_market(supabase_client, lat: float, lng: float) -> str:
    """Resolve a restaurant's location to the nearest MARS terminal market.

    Uses the actual terminal_market values from wholesale_prices, not API report titles.
    """
    market_coords = get_db_market_coords(supabase_client)
    if not market_coords:
        return ""

    return min(
        market_coords,
        key=lambda m: haversine(lat, lng, market_coords[m][0], market_coords[m][1]),
    )


# --- Price series helpers ---


def build_mars_series(
    supabase_client, parent: str, market: str
) -> tuple[list[float], list[str]]:
    """Pull full MARS price history for a parent category.

    Returns (daily_avg_mid_prices, dates).
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
        return [], []

    prices = (
        supabase_client.table("wholesale_prices")
        .select("report_date, low_price, high_price")
        .in_("commodity", raw_names)
        .eq("terminal_market", market)
        .order("report_date", desc=False)
        .execute()
    )

    if not prices.data:
        return [], []

    date_mids = defaultdict(list)
    for p in prices.data:
        low = p["low_price"] or 0
        high = p["high_price"] or low
        date_mids[p["report_date"]].append((low + high) / 2)

    dates = sorted(date_mids.keys())
    series = [sum(date_mids[d]) / len(date_mids[d]) for d in dates]
    return series, dates


def build_nass_series(
    supabase_client, parent: str
) -> tuple[list[float], str, list[str]]:
    """Pull full NASS price history for a parent category.

    Returns (monthly_prices, unit, date_labels).
    Date labels are "YYYY-MM" strings for range display.
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
        return [], "", []

    prices = (
        supabase_client.table("commodity_prices")
        .select("price, unit, year, month")
        .in_("commodity", raw_names)
        .eq("agg_level", "NATIONAL")
        .order("year", desc=False)
        .order("month", desc=False)
        .execute()
    )

    if not prices.data:
        return [], "", []

    sorted_prices = sorted(prices.data, key=lambda p: (p["year"], p["month"]))
    series = [p["price"] for p in sorted_prices]
    unit = sorted_prices[-1]["unit"]
    dates = [f"{p['year']}-{p['month']:02d}" for p in sorted_prices]
    return series, unit, dates


# --- Statistical calibration ---


def pct_changes(series: list[float]) -> list[float]:
    """Compute period-over-period percentage changes from a price series."""
    changes = []
    for i in range(1, len(series)):
        if series[i - 1] != 0:
            changes.append((series[i] - series[i - 1]) / series[i - 1] * 100)
    return changes


def rolling_std(series: list[float], window: int = 10) -> float:
    """Compute the average rolling standard deviation of a series."""
    if len(series) < window:
        return std(series) if series else 0.0

    stds = []
    for i in range(window, len(series) + 1):
        chunk = series[i - window : i]
        stds.append(std(chunk))
    return sum(stds) / len(stds) if stds else 0.0


def std(values: list[float]) -> float:
    """Sample standard deviation (Bessel's correction, n-1)."""
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def autocorrelation(series: list[float], max_lag: int = 20) -> int:
    """Find the lag (1..max_lag) with the highest autocorrelation.

    Returns the lag that shows the strongest repeating pattern.
    """
    if len(series) < max_lag + 2:
        max_lag = max(1, len(series) // 2 - 1)

    if max_lag < 1:
        return 1

    n = len(series)
    m = mean(series)
    var = sum((x - m) ** 2 for x in series)

    if var == 0:
        return 1

    best_lag = 1
    best_corr = -2.0

    for lag in range(1, max_lag + 1):
        corr = sum((series[i] - m) * (series[i - lag] - m) for i in range(lag, n))
        corr /= var
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    return best_lag


def percentile(sorted_values: list[float], pct: float) -> float:
    """Compute the pct-th percentile of a sorted list using linear interpolation."""
    k = (len(sorted_values) - 1) * pct / 100
    f = int(k)
    c = f + 1
    if c >= len(sorted_values):
        return sorted_values[f]
    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


def compute_vol_stats(supabase_client) -> dict:
    """Compute volatility percentiles across all calibrated commodities.

    Returns {p25, p50, p75} from the full commodity_calibrations table.
    Used by compute_dynamic_horizon to define "high" and "low" volatility
    relative to the data, not hardcoded thresholds.
    """
    rows = (
        supabase_client.table("commodity_calibrations")
        .select("volatility")
        .gt("volatility", 0)
        .execute()
    )
    vols = sorted(r["volatility"] for r in rows.data)

    if len(vols) < 4:
        # Bootstrap fallback: not enough commodities yet to form a real distribution.
        # Conservative defaults matching typical USDA commodity volatility ranges.
        # Replaced by actual data after 4+ commodities are calibrated.
        return {"p25": 3.0, "p50": 8.0, "p75": 15.0}

    return {
        "p25": percentile(vols, 25),
        "p50": percentile(vols, 50),
        "p75": percentile(vols, 75),
    }


def compute_dynamic_horizon(
    volatility: float, acf_lag: int, n_points: int, vol_stats: dict
) -> int:
    """Determine the recent window size based on volatility and autocorrelation.

    Volatility thresholds are relative to the system-wide distribution (vol_stats),
    not hardcoded breakpoints. "High volatility" means above the 75th percentile
    of all tracked commodities. As the system tracks more commodities, the
    distribution gets richer and thresholds adapt automatically.

    The horizon scales continuously from 0.5x base (very volatile) to 2.0x base
    (very stable) instead of jumping at arbitrary breakpoints.
    """
    if n_points < 6:
        return max(2, n_points // 2)

    base = max(3, acf_lag)

    # Normalize volatility to 0-1 using the interquartile range.
    # 0 = at or below p25 (stable), 1 = at or above p75 (volatile).
    iqr = vol_stats["p75"] - vol_stats["p25"]
    if iqr > 0:
        vol_pct = (volatility - vol_stats["p25"]) / iqr
        vol_pct = max(0.0, min(1.0, vol_pct))
    else:
        vol_pct = 0.5

    # Continuous scaling: high percentile → 0.5x base, low → 2.0x base
    scale = 2.0 - 1.5 * vol_pct
    horizon = int(base * scale)

    return max(3, min(horizon, n_points // 2))


def calibrate(series: list[float], source: str, market: str = None) -> dict:
    """Calibrate a price series: compute volatility, autocorrelation,
    and the distribution of historical changes (mean, std).

    dynamic_horizon is NOT computed here — it requires system-wide vol_stats
    and is set later by compute_trends after all commodities are calibrated.

    Returns a dict ready for DB storage.
    """
    changes = pct_changes(series)

    if len(changes) < 3:
        return {
            "source": source,
            "market": market,
            "volatility": 0.0,
            "autocorrelation_lag": 1,
            "dynamic_horizon": max(2, len(series) // 2),
            "mean_change": 0.0,
            "std_change": 0.0,
            "data_points_used": len(series),
        }

    vol = rolling_std(changes)
    acf_lag = autocorrelation(changes)
    mean_chg = mean(changes)
    std_chg = std(changes)

    return {
        "source": source,
        "market": market,
        "volatility": round(vol, 4),
        "autocorrelation_lag": acf_lag,
        "dynamic_horizon": 0,
        "mean_change": round(mean_chg, 4),
        "std_change": round(std_chg, 4),
        "data_points_used": len(series),
    }


# --- Z-score trend computation ---


def date_range_for_horizon(dates: list[str], horizon: int) -> str | None:
    """Derive the date range string for the z-score comparison window.

    The z-score compares series[-(horizon*2):-horizon] vs series[-horizon:],
    so the full window spans the last (horizon*2) data points.
    """
    if not dates or len(dates) < horizon * 2:
        return None
    start = dates[-(horizon * 2)]
    end = dates[-1]
    return f"{start} to {end}"


def compute_z_score(
    series: list[float], horizon: int, mean_change: float, std_change: float
) -> dict | None:
    """Compute the current trend z-score for a price series using calibration params.

    Compares recent window (sized by dynamic horizon) vs the prior window.
    Returns z-score, current avg, previous avg, and change pct.
    """
    if len(series) < horizon + 2:
        return None

    recent = series[-horizon:]
    earlier = series[-(horizon * 2) : -horizon]

    if not earlier:
        return None

    recent_avg = mean(recent)
    earlier_avg = mean(earlier)

    if earlier_avg == 0:
        return None

    change_pct = (recent_avg - earlier_avg) / earlier_avg * 100

    if std_change > 0:
        z_score = (change_pct - mean_change) / std_change
    else:
        z_score = 0.0

    return {
        "current": round(recent_avg, 2),
        "previous": round(earlier_avg, 2),
        "change_pct": round(change_pct, 2),
        "z_score": round(z_score, 2),
        "horizon": horizon,
    }


def classify_signal(mars_z: float | None, nass_z: float | None) -> str:
    """Classify trend signal based on z-scores from MARS and NASS.

    Z-score thresholds:
      |z| >= 2.0 → strong signal (very unusual for this commodity)
      |z| >= 1.5 → moderate signal (notable move)
      |z| < 1.5  → stable (within normal range)
    """

    def direction(z):
        if z is None:
            return None
        if z >= 2.0:
            return "up"
        if z <= -2.0:
            return "down"
        if z >= 1.5:
            return "moderate_up"
        if z <= -1.5:
            return "moderate_down"
        return "flat"

    mars_dir = direction(mars_z)
    nass_dir = direction(nass_z)

    # Both present
    if mars_dir and nass_dir:
        dirs = (mars_dir, nass_dir)

        # Both strong same direction
        if mars_dir == nass_dir == "up":
            return "strong_up"
        if mars_dir == nass_dir == "down":
            return "strong_down"

        # Both moderate same direction
        if mars_dir == nass_dir == "moderate_up":
            return "moderate_up"
        if mars_dir == nass_dir == "moderate_down":
            return "moderate_down"

        # One strong + one moderate same side
        if set(dirs) == {"up", "moderate_up"}:
            return "strong_up"
        if set(dirs) == {"down", "moderate_down"}:
            return "strong_down"

        # Both flat
        if mars_dir == nass_dir == "flat":
            return "stable"

        # Opposing directions (one up-ish, one down-ish)
        up_set = {"up", "moderate_up"}
        down_set = {"down", "moderate_down"}
        if (mars_dir in up_set and nass_dir in down_set) or (
            mars_dir in down_set and nass_dir in up_set
        ):
            return "mixed"

        # One significant + one flat
        if mars_dir in up_set or nass_dir in up_set:
            return "moderate_up"
        if mars_dir in down_set or nass_dir in down_set:
            return "moderate_down"

        return "stable"

    # Only one source
    single = mars_dir or nass_dir
    if single in ("up", "moderate_up"):
        return "moderate_up"
    if single in ("down", "moderate_down"):
        return "moderate_down"
    return "stable"


# --- Calibration caching ---


def series_checksum(series: list[float]) -> str:
    """Fast fingerprint of a price series for cache invalidation.

    Catches data corrections where point count stays the same but values change.
    """
    raw = ",".join(f"{v:.4f}" for v in series)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def load_or_recalibrate(
    supabase_client,
    commodity_id: str,
    series: list[float],
    source: str,
    market: str | None,
    now: str,
) -> dict:
    """Load existing calibration if still valid, otherwise recalibrate.

    A calibration is valid when both data_points_used matches the current
    series length AND the series_checksum matches (catches corrections
    where count stays the same but values change).
    """
    checksum = series_checksum(series)

    query = (
        supabase_client.table("commodity_calibrations")
        .select("*")
        .eq("commodity_id", commodity_id)
        .eq("source", source)
    )
    if market:
        query = query.eq("market", market)
    else:
        query = query.is_("market", "null")

    existing = query.execute()

    if existing.data:
        stored = existing.data[0]
        if (
            stored.get("data_points_used") == len(series)
            and stored.get("series_checksum") == checksum
        ):
            return stored

    cal = calibrate(series, source, market)
    cal["commodity_id"] = commodity_id
    cal["calibrated_at"] = now
    cal["series_checksum"] = checksum

    supabase_client.table("commodity_calibrations").upsert(
        cal, on_conflict="commodity_id,source,market"
    ).execute()

    return cal


# --- Main orchestrator ---


def compute_trends(supabase_client, restaurant_id: str) -> dict:
    """Compute self-calibrating price trends for all tracked commodities.

    Two-pass approach:
    1. Pull price history and calibrate every commodity (volatility, acf_lag, etc.)
    2. Compute system-wide vol_stats from all calibrations, then use those
       to derive data-driven horizons and z-scores for each commodity.

    This means "high volatility" is defined by the data itself — above the 75th
    percentile of all tracked commodities — not by hardcoded thresholds.
    """
    restaurant = (
        supabase_client.table("restaurants")
        .select("lat, lng")
        .eq("id", restaurant_id)
        .single()
        .execute()
    )
    lat = float(restaurant.data["lat"])
    lng = float(restaurant.data["lng"])
    mars_market = resolve_mars_market(supabase_client, lat, lng)

    tracked = (
        supabase_client.table("restaurant_commodities")
        .select("commodity_id, raw_ingredient_name, commodities(id, parent)")
        .eq("restaurant_id", restaurant_id)
        .eq("status", "tracked")
        .execute()
    )

    now = datetime.now(timezone.utc).isoformat()

    # --- Pass 1: Pull data + calibrate all commodities ---
    prepared = []
    for item in tracked.data:
        commodity = item.get("commodities")
        if not commodity:
            continue

        parent = commodity["parent"]
        commodity_id = commodity["id"]

        mars_series, mars_dates = build_mars_series(
            supabase_client, parent, mars_market
        )
        nass_series, nass_unit, nass_dates = build_nass_series(supabase_client, parent)

        mars_cal = None
        nass_cal = None

        if len(mars_series) >= 6:
            mars_cal = load_or_recalibrate(
                supabase_client, commodity_id, mars_series, "MARS", mars_market, now
            )

        if len(nass_series) >= 6:
            nass_cal = load_or_recalibrate(
                supabase_client, commodity_id, nass_series, "NASS", None, now
            )

        if not mars_cal and not nass_cal:
            continue

        prepared.append(
            {
                "parent": parent,
                "commodity_id": commodity_id,
                "mars_series": mars_series,
                "mars_dates": mars_dates,
                "mars_cal": mars_cal,
                "nass_series": nass_series,
                "nass_unit": nass_unit,
                "nass_dates": nass_dates,
                "nass_cal": nass_cal,
            }
        )

    # --- Compute system-wide volatility distribution ---
    vol_stats = compute_vol_stats(supabase_client)

    # --- Pass 2: Compute horizons + z-scores using data-driven thresholds ---
    # DB-generated fields that should not be sent back in upserts
    db_fields = {"id", "created_at"}

    computed = 0
    results = []

    for p in prepared:
        mars_result = None
        nass_result = None

        if p["mars_cal"]:
            horizon = compute_dynamic_horizon(
                p["mars_cal"]["volatility"],
                p["mars_cal"]["autocorrelation_lag"],
                len(p["mars_series"]),
                vol_stats,
            )
            p["mars_cal"]["dynamic_horizon"] = horizon
            upsert_row = {k: v for k, v in p["mars_cal"].items() if k not in db_fields}
            supabase_client.table("commodity_calibrations").upsert(
                upsert_row, on_conflict="commodity_id,source,market"
            ).execute()

            mars_result = compute_z_score(
                p["mars_series"],
                horizon,
                p["mars_cal"]["mean_change"],
                p["mars_cal"]["std_change"],
            )
            if mars_result:
                mars_result["market"] = mars_market
                mars_result["commodity"] = p["parent"]

        if p["nass_cal"]:
            horizon = compute_dynamic_horizon(
                p["nass_cal"]["volatility"],
                p["nass_cal"]["autocorrelation_lag"],
                len(p["nass_series"]),
                vol_stats,
            )
            p["nass_cal"]["dynamic_horizon"] = horizon
            upsert_row = {k: v for k, v in p["nass_cal"].items() if k not in db_fields}
            supabase_client.table("commodity_calibrations").upsert(
                upsert_row, on_conflict="commodity_id,source,market"
            ).execute()

            nass_result = compute_z_score(
                p["nass_series"],
                horizon,
                p["nass_cal"]["mean_change"],
                p["nass_cal"]["std_change"],
            )
            if nass_result:
                nass_result["unit"] = p["nass_unit"]

        if not mars_result and not nass_result:
            continue

        signal = classify_signal(
            mars_result["z_score"] if mars_result else None,
            nass_result["z_score"] if nass_result else None,
        )

        mars_dr = None
        if mars_result:
            mars_dr = date_range_for_horizon(p["mars_dates"], mars_result["horizon"])
        nass_dr = None
        if nass_result:
            nass_dr = date_range_for_horizon(p["nass_dates"], nass_result["horizon"])

        trend_row = (
            supabase_client.table("trends")
            .upsert(
                {
                    "restaurant_id": restaurant_id,
                    "commodity_id": p["commodity_id"],
                    "parent": p["parent"],
                    "signal": signal,
                    "computed_at": now,
                },
                on_conflict="restaurant_id,commodity_id",
            )
            .execute()
        )
        trend_id = trend_row.data[0]["id"]

        if mars_result:
            supabase_client.table("trend_signals").upsert(
                {
                    "trend_id": trend_id,
                    "source": "mars",
                    "raw_commodity": mars_result["commodity"],
                    "market": mars_result["market"],
                    "current_price": mars_result["current"],
                    "previous_price": mars_result["previous"],
                    "change_pct": mars_result["change_pct"],
                    "z_score": mars_result["z_score"],
                    "horizon": mars_result["horizon"],
                    "date_range": mars_dr,
                },
                on_conflict="trend_id,source",
            ).execute()

        if nass_result:
            supabase_client.table("trend_signals").upsert(
                {
                    "trend_id": trend_id,
                    "source": "nass",
                    "current_price": nass_result["current"],
                    "previous_price": nass_result["previous"],
                    "change_pct": nass_result["change_pct"],
                    "z_score": nass_result["z_score"],
                    "horizon": nass_result["horizon"],
                    "unit": nass_result["unit"],
                    "date_range": nass_dr,
                },
                on_conflict="trend_id,source",
            ).execute()
        computed += 1
        results.append(
            {
                "parent": p["parent"],
                "signal": signal,
                "mars": mars_result,
                "nass": nass_result,
                "mars_calibration": p["mars_cal"],
                "nass_calibration": p["nass_cal"],
            }
        )

    return {
        "restaurant_id": restaurant_id,
        "mars_market": mars_market,
        "computed": computed,
        "vol_stats": vol_stats,
        "trends": results,
    }
