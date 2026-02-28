import sys
import os
from concurrent.futures import ThreadPoolExecutor
import httpx
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get
from src.core.http import safe_request

MARS_MARKET_TYPES = {
    "Terminal",
    "Retail - Dairy",
    "Retail - Specialty Crops",
    "Point of Sale - Poultry",
    "Point of Sale - Eggs",
}


def to_display(parent: str) -> str:
    return parent.replace("_", " ").title()


def parse_parent(raw_name: str) -> str:
    if "," in raw_name:
        return raw_name.split(",", 1)[0].strip().lower()
    return raw_name.strip().lower()


def fetch_nass_commodities() -> list[dict]:
    base = get("NASS_BASE_URL")
    key = get("NASS_API_KEY")

    with safe_request():
        resp = httpx.get(
            f"{base}/get_param_values/",
            params={
                "key": key,
                "param": "commodity_desc",
                "statisticcat_desc": "PRICE RECEIVED",
            },
        )
    names = resp.json().get("commodity_desc", [])

    rows = []
    for name in names:
        parent = name.strip().lower()
        rows.append(
            {
                "parent": parent,
                "display_name": to_display(parent),
                "raw_name": name.strip(),
                "source": "NASS",
                "source_params": {
                    "commodity_desc": name.strip(),
                    "statisticcat_desc": "PRICE RECEIVED",
                },
                "unit": None,
                "cadence": "monthly",
            }
        )

    return rows


def discover_mars_reports() -> list[dict]:
    key = get("MYMARKET_NEWS_API_KEY")
    base = get("MYMARKET_NEWS_BASE_URL")

    with safe_request():
        resp = httpx.get(f"{base}/reports", auth=(key, ""), timeout=30)
    reports = resp.json()

    relevant = []
    for r in reports:
        title = r.get("report_title", "") or ""
        slug = r.get("slug_id", "")
        market_types = r.get("market_types", [])

        if not slug or "Discontinued" in title:
            continue

        if any(mt in MARS_MARKET_TYPES for mt in market_types):
            relevant.append(
                {
                    "slug_id": int(slug),
                    "title": title,
                    "market_types": market_types,
                }
            )

    return relevant


def find_latest_mars_date(reports: list[dict]) -> str:
    key = get("MYMARKET_NEWS_API_KEY")
    base = get("MYMARKET_NEWS_BASE_URL")

    for report in reports:
        try:
            with safe_request():
                resp = httpx.get(
                    f"{base}/reports/{report['slug_id']}",
                    auth=(key, ""),
                    timeout=15,
                )
            data = resp.json()
            if isinstance(data, dict) and data.get("results"):
                return data["results"][0].get(
                    "report_date",
                    data["results"][0].get("report_begin_date", ""),
                )
        except Exception:
            continue

    return datetime.now(timezone.utc).strftime("%m/%d/%Y")


def extract_commodities_from_report(slug_id: int, report_date: str | None) -> list[str]:
    key = get("MYMARKET_NEWS_API_KEY")
    base = get("MYMARKET_NEWS_BASE_URL")

    params = {"allSections": "true"}
    if report_date:
        params["q"] = f"report_date={report_date}"

    try:
        with safe_request():
            resp = httpx.get(
                f"{base}/reports/{slug_id}",
                params=params,
                auth=(key, ""),
                timeout=15,
            )
        sections = resp.json()
        if not isinstance(sections, list):
            return []
    except Exception:
        return []

    raw_names = set()

    for section in sections:
        sect_name = section.get("reportSection", "")
        if "Header" in sect_name or not section.get("results"):
            continue

        records = section["results"]
        commodities = set(r.get("commodity", "") for r in records if r.get("commodity"))

        if len(commodities) > 1:
            # Multiple commodities — use commodity field directly
            raw_names.update(commodities)
        elif len(commodities) == 1:
            # Single commodity (e.g., "Chicken", "Shell Eggs") — differentiate by item/class
            base_commodity = commodities.pop()
            detail_fields = ["item", "class"]
            for field in detail_fields:
                details = set(r.get(field, "") for r in records if r.get(field))
                details.discard("")
                if details:
                    for detail in details:
                        if "all" not in detail.lower():
                            raw_names.add(f"{base_commodity}, {detail}")
                    break
            else:
                raw_names.add(base_commodity)

        break  # only process first detail section

    return sorted(raw_names)


def cadence_for_market_type(market_types: list[str]) -> str:
    for mt in market_types:
        if mt == "Terminal":
            return "daily"
    return "weekly"


def fetch_mars_commodities(reports: list[dict], report_date: str) -> list[dict]:
    def extract(report):
        slug_id = report["slug_id"]
        is_terminal = "Terminal" in report["market_types"]
        date_param = report_date if is_terminal else None
        raw_names = extract_commodities_from_report(slug_id, date_param)
        return report, raw_names

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(extract, reports))

    seen = set()
    rows = []
    for report, raw_names in results:
        slug_id = report["slug_id"]
        market_types = report["market_types"]
        cadence = cadence_for_market_type(market_types)

        for raw in raw_names:
            dedup_key = f"{raw}|MARS"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            rows.append(
                {
                    "parent": parse_parent(raw),
                    "display_name": to_display(parse_parent(raw)),
                    "raw_name": raw,
                    "source": "MARS",
                    "source_params": {
                        "slug_id": slug_id,
                        "market_types": market_types,
                    },
                    "unit": None,
                    "cadence": cadence,
                }
            )

    return rows


def refresh_registry(supabase_client) -> dict:
    now = datetime.now(timezone.utc).isoformat()

    mars_reports = discover_mars_reports()
    mars_date = find_latest_mars_date(
        [r for r in mars_reports if "Terminal" in r["market_types"]]
    )

    nass = fetch_nass_commodities()
    mars = fetch_mars_commodities(mars_reports, mars_date)

    all_rows = nass + mars
    for row in all_rows:
        row["last_refreshed"] = now

    batch_size = 500
    for i in range(0, len(all_rows), batch_size):
        batch = all_rows[i : i + batch_size]
        supabase_client.table("commodities").upsert(
            batch, on_conflict="raw_name,source"
        ).execute()

    inserted = len(all_rows)

    parents = sorted(set(r["parent"] for r in all_rows))

    return {
        "total_commodities": inserted,
        "parent_categories": len(parents),
        "parents": parents,
    }
