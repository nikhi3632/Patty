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


def build_correction_hints(supabase_client) -> str:
    """Build correction hints from cross-restaurant user patterns.

    False positives (rate-based): system-extracted items users deleted or demoted.
    Uses correction_rate >= dynamic threshold (mean + 1.5*std of all rates).
    Bootstrap: 30% threshold when <10 restaurants processed.

    False negatives (count-based): user-added items at N+ distinct restaurants.
    Bootstrap: min_count 2 when <10 restaurants. Distribution-based after.

    Absolute floor: min_count 2 always. One correction is never signal.
    """
    # --- False positives (rate-based) ---

    # All system-extracted rows — need both extractions and corrections
    system_rows = (
        supabase_client.table("restaurant_commodities")
        .select(
            "raw_ingredient_name, restaurant_id, original_status, status, deleted_at"
        )
        .eq("added_by", "system")
        .execute()
    )

    # Count distinct restaurants per ingredient: total extractions + corrections
    extraction_restaurants = {}
    correction_restaurants = {}
    all_restaurant_ids = set()

    for row in system_rows.data:
        name = row["raw_ingredient_name"]
        rid = row["restaurant_id"]
        all_restaurant_ids.add(rid)
        extraction_restaurants.setdefault(name, set()).add(rid)
        is_deleted = row["deleted_at"] is not None
        is_demoted = row["original_status"] == "tracked" and row["status"] == "other"
        if is_deleted or is_demoted:
            correction_restaurants.setdefault(name, set()).add(rid)

    total_restaurants = len(all_restaurant_ids)
    min_sample = 3
    min_count = 2

    # Compute per-ingredient correction rates (only where sample >= min_sample)
    rates = {}
    for name, ext_rids in extraction_restaurants.items():
        if len(ext_rids) >= min_sample:
            corr_count = len(correction_restaurants.get(name, set()))
            rates[name] = corr_count / len(ext_rids)

    # Dynamic threshold from rate distribution
    # NOTE: correction rate distribution is right-skewed (most items at 0%).
    # mean + 1.5*std works at small scale. If threshold becomes too
    # aggressive at 500+ restaurants, switch to median + MAD for robustness.
    if total_restaurants < 10:
        fp_threshold = 0.3
    elif rates:
        rate_values = list(rates.values())
        avg = sum(rate_values) / len(rate_values)
        variance = sum((r - avg) ** 2 for r in rate_values) / len(rate_values)
        std = variance**0.5
        fp_threshold = avg + 1.5 * std
    else:
        fp_threshold = 0.3

    false_positives = []
    for name, rate in rates.items():
        corr_count = len(correction_restaurants.get(name, set()))
        if rate >= fp_threshold and corr_count >= min_count:
            false_positives.append((name, corr_count, int(rate * 100)))

    # --- False negatives (count-based) ---

    added = (
        supabase_client.table("restaurant_commodities")
        .select("raw_ingredient_name, restaurant_id")
        .eq("added_by", "user")
        .is_("deleted_at", "null")
        .execute()
    )
    fn_counts = {}
    for row in added.data:
        name = row["raw_ingredient_name"]
        fn_counts.setdefault(name, set()).add(row["restaurant_id"])

    if total_restaurants < 10:
        fn_threshold = min_count
    elif fn_counts:
        count_values = [len(rids) for rids in fn_counts.values()]
        avg = sum(count_values) / len(count_values)
        variance = sum((c - avg) ** 2 for c in count_values) / len(count_values)
        std = variance**0.5
        fn_threshold = max(min_count, avg + 1.5 * std)
    else:
        fn_threshold = min_count

    false_negatives = [
        (name, len(rids))
        for name, rids in fn_counts.items()
        if len(rids) >= fn_threshold and len(rids) >= min_count
    ]

    # --- Build prompt ---

    if not false_positives and not false_negatives:
        return ""

    sections = ["\n\nBased on corrections from previous restaurants:"]

    if false_positives:
        sections.append(
            "\nDO NOT extract these unless explicitly listed as a standalone item:"
        )
        for name, count, pct in sorted(false_positives, key=lambda x: -x[2]):
            sections.append(
                f"- {name} (corrected {pct}% of the time across {count} restaurants)"
            )

    if false_negatives:
        sections.append("\nLOOK CAREFULLY for these, they are commonly missed:")
        for name, count in sorted(false_negatives, key=lambda x: -x[1]):
            sections.append(f"- {name} (added manually at {count} restaurants)")

    return "\n".join(sections)


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


def upsert_commodity(
    supabase_client,
    restaurant_id,
    info,
    name,
    status,
    tracked_count,
    other_matched_count,
):
    """Insert or update a commodity row, respecting soft deletes.

    If an active row exists for this restaurant+commodity, update it.
    Otherwise insert a new row (even if a soft-deleted row exists).
    """
    existing = (
        supabase_client.table("restaurant_commodities")
        .select("id")
        .eq("restaurant_id", restaurant_id)
        .eq("commodity_id", info["id"])
        .is_("deleted_at", "null")
        .execute()
    )
    if existing.data:
        supabase_client.table("restaurant_commodities").update(
            {
                "raw_ingredient_name": name,
                "status": status,
            }
        ).eq("id", existing.data[0]["id"]).execute()
    else:
        supabase_client.table("restaurant_commodities").insert(
            {
                "restaurant_id": restaurant_id,
                "commodity_id": info["id"],
                "raw_ingredient_name": name,
                "status": status,
                "original_status": status,
                "added_by": "system",
            }
        ).execute()

    if status == "tracked":
        tracked_count += 1
    else:
        other_matched_count += 1
    return tracked_count, other_matched_count


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

    For re-uploads: inserts new items, updates existing active items.
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

    # Insert or update matched items — status based on has_price_data
    tracked_count = 0
    other_matched_count = 0
    for parent in tracked_parents:
        info = commodity_map.get(parent)
        if not info:
            continue

        status = "tracked" if info["has_price_data"] else "other"
        tracked_count, other_matched_count = upsert_commodity(
            supabase_client,
            restaurant_id,
            info,
            parent,
            status,
            tracked_count,
            other_matched_count,
        )

    # Resolve "other" items against the registry too (catches LLM misclassifications)
    other_names = []
    for ingredient in other_ingredients:
        name = normalize_ingredient(ingredient)
        if name:
            other_names.append(name)

    other_resolved = (
        resolve_commodity_ids(supabase_client, other_names) if other_names else {}
    )

    # "Other" items that matched the registry
    for name in other_names:
        info = other_resolved.get(name)
        if not info:
            continue
        status = "tracked" if info["has_price_data"] else "other"
        tracked_count, other_matched_count = upsert_commodity(
            supabase_client,
            restaurant_id,
            info,
            name,
            status,
            tracked_count,
            other_matched_count,
        )

    # Truly unmatched "other" items — insert with no commodity_id
    unmatched_names = [n for n in other_names if n not in other_resolved]
    other_unmatched_count = 0
    if unmatched_names:
        existing = (
            supabase_client.table("restaurant_commodities")
            .select("raw_ingredient_name")
            .eq("restaurant_id", restaurant_id)
            .is_("deleted_at", "null")
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
                "original_status": "other",
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

    corrections_prompt = build_correction_hints(supabase_client)
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
