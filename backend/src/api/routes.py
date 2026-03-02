import json
import logging
import sys
import os
import threading
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from src.db.client import supabase, create_supabase_client
from src.core.pricing.market_selector import find_nearest_market
from src.core.menu.parser import parse_menu
from src.core.menu.matcher import add_ingredient
from src.core.pricing.trend_analyzer import (
    compute_trends,
    build_nass_series,
    build_mars_series,
)
from src.core.pricing.nass_client import fetch_and_store_nass
from src.core.pricing.mars_client import fetch_and_store_mars
from src.core.suppliers.finder import find_suppliers
from src.core.email.drafter import draft_all_emails
from src.config import get
from src.core.email.sender import send_email
from src.core.email.poller import poll_inbox, check_followups
from src.core.email.agent import run_procurement_agent
from src.core.email.notifications import notify

logger = logging.getLogger(__name__)

REFRESH_COOLDOWN = timedelta(hours=1)

router = APIRouter(prefix="/api")


def needs_parse(supabase_client, restaurant_id: str) -> bool:
    """Check whether menu parsing is needed for a restaurant.

    Returns True when:
    - No commodities exist (new restaurant / first upload)
    - Menu files were uploaded after the latest parse (re-upload)
    """
    commodities = (
        supabase_client.table("restaurant_commodities")
        .select("id")
        .eq("restaurant_id", restaurant_id)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
    )
    if not commodities.data:
        return True

    latest_upload = (
        supabase_client.table("menu_files")
        .select("uploaded_at")
        .eq("restaurant_id", restaurant_id)
        .order("uploaded_at", desc=True)
        .limit(1)
        .execute()
    )
    if not latest_upload.data:
        return False

    latest_parse = (
        supabase_client.table("menu_parses")
        .select("parsed_at")
        .eq("restaurant_id", restaurant_id)
        .order("parsed_at", desc=True)
        .limit(1)
        .execute()
    )
    if not latest_parse.data:
        return True

    return latest_upload.data[0]["uploaded_at"] > latest_parse.data[0]["parsed_at"]


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
        for attempt in range(3):
            try:
                supabase.storage.from_("menus").upload(
                    storage_path, content, {"content-type": f.content_type}
                )
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(1)

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


def sse_event(step: str, status: str, result: dict | None = None) -> str:
    """Format a server-sent event."""
    payload = {"step": step, "status": status}
    if result is not None:
        payload["result"] = result
    return f"data: {json.dumps(payload)}\n\n"


def parse_stream(restaurant_id: str):
    """Stream 1: Parse menu only. Runs during upload, before confirmation."""
    yield sse_event("menu_parse", "running")
    try:
        parse_result = None
        if needs_parse(supabase, restaurant_id):
            parse_result = parse_menu(supabase, restaurant_id)
        yield sse_event(
            "menu_parse",
            "done",
            {
                "tracked": parse_result["tracked"] if parse_result else 0,
                "other": parse_result["other"] if parse_result else 0,
                "skipped": parse_result is None,
            },
        )
    except Exception as exc:
        logger.exception("menu_parse failed for %s", restaurant_id)
        yield sse_event("menu_parse", "error", {"message": str(exc)})

    yield sse_event("complete", "done")


def post_confirm_stream(restaurant_id: str):
    """Stream 2: Trends → suppliers → emails. Runs after confirmation."""
    yield sse_event("trends", "running")
    try:
        trend_result = compute_trends(supabase, restaurant_id)
        yield sse_event("trends", "done", {"computed": trend_result.get("computed", 0)})
    except Exception as exc:
        logger.exception("trends failed for %s", restaurant_id)
        yield sse_event("trends", "error", {"message": str(exc)})

    yield sse_event("suppliers", "running")
    try:
        supplier_result = find_suppliers(supabase, restaurant_id)
        yield sse_event(
            "suppliers",
            "done",
            {"suppliers_found": supplier_result.get("suppliers_found", 0)},
        )
    except Exception as exc:
        logger.exception("suppliers failed for %s", restaurant_id)
        yield sse_event("suppliers", "error", {"message": str(exc)})

    yield sse_event("emails", "running")
    try:
        email_result = draft_all_emails(supabase, restaurant_id)
        yield sse_event("emails", "done", {"drafted": email_result.get("drafted", 0)})
    except Exception as exc:
        logger.exception("emails failed for %s", restaurant_id)
        yield sse_event("emails", "error", {"message": str(exc)})

    yield sse_event("complete", "done")


@router.get("/analyze/{restaurant_id}/stream")
def analyze_stream(restaurant_id: str):
    """SSE stream 1: parse menu only."""
    return StreamingResponse(
        parse_stream(restaurant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/analyze/{restaurant_id}/pipeline")
def pipeline_endpoint(restaurant_id: str):
    """SSE stream 2: trends → suppliers → emails (post-confirmation)."""
    return StreamingResponse(
        post_confirm_stream(restaurant_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --- Menu Files ---


@router.get("/restaurants/{restaurant_id}/menu-files")
def list_menu_files(restaurant_id: str):
    """List uploaded menu files with signed URLs for display."""
    rows = (
        supabase.table("menu_files")
        .select("id, file_name, file_type, storage_path, uploaded_at")
        .eq("restaurant_id", restaurant_id)
        .order("uploaded_at", desc=True)
        .execute()
    )
    for row in rows.data:
        signed = supabase.storage.from_("menus").create_signed_url(
            row["storage_path"], 3600
        )
        row["url"] = signed.get("signedURL", "")
    return {"data": rows.data}


# --- Restaurant ---


@router.get("/restaurants/{restaurant_id}")
def get_restaurant(restaurant_id: str):
    """Get restaurant details including confirmation status."""
    result = (
        supabase.table("restaurants")
        .select("id, name, address, confirmed_at")
        .eq("id", restaurant_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Restaurant not found")
    return {"data": result.data}


@router.patch("/restaurants/{restaurant_id}")
def confirm_restaurant(restaurant_id: str):
    """Set confirmed_at timestamp to mark ingredient review as complete."""
    from datetime import datetime, timezone

    result = (
        supabase.table("restaurants")
        .update({"confirmed_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", restaurant_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Restaurant not found")
    return {"data": result.data[0]}


# --- Restaurant Commodities ---


@router.get("/restaurants/{restaurant_id}/commodities")
def list_commodities(restaurant_id: str):
    """List tracked + other commodities for a restaurant, joined with commodity details."""
    rows = (
        supabase.table("restaurant_commodities")
        .select("*, commodities(parent, display_name, source, cadence, has_price_data)")
        .eq("restaurant_id", restaurant_id)
        .is_("deleted_at", "null")
        .order("status")
        .order("raw_ingredient_name")
        .execute()
    )
    return {"data": rows.data}


@router.get("/commodities/registry")
def commodity_registry():
    """List unique parent commodities with price data availability.

    Used by the add-ingredient combobox to show what's trackable.
    """
    rows = (
        supabase.table("commodities")
        .select("parent, has_price_data")
        .eq("active", True)
        .order("parent")
        .execute()
    )
    # Deduplicate parents — a parent is trackable if ANY of its entries has data
    registry = {}
    for row in rows.data:
        parent = row["parent"]
        if parent not in registry:
            registry[parent] = row["has_price_data"]
        elif row["has_price_data"]:
            registry[parent] = True

    return {
        "data": [
            {"parent": k, "has_price_data": v} for k, v in sorted(registry.items())
        ]
    }


class CommodityUpdate(BaseModel):
    automation_pref: str | None = None


@router.patch("/restaurant-commodities/{item_id}")
def update_commodity(item_id: str, body: CommodityUpdate):
    """Update a restaurant commodity (set automation preference)."""
    updates = {}
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


@router.post("/restaurant-commodities/{item_id}/demote")
def demote_commodity(item_id: str):
    """Move a commodity from tracked to other (✕ on tracked pill)."""
    result = (
        supabase.table("restaurant_commodities")
        .update({"status": "other"})
        .eq("id", item_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Item not found")
    return {"data": result.data[0]}


@router.delete("/restaurant-commodities/{item_id}")
def remove_commodity(item_id: str):
    """Soft-delete a commodity from a restaurant's list (✕ on pill)."""
    result = (
        supabase.table("restaurant_commodities")
        .update(
            {
                "deleted_at": datetime.now(timezone.utc).isoformat(),
                "deleted_by": "user",
            }
        )
        .eq("id", item_id)
        .is_("deleted_at", "null")
        .execute()
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


# --- Trends ---


@router.get("/restaurants/{restaurant_id}/trends")
def get_trends(restaurant_id: str):
    """Get stored trends for a restaurant, sorted by signal strength."""
    rows = (
        supabase.table("trends")
        .select("*, trend_signals(*)")
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


@router.get("/restaurants/{restaurant_id}/calibrations")
def get_calibrations(restaurant_id: str):
    """Get calibration data for all tracked commodities (System View).

    Shows the system's reasoning: volatility, chosen horizon, normal range.
    """
    tracked = (
        supabase.table("restaurant_commodities")
        .select("commodity_id, commodities(id, parent)")
        .eq("restaurant_id", restaurant_id)
        .eq("status", "tracked")
        .is_("deleted_at", "null")
        .execute()
    )
    commodity_ids = [
        item["commodities"]["id"] for item in tracked.data if item.get("commodities")
    ]
    if not commodity_ids:
        return {"data": []}

    rows = (
        supabase.table("commodity_calibrations")
        .select("*")
        .in_("commodity_id", commodity_ids)
        .order("calibrated_at", desc=True)
        .execute()
    )
    return {"data": rows.data}


@router.get("/commodities/{commodity_id}/prices")
def get_price_series(
    commodity_id: str, source: str = "nass", market: str | None = None
):
    """Return the full price history for a commodity.

    Used by the frontend to render sparkline charts in trend cards.
    """
    row = (
        supabase.table("commodities")
        .select("parent")
        .eq("id", commodity_id)
        .single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Commodity not found")
    parent = row.data["parent"]

    if source == "mars" and market:
        prices, dates = build_mars_series(supabase, parent, market)
        return {
            "data": {
                "source": "mars",
                "parent": parent,
                "prices": prices,
                "dates": dates,
            }
        }

    prices, unit, dates = build_nass_series(supabase, parent)
    return {
        "data": {
            "source": "nass",
            "parent": parent,
            "unit": unit,
            "prices": prices,
            "dates": dates,
        }
    }


# --- Suppliers ---


@router.get("/restaurants/{restaurant_id}/suppliers")
def list_suppliers(restaurant_id: str):
    """List discovered suppliers for a restaurant."""
    rows = (
        supabase.table("restaurant_suppliers")
        .select("distance_miles, suppliers(*)")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    data = []
    for row in rows.data:
        supplier = row.get("suppliers", {})
        supplier["distance_miles"] = row.get("distance_miles")
        data.append(supplier)
    data.sort(key=lambda s: s.get("name", ""))
    return {"data": data}


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

    # Enrich with supplier distance
    distances = (
        supabase.table("restaurant_suppliers")
        .select("supplier_id, distance_miles")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    dist_map = {r["supplier_id"]: r["distance_miles"] for r in distances.data}
    for row in rows.data:
        if row.get("suppliers"):
            row["suppliers"]["distance_miles"] = dist_map.get(row["supplier_id"])

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
    """Send an email via Gmail API."""
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


@router.get("/restaurants/{restaurant_id}/threads")
def list_threads(restaurant_id: str):
    """List email threads for a restaurant with supplier info and messages."""
    threads = (
        supabase.table("email_threads")
        .select("*, suppliers(name, email, categories)")
        .eq("restaurant_id", restaurant_id)
        .order("updated_at", desc=True)
        .execute()
    )
    thread_ids = [t["id"] for t in threads.data]
    if not thread_ids:
        return {"data": []}

    messages = (
        supabase.table("email_messages")
        .select("*")
        .in_("thread_id", thread_ids)
        .order("created_at")
        .execute()
    )

    msgs_by_thread = {}
    for msg in messages.data:
        msgs_by_thread.setdefault(msg["thread_id"], []).append(msg)

    result = []
    for t in threads.data:
        t["messages"] = msgs_by_thread.get(t["id"], [])
        result.append(t)

    return {"data": result}


@router.post("/email/poll")
def poll_email_inbox():
    """Poll Gmail for inbound replies to tracked threads."""
    result = poll_inbox(supabase)
    if "error" in result:
        raise HTTPException(500, result["error"])
    return {"data": result}


@router.post("/email/webhook")
async def gmail_webhook(request: Request):
    """Receive Gmail push notifications via Google Pub/Sub.

    Pub/Sub sends a JSON envelope with a base64-encoded message.
    We decode it, verify it's a Gmail notification, then poll for new messages.
    """
    import base64 as b64

    body = await request.json()
    message = body.get("message", {})
    data = message.get("data", "")

    if data:
        decoded = json.loads(b64.b64decode(data).decode("utf-8"))
        logger.info(
            "Gmail webhook: emailAddress=%s historyId=%s",
            decoded.get("emailAddress"),
            decoded.get("historyId"),
        )

    result = poll_inbox(supabase)
    logger.info("Gmail webhook poll result: %s", result)

    # Notify + auto-run agent on threads that received new replies
    reopened = set(result.get("reopened_thread_ids", []))
    for thread_id in result.get("updated_thread_ids", []):
        try:
            t = (
                supabase.table("email_threads")
                .select("restaurant_id, suppliers(name)")
                .eq("id", thread_id)
                .single()
                .execute()
            )
            supplier_name = t.data.get("suppliers", {}).get("name", "supplier")
            if thread_id in reopened:
                notify(
                    supabase,
                    t.data["restaurant_id"],
                    thread_id,
                    "reopened",
                    f"Re-opened: {supplier_name} replied after close",
                )
            else:
                notify(
                    supabase,
                    t.data["restaurant_id"],
                    thread_id,
                    "inbound_reply",
                    f"New reply from {supplier_name}",
                )
        except Exception:
            pass
        run_agent_and_maybe_send(thread_id)

    # Check for stale threads needing follow-up
    followups = check_followups(supabase)
    for thread_id in followups.get("nudge", []):
        run_agent_and_maybe_send(thread_id)

    # Notify about auto-closed threads
    for thread_id in followups.get("close", []):
        try:
            t = (
                supabase.table("email_threads")
                .select("restaurant_id, suppliers(name)")
                .eq("id", thread_id)
                .single()
                .execute()
            )
            notify(
                supabase,
                t.data["restaurant_id"],
                thread_id,
                "closed",
                f"Auto-closed: {t.data.get('suppliers', {}).get('name', 'supplier')}",
                "No reply after follow-up attempts",
            )
        except Exception:
            pass

    return {"ok": True}


def run_agent_and_maybe_send(thread_id: str):
    """Run the procurement agent on a thread, store the result, and auto-send if in auto mode."""
    try:
        thread_row = (
            supabase.table("email_threads")
            .select(
                "restaurant_id, approval_mode, supplier_id, gmail_thread_id, suppliers(name)"
            )
            .eq("id", thread_id)
            .single()
            .execute()
        )
        restaurant_id = thread_row.data["restaurant_id"]
        supplier_name = thread_row.data.get("suppliers", {}).get("name", "Supplier")

        agent_result = run_procurement_agent(supabase, thread_id)
        logger.info(
            "Auto-agent on %s: %s",
            thread_id,
            agent_result.get("action", agent_result.get("error")),
        )

        if agent_result.get("action") == "draft":
            msg_row = (
                supabase.table("email_messages")
                .insert(
                    {
                        "thread_id": thread_id,
                        "direction": "outbound",
                        "sender": get("FROM_EMAIL") or "anamnikhilesh@gmail.com",
                        "recipient": "",
                        "subject": agent_result["subject"],
                        "body": "",
                        "draft_body": agent_result["body"],
                        "agent_reasoning": agent_result["reasoning"],
                    }
                )
                .execute()
            )

            if thread_row.data.get("approval_mode") == "auto":
                auto_send_draft(
                    supabase,
                    thread_id,
                    msg_row.data[0]["id"],
                    agent_result,
                    thread_row.data,
                )
                notify(
                    supabase,
                    restaurant_id,
                    thread_id,
                    "auto_sent",
                    f"Auto-sent reply to {supplier_name}",
                    agent_result.get("reasoning"),
                )
            else:
                notify(
                    supabase,
                    restaurant_id,
                    thread_id,
                    "draft_ready",
                    f"Draft ready for {supplier_name}",
                    agent_result.get("reasoning"),
                )

        elif agent_result.get("action") == "escalate":
            supabase.table("email_threads").update({"state": "escalated"}).eq(
                "id", thread_id
            ).execute()
            notify(
                supabase,
                restaurant_id,
                thread_id,
                "escalated",
                f"Escalated: {supplier_name}",
                agent_result.get("reason"),
            )

        elif agent_result.get("action") == "close":
            now = datetime.now(timezone.utc).isoformat()
            supabase.table("email_threads").update(
                {
                    "state": "closed",
                    "closed_reason": agent_result.get("reason", ""),
                    "closed_outcome": agent_result.get("outcome", ""),
                    "updated_at": now,
                }
            ).eq("id", thread_id).execute()
            notify(
                supabase,
                restaurant_id,
                thread_id,
                "closed",
                f"Closed: {supplier_name}",
                agent_result.get("reason"),
            )

    except Exception as exc:
        logger.warning("Auto-agent failed for %s: %s", thread_id, exc)


def auto_send_draft(supabase_client, thread_id, msg_id, agent_result, thread_data):
    """Send an agent draft automatically (auto mode). Same logic as approve endpoint."""
    import base64 as b64_mod
    from src.core.email.gmail_client import (
        get_gmail_service,
        get_last_message_id,
        build_reply_mime,
    )

    supplier = (
        supabase_client.table("suppliers")
        .select("email")
        .eq("id", thread_data["supplier_id"])
        .single()
        .execute()
    )
    to_email = get("TEST_EMAIL_OVERRIDE") or supplier.data["email"]

    service = get_gmail_service()
    if not service:
        logger.warning("Auto-send failed for %s: Gmail not configured", thread_id)
        return

    gmail_thread_id = thread_data.get("gmail_thread_id")

    # Fetch threading headers from the last message in the thread
    last_message_id = None
    if gmail_thread_id:
        last_message_id, _ = get_last_message_id(service, gmail_thread_id)

    msg = build_reply_mime(
        to_email, agent_result["subject"], agent_result["body"], last_message_id
    )

    raw = b64_mod.urlsafe_b64encode(msg.as_bytes()).decode()
    send_body = {"raw": raw}
    if gmail_thread_id:
        send_body["threadId"] = gmail_thread_id

    gmail_result = (
        service.users().messages().send(userId="me", body=send_body).execute()
    )

    now = datetime.now(timezone.utc).isoformat()
    supabase_client.table("email_messages").update(
        {
            "final_body": agent_result["body"],
            "recipient": to_email,
            "gmail_message_id": gmail_result.get("id", ""),
            "auto_sent": True,
        }
    ).eq("id", msg_id).execute()

    supabase_client.table("email_threads").update(
        {"state": "waiting_reply", "updated_at": now}
    ).eq("id", thread_id).execute()

    logger.info("Auto-sent draft for thread %s to %s", thread_id, to_email)


@router.patch("/email/threads/{thread_id}/mode")
def update_thread_mode(thread_id: str, payload: dict):
    """Toggle approval mode for a thread (manual/auto)."""
    mode = payload.get("approval_mode")
    if mode not in ("manual", "auto"):
        raise HTTPException(400, "approval_mode must be 'manual' or 'auto'")
    supabase.table("email_threads").update({"approval_mode": mode}).eq(
        "id", thread_id
    ).execute()
    return {"data": {"approval_mode": mode}}


class CloseBody(BaseModel):
    reason: str
    outcome: str


@router.post("/email/threads/{thread_id}/close")
def close_thread(thread_id: str, payload: CloseBody):
    """Manually close a thread (owner action)."""
    valid_outcomes = {
        "quote_received",
        "meeting_booked",
        "samples_arranged",
        "declined",
        "no_response",
        "owner_closed",
    }
    if payload.outcome not in valid_outcomes:
        raise HTTPException(400, f"outcome must be one of {valid_outcomes}")

    now = datetime.now(timezone.utc).isoformat()
    result = (
        supabase.table("email_threads")
        .update(
            {
                "state": "closed",
                "closed_reason": payload.reason,
                "closed_outcome": payload.outcome,
                "updated_at": now,
            }
        )
        .eq("id", thread_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Thread not found")
    return {"data": result.data[0]}


@router.post("/email/watch")
def register_gmail_watch():
    """Register Gmail push notifications via Pub/Sub watch.

    Call this once to start, then every 7 days to renew.
    """
    from src.core.email.gmail_client import get_gmail_service

    service = get_gmail_service()
    if not service:
        raise HTTPException(500, "Gmail API not configured")

    result = (
        service.users()
        .watch(
            userId="me",
            body={
                "topicName": "projects/project-88283f31-441d-41b5-a0f/topics/gmail-notifications",
                "labelIds": ["INBOX"],
            },
        )
        .execute()
    )

    return {"data": result}


@router.post("/email/threads/{thread_id}/run-agent")
def run_agent_on_thread(thread_id: str):
    """Run the procurement agent on a thread to draft a response."""
    result = run_procurement_agent(supabase, thread_id)
    if "error" in result:
        raise HTTPException(400, result["error"])

    # Store the draft or escalation on the thread
    if result["action"] == "draft":
        supabase.table("email_messages").insert(
            {
                "thread_id": thread_id,
                "direction": "outbound",
                "sender": get("FROM_EMAIL") or "anamnikhilesh@gmail.com",
                "recipient": "",
                "subject": result["subject"],
                "body": "",
                "draft_body": result["body"],
                "agent_reasoning": result["reasoning"],
            }
        ).execute()
        supabase.table("email_threads").update({"state": "draft_ready"}).eq(
            "id", thread_id
        ).execute()

    elif result["action"] == "escalate":
        supabase.table("email_threads").update({"state": "escalated"}).eq(
            "id", thread_id
        ).execute()

    elif result["action"] == "close":
        now = datetime.now(timezone.utc).isoformat()
        supabase.table("email_threads").update(
            {
                "state": "closed",
                "closed_reason": result.get("reason", ""),
                "closed_outcome": result.get("outcome", ""),
                "updated_at": now,
            }
        ).eq("id", thread_id).execute()

    return {"data": result}


class ApproveBody(BaseModel):
    body: str | None = None
    subject: str | None = None


@router.post("/email/threads/{thread_id}/approve")
def approve_thread_draft(thread_id: str, payload: ApproveBody = ApproveBody()):
    """Approve (and optionally edit) the agent's draft, then send via Gmail."""
    # Get the latest draft message
    draft = (
        supabase.table("email_messages")
        .select("id, draft_body, subject, thread_id")
        .eq("thread_id", thread_id)
        .eq("direction", "outbound")
        .not_.is_("draft_body", "null")
        .is_("final_body", "null")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not draft.data:
        raise HTTPException(404, "No pending draft for this thread")

    draft_row = draft.data[0]
    final_body = payload.body or draft_row["draft_body"]
    final_subject = payload.subject or draft_row["subject"]
    owner_edited = payload.body is not None or payload.subject is not None

    # Get thread to find supplier email
    thread = (
        supabase.table("email_threads")
        .select("supplier_id, gmail_thread_id")
        .eq("id", thread_id)
        .single()
        .execute()
    )
    supplier = (
        supabase.table("suppliers")
        .select("email")
        .eq("id", thread.data["supplier_id"])
        .single()
        .execute()
    )
    to_email = get("TEST_EMAIL_OVERRIDE") or supplier.data["email"]

    # Send via Gmail
    from src.core.email.gmail_client import (
        get_gmail_service,
        get_last_message_id,
        build_reply_mime,
    )
    import base64

    service = get_gmail_service()
    if not service:
        raise HTTPException(500, "Gmail API not configured")

    gmail_thread_id = thread.data.get("gmail_thread_id")

    # Fetch threading headers from the last message in the thread
    last_message_id = None
    if gmail_thread_id:
        last_message_id, _ = get_last_message_id(service, gmail_thread_id)

    msg = build_reply_mime(to_email, final_subject, final_body, last_message_id)

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    send_body = {"raw": raw}
    if gmail_thread_id:
        send_body["threadId"] = gmail_thread_id

    gmail_result = (
        service.users().messages().send(userId="me", body=send_body).execute()
    )

    # Update the draft message with final sent data
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("email_messages").update(
        {
            "final_body": final_body,
            "subject": final_subject,
            "recipient": to_email,
            "gmail_message_id": gmail_result.get("id", ""),
            "owner_edited": owner_edited,
        }
    ).eq("id", draft_row["id"]).execute()

    # Update thread state back to waiting for reply
    supabase.table("email_threads").update(
        {"state": "waiting_reply", "updated_at": now}
    ).eq("id", thread_id).execute()

    return {
        "data": {
            "sent": True,
            "gmail_message_id": gmail_result.get("id", ""),
            "routed_to": to_email,
        }
    }


# --- Notifications ---


@router.get("/restaurants/{restaurant_id}/notifications")
def list_notifications(restaurant_id: str, unread_only: bool = False):
    """List notifications for a restaurant, newest first."""
    query = (
        supabase.table("notifications")
        .select("*")
        .eq("restaurant_id", restaurant_id)
        .order("created_at", desc=True)
        .limit(50)
    )
    if unread_only:
        query = query.eq("read", False)
    rows = query.execute()
    return {"data": rows.data}


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    """Mark a single notification as read."""
    result = (
        supabase.table("notifications")
        .update({"read": True})
        .eq("id", notification_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Notification not found")
    return {"data": result.data[0]}


@router.post("/restaurants/{restaurant_id}/notifications/read-all")
def mark_all_read(restaurant_id: str):
    """Mark all notifications as read for a restaurant."""
    supabase.table("notifications").update({"read": True}).eq(
        "restaurant_id", restaurant_id
    ).eq("read", False).execute()
    return {"ok": True}


# --- Restaurant Management ---


# --- Price Refresh ---

refresh_lock = threading.Lock()
refresh_running = False


def refresh_prices(restaurant_id: str):
    """Background job: fetch latest prices for tracked commodities only, then recompute trends.

    Uses its own Supabase client to avoid sharing the connection pool with
    request-handling threads (which causes SSL corruption).
    """
    global refresh_running
    try:
        logger.info("refresh started for %s", restaurant_id)
        db = create_supabase_client()

        # Get the parents this restaurant tracks
        tracked = (
            db.table("restaurant_commodities")
            .select("commodities(parent)")
            .eq("restaurant_id", restaurant_id)
            .eq("status", "tracked")
            .is_("deleted_at", "null")
            .execute()
        )
        parents = {
            r["commodities"]["parent"] for r in tracked.data if r.get("commodities")
        }

        if not parents:
            logger.info("no tracked commodities for %s", restaurant_id)
            return

        # Fetch only the commodity records matching tracked parents
        registry = (
            db.table("commodities")
            .select("source, source_params")
            .in_("parent", list(parents))
            .execute()
        )

        seen_slugs = set()
        for row in registry.data:
            params = row["source_params"]
            if row["source"] == "NASS":
                fetch_and_store_nass(db, params["commodity_desc"], "US", 12)
            elif row["source"] == "MARS":
                slug_id = params["slug_id"]
                if slug_id not in seen_slugs:
                    seen_slugs.add(slug_id)
                    is_daily = "Terminal" in params.get("market_types", [])
                    fetch_and_store_mars(
                        db, slug_id, last_reports=30 if is_daily else 12
                    )

        compute_trends(db, restaurant_id)
        logger.info("refresh completed for %s", restaurant_id)
    except Exception:
        logger.exception("refresh failed for %s", restaurant_id)
    finally:
        with refresh_lock:
            refresh_running = False


@router.post("/restaurants/{restaurant_id}/refresh")
def refresh_endpoint(restaurant_id: str):
    """Trigger a background price data refresh.

    Throttled to once per hour based on last_refreshed on any commodity.
    Only one refresh runs at a time — concurrent requests get skipped.
    Returns immediately — the fetch runs in a background thread.
    """
    global refresh_running

    with refresh_lock:
        if refresh_running:
            return {"status": "skipped", "reason": "refresh already in progress"}

    latest = (
        supabase.table("commodities")
        .select("last_refreshed")
        .not_.is_("last_refreshed", "null")
        .order("last_refreshed", desc=True)
        .limit(1)
        .execute()
    )

    if latest.data:
        last = datetime.fromisoformat(latest.data[0]["last_refreshed"])
        if datetime.now(timezone.utc) - last < REFRESH_COOLDOWN:
            return {"status": "skipped", "reason": "refreshed recently"}

    with refresh_lock:
        if refresh_running:
            return {"status": "skipped", "reason": "refresh already in progress"}
        refresh_running = True

    # Stamp immediately so the 1-hour throttle kicks in
    now = datetime.now(timezone.utc).isoformat()
    supabase.table("commodities").update({"last_refreshed": now}).eq(
        "active", True
    ).execute()

    thread = threading.Thread(target=refresh_prices, args=(restaurant_id,), daemon=True)
    thread.start()
    return {"status": "refreshing"}


@router.delete("/restaurants/{restaurant_id}")
def delete_restaurant(restaurant_id: str):
    """Delete a restaurant and all related data.

    All child tables cascade on delete, so only the restaurant row
    and storage blobs need explicit handling.
    """
    restaurant = (
        supabase.table("restaurants")
        .select("id, name")
        .eq("id", restaurant_id)
        .execute()
    )
    if not restaurant.data:
        raise HTTPException(404, "Restaurant not found")

    # Clean up storage blobs (not covered by DB cascades)
    menu_files = (
        supabase.table("menu_files")
        .select("storage_path")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    storage_paths = [f["storage_path"] for f in menu_files.data]
    if storage_paths:
        supabase.storage.from_("menus").remove(storage_paths)

    # Cascade handles all child tables
    supabase.table("restaurants").delete().eq("id", restaurant_id).execute()

    return {"deleted": True, "name": restaurant.data[0]["name"]}
