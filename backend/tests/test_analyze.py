import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from src.db.client import supabase
from src.api.routes import needs_parse, sse_event

client = TestClient(app)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


@pytest.mark.integration
def test_analyze_full_pipeline():
    food_path = os.path.join(PROJECT_ROOT, "test_data/chicago_illporcelino/Food.png")
    drinks_path = os.path.join(
        PROJECT_ROOT, "test_data/chicago_illporcelino/Drinks.png"
    )

    with open(food_path, "rb") as food, open(drinks_path, "rb") as drinks:
        response = client.post(
            "/api/analyze",
            data={
                "name": "Test Il Porcellino",
                "address": "59 W Hubbard St, Chicago, IL 60654",
                "lat": "41.8902",
                "lng": "-87.6308",
                "state": "IL",
            },
            files=[
                ("files", ("Food.png", food, "image/png")),
                ("files", ("Drinks.png", drinks, "image/png")),
            ],
        )

    assert response.status_code == 200
    body = response.json()

    restaurant_id = body["restaurant_id"]

    try:
        assert body["nearest_market"] == "Chicago"
        assert body["files_uploaded"] == 2

    finally:
        menu_files = (
            supabase.table("menu_files")
            .select("storage_path")
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
        for mf in menu_files.data:
            try:
                supabase.storage.from_("menus").remove([mf["storage_path"]])
            except Exception:
                pass

        supabase.table("menu_files").delete().eq(
            "restaurant_id", restaurant_id
        ).execute()
        supabase.table("restaurants").delete().eq("id", restaurant_id).execute()


def test_analyze_requires_files():
    response = client.post(
        "/api/analyze",
        data={
            "name": "Test Restaurant",
            "address": "123 Main St",
            "lat": "41.88",
            "lng": "-87.63",
            "state": "IL",
        },
    )
    assert response.status_code == 422


# --- needs_parse ---


def make_needs_parse_mock(
    commodities_data, menu_files_data=None, menu_parses_data=None
):
    """Build a mock supabase client with table routing for needs_parse tests."""
    mock_sb = MagicMock()

    def table_router(name):
        t = MagicMock()
        if name == "restaurant_commodities":
            t.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
                data=commodities_data
            )
        elif name == "menu_files":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=menu_files_data or []
            )
        elif name == "menu_parses":
            t.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
                data=menu_parses_data or []
            )
        return t

    mock_sb.table.side_effect = table_router
    return mock_sb


def test_needs_parse_no_commodities():
    """New restaurant with no commodities → needs parse."""
    mock_sb = make_needs_parse_mock(commodities_data=[])
    assert needs_parse(mock_sb, "rest-1") is True


def test_needs_parse_commodities_exist_no_new_menu():
    """Commodities exist and parse is newer than upload → skip."""
    mock_sb = make_needs_parse_mock(
        commodities_data=[{"id": "rc-1"}],
        menu_files_data=[{"uploaded_at": "2025-01-01T00:00:00Z"}],
        menu_parses_data=[{"parsed_at": "2025-01-01T00:01:00Z"}],
    )
    assert needs_parse(mock_sb, "rest-1") is False


def test_needs_parse_new_menu_uploaded():
    """Menu uploaded after last parse → needs parse."""
    mock_sb = make_needs_parse_mock(
        commodities_data=[{"id": "rc-1"}],
        menu_files_data=[{"uploaded_at": "2025-01-02T00:00:00Z"}],
        menu_parses_data=[{"parsed_at": "2025-01-01T00:00:00Z"}],
    )
    assert needs_parse(mock_sb, "rest-1") is True


def test_needs_parse_no_parse_record():
    """Commodities exist but no parse record → needs parse."""
    mock_sb = make_needs_parse_mock(
        commodities_data=[{"id": "rc-1"}],
        menu_files_data=[{"uploaded_at": "2025-01-01T00:00:00Z"}],
        menu_parses_data=[],
    )
    assert needs_parse(mock_sb, "rest-1") is True


# --- sse_event ---


def test_sse_event_running():
    event = sse_event("menu_parse", "running")
    assert event == 'data: {"step": "menu_parse", "status": "running"}\n\n'


def test_sse_event_done_with_result():
    event = sse_event("trends", "done", {"computed": 12})
    assert '"step": "trends"' in event
    assert '"computed": 12' in event
    assert event.startswith("data: ")
    assert event.endswith("\n\n")
