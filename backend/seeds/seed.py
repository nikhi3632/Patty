"""Seed static reference data: commodity registry + price history.

This populates the data the system needs to function:
1. Commodity registry (NASS + MARS commodity lists)
2. NASS national price data
3. MARS wholesale price data
4. has_price_data / markets_covered flags on commodities
5. Kitchen aliases for commodity parents (LLM-generated)

Restaurants, menus, and all per-restaurant data are created
through the product flow, not seeded.
"""

import sys
import os

import psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import get
from src.db.client import supabase
from src.core.pricing.registry import refresh_registry
from src.core.pricing.nass_client import fetch_all_nass_prices
from src.core.pricing.mars_client import fetch_all_mars_prices
from src.core.pricing.aliases import generate_all_aliases


def update_price_availability():
    """Set has_price_data and markets_covered based on actual price records."""
    print("Updating price availability flags...")

    conn = psycopg2.connect(get("DATABASE_URL"))
    cur = conn.cursor()

    # NASS
    cur.execute("""
        UPDATE commodities c
        SET has_price_data = true
        WHERE EXISTS (
            SELECT 1 FROM commodity_prices cp
            WHERE LOWER(cp.commodity) = LOWER(c.parent)
        ) AND c.has_price_data = false
    """)
    nass_count = cur.rowcount

    # MARS
    cur.execute("""
        UPDATE commodities c
        SET has_price_data = true
        WHERE EXISTS (
            SELECT 1 FROM wholesale_prices wp
            WHERE LOWER(wp.commodity) = LOWER(c.parent)
        ) AND c.has_price_data = false
    """)
    mars_count = cur.rowcount

    # Markets covered — NASS states
    cur.execute("""
        UPDATE commodities c
        SET markets_covered = sub.markets
        FROM (
            SELECT LOWER(cp.commodity) AS commodity,
                   ARRAY_AGG(DISTINCT cp.state) AS markets
            FROM commodity_prices cp
            WHERE cp.state IS NOT NULL
            GROUP BY LOWER(cp.commodity)
        ) sub
        WHERE LOWER(c.parent) = sub.commodity
    """)

    # Markets covered — append MARS terminal markets
    cur.execute("""
        UPDATE commodities c
        SET markets_covered = ARRAY(
            SELECT DISTINCT unnest(c.markets_covered || sub.markets)
        )
        FROM (
            SELECT LOWER(wp.commodity) AS commodity,
                   ARRAY_AGG(DISTINCT wp.terminal_market) AS markets
            FROM wholesale_prices wp
            GROUP BY LOWER(wp.commodity)
        ) sub
        WHERE LOWER(c.parent) = sub.commodity
    """)

    conn.commit()

    cur.execute("SELECT count(*) FROM commodities WHERE has_price_data = true")
    total = cur.fetchone()[0]

    cur.close()
    conn.close()

    print(
        f"  {nass_count + mars_count} commodities flagged, {total} total with price data"
    )


def seed():
    print("1. Refreshing commodity registry...")
    result = refresh_registry(supabase)
    print(
        f"  {result['total_commodities']} commodities, "
        f"{result['parent_categories']} parents"
    )

    print("2. Fetching NASS prices...")
    nass = fetch_all_nass_prices(supabase, state="US", months=12)
    print(f"  {nass['total_prices']} prices, {len(nass['errors'])} errors")

    print("3. Fetching MARS prices...")
    mars = fetch_all_mars_prices(supabase)
    print(
        f"  {mars['total_prices']} prices from {mars['slugs_fetched']} reports, "
        f"{len(mars['errors'])} errors"
    )

    print("4. Updating price availability...")
    update_price_availability()

    print("5. Generating kitchen aliases...")
    aliases = generate_all_aliases(supabase)
    print(
        f"  {aliases['parents_processed']} parents processed, "
        f"{aliases['aliases_generated']} aliases generated"
    )

    print("Done. Reference data is ready.")


if __name__ == "__main__":
    try:
        seed()
    except KeyboardInterrupt:
        print("\nAborted. Data stored so far is safe in the DB.")
        sys.exit(1)
