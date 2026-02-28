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


def get_parent_categories(supabase_client) -> list[dict]:
    """Get distinct parent categories with aliases from the commodities table.

    Returns list of {"parent": str, "aliases": list[str]} dicts, sorted by parent.
    """
    result = supabase_client.table("commodities").select("parent, aliases").execute()
    seen = {}
    for row in result.data:
        parent = row["parent"]
        if parent not in seen:
            seen[parent] = row.get("aliases") or []
    return sorted(
        [{"parent": p, "aliases": a} for p, a in seen.items()],
        key=lambda x: x["parent"],
    )


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


def get_past_corrections(supabase_client) -> list[dict]:
    """Fetch user corrections from past reviews across all restaurants.

    Returns list of {"name": str, "action": str} where action is one of:
    - "removed_from_tracked" — user demoted/deleted a system-tracked item
    - "added_to_tracked" — user added an ingredient the system missed
    - "removed_from_other" — user deleted a hallucinated ingredient
    """
    # User-added ingredients (system missed these)
    added = (
        supabase_client.table("restaurant_commodities")
        .select("raw_ingredient_name, status")
        .eq("added_by", "user")
        .execute()
    )

    corrections = []
    for row in added.data:
        if row["status"] == "tracked":
            corrections.append(
                {"name": row["raw_ingredient_name"], "action": "added_to_tracked"}
            )

    return corrections


def build_corrections_prompt(corrections: list[dict]) -> str:
    """Build a prompt section from past user corrections."""
    if not corrections:
        return ""

    lines = []
    added = [c["name"] for c in corrections if c["action"] == "added_to_tracked"]

    if added:
        lines.append(
            "Ingredients the system previously missed that users had to add manually: "
            + ", ".join(added)
            + ". Make sure to check for these."
        )

    if not lines:
        return ""

    return "\n\nLearnings from past reviews:\n" + "\n".join(lines)


def format_parent_list(parent_entries: list[dict]) -> str:
    """Format parent categories with aliases for the LLM prompt.

    Input: [{"parent": "cattle", "aliases": ["beef", "steak", "veal"]}, ...]
    Output: "- cattle (beef, steak, veal)\n- chicken\n..."
    """
    lines = []
    for entry in parent_entries:
        parent = entry["parent"]
        aliases = entry.get("aliases") or []
        if aliases:
            lines.append(f"- {parent} ({', '.join(aliases)})")
        else:
            lines.append(f"- {parent}")
    return "\n".join(lines)


def call_vision_llm(
    files: list[dict], parent_entries: list[dict], corrections: str = ""
) -> dict:
    """Call Claude Vision with menu files and parent categories.

    Returns raw tool_use result: {"tracked": [...], "other": [...]}.
    """
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    parent_list = format_parent_list(parent_entries)
    prompt = f"""Here are the known commodity parent categories with price tracking data.
Terms in parentheses are common aliases — use the PARENT NAME (before the parentheses) in your output:

{parent_list}

Analyze the menu and identify which of these categories the restaurant needs to purchase, and any other significant ingredients not in the list.{corrections}"""

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


def resolve_commodity_ids(supabase_client, names: list[str]) -> dict:
    """Map ingredient names to commodity IDs and price availability.

    Checks both parent names and aliases. For example, "beef" matches
    the "cattle" commodity via its aliases.

    Returns {input_name: {"id": commodity_id, "has_price_data": bool}}
    using the first commodity found per parent.
    """
    result = (
        supabase_client.table("commodities")
        .select("id, parent, has_price_data, aliases")
        .execute()
    )

    # Build lookup: parent name → info (first per parent)
    parent_to_info = {}
    for row in result.data:
        parent = row["parent"]
        if parent not in parent_to_info:
            parent_to_info[parent] = {
                "id": row["id"],
                "has_price_data": row["has_price_data"],
            }

    # Build reverse alias lookup: alias → parent name
    alias_to_parent = {}
    for row in result.data:
        parent = row["parent"]
        for alias in row.get("aliases") or []:
            alias_lower = alias.lower()
            if alias_lower not in alias_to_parent:
                alias_to_parent[alias_lower] = parent

    resolved = {}
    for name in names:
        name_lower = name.lower()
        # Direct parent match
        if name_lower in parent_to_info:
            resolved[name] = parent_to_info[name_lower]
        # Alias match
        elif name_lower in alias_to_parent:
            parent = alias_to_parent[name_lower]
            resolved[name] = parent_to_info[parent]

    return resolved


def store_parse_results(
    supabase_client,
    restaurant_id: str,
    tracked_parents: list[str],
    other_ingredients: list[str],
    raw_response: dict,
) -> dict:
    """Store parse results in restaurant_commodities + menu_parses.

    Classification uses has_price_data on the commodity:
    - LLM matched + has_price_data=true  → status "tracked"
    - LLM matched + has_price_data=false → status "other" (commodity_id set)
    - LLM unmatched                      → status "other" (commodity_id null)

    For re-uploads: upserts matched items, skips existing "other" items.
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

    # Resolve parent names to commodity IDs + price availability
    commodity_map = resolve_commodity_ids(supabase_client, tracked_parents)

    # Upsert matched items — status based on has_price_data
    tracked_count = 0
    other_matched_count = 0
    for parent in tracked_parents:
        info = commodity_map.get(parent)
        if not info:
            continue

        status = "tracked" if info["has_price_data"] else "other"
        supabase_client.table("restaurant_commodities").upsert(
            {
                "restaurant_id": restaurant_id,
                "commodity_id": info["id"],
                "raw_ingredient_name": parent,
                "status": status,
                "added_by": "system",
            },
            on_conflict="restaurant_id,commodity_id",
        ).execute()
        if status == "tracked":
            tracked_count += 1
        else:
            other_matched_count += 1

    # Resolve "other" items against the registry too (catches LLM misclassifications)
    other_names = []
    for ingredient in other_ingredients:
        name = normalize_ingredient(ingredient)
        if name:
            other_names.append(name)

    other_resolved = (
        resolve_commodity_ids(supabase_client, other_names) if other_names else {}
    )

    # "Other" items that matched the registry — upsert with commodity_id
    for name in other_names:
        info = other_resolved.get(name)
        if not info:
            continue
        status = "tracked" if info["has_price_data"] else "other"
        supabase_client.table("restaurant_commodities").upsert(
            {
                "restaurant_id": restaurant_id,
                "commodity_id": info["id"],
                "raw_ingredient_name": name,
                "status": status,
                "added_by": "system",
            },
            on_conflict="restaurant_id,commodity_id",
        ).execute()
        if status == "tracked":
            tracked_count += 1
        else:
            other_matched_count += 1

    # Truly unmatched "other" items — insert with no commodity_id
    unmatched_names = [n for n in other_names if n not in other_resolved]
    other_unmatched_count = 0
    if unmatched_names:
        existing = (
            supabase_client.table("restaurant_commodities")
            .select("raw_ingredient_name")
            .eq("restaurant_id", restaurant_id)
            .eq("status", "other")
            .in_("raw_ingredient_name", unmatched_names)
            .execute()
        )
        existing_names = {row["raw_ingredient_name"] for row in existing.data}
        new_rows = [
            {
                "restaurant_id": restaurant_id,
                "commodity_id": None,
                "raw_ingredient_name": name,
                "status": "other",
                "added_by": "system",
            }
            for name in unmatched_names
            if name not in existing_names
        ]
        if new_rows:
            result = (
                supabase_client.table("restaurant_commodities")
                .insert(new_rows)
                .execute()
            )
            other_unmatched_count = len(result.data)

    return {
        "tracked": tracked_count,
        "other": other_matched_count + other_unmatched_count,
    }


def parse_menu(supabase_client, restaurant_id: str) -> dict:
    """Parse a restaurant's menu files and store commodity matches.

    Main orchestrator: fetches files, calls Vision LLM, stores results.
    Returns {"tracked": count, "other": count, "raw_response": dict}.
    """
    parent_entries = get_parent_categories(supabase_client)
    if not parent_entries:
        return {"tracked": 0, "other": 0, "raw_response": {"tracked": [], "other": []}}

    files = fetch_menu_files(supabase_client, restaurant_id)
    if not files:
        return {"tracked": 0, "other": 0, "raw_response": {"tracked": [], "other": []}}

    corrections = get_past_corrections(supabase_client)
    corrections_prompt = build_corrections_prompt(corrections)
    raw_response = call_vision_llm(files, parent_entries, corrections_prompt)

    parent_set = set(entry["parent"] for entry in parent_entries)
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
