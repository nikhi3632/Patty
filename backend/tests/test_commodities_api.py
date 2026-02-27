import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

RESTAURANT_ID = "00000000-0000-0000-0000-000000000001"


def mock_supabase_list(data):
    mock = MagicMock()
    mock.table().select().eq().order().order().execute.return_value = MagicMock(
        data=data
    )
    return mock


# --- GET /api/restaurants/:id/commodities ---


@patch("src.api.routes.supabase")
def test_list_commodities(mock_sb):
    mock_sb.table().select().eq().order().order().execute.return_value = MagicMock(
        data=[
            {
                "id": "rc-1",
                "raw_ingredient_name": "tomatoes",
                "status": "tracked",
                "commodities": {"parent": "tomatoes", "display_name": "Tomatoes"},
            },
            {
                "id": "rc-2",
                "raw_ingredient_name": "truffle",
                "status": "other",
                "commodities": None,
            },
        ]
    )

    resp = client.get(f"/api/restaurants/{RESTAURANT_ID}/commodities")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["status"] == "tracked"
    assert data[1]["status"] == "other"


# --- PATCH /api/restaurant-commodities/:id ---


@patch("src.api.routes.supabase")
def test_update_commodity_confirm(mock_sb):
    mock_sb.table().update().eq().execute.return_value = MagicMock(
        data=[{"id": "rc-1", "user_confirmed": True}]
    )

    resp = client.patch(
        "/api/restaurant-commodities/rc-1",
        json={"user_confirmed": True},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["user_confirmed"] is True


@patch("src.api.routes.supabase")
def test_update_commodity_bad_automation_pref(mock_sb):
    resp = client.patch(
        "/api/restaurant-commodities/rc-1",
        json={"automation_pref": "invalid"},
    )
    assert resp.status_code == 400


@patch("src.api.routes.supabase")
def test_update_commodity_no_fields(mock_sb):
    resp = client.patch(
        "/api/restaurant-commodities/rc-1",
        json={},
    )
    assert resp.status_code == 400


@patch("src.api.routes.supabase")
def test_update_commodity_not_found(mock_sb):
    mock_sb.table().update().eq().execute.return_value = MagicMock(data=[])

    resp = client.patch(
        "/api/restaurant-commodities/nonexistent",
        json={"user_confirmed": True},
    )
    assert resp.status_code == 404


# --- DELETE /api/restaurant-commodities/:id ---


@patch("src.api.routes.supabase")
def test_delete_commodity(mock_sb):
    mock_sb.table().delete().eq().execute.return_value = MagicMock(
        data=[{"id": "rc-1"}]
    )

    resp = client.delete("/api/restaurant-commodities/rc-1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True


@patch("src.api.routes.supabase")
def test_delete_commodity_not_found(mock_sb):
    mock_sb.table().delete().eq().execute.return_value = MagicMock(data=[])

    resp = client.delete("/api/restaurant-commodities/nonexistent")
    assert resp.status_code == 404


# --- POST /api/restaurants/:id/commodities ---


@patch("src.api.routes.add_ingredient")
def test_add_commodity_tracked(mock_add):
    mock_add.return_value = {
        "status": "tracked",
        "match": {
            "matched_parent": "cheese",
            "commodity_id": "aaa",
            "confidence": "high",
            "reasoning": "Mozzarella is cheese",
        },
        "row": {"id": "new-1", "status": "tracked"},
    }

    resp = client.post(
        f"/api/restaurants/{RESTAURANT_ID}/commodities",
        json={"ingredient": "mozzarella"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "tracked"


@patch("src.api.routes.add_ingredient")
def test_add_commodity_other(mock_add):
    mock_add.return_value = {
        "status": "other",
        "match": {
            "matched_parent": None,
            "commodity_id": None,
            "confidence": "low",
            "reasoning": "No match",
        },
        "row": {"id": "new-2", "status": "other"},
    }

    resp = client.post(
        f"/api/restaurants/{RESTAURANT_ID}/commodities",
        json={"ingredient": "sriracha"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "other"


def test_add_commodity_empty_name():
    resp = client.post(
        f"/api/restaurants/{RESTAURANT_ID}/commodities",
        json={"ingredient": "  "},
    )
    assert resp.status_code == 400


# --- POST /api/restaurants/:id/commodities/confirm ---


@patch("src.api.routes.supabase")
def test_bulk_confirm(mock_sb):
    mock_sb.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "rc-1"}]
    )

    resp = client.post(
        f"/api/restaurants/{RESTAURANT_ID}/commodities/confirm",
        json={"item_ids": ["rc-1", "rc-2"]},
    )
    assert resp.status_code == 200
    assert resp.json()["confirmed"] == 2
