import sys
import os

import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

MATCH_TOOL = {
    "name": "match_ingredient",
    "description": "Match a user-provided ingredient to a commodity parent category",
    "input_schema": {
        "type": "object",
        "properties": {
            "matched_parent": {
                "type": ["string", "null"],
                "description": "The exact parent category name that matches, or null if no match",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "How confident the match is",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this match was chosen or why no match exists",
            },
        },
        "required": ["matched_parent", "confidence", "reasoning"],
    },
}

SYSTEM_PROMPT = """You are matching a user-provided ingredient name to a known commodity parent category.

You will receive:
1. A free-text ingredient name from the user (e.g. "baby spinach", "porterhouse steak", "mozzarella")
2. A list of known parent categories from the commodity registry

Your job: find the best matching parent category, or return null if there's no reasonable match.

Rules:
- Match based on what the ingredient IS, not just string similarity
- "baby spinach" → "spinach" (it's a type of spinach)
- "porterhouse" → "cattle" (it's a beef cut)
- "mozzarella" → "cheese" (it's a type of cheese)
- "sriracha" → null (no hot sauce category)
- Use the EXACT parent category name from the list
- Only match with high/medium confidence. If it's a stretch, return null."""


def match_ingredient(supabase_client, ingredient: str) -> dict:
    """Fuzzy match a user-provided ingredient against the commodity registry.

    Returns {"matched_parent": str|None, "commodity_id": str|None,
             "confidence": str, "reasoning": str}.
    """
    result = supabase_client.table("commodities").select("id, parent").execute()

    parent_to_id = {}
    for row in result.data:
        if row["parent"] not in parent_to_id:
            parent_to_id[row["parent"]] = row["id"]

    parents = sorted(parent_to_id.keys())
    if not parents:
        return {
            "matched_parent": None,
            "commodity_id": None,
            "confidence": "low",
            "reasoning": "No commodities in registry",
        }

    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    parent_list = "\n".join(f"- {p}" for p in parents)
    prompt = f"""Ingredient to match: "{ingredient}"

Known parent categories:
{parent_list}

Match this ingredient to the best parent category, or return null if no match."""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        tools=[MATCH_TOOL],
        tool_choice={"type": "tool", "name": "match_ingredient"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            matched = block.input.get("matched_parent")
            commodity_id = parent_to_id.get(matched) if matched else None
            return {
                "matched_parent": matched,
                "commodity_id": commodity_id,
                "confidence": block.input.get("confidence", "low"),
                "reasoning": block.input.get("reasoning", ""),
            }

    return {
        "matched_parent": None,
        "commodity_id": None,
        "confidence": "low",
        "reasoning": "LLM did not return a tool response",
    }


def add_ingredient(supabase_client, restaurant_id: str, ingredient: str) -> dict:
    """Add a user-provided ingredient to a restaurant's commodity list.

    Runs the matcher to try to find a registry match.
    Match → tracked. No match → other.
    Returns the created restaurant_commodities row + match info.
    """
    match = match_ingredient(supabase_client, ingredient)

    if match["commodity_id"]:
        # Check if already tracked
        existing = (
            supabase_client.table("restaurant_commodities")
            .select("id")
            .eq("restaurant_id", restaurant_id)
            .eq("commodity_id", match["commodity_id"])
            .execute()
        )
        if existing.data:
            return {
                "status": "already_tracked",
                "match": match,
            }

        row = (
            supabase_client.table("restaurant_commodities")
            .insert(
                {
                    "restaurant_id": restaurant_id,
                    "commodity_id": match["commodity_id"],
                    "raw_ingredient_name": match["matched_parent"],
                    "status": "tracked",
                    "added_by": "user",
                    "user_confirmed": True,
                }
            )
            .execute()
        )
    else:
        name = ingredient.strip().lower()
        existing = (
            supabase_client.table("restaurant_commodities")
            .select("id")
            .eq("restaurant_id", restaurant_id)
            .eq("raw_ingredient_name", name)
            .eq("status", "other")
            .execute()
        )
        if existing.data:
            return {
                "status": "already_other",
                "match": match,
            }

        row = (
            supabase_client.table("restaurant_commodities")
            .insert(
                {
                    "restaurant_id": restaurant_id,
                    "commodity_id": None,
                    "raw_ingredient_name": name,
                    "status": "other",
                    "added_by": "user",
                    "user_confirmed": True,
                }
            )
            .execute()
        )

    return {
        "status": "tracked" if match["commodity_id"] else "other",
        "match": match,
        "row": row.data[0],
    }
