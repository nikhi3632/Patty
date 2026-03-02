import sys
import os
import html
import base64
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import quote_plus

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get
from src.core.http import safe_request
from src.core.email.gmail_client import get_gmail_service


def build_map_url(address: str, lat: float = None, lng: float = None) -> str:
    """Build a Google Static Maps URL for the restaurant location."""
    api_key = get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return ""

    marker = f"{lat},{lng}" if lat and lng else quote_plus(address)
    return (
        f"https://maps.googleapis.com/maps/api/staticmap"
        f"?center={quote_plus(address)}"
        f"&zoom=14&size=560x200&scale=2&maptype=roadmap"
        f"&markers=color:red%7C{marker}"
        f"&key={api_key}"
    )


def build_maps_link(address: str) -> str:
    """Build a Google Maps directions link."""
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}"


def lookup_restaurant_website(name: str, address: str) -> str:
    """Look up a restaurant's website via Google Places API (Find Place → Details)."""
    api_key = get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return ""

    try:
        with safe_request():
            find_resp = httpx.get(
                "https://maps.googleapis.com/maps/api/place/findplacefromtext/json",
                params={
                    "input": f"{name} {address}",
                    "inputtype": "textquery",
                    "fields": "place_id",
                    "key": api_key,
                },
                timeout=10,
            )
        candidates = find_resp.json().get("candidates", [])
        if not candidates:
            return ""

        place_id = candidates[0]["place_id"]

        with safe_request():
            details_resp = httpx.get(
                "https://maps.googleapis.com/maps/api/place/details/json",
                params={
                    "place_id": place_id,
                    "fields": "website",
                    "key": api_key,
                },
                timeout=10,
            )
        return details_resp.json().get("result", {}).get("website", "")
    except Exception:
        return ""


def plain_to_html(
    body: str,
    restaurant_name: str,
    restaurant_address: str,
    supplier_website: str = "",
    supplier_name: str = "",
    restaurant_lat: float = None,
    restaurant_lng: float = None,
    restaurant_website: str = "",
) -> str:
    """Convert plain text email body into styled HTML with links and map."""
    escaped = html.escape(body)
    paragraphs = escaped.split("\n\n")
    body_html = "\n".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)

    # Google Maps static image + link
    map_url = build_map_url(restaurant_address, restaurant_lat, restaurant_lng)
    maps_link = build_maps_link(restaurant_address)
    map_section = ""
    if map_url:
        map_section = f"""
    <div class="map-section">
      <p class="map-label">Our Location</p>
      <a href="{maps_link}" target="_blank">
        <img src="{map_url}" alt="Restaurant location" class="map-img">
      </a>
      <a href="{maps_link}" target="_blank" class="map-link">
        View on Google Maps
      </a>
    </div>"""

    # Supplier website link
    supplier_link = ""
    if supplier_website:
        safe_url = html.escape(supplier_website)
        safe_name = html.escape(supplier_name or supplier_website)
        supplier_link = f"""
    <div class="supplier-link">
      We visited your website at
      <a href="{safe_url}" target="_blank">{safe_name}</a>
      and believe there is a strong fit.
    </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{
    margin: 0;
    padding: 0;
    background-color: #f4f4f5;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }}
  .wrapper {{
    max-width: 600px;
    margin: 0 auto;
    padding: 40px 20px;
  }}
  .card {{
    background: #ffffff;
    border-radius: 8px;
    padding: 40px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .card p {{
    color: #1a1a1a;
    font-size: 15px;
    line-height: 1.7;
    margin: 0 0 16px 0;
  }}
  .card p:last-child {{
    margin-bottom: 0;
  }}
  .supplier-link {{
    background: #f0fdf4;
    border-left: 3px solid #22c55e;
    padding: 12px 16px;
    margin: 20px 0;
    font-size: 14px;
    color: #1a1a1a;
    line-height: 1.6;
    border-radius: 0 6px 6px 0;
  }}
  .supplier-link a {{
    color: #16a34a;
    text-decoration: underline;
  }}
  .map-section {{
    margin-top: 24px;
    text-align: center;
  }}
  .map-label {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #71717a;
    margin: 0 0 8px 0;
  }}
  .map-img {{
    width: 100%;
    border-radius: 6px;
    display: block;
  }}
  .map-link {{
    display: inline-block;
    margin-top: 8px;
    font-size: 13px;
    color: #2563eb;
    text-decoration: none;
  }}
  .map-link:hover {{
    text-decoration: underline;
  }}
  .footer {{
    text-align: center;
    padding: 24px 0 0 0;
    color: #71717a;
    font-size: 12px;
    line-height: 1.5;
  }}
  .footer a {{
    color: #71717a;
    text-decoration: underline;
  }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="card">
    {body_html}
    {supplier_link}
    {map_section}
  </div>
  <div class="footer">
    {html.escape(restaurant_name)}<br>
    <a href="{maps_link}">{html.escape(restaurant_address)}</a>
    {f'<br><a href="{html.escape(restaurant_website)}">{html.escape(restaurant_website)}</a>' if restaurant_website else ""}
  </div>
</div>
</body>
</html>"""


def send_email(supabase_client, email_id: str) -> dict:
    """Send an email via Gmail API.

    Respects TEST_EMAIL_OVERRIDE: if set, all emails route to that address
    instead of the real supplier. The stored to_email remains unchanged.
    """
    email = (
        supabase_client.table("emails")
        .select("*")
        .eq("id", email_id)
        .single()
        .execute()
    )

    if not email.data:
        return {"error": "Email not found"}

    if email.data["status"] == "sent":
        return {"error": "Email already sent"}

    service = get_gmail_service()
    if not service:
        return {"error": "Gmail API not configured — missing credentials or token"}

    # Route to test email if override is set
    to_email = get("TEST_EMAIL_OVERRIDE") or email.data["to_email"]

    # Get restaurant info for HTML template
    restaurant = (
        supabase_client.table("restaurants")
        .select("name, address, lat, lng")
        .eq("id", email.data["restaurant_id"])
        .single()
        .execute()
    )
    r_data = restaurant.data or {}

    # Get supplier info for website link
    supplier = (
        supabase_client.table("suppliers")
        .select("name, website")
        .eq("id", email.data["supplier_id"])
        .single()
        .execute()
    )
    s_data = supplier.data or {}

    restaurant_website = lookup_restaurant_website(
        r_data.get("name", ""), r_data.get("address", "")
    )

    html_body = plain_to_html(
        body=email.data["body"],
        restaurant_name=r_data.get("name", ""),
        restaurant_address=r_data.get("address", ""),
        supplier_website=s_data.get("website", "") or "",
        supplier_name=s_data.get("name", ""),
        restaurant_lat=r_data.get("lat"),
        restaurant_lng=r_data.get("lng"),
        restaurant_website=restaurant_website,
    )

    msg = MIMEMultipart("alternative")
    msg["to"] = to_email
    msg["subject"] = email.data["subject"]
    msg.attach(MIMEText(email.data["body"], "plain"))
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()

    gmail_message_id = result.get("id", "")
    gmail_thread_id = result.get("threadId", "")

    now = datetime.now(timezone.utc).isoformat()
    supabase_client.table("emails").update(
        {
            "status": "sent",
            "gmail_message_id": gmail_message_id,
            "gmail_thread_id": gmail_thread_id,
            "sent_at": now,
        }
    ).eq("id", email_id).execute()

    # Create thread and first message for the procurement agent
    thread = (
        supabase_client.table("email_threads")
        .insert(
            {
                "restaurant_id": email.data["restaurant_id"],
                "supplier_id": email.data["supplier_id"],
                "gmail_thread_id": gmail_thread_id,
                "state": "waiting_reply",
                "approval_mode": "manual",
            }
        )
        .execute()
    )

    thread_id = thread.data[0]["id"]
    supabase_client.table("email_messages").insert(
        {
            "thread_id": thread_id,
            "direction": "outbound",
            "gmail_message_id": gmail_message_id,
            "sender": email.data["from_email"],
            "recipient": to_email,
            "subject": email.data["subject"],
            "body": email.data["body"],
            "final_body": email.data["body"],
        }
    ).execute()

    return {
        "sent": True,
        "gmail_message_id": gmail_message_id,
        "gmail_thread_id": gmail_thread_id,
        "thread_id": thread_id,
        "routed_to": to_email,
    }
