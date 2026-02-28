"""Generate kitchen/restaurant aliases for USDA commodity parent names.

Uses an LLM to bridge the vocabulary gap between USDA naming conventions
(e.g. "cattle", "sheep", "crustaceans") and how restaurants write menus
(e.g. "beef", "lamb", "shrimp").

Called once during seed, results stored in commodities.aliases column.
"""

import sys
import os
import json

import anthropic

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

BATCH_SIZE = 40

SYSTEM_PROMPT = """You generate common kitchen and restaurant menu aliases for USDA commodity names.

For each commodity parent name, list the common names a restaurant menu would use.
Include cuts, preparations, colloquial terms, and related products.
Only include terms that clearly refer to the same commodity for purchasing purposes.
Keep each list to 15 terms max. Return ONLY valid JSON."""

USER_PROMPT_TEMPLATE = """For each USDA commodity parent name below, list common restaurant/kitchen aliases.

Return a JSON object mapping each parent to an array of lowercase alias strings.
Only include aliases that differ from the parent name itself.
If a commodity has no common aliases (the name is already what menus use), return an empty array.

Commodity parents:
{parents}

Return JSON like:
{{"cattle": ["beef", "steak", "veal", "brisket", "ribeye", "ground beef"], "sheep": ["lamb", "mutton", "lamb chop"], ...}}"""


def generate_aliases_batch(parents: list[str]) -> dict[str, list[str]]:
    """Generate aliases for a batch of parent commodity names via LLM."""
    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    prompt = USER_PROMPT_TEMPLATE.format(parents="\n".join(f"- {p}" for p in parents))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[: text.rfind("```")]

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        return {}

    # Normalize: lowercase, deduplicate, remove self-references
    cleaned = {}
    for parent, aliases in result.items():
        parent_lower = parent.lower()
        if not isinstance(aliases, list):
            continue
        unique = []
        seen = {parent_lower}
        for a in aliases:
            a_lower = str(a).strip().lower()
            if a_lower and a_lower not in seen:
                seen.add(a_lower)
                unique.append(a_lower)
        cleaned[parent_lower] = unique

    return cleaned


def generate_all_aliases(supabase_client) -> dict:
    """Generate and store aliases for all commodity parents.

    Returns {"parents_processed": int, "aliases_generated": int}.
    """
    result = supabase_client.table("commodities").select("parent").execute()
    parents = sorted(set(row["parent"] for row in result.data))

    all_aliases = {}
    for i in range(0, len(parents), BATCH_SIZE):
        batch = parents[i : i + BATCH_SIZE]
        batch_result = generate_aliases_batch(batch)
        all_aliases.update(batch_result)
        print(f"  Batch {i // BATCH_SIZE + 1}: {len(batch_result)} parents aliased")

    # Store aliases in DB
    total_aliases = 0
    for parent, aliases in all_aliases.items():
        if not aliases:
            continue
        supabase_client.table("commodities").update({"aliases": aliases}).eq(
            "parent", parent
        ).execute()
        total_aliases += len(aliases)

    return {"parents_processed": len(parents), "aliases_generated": total_aliases}
