import sys
import os
import base64

import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

EXTRACT_TOOL = {
    "name": "extract_ingredients",
    "description": "Extract ingredient categories identified from the restaurant menu",
    "input_schema": {
        "type": "object",
        "properties": {
            "tracked": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Parent category names from the provided list that this restaurant's kitchen would need to purchase based on the menu",
            },
            "other": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ingredients visible on the menu that don't match any provided category. Use lowercase, singular form.",
            },
        },
        "required": ["tracked", "other"],
    },
}

SYSTEM_PROMPT = """You are analyzing a restaurant menu to identify what commodity ingredients the kitchen needs to purchase.

You will be shown one or more menu pages (images or PDF). You will also receive a list of known commodity parent categories that have real price tracking data.

Your job:
1. Read the menu carefully.
2. Identify which parent categories from the provided list the restaurant would need to buy.
3. Note any other key ingredients you see that don't match any provided category.

Rules:
- Only select categories you're confident the menu requires
- Think about what raw ingredients go INTO the dishes, not just what's listed
- For "other": only include significant purchasing ingredients, not garnishes or minor seasonings
- Use the EXACT category names from the provided list for "tracked"
- Return results using the extract_ingredients tool"""


def build_vision_content(files: list[dict], prompt: str) -> list[dict]:
    content = []
    for f in files:
        encoded = base64.standard_b64encode(f["data"]).decode("utf-8")
        media_type = f["file_type"]

        if media_type == "application/pdf":
            content.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )
        else:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": encoded,
                    },
                }
            )

    content.append({"type": "text", "text": prompt})
    return content


def normalize_ingredient(name: str) -> str:
    return name.strip().lower()


def get_parent_categories(supabase_client) -> list[str]:
    """Get distinct parent categories from the commodities table."""
    result = supabase_client.table("commodities").select("parent").execute()
    parents = sorted(set(row["parent"] for row in result.data))
    return parents


def fetch_menu_files(supabase_client, restaurant_id: str) -> list[dict]:
    """Download menu files for a restaurant from Supabase Storage."""
    rows = (
        supabase_client.table("menu_files")
        .select("storage_path, file_type, file_name")
        .eq("restaurant_id", restaurant_id)
        .execute()
    )

    files = []
    for row in rows.data:
        data = supabase_client.storage.from_("menus").download(row["storage_path"])
        files.append(
            {
                "data": data,
                "file_type": row["file_type"],
                "file_name": row["file_name"],
            }
        )

    return files


def call_vision_llm(files: list[dict], parents: list[str]) -> dict:
    """Call Claude Vision with menu files and parent categories.

    Returns raw tool_use result: {"tracked": [...], "other": [...]}.
    """
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    parent_list = "\n".join(f"- {p}" for p in parents)
    prompt = f"""Here are the known commodity parent categories with price tracking data:

{parent_list}

Analyze the menu and identify which of these categories the restaurant needs to purchase, and any other significant ingredients not in the list."""

    content = build_vision_content(files, prompt)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=[EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": "extract_ingredients"},
        messages=[{"role": "user", "content": content}],
    )

    for block in response.content:
        if block.type == "tool_use":
            return block.input

    return {"tracked": [], "other": []}


def resolve_commodity_ids(supabase_client, parents: list[str]) -> dict:
    """Map parent category names to commodity IDs.

    Returns {parent_name: commodity_id} using the first commodity found per parent.
    """
    result = supabase_client.table("commodities").select("id, parent").execute()

    parent_to_id = {}
    for row in result.data:
        parent = row["parent"]
        if parent not in parent_to_id:
            parent_to_id[parent] = row["id"]

    return {p: parent_to_id[p] for p in parents if p in parent_to_id}


def store_parse_results(
    supabase_client,
    restaurant_id: str,
    tracked_parents: list[str],
    other_ingredients: list[str],
    raw_response: dict,
) -> dict:
    """Store parse results in restaurant_commodities + menu_parses.

    For re-uploads: upserts tracked items, skips existing "other" items.
    Returns {"tracked": count, "other": count}.
    """
    # Audit trail
    supabase_client.table("menu_parses").insert(
        {
            "restaurant_id": restaurant_id,
            "status": "completed",
            "raw_llm_response": raw_response,
        }
    ).execute()

    # Resolve parent names to commodity IDs
    commodity_map = resolve_commodity_ids(supabase_client, tracked_parents)

    # Upsert tracked items
    tracked_count = 0
    for parent in tracked_parents:
        commodity_id = commodity_map.get(parent)
        if not commodity_id:
            continue

        supabase_client.table("restaurant_commodities").upsert(
            {
                "restaurant_id": restaurant_id,
                "commodity_id": commodity_id,
                "raw_ingredient_name": parent,
                "status": "tracked",
                "added_by": "system",
            },
            on_conflict="restaurant_id,commodity_id",
        ).execute()
        tracked_count += 1

    # Insert "other" items (skip if already exists)
    other_count = 0
    for ingredient in other_ingredients:
        name = normalize_ingredient(ingredient)
        if not name:
            continue

        existing = (
            supabase_client.table("restaurant_commodities")
            .select("id")
            .eq("restaurant_id", restaurant_id)
            .eq("raw_ingredient_name", name)
            .eq("status", "other")
            .execute()
        )
        if existing.data:
            continue

        supabase_client.table("restaurant_commodities").insert(
            {
                "restaurant_id": restaurant_id,
                "commodity_id": None,
                "raw_ingredient_name": name,
                "status": "other",
                "added_by": "system",
            }
        ).execute()
        other_count += 1

    return {"tracked": tracked_count, "other": other_count}


def parse_menu(supabase_client, restaurant_id: str) -> dict:
    """Parse a restaurant's menu files and store commodity matches.

    Main orchestrator: fetches files, calls Vision LLM, stores results.
    Returns {"tracked": count, "other": count, "raw_response": dict}.
    """
    parents = get_parent_categories(supabase_client)
    if not parents:
        return {"tracked": 0, "other": 0, "raw_response": {"tracked": [], "other": []}}

    files = fetch_menu_files(supabase_client, restaurant_id)
    if not files:
        return {"tracked": 0, "other": 0, "raw_response": {"tracked": [], "other": []}}

    raw_response = call_vision_llm(files, parents)

    parent_set = set(parents)
    tracked_parents = []
    other_ingredients = list(raw_response.get("other", []))
    for p in raw_response.get("tracked", []):
        if p in parent_set:
            tracked_parents.append(p)
        else:
            other_ingredients.append(p)

    counts = store_parse_results(
        supabase_client, restaurant_id, tracked_parents, other_ingredients, raw_response
    )

    return {
        "tracked": counts["tracked"],
        "other": counts["other"],
        "raw_response": raw_response,
    }
