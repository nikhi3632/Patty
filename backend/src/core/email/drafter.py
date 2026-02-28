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
3. If price drops are provided, you MUST cite the exact percentages from the data — these are negotiation leverage. Never mention rising prices.
4. Name the commodities/categories they're looking to source
5. Ask about pricing, availability, and minimum order quantities
6. Keep it concise — 150-250 words max
7. Do NOT use placeholder brackets like [Your Name] — leave the sign-off as just the restaurant name
8. Do NOT use markdown formatting — plain text only"""


def build_trend_summary(trends: list[dict]) -> str:
    """Build a human-readable summary of downward price trends for the email.

    Only cites falling prices — used as negotiation leverage.
    Upward trends are omitted to avoid giving suppliers pricing power.

    Expects normalized trends with nested trend_signals list per trend.
    """
    if not trends:
        return "We're actively monitoring commodity prices and looking to optimize our supply chain."

    lines = []
    for t in trends:
        parent = t.get("parent", "")
        signal = t.get("signal", "stable")

        if signal == "stable":
            continue

        signals = t.get("trend_signals", [])

        # Pick the most significant data source (prefer MARS wholesale)
        pct = None
        label = "prices"
        z = None
        for s in signals:
            src = s.get("source")
            p = s.get("change_pct")
            if p is None:
                continue
            p = float(p)
            if src == "mars":
                pct = p
                label = "wholesale prices"
                z = s.get("z_score")
                break
            elif pct is None:
                pct = p
                label = "commodity prices"
                z = s.get("z_score")

        if pct is None or pct >= 0:
            continue

        emphasis = ""
        if z is not None and abs(float(z)) >= 2.0:
            emphasis = " (a significant move)"

        lines.append(f"{parent}: {label} down {abs(pct):.1f}%{emphasis}")

    if not lines:
        return "We're actively monitoring commodity prices and looking to optimize our supply chain."

    return "Recent price drops we're seeing:\n" + "\n".join(
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
        .select("parent, signal, trend_signals(source, change_pct, z_score)")
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
    links = (
        supabase_client.table("restaurant_suppliers")
        .select("suppliers(id, name, email)")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )
    suppliers_data = [row["suppliers"] for row in links.data]
    suppliers_data.sort(key=lambda s: s.get("name", ""))

    # Clear old generated emails (not sent ones)
    supabase_client.table("emails").delete().eq("restaurant_id", restaurant_id).in_(
        "status", ["generated", "draft"]
    ).execute()

    drafted = []
    skipped = []
    for s in suppliers_data:
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
