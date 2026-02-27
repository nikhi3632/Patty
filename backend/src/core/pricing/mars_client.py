import sys
import os
import time
from datetime import datetime
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get
from src.core.pricing.interruptible import InterruptHandler


def fetch_mars_prices(
    slug_id: int, report_date: str = None, last_reports: int = 1
) -> list[dict]:
    """Fetch price data from a MARS report.

    report_date format: "MM/DD/YYYY". If None, fetches the latest report(s).
    last_reports: how many recent reports to fetch (e.g., 30 for ~30 days of daily data).
    Returns parsed price records.
    """
    key = get("MYMARKET_NEWS_API_KEY")
    base = get("MYMARKET_NEWS_BASE_URL")

    params = {"allSections": "true", "lastReports": str(last_reports)}
    if report_date:
        params["q"] = f"report_date={report_date}"

    sections = []
    for attempt in range(5):
        try:
            resp = httpx.get(
                f"{base}/reports/{slug_id}",
                params=params,
                auth=(key, ""),
                timeout=60,
            )
            sections = resp.json()
            break
        except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError):
            if attempt == 4:
                raise
            time.sleep(3 * (2**attempt))  # 3, 6, 12, 24, 48s

    if not isinstance(sections, list):
        return []

    records = []
    for section in sections:
        sect_name = section.get("reportSection", "")
        if "Header" in sect_name or not section.get("results"):
            continue

        for row in section["results"]:
            commodity = row.get("commodity", "")
            if not commodity:
                continue

            item = row.get("item", "")
            item_class = row.get("class", "")
            if item and "all" not in item.lower():
                commodity = f"{commodity}, {item}"
            elif item_class and "all" not in item_class.lower():
                commodity = f"{commodity}, {item_class}"

            low = parse_price(row.get("low_price"))
            high = parse_price(row.get("high_price"))
            if low is None and high is None:
                continue

            date_str = row.get("report_date", report_date or "")
            report_dt = parse_mars_date(date_str)
            if not report_dt:
                continue

            market = row.get("market_location_city", "")

            records.append(
                {
                    "commodity": commodity,
                    "terminal_market": market,
                    "report_date": report_dt.strftime("%Y-%m-%d"),
                    "low_price": low,
                    "high_price": high,
                    "mostly_low": parse_price(row.get("mostly_low_price")),
                    "mostly_high": parse_price(row.get("mostly_high_price")),
                    "package": row.get("package", None),
                    "origin": row.get("origin", None),
                    "variety": row.get("variety", None),
                    "organic": row.get("organic", "N") == "Y",
                    "slug_id": slug_id,
                }
            )

    return records


def parse_price(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return None


def parse_mars_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def dedup_records(records: list[dict]) -> list[dict]:
    """Remove duplicates by unique constraint key, keeping last occurrence."""
    seen = {}
    for r in records:
        key = (
            r["commodity"],
            r["terminal_market"],
            r["report_date"],
            r.get("package"),
            r.get("origin"),
        )
        seen[key] = r
    return list(seen.values())


def store_mars_prices(supabase_client, records: list[dict]) -> int:
    """Upsert MARS price records into wholesale_prices table. Returns count stored."""
    records = dedup_records(records)
    batch_size = 500
    stored = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase_client.table("wholesale_prices").upsert(
            batch, on_conflict="commodity,terminal_market,report_date,package,origin"
        ).execute()
        stored += len(batch)
    return stored


def fetch_and_store_mars(
    supabase_client, slug_id: int, report_date: str = None, last_reports: int = 1
) -> int:
    """Fetch prices from a MARS report and store them. Returns count stored."""
    records = fetch_mars_prices(slug_id, report_date, last_reports)
    return store_mars_prices(supabase_client, records)


def fetch_all_mars_prices(supabase_client) -> dict:
    """Fetch historical prices for ALL distinct MARS slug_ids in the registry.

    Terminal (daily) reports: last 30 reports (~30 market days).
    Weekly reports: last 12 reports (~12 weeks).
    Handles Ctrl+C gracefully — stops fetching, returns what was stored so far.
    """
    commodities = (
        supabase_client.table("commodities")
        .select("source_params")
        .eq("source", "MARS")
        .execute()
    )

    seen_slugs = set()
    slug_meta = {}
    for row in commodities.data:
        params = row["source_params"]
        slug_id = params["slug_id"]
        if slug_id not in seen_slugs:
            seen_slugs.add(slug_id)
            slug_meta[slug_id] = params.get("market_types", [])

    total = 0
    errors = []

    with InterruptHandler() as handler:
        for i, (slug_id, market_types) in enumerate(slug_meta.items(), 1):
            if handler.interrupted:
                print(f"  Stopped early at {i}/{len(slug_meta)}")
                break

            is_daily = "Terminal" in market_types
            last_reports = 30 if is_daily else 12
            try:
                count = fetch_and_store_mars(
                    supabase_client, slug_id, last_reports=last_reports
                )
                total += count
                print(f"  [{i}/{len(slug_meta)}] slug {slug_id}: {count} prices")
            except Exception as e:
                errors.append({"slug_id": slug_id, "error": str(e)})
                print(f"  [{i}/{len(slug_meta)}] slug {slug_id}: ERROR {e}")

    return {"total_prices": total, "slugs_fetched": len(seen_slugs), "errors": errors}
