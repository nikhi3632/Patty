"""Procurement agent — Claude tool-use agent for supplier negotiations.

Given a thread_id, the agent:
1. Reads the conversation history
2. Uses tools to gather price data, restaurant/supplier context
3. Reasons about the best next move
4. Drafts a reply or escalates to the restaurant owner
"""

import sys
import os
import json
import logging

import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a procurement agent acting on behalf of a restaurant. Your job is to negotiate with food suppliers via email.

Your goal: Move each conversation toward a concrete outcome — a price quote, a meeting, or a sample delivery. You are NOT closing deals. You are getting the restaurant owner to the table with a warm lead.

Before drafting a reply, use your tools to gather context:
- Look up the conversation history to understand where things stand
- Check current price data for relevant commodities (this is your negotiation leverage)
- Review the restaurant's profile and what they track
- Check what competing suppliers have offered

When drafting:
- Be professional but warm
- If you have price data showing drops, reference it as leverage ("We've seen wholesale prices trending down...")
- Ask specific questions that move the conversation forward
- Keep replies concise — 100-200 words
- Match the tone of the supplier's messages
- If the supplier asked questions, answer them using the restaurant's context

CRITICAL GUARDRAILS — you must NEVER:
- Commit to purchase volumes or specific pricing
- Sign or agree to any terms
- Misrepresent the restaurant's size, needs, or current suppliers
- Respond to anything that looks like a legal document or contract
- Be aggressive or confrontational

If any of these situations arise, use the escalate tool instead of draft_reply. Explain clearly why you're escalating."""

TOOLS = [
    {
        "name": "get_thread_history",
        "description": "Get the full conversation history for this email thread — all messages in order, with sender, direction, and body.",
        "input_schema": {
            "type": "object",
            "properties": {
                "thread_id": {
                    "type": "string",
                    "description": "The thread ID to look up",
                },
            },
            "required": ["thread_id"],
        },
    },
    {
        "name": "get_price_data",
        "description": "Get current price trends for a commodity — includes MARS wholesale prices, NASS farm-gate prices, percentage changes, and z-scores indicating how unusual the movement is.",
        "input_schema": {
            "type": "object",
            "properties": {
                "commodity": {
                    "type": "string",
                    "description": "The commodity parent name (e.g. 'tomatoes', 'chicken', 'cattle')",
                },
                "restaurant_id": {
                    "type": "string",
                    "description": "The restaurant ID — used to find the nearest terminal market",
                },
            },
            "required": ["commodity", "restaurant_id"],
        },
    },
    {
        "name": "get_restaurant_profile",
        "description": "Get restaurant details — name, address, cuisine type, and all tracked commodities with their current trend signals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "restaurant_id": {
                    "type": "string",
                    "description": "The restaurant ID",
                },
            },
            "required": ["restaurant_id"],
        },
    },
    {
        "name": "get_supplier_profile",
        "description": "Get supplier details — name, categories they supply, contact info, distance from restaurant, and website.",
        "input_schema": {
            "type": "object",
            "properties": {
                "supplier_id": {
                    "type": "string",
                    "description": "The supplier ID",
                },
                "restaurant_id": {
                    "type": "string",
                    "description": "The restaurant ID — used to calculate distance",
                },
            },
            "required": ["supplier_id", "restaurant_id"],
        },
    },
    {
        "name": "draft_reply",
        "description": "Draft the reply email to send to the supplier. Use this when you have enough context and the response doesn't require escalation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body — plain text, professional tone",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Your reasoning for this response — what strategy you're using and why. This is shown to the restaurant owner.",
                },
            },
            "required": ["subject", "body", "reasoning"],
        },
    },
    {
        "name": "escalate",
        "description": "Escalate to the restaurant owner instead of replying. Use when: supplier mentions pricing commitments, contracts, legal terms, or anything outside your authority. Also use when the intent is unclear and you're not sure how to respond.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Clear explanation of why you're escalating — shown to the restaurant owner.",
                },
            },
            "required": ["reason"],
        },
    },
]


def run_procurement_agent(supabase_client, thread_id: str) -> dict:
    """Run the procurement agent for a thread.

    Returns one of:
    - {"action": "draft", "subject": ..., "body": ..., "reasoning": ...}
    - {"action": "escalate", "reason": ...}
    - {"error": ...}
    """
    # Load thread metadata
    thread = (
        supabase_client.table("email_threads")
        .select("id, restaurant_id, supplier_id, state, gmail_thread_id")
        .eq("id", thread_id)
        .single()
        .execute()
    )
    if not thread.data:
        return {"error": "Thread not found"}

    restaurant_id = thread.data["restaurant_id"]
    supplier_id = thread.data["supplier_id"]

    # Get the latest inbound message to present to the agent
    latest_inbound = (
        supabase_client.table("email_messages")
        .select("body, sender, subject")
        .eq("thread_id", thread_id)
        .eq("direction", "inbound")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not latest_inbound.data:
        return {"error": "No inbound message to respond to"}

    inbound = latest_inbound.data[0]

    user_message = f"""A supplier has replied in an ongoing procurement conversation.

Thread ID: {thread_id}
Restaurant ID: {restaurant_id}
Supplier ID: {supplier_id}

Latest reply from supplier ({inbound['sender']}):
Subject: {inbound.get('subject', '')}
Body:
{inbound['body']}

Use your tools to gather context, then draft a reply or escalate."""

    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))
    messages = [{"role": "user", "content": user_message}]

    # Tool-use loop
    for _ in range(10):  # max iterations to prevent runaway
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        # Check if we got a final answer (draft_reply or escalate)
        for block in response.content:
            if block.type == "tool_use":
                if block.name == "draft_reply":
                    return {
                        "action": "draft",
                        "subject": block.input.get("subject", ""),
                        "body": block.input.get("body", ""),
                        "reasoning": block.input.get("reasoning", ""),
                    }
                if block.name == "escalate":
                    return {
                        "action": "escalate",
                        "reason": block.input.get("reason", ""),
                    }

        # Process tool calls and continue the loop
        tool_results = []
        has_tool_calls = False

        for block in response.content:
            if block.type == "tool_use":
                has_tool_calls = True
                result = execute_tool(
                    supabase_client, block.name, block.input
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )

        if not has_tool_calls:
            # Model responded with text only — no tool call, no draft
            return {"error": "Agent did not produce a draft or escalation"}

        # Add assistant response and tool results to continue the conversation
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return {"error": "Agent exceeded maximum iterations"}


def execute_tool(supabase_client, tool_name: str, tool_input: dict) -> dict:
    """Execute a tool call and return the result."""
    if tool_name == "get_thread_history":
        return tool_get_thread_history(supabase_client, tool_input["thread_id"])
    elif tool_name == "get_price_data":
        return tool_get_price_data(
            supabase_client, tool_input["commodity"], tool_input["restaurant_id"]
        )
    elif tool_name == "get_restaurant_profile":
        return tool_get_restaurant_profile(
            supabase_client, tool_input["restaurant_id"]
        )
    elif tool_name == "get_supplier_profile":
        return tool_get_supplier_profile(
            supabase_client,
            tool_input["supplier_id"],
            tool_input["restaurant_id"],
        )
    return {"error": f"Unknown tool: {tool_name}"}


def tool_get_thread_history(supabase_client, thread_id: str) -> dict:
    """Return all messages in a thread, oldest first."""
    messages = (
        supabase_client.table("email_messages")
        .select("direction, sender, recipient, subject, body, created_at")
        .eq("thread_id", thread_id)
        .order("created_at")
        .execute()
    )
    return {"messages": messages.data}


def tool_get_price_data(supabase_client, commodity: str, restaurant_id: str) -> dict:
    """Return trend data for a commodity at this restaurant."""
    trends = (
        supabase_client.table("trends")
        .select("parent, signal, trend_signals(source, change_pct, z_score, market)")
        .eq("restaurant_id", restaurant_id)
        .ilike("parent", commodity)
        .execute()
    )

    if not trends.data:
        return {"commodity": commodity, "data": "No trend data available"}

    results = []
    for t in trends.data:
        signals = []
        for s in t.get("trend_signals", []):
            signals.append(
                {
                    "source": s.get("source"),
                    "change_pct": s.get("change_pct"),
                    "z_score": s.get("z_score"),
                    "market": s.get("market"),
                }
            )
        results.append(
            {
                "commodity": t["parent"],
                "signal": t["signal"],
                "details": signals,
            }
        )

    return {"commodity": commodity, "trends": results}


def tool_get_restaurant_profile(supabase_client, restaurant_id: str) -> dict:
    """Return restaurant info and tracked commodities."""
    restaurant = (
        supabase_client.table("restaurants")
        .select("name, address, cuisine_type")
        .eq("id", restaurant_id)
        .single()
        .execute()
    )

    tracked = (
        supabase_client.table("restaurant_commodities")
        .select("raw_ingredient_name, status, commodities(parent, display_name)")
        .eq("restaurant_id", restaurant_id)
        .eq("status", "tracked")
        .is_("deleted_at", "null")
        .execute()
    )

    ingredients = []
    for row in tracked.data:
        ingredients.append(
            {
                "menu_name": row["raw_ingredient_name"],
                "commodity": row.get("commodities", {}).get("parent", ""),
            }
        )

    return {
        "restaurant": restaurant.data,
        "tracked_ingredients": ingredients,
    }


def tool_get_supplier_profile(
    supabase_client, supplier_id: str, restaurant_id: str
) -> dict:
    """Return supplier info and distance from restaurant."""
    supplier = (
        supabase_client.table("suppliers")
        .select("name, email, contact_name, contact_title, phone, website, categories")
        .eq("id", supplier_id)
        .single()
        .execute()
    )

    link = (
        supabase_client.table("restaurant_suppliers")
        .select("distance_miles")
        .eq("restaurant_id", restaurant_id)
        .eq("supplier_id", supplier_id)
        .execute()
    )

    distance = None
    if link.data:
        distance = link.data[0].get("distance_miles")

    return {
        "supplier": supplier.data,
        "distance_miles": distance,
    }
