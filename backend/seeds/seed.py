"""Seed test data: two restaurants with menu files uploaded to Supabase Storage."""

import sys
import os
import time
import mimetypes

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db.client import supabase
from src.core.pricing.registry import refresh_registry
from src.core.pricing.nass_client import fetch_all_nass_prices
from src.core.pricing.mars_client import fetch_all_mars_prices

REFRESH_FLAG = "--refresh" in sys.argv

RESTAURANTS = [
    {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Il Porcellino",
        "address": "59 W Hubbard St, Chicago, IL 60654, USA",
        "lat": 41.8898045,
        "lng": -87.6302880,
        "state": "IL",
        "nearest_market": "Chicago",
    },
    {
        "id": "00000000-0000-0000-0000-000000000002",
        "name": "New City Pizza",
        "address": "218 S Main St, New City, NY 10956, USA",
        "lat": 41.1395018,
        "lng": -73.9894922,
        "state": "NY",
        "nearest_market": "New York",
    },
]

MENU_FILES = [
    {
        "restaurant_id": "00000000-0000-0000-0000-000000000001",
        "files": [
            "test_data/chicago_illporcelino/Food.png",
            "test_data/chicago_illporcelino/Drinks.png",
        ],
    },
    {
        "restaurant_id": "00000000-0000-0000-0000-000000000002",
        "files": [
            "test_data/nyc_pizzeria/New_City_pizza_full_menu_Aug_2022.pdf",
        ],
    },
]

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def seed():
    for r in RESTAURANTS:
        supabase.table("restaurants").upsert(r, on_conflict="id").execute()
        print(f"  Restaurant: {r['name']}")

    for entry in MENU_FILES:
        rid = entry["restaurant_id"]

        # Clear existing menu_files for this restaurant (idempotent re-runs)
        supabase.table("menu_files").delete().eq("restaurant_id", rid).execute()

        for file_path in entry["files"]:
            full_path = os.path.join(PROJECT_ROOT, file_path)
            file_name = os.path.basename(full_path)
            content_type = (
                mimetypes.guess_type(full_path)[0] or "application/octet-stream"
            )
            storage_path = f"menus/{rid}/{file_name}"

            with open(full_path, "rb") as f:
                content = f.read()

            try:
                supabase.storage.from_("menus").remove([storage_path])
            except Exception:
                pass

            for attempt in range(3):
                try:
                    supabase.storage.from_("menus").upload(
                        storage_path, content, {"content-type": content_type}
                    )
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(1)

            supabase.table("menu_files").insert(
                {
                    "restaurant_id": rid,
                    "file_type": content_type,
                    "storage_path": storage_path,
                    "file_name": file_name,
                }
            ).execute()
            print(f"  Uploaded: {storage_path}")

    if REFRESH_FLAG:
        print("Refreshing commodity registry...")
        result = refresh_registry(supabase)
        print(
            f"  {result['total_commodities']} commodities, {result['parent_categories']} parents"
        )

        print("Fetching NASS prices (Ctrl+C to skip)...")
        nass = fetch_all_nass_prices(supabase, state="US", months=12)
        print(
            f"  NASS total: {nass['total_prices']} prices, {len(nass['errors'])} errors"
        )

        print("Fetching MARS prices (Ctrl+C to skip)...")
        mars = fetch_all_mars_prices(supabase)
        print(
            f"  MARS total: {mars['total_prices']} prices from {mars['slugs_fetched']} reports, {len(mars['errors'])} errors"
        )
    else:
        print("Skipping registry + prices (use 'make db-refresh' to fetch)")

    print("Done.")


if __name__ == "__main__":
    try:
        seed()
    except KeyboardInterrupt:
        print("\nAborted. Data stored so far is safe in the DB.")
        sys.exit(1)
