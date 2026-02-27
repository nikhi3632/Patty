import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app
from src.db.client import supabase

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
