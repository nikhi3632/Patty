import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from src.db.client import supabase
from src.core.pricing.market_selector import find_nearest_market
from src.core.menu.matcher import add_ingredient
from src.core.pricing.trend_analyzer import compute_trends
from src.core.suppliers.finder import find_suppliers
from src.core.email.drafter import draft_all_emails
from src.core.email.sender import send_email

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


# --- Restaurant Commodities ---


@router.get("/restaurants/{restaurant_id}/commodities")
def list_commodities(restaurant_id: str):
    """List tracked + other commodities for a restaurant, joined with commodity details."""
    rows = (
        supabase.table("restaurant_commodities")
        .select("*, commodities(parent, display_name, source, cadence)")
        .eq("restaurant_id", restaurant_id)
        .order("status")
        .order("raw_ingredient_name")
        .execute()
    )
    return {"data": rows.data}


class CommodityUpdate(BaseModel):
    user_confirmed: bool | None = None
    automation_pref: str | None = None


@router.patch("/restaurant-commodities/{item_id}")
def update_commodity(item_id: str, body: CommodityUpdate):
    """Update a restaurant commodity (confirm, set automation preference)."""
    updates = {}
    if body.user_confirmed is not None:
        updates["user_confirmed"] = body.user_confirmed
    if body.automation_pref is not None:
        if body.automation_pref not in ("full_auto", "review", "monitor"):
            raise HTTPException(
                400, "automation_pref must be full_auto, review, or monitor"
            )
        updates["automation_pref"] = body.automation_pref

    if not updates:
        raise HTTPException(400, "No fields to update")

    result = (
        supabase.table("restaurant_commodities")
        .update(updates)
        .eq("id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Item not found")
    return {"data": result.data[0]}


@router.delete("/restaurant-commodities/{item_id}")
def remove_commodity(item_id: str):
    """Remove a commodity from a restaurant's list."""
    result = (
        supabase.table("restaurant_commodities").delete().eq("id", item_id).execute()
    )
    if not result.data:
        raise HTTPException(404, "Item not found")
    return {"deleted": True}


class IngredientAdd(BaseModel):
    ingredient: str


@router.post("/restaurants/{restaurant_id}/commodities")
def add_commodity(restaurant_id: str, body: IngredientAdd):
    """Manually add an ingredient — Agent 2 fuzzy matches against registry."""
    ingredient = body.ingredient.strip()
    if not ingredient:
        raise HTTPException(400, "Ingredient name required")

    result = add_ingredient(supabase, restaurant_id, ingredient)
    return {"data": result}


class BulkConfirm(BaseModel):
    item_ids: list[str]


@router.post("/restaurants/{restaurant_id}/commodities/confirm")
def confirm_commodities(restaurant_id: str, body: BulkConfirm):
    """Bulk confirm tracked commodities after user review."""
    updated = 0
    for item_id in body.item_ids:
        result = (
            supabase.table("restaurant_commodities")
            .update({"user_confirmed": True})
            .eq("id", item_id)
            .eq("restaurant_id", restaurant_id)
            .execute()
        )
        if result.data:
            updated += 1
    return {"confirmed": updated}


# --- Trends ---


@router.get("/restaurants/{restaurant_id}/trends")
def get_trends(restaurant_id: str):
    """Get stored trends for a restaurant, sorted by signal strength."""
    rows = (
        supabase.table("trends")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .order("signal")
        .execute()
    )
    return {"data": rows.data}


@router.post("/restaurants/{restaurant_id}/trends/compute")
def recompute_trends(restaurant_id: str):
    """Recompute price trends for all tracked commodities."""
    result = compute_trends(supabase, restaurant_id)
    return {"data": result}


# --- Suppliers ---


@router.get("/restaurants/{restaurant_id}/suppliers")
def list_suppliers(restaurant_id: str):
    """List discovered suppliers for a restaurant."""
    rows = (
        supabase.table("suppliers")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .order("name")
        .execute()
    )
    return {"data": rows.data}


@router.post("/restaurants/{restaurant_id}/suppliers/refresh")
def refresh_suppliers(restaurant_id: str):
    """Re-run supplier discovery for a restaurant."""
    result = find_suppliers(supabase, restaurant_id)
    return {"data": result}


# --- Emails ---


@router.get("/restaurants/{restaurant_id}/emails")
def list_emails(restaurant_id: str, status: str | None = None):
    """List emails for a restaurant, optionally filtered by status."""
    query = (
        supabase.table("emails")
        .select("*, suppliers(name, email, categories)")
        .eq("restaurant_id", restaurant_id)
    )
    if status:
        query = query.eq("status", status)
    rows = query.order("generated_at", desc=True).execute()
    return {"data": rows.data}


class EmailUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    status: str | None = None


@router.patch("/emails/{email_id}")
def update_email(email_id: str, body: EmailUpdate):
    """Edit email subject/body or change status."""
    updates = {}
    if body.subject is not None:
        updates["subject"] = body.subject
    if body.body is not None:
        updates["body"] = body.body
    if body.status is not None:
        if body.status not in ("generated", "draft", "discarded"):
            raise HTTPException(400, "status must be generated, draft, or discarded")
        updates["status"] = body.status

    if not updates:
        raise HTTPException(400, "No fields to update")

    if "subject" in updates or "body" in updates:
        from datetime import datetime, timezone

        updates["edited_at"] = datetime.now(timezone.utc).isoformat()

    result = supabase.table("emails").update(updates).eq("id", email_id).execute()
    if not result.data:
        raise HTTPException(404, "Email not found")
    return {"data": result.data[0]}


@router.post("/emails/{email_id}/send")
def send_email_endpoint(email_id: str):
    """Send an email via Resend."""
    result = send_email(supabase, email_id)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return {"data": result}


@router.post("/emails/{email_id}/revert")
def revert_email(email_id: str):
    """Revert email to original LLM-generated content."""
    email = (
        supabase.table("emails")
        .select("subject_original, body_original")
        .eq("id", email_id)
        .single()
        .execute()
    )
    if not email.data:
        raise HTTPException(404, "Email not found")

    result = (
        supabase.table("emails")
        .update(
            {
                "subject": email.data["subject_original"],
                "body": email.data["body_original"],
                "edited_at": None,
            }
        )
        .eq("id", email_id)
        .execute()
    )
    return {"data": result.data[0]}


@router.post("/restaurants/{restaurant_id}/emails/generate")
def generate_emails(restaurant_id: str):
    """Generate outreach emails for all suppliers with email addresses."""
    result = draft_all_emails(supabase, restaurant_id)
    return {"data": result}
