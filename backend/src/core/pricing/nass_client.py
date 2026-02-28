import sys
import os
import time
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get
from src.core.pricing.interruptible import InterruptHandler


def fetch_nass_prices(
    commodity_desc: str, state: str = "US", months: int = 12
) -> list[dict]:
    """Fetch PRICE RECEIVED data for a commodity from NASS QuickStats.

    Returns raw API records sorted by year/month descending.
    """
    base = get("NASS_BASE_URL")
    key = get("NASS_API_KEY")

    params = {
        "key": key,
        "commodity_desc": commodity_desc,
        "statisticcat_desc": "PRICE RECEIVED",
        "freq_desc": "MONTHLY",
        "format": "JSON",
    }

    if state == "US":
        params["agg_level_desc"] = "NATIONAL"
    else:
        params["agg_level_desc"] = "STATE"
        params["state_alpha"] = state

    data = []
    for attempt in range(5):
        resp = httpx.get(f"{base}/api_GET/", params=params, timeout=30)
        if resp.status_code == 400:
            # NASS returns 400 when no data matches the query — not an error
            return []
        if resp.status_code != 200:
            if attempt == 4:
                resp.raise_for_status()
            time.sleep(5 * (2**attempt))
            continue
        try:
            body = resp.json()
            data = body.get("data", [])
            break
        except Exception:
            if attempt == 4:
                raise
            time.sleep(5 * (2**attempt))  # 5, 10, 20, 40, 80s

    records = []
    for row in data:
        value = row.get("Value", "").strip()
        unit = row.get("unit_desc", "")
        if not value or value.startswith("("):
            continue
        if not unit.startswith("$"):
            continue

        try:
            price = float(value.replace(",", ""))
        except ValueError:
            continue
        year = int(row["year"])
        month = int(row["begin_code"])

        records.append(
            {
                "commodity": row["commodity_desc"],
                "short_desc": row["short_desc"],
                "price": price,
                "unit": row["unit_desc"],
                "year": year,
                "month": month,
                "state": row.get("state_alpha", "US"),
                "agg_level": row["agg_level_desc"],
            }
        )

    records.sort(key=lambda r: (r["year"], r["month"]), reverse=True)
    return records[:months]


def store_nass_prices(supabase_client, records: list[dict]) -> int:
    """Upsert NASS price records into commodity_prices table. Returns count stored."""
    batch_size = 500
    stored = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase_client.table("commodity_prices").upsert(
            batch, on_conflict="commodity,short_desc,year,month,state"
        ).execute()
        stored += len(batch)
    return stored


def fetch_and_store_nass(
    supabase_client, commodity_desc: str, state: str = "US", months: int = 12
) -> int:
    """Fetch prices from NASS and store them. Returns count stored."""
    records = fetch_nass_prices(commodity_desc, state, months)
    return store_nass_prices(supabase_client, records)


def fetch_all_nass_prices(supabase_client, state: str = "US", months: int = 12) -> dict:
    """Fetch prices for ALL NASS commodities in the registry.

    Handles Ctrl+C gracefully — stops fetching, returns what was stored so far.
    """
    commodities = (
        supabase_client.table("commodities")
        .select("source_params")
        .eq("source", "NASS")
        .execute()
    )

    total_commodities = len(commodities.data)
    total = 0
    errors = []

    with InterruptHandler() as handler:
        for i, row in enumerate(commodities.data, 1):
            if handler.interrupted:
                print(f"  Stopped early at {i}/{total_commodities}")
                break

            commodity_desc = row["source_params"]["commodity_desc"]
            try:
                count = fetch_and_store_nass(
                    supabase_client, commodity_desc, state, months
                )
                total += count
                print(f"  [{i}/{total_commodities}] {commodity_desc}: {count} prices")
            except Exception as e:
                errors.append({"commodity": commodity_desc, "error": str(e)})
                print(f"  [{i}/{total_commodities}] {commodity_desc}: ERROR {e}")
            time.sleep(1)

    return {"total_prices": total, "errors": errors}
