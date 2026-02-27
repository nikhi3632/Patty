import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.pricing.registry import parse_parent, to_display


def test_parse_parent_with_comma():
    assert parse_parent("Tomatoes, Plum Type") == "tomatoes"
    assert parse_parent("Peppers, Bell Type") == "peppers"
    assert parse_parent("Lettuce, Romaine") == "lettuce"


def test_parse_parent_without_comma():
    assert parse_parent("Asparagus") == "asparagus"
    assert parse_parent("Broccoli") == "broccoli"
    assert parse_parent("WHEAT") == "wheat"


def test_to_display_title_cases_everything():
    assert to_display("cattle") == "Cattle"
    assert to_display("hogs") == "Hogs"
    assert to_display("sheep") == "Sheep"


def test_to_display_title_case():
    assert to_display("tomatoes") == "Tomatoes"
    assert to_display("sweet potatoes") == "Sweet Potatoes"


@pytest.mark.integration
def test_refresh_registry_populates_db():
    from src.db.client import supabase
    from src.core.pricing.registry import refresh_registry

    result = refresh_registry(supabase)

    assert result["total_commodities"] > 100
    assert result["parent_categories"] > 30

    db_rows = supabase.table("commodities").select("id", count="exact").execute()
    assert db_rows.count >= result["total_commodities"]

    tomatoes = (
        supabase.table("commodities")
        .select("raw_name, source")
        .eq("parent", "tomatoes")
        .execute()
    )
    assert len(tomatoes.data) >= 2
