import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

RESTAURANT_ID = "00000000-0000-0000-0000-000000000001"


@patch("src.api.routes.supabase")
def test_list_suppliers(mock_sb):
    rows = [
        {
            "id": "s1",
            "name": "ABC Foods",
            "email": "sales@abc.com",
            "website": "https://abc.com",
        },
        {
            "id": "s2",
            "name": "XYZ Produce",
            "email": None,
            "website": "https://xyz.com",
        },
    ]
    mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=rows
    )

    resp = client.get(f"/api/restaurants/{RESTAURANT_ID}/suppliers")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2
    assert resp.json()["data"][0]["name"] == "ABC Foods"


@patch("src.api.routes.supabase")
def test_list_suppliers_empty(mock_sb):
    mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[]
    )

    resp = client.get(f"/api/restaurants/{RESTAURANT_ID}/suppliers")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


@patch("src.api.routes.find_suppliers")
def test_refresh_suppliers(mock_find):
    mock_find.return_value = {
        "restaurant_id": RESTAURANT_ID,
        "suppliers_found": 3,
        "suppliers": [
            {"name": "Supplier A"},
            {"name": "Supplier B"},
            {"name": "Supplier C"},
        ],
    }

    resp = client.post(f"/api/restaurants/{RESTAURANT_ID}/suppliers/refresh")
    assert resp.status_code == 200
    assert resp.json()["data"]["suppliers_found"] == 3
    mock_find.assert_called_once()
