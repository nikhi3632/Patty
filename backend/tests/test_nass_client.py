import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.pricing.nass_client import fetch_nass_prices, fetch_and_store_nass


@pytest.mark.integration
def test_fetch_nass_prices_corn():
    records = fetch_nass_prices("CORN", state="US", months=6)

    assert len(records) > 0
    assert len(records) <= 6

    record = records[0]
    assert record["commodity"] == "CORN"
    assert record["price"] > 0
    assert record["unit"]
    assert record["year"] >= 2024
    assert 1 <= record["month"] <= 12
    assert record["agg_level"] == "NATIONAL"


@pytest.mark.integration
def test_fetch_nass_prices_state_level():
    records = fetch_nass_prices("WHEAT", state="TX", months=6)

    assert len(records) > 0
    for r in records:
        assert r["state"] == "TX"
        assert r["agg_level"] == "STATE"


@pytest.mark.integration
def test_fetch_nass_prices_filters_withheld():
    """Records with (D) or (NA) values should be excluded."""
    records = fetch_nass_prices("CORN", state="US", months=12)
    for r in records:
        assert r["price"] > 0


@pytest.mark.integration
def test_fetch_and_store_nass():
    from src.db.client import supabase

    count = fetch_and_store_nass(supabase, "CORN", state="US", months=3)
    assert count > 0

    rows = (
        supabase.table("commodity_prices")
        .select("*")
        .eq("commodity", "CORN")
        .eq("state", "US")
        .limit(3)
        .execute()
    )
    assert len(rows.data) > 0
    assert rows.data[0]["price"] is not None
