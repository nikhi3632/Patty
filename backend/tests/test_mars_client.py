import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.pricing.mars_client import parse_price, parse_mars_date


def test_parse_price_valid():
    assert parse_price("40.00") == 40.0
    assert parse_price("1,250.50") == 1250.5
    assert parse_price(35) == 35.0


def test_parse_price_invalid():
    assert parse_price(None) is None
    assert parse_price("") is None
    assert parse_price("N/A") is None


def test_parse_mars_date_formats():
    dt = parse_mars_date("02/26/2026")
    assert dt.year == 2026
    assert dt.month == 2
    assert dt.day == 26

    dt2 = parse_mars_date("2026-02-26")
    assert dt2.year == 2026

    assert parse_mars_date("") is None
    assert parse_mars_date(None) is None


@pytest.mark.integration
def test_fetch_mars_prices_terminal():
    from src.core.pricing.mars_client import fetch_mars_prices

    # slug 2290 = Chicago Terminal Market Fruits
    records = fetch_mars_prices(2290)

    assert len(records) > 0
    record = records[0]
    assert record["commodity"]
    assert record["terminal_market"]
    assert record["report_date"]
    assert record["slug_id"] == 2290


@pytest.mark.integration
def test_fetch_and_store_mars():
    from src.db.client import supabase
    from src.core.pricing.mars_client import fetch_and_store_mars

    count = fetch_and_store_mars(supabase, 2290)
    assert count > 0

    rows = (
        supabase.table("wholesale_prices")
        .select("*")
        .eq("slug_id", 2290)
        .limit(5)
        .execute()
    )
    assert len(rows.data) > 0
    assert rows.data[0]["commodity"]
