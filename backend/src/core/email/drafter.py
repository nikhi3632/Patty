import sys
import os

import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

DRAFT_TOOL = {
    "name": "draft_email",
    "description": "Draft a personalized supplier outreach email",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject": {
                "type": "string",
                "description": "Email subject line — concise, professional",
            },
            "body": {
                "type": "string",
                "description": "Email body — plain text, professional tone, cites specific data",
            },
        },
        "required": ["subject", "body"],
    },
}

SYSTEM_PROMPT = """You are drafting a professional outreach email from a restaurant to a food supplier.

The restaurant wants to negotiate better pricing or establish a new supplier relationship. The email should:

1. Be professional but warm — this is a business introduction, not a cold sales pitch
2. Mention the restaurant by name and what they serve
3. Reference specific price trends (cite numbers) to show the restaurant is data-informed
4. Name the commodities/categories they're looking to source
5. Ask about pricing, availability, and minimum order quantities
6. Keep it concise — 150-250 words max
7. Do NOT use placeholder brackets like [Your Name] — leave the sign-off as just the restaurant name
8. Do NOT use markdown formatting — plain text only"""


def build_trend_summary(trends: list[dict]) -> str:
    """Build a human-readable summary of price trends for the email."""
    if not trends:
        return "We're actively monitoring commodity prices and looking to optimize our supply chain."

    lines = []
    for t in trends:
        parent = t.get("parent", "")

        mars_pct = t.get("mars_change_pct")
        nass_pct = t.get("nass_change_pct")

        if mars_pct is not None:
            direction = "up" if float(mars_pct) > 0 else "down"
            lines.append(
                f"{parent}: wholesale prices {direction} {abs(float(mars_pct)):.1f}%"
            )
        elif nass_pct is not None:
            direction = "up" if float(nass_pct) > 0 else "down"
            lines.append(
                f"{parent}: commodity prices {direction} {abs(float(nass_pct)):.1f}%"
            )

    if not lines:
        return "We're actively monitoring commodity prices and looking to optimize our supply chain."

    return "Recent price trends we're tracking:\n" + "\n".join(
        f"- {line}" for line in lines[:5]
    )


def draft_email(
    supabase_client,
    restaurant_id: str,
    supplier_id: str,
) -> dict:
    """Generate a personalized outreach email for a supplier.

    Uses restaurant info, supplier details, and price trends to draft
    a data-informed negotiation email.
    """
    # Get restaurant info
    restaurant = (
        supabase_client.table("restaurants")
        .select("name, address")
        .eq("id", restaurant_id)
        .single()
        .execute()
    )

    # Get supplier info
    supplier = (
        supabase_client.table("suppliers")
        .select("name, email, contact_name, contact_title, categories")
        .eq("id", supplier_id)
        .single()
        .execute()
    )

    if not supplier.data.get("email"):
        return {"error": "Supplier has no email address"}

    # Get trends for this restaurant
    trends = (
        supabase_client.table("trends")
        .select("parent, signal, mars_change_pct, nass_change_pct")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )

    trend_summary = build_trend_summary(trends.data)

    # Build the prompt
    supplier_cats = ", ".join(supplier.data.get("categories", []))
    contact_line = ""
    if supplier.data.get("contact_name"):
        contact_line = f"Contact person: {supplier.data['contact_name']}"
        if supplier.data.get("contact_title"):
            contact_line += f" ({supplier.data['contact_title']})"

    prompt = f"""Draft an outreach email from this restaurant to this supplier.

Restaurant: {restaurant.data["name"]}
Location: {restaurant.data["address"]}

Supplier: {supplier.data["name"]}
{contact_line}
Categories they supply: {supplier_cats}

{trend_summary}

Write a professional email introducing the restaurant and inquiring about pricing for the categories this supplier covers."""

    from_email = get("FROM_EMAIL") or "onboarding@resend.dev"

    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[DRAFT_TOOL],
        tool_choice={"type": "tool", "name": "draft_email"},
        messages=[{"role": "user", "content": prompt}],
    )

    subject = ""
    body = ""
    for block in response.content:
        if block.type == "tool_use":
            subject = block.input.get("subject", "")
            body = block.input.get("body", "")
            break

    if not subject or not body:
        return {"error": "LLM did not generate email content"}

    # Store in emails table
    row = (
        supabase_client.table("emails")
        .insert(
            {
                "restaurant_id": restaurant_id,
                "supplier_id": supplier_id,
                "to_email": supplier.data["email"],
                "to_name": supplier.data.get("contact_name"),
                "from_email": from_email,
                "subject": subject,
                "subject_original": subject,
                "body": body,
                "body_original": body,
                "status": "generated",
            }
        )
        .execute()
    )

    return {"email": row.data[0]}


def draft_all_emails(supabase_client, restaurant_id: str) -> dict:
    """Draft outreach emails for all suppliers with email addresses."""
    suppliers = (
        supabase_client.table("suppliers")
        .select("id, name, email")
        .eq("restaurant_id", restaurant_id)
        .order("name")
        .execute()
    )

    # Clear old generated emails (not sent ones)
    supabase_client.table("emails").delete().eq("restaurant_id", restaurant_id).in_(
        "status", ["generated", "draft"]
    ).execute()

    drafted = []
    skipped = []
    for s in suppliers.data:
        if not s.get("email"):
            skipped.append(s["name"])
            continue

        result = draft_email(supabase_client, restaurant_id, s["id"])
        if "error" in result:
            skipped.append(f"{s['name']}: {result['error']}")
        else:
            drafted.append(result["email"])

    return {
        "restaurant_id": restaurant_id,
        "drafted": len(drafted),
        "skipped": len(skipped),
        "skipped_names": skipped,
        "emails": drafted,
    }
