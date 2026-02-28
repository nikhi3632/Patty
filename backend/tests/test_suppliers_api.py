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
            "distance_miles": None,
            "suppliers": {
                "id": "s1",
                "name": "ABC Foods",
                "email": "sales@abc.com",
                "website": "https://abc.com",
            },
        },
        {
            "distance_miles": 5.2,
            "suppliers": {
                "id": "s2",
                "name": "XYZ Produce",
                "email": None,
                "website": "https://xyz.com",
            },
        },
    ]
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=rows
    )

    resp = client.get(f"/api/restaurants/{RESTAURANT_ID}/suppliers")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["name"] == "ABC Foods"
    assert data[1]["name"] == "XYZ Produce"
    assert data[1]["distance_miles"] == 5.2


@patch("src.api.routes.supabase")
def test_list_suppliers_empty(mock_sb):
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
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
