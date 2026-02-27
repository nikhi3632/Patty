import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, File, Form, UploadFile
from src.db.client import supabase
from src.core.pricing.market_selector import find_nearest_market

router = APIRouter(prefix="/api")


@router.post("/analyze")
async def analyze(
    name: str = Form(...),
    address: str = Form(...),
    lat: float = Form(...),
    lng: float = Form(...),
    state: str = Form(...),
    files: list[UploadFile] = File(...),
):
    nearest_market = find_nearest_market(lat, lng)

    restaurant = (
        supabase.table("restaurants")
        .insert(
            {
                "name": name,
                "address": address,
                "lat": lat,
                "lng": lng,
                "state": state,
                "nearest_market": nearest_market,
            }
        )
        .execute()
    )
    restaurant_id = restaurant.data[0]["id"]

    file_records = []
    for f in files:
        content = await f.read()
        storage_path = f"menus/{restaurant_id}/{f.filename}"

        try:
            supabase.storage.from_("menus").remove([storage_path])
        except Exception:
            pass
        supabase.storage.from_("menus").upload(
            storage_path, content, {"content-type": f.content_type}
        )

        record = (
            supabase.table("menu_files")
            .insert(
                {
                    "restaurant_id": restaurant_id,
                    "file_type": f.content_type,
                    "storage_path": storage_path,
                    "file_name": f.filename,
                }
            )
            .execute()
        )
        file_records.append(record.data[0])

    return {
        "restaurant_id": restaurant_id,
        "nearest_market": nearest_market,
        "files_uploaded": len(file_records),
    }
