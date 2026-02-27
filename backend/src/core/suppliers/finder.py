import sys
import os
import re
from urllib.parse import urlparse

import anthropic
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"[\(]?\d{3}[\)]?[-.\s]?\d{3}[-.\s]?\d{4}")

FILTER_TOOL = {
    "name": "filter_suppliers",
    "description": "Filter and structure a list of potential food suppliers for a restaurant",
    "input_schema": {
        "type": "object",
        "properties": {
            "suppliers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Business name",
                        },
                        "website": {
                            "type": ["string", "null"],
                            "description": "Website URL",
                        },
                        "phone": {
                            "type": ["string", "null"],
                            "description": "Phone number if found",
                        },
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Food categories they supply (e.g. produce, meat, dairy)",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this is a relevant supplier",
                        },
                    },
                    "required": ["name", "website", "categories", "reasoning"],
                },
                "description": "Filtered list of real food distributors/suppliers that serve restaurants",
            },
        },
        "required": ["suppliers"],
    },
}

SYSTEM_PROMPT = """You are filtering web search results to find real food distributors and suppliers that serve restaurants.

You will receive search result snippets. Your job: pick out real wholesale food suppliers/distributors.

Include:
- Wholesale food distributors (US Foods, Sysco, Performance Foodservice, etc.)
- Regional/local produce distributors
- Specialty food suppliers (meat, seafood, dairy, bakery)
- Restaurant supply companies that sell food products

Exclude:
- Retail grocery stores (unless they have a wholesale/restaurant program)
- Equipment suppliers (kitchen equipment, furniture)
- Food delivery apps (DoorDash, UberEats)
- Recipe blogs, review sites, directories/listing pages
- Companies that are clearly not food suppliers

For each valid supplier, extract the business name, website, phone (if visible), and food categories they cover."""


def extract_domain(url: str) -> str | None:
    """Extract the root domain from a URL."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host if host else None
    except Exception:
        return None


def extract_emails_from_text(text: str) -> list[str]:
    """Extract email addresses from text using regex."""
    return EMAIL_RE.findall(text)


def extract_phones_from_text(text: str) -> list[str]:
    """Extract phone numbers from text using regex."""
    raw = PHONE_RE.findall(text)
    # Filter out obvious non-phone numbers (too many digits in a row, etc.)
    phones = []
    for p in raw:
        digits = re.sub(r"\D", "", p)
        if len(digits) == 10:
            phones.append(p.strip())
    return phones


def search_tavily(query: str, max_results: int = 5) -> list[dict]:
    """Run a Tavily web search and return results."""
    api_key = get("TAVILY_API_KEY")
    if not api_key:
        return []

    try:
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={
                "query": query,
                "max_results": max_results,
                "include_answer": False,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("results", [])
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
        return []


def extract_tavily(urls: list[str]) -> list[dict]:
    """Extract content from URLs using Tavily extract API."""
    api_key = get("TAVILY_API_KEY")
    if not api_key or not urls:
        return []

    try:
        resp = httpx.post(
            "https://api.tavily.com/extract",
            json={"urls": urls},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("results", [])
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
        return []


def search_hunter(domain: str, limit: int = 5) -> list[dict]:
    """Search Hunter.io for email contacts at a domain."""
    api_key = get("HUNTER_API_KEY")
    if not api_key:
        return []

    try:
        resp = httpx.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": api_key,
                "limit": limit,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", {})
        return data.get("emails", [])
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
        return []


def pick_best_email(emails: list[dict]) -> dict | None:
    """Pick the best email contact from Hunter results.

    Prefers: sales/generic emails > high confidence > seniority.
    """
    if not emails:
        return None

    for e in emails:
        val = e.get("value", "")
        if val.startswith(("sales@", "info@", "contact@", "hello@")):
            return e

    sorted_emails = sorted(emails, key=lambda e: e.get("confidence", 0), reverse=True)
    return sorted_emails[0]


def pick_best_email_from_list(emails: list[str]) -> str | None:
    """Pick the best email from a plain list of email strings.

    Prefers: sales/info/contact@ > first found.
    Ignores common junk emails.
    """
    junk = {"noreply@", "no-reply@", "donotreply@", "mailer-daemon@", "postmaster@"}
    filtered = [e for e in emails if not any(e.lower().startswith(j) for j in junk)]
    if not filtered:
        return None

    for e in filtered:
        local = e.split("@")[0].lower()
        if local in ("sales", "info", "contact", "hello", "orders", "ordering"):
            return e

    return filtered[0]


def filter_with_llm(
    search_results: list[dict], city: str, state: str, categories: list[str]
) -> list[dict]:
    """Use LLM to filter search results into real food suppliers."""
    if not search_results:
        return []

    snippets = []
    for i, r in enumerate(search_results):
        snippets.append(
            f"[{i + 1}] {r.get('title', 'No title')}\n"
            f"    URL: {r.get('url', '')}\n"
            f"    {r.get('content', '')[:500]}"
        )

    prompt = f"""Restaurant location: {city}, {state}
Menu categories the restaurant buys: {", ".join(categories)}

Search results to filter:

{chr(10).join(snippets)}

Pick out real food distributors/suppliers from these results. Ignore directories, blogs, retail stores, and equipment companies."""

    client = anthropic.Anthropic(api_key=get("ANTHROPIC_API_KEY"))

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=[FILTER_TOOL],
        tool_choice={"type": "tool", "name": "filter_suppliers"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use":
            return block.input.get("suppliers", [])

    return []


def enrich_contact(name: str, website: str | None, city: str, state: str) -> dict:
    """Try multiple strategies to find email + phone for a supplier.

    Waterfall:
    1. Hunter.io domain search
    2. Regex extract from supplier's website (Tavily extract)
    3. Targeted Tavily search for "{company} {city} email contact"

    Returns {"email": str|None, "phone": str|None, "contact_name": str|None, "contact_title": str|None}.
    """
    result = {"email": None, "phone": None, "contact_name": None, "contact_title": None}
    domain = extract_domain(website) if website else None

    # --- Layer 1: Hunter.io ---
    if domain:
        hunter_emails = search_hunter(domain)
        best = pick_best_email(hunter_emails)
        if best:
            result["email"] = best.get("value")
            first = best.get("first_name") or ""
            last = best.get("last_name") or ""
            result["contact_name"] = f"{first} {last}".strip() or None
            result["contact_title"] = best.get("position") or None

    if result["email"]:
        return result

    # --- Layer 2: Scrape supplier website via Tavily extract ---
    if website:
        # Try the main page + common contact paths
        base = website.rstrip("/")
        urls_to_try = [base]
        for path in ["/contact", "/contact-us", "/about", "/about-us"]:
            urls_to_try.append(base + path)

        pages = extract_tavily(urls_to_try)
        for page in pages:
            content = page.get("raw_content", "")
            if not result["email"]:
                emails = extract_emails_from_text(content)
                result["email"] = pick_best_email_from_list(emails)
            if not result["phone"]:
                phones = extract_phones_from_text(content)
                if phones:
                    result["phone"] = phones[0]

    if result["email"]:
        return result

    # --- Layer 3: Targeted Tavily search ---
    search_results = search_tavily(
        f"{name} {city} {state} email contact", max_results=3
    )
    for r in search_results:
        content = r.get("content", "")
        if not result["email"]:
            emails = extract_emails_from_text(content)
            result["email"] = pick_best_email_from_list(emails)
        if not result["phone"]:
            phones = extract_phones_from_text(content)
            if phones:
                result["phone"] = phones[0]

    return result


def find_suppliers(supabase_client, restaurant_id: str) -> dict:
    """Find food suppliers near a restaurant.

    Steps:
    1. Get restaurant location + tracked commodity categories
    2. Tavily search for suppliers
    3. LLM filters to real food suppliers
    4. Enrich each supplier with email/phone (Hunter → website scrape → targeted search)
    5. Store in suppliers table
    """
    restaurant = (
        supabase_client.table("restaurants")
        .select("name, address, lat, lng, state")
        .eq("id", restaurant_id)
        .single()
        .execute()
    )
    address = restaurant.data["address"]
    state = restaurant.data["state"]
    city = address.split(",")[0].strip()

    tracked = (
        supabase_client.table("restaurant_commodities")
        .select("raw_ingredient_name")
        .eq("restaurant_id", restaurant_id)
        .eq("status", "tracked")
        .execute()
    )
    categories = list({row["raw_ingredient_name"] for row in tracked.data})

    # Build search queries
    queries = [f"wholesale food supplier distributor near {city} {state}"]
    for cat in categories[:3]:
        queries.append(f"{cat} food distributor wholesale near {city} {state}")

    # Run all Tavily searches
    all_results = []
    seen_urls = set()
    for query in queries:
        results = search_tavily(query, max_results=5)
        for r in results:
            url = r.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)

    # LLM filters to real food suppliers
    filtered = filter_with_llm(all_results, city, state, categories)

    # Enrich each supplier with contact info (waterfall: Hunter → scrape → search)
    suppliers = []
    seen_domains = set()
    for s in filtered:
        website = s.get("website")
        domain = extract_domain(website) if website else None

        if domain and domain in seen_domains:
            continue
        if domain:
            seen_domains.add(domain)

        contact = enrich_contact(s["name"], website, city, state)

        # Use phone from LLM filter if enrichment didn't find one
        phone = contact["phone"] or s.get("phone")

        suppliers.append(
            {
                "restaurant_id": restaurant_id,
                "name": s["name"],
                "email": contact["email"],
                "contact_name": contact["contact_name"],
                "contact_title": contact["contact_title"],
                "phone": phone,
                "website": website,
                "categories": s.get("categories", []),
                "source": "tavily",
            }
        )

    # Clear old suppliers and insert new ones
    supabase_client.table("suppliers").delete().eq(
        "restaurant_id", restaurant_id
    ).execute()

    inserted = []
    for s in suppliers:
        try:
            row = supabase_client.table("suppliers").insert(s).execute()
            inserted.append(row.data[0])
        except Exception:
            pass  # Skip duplicates (e.g. two suppliers with no website)

    return {
        "restaurant_id": restaurant_id,
        "city": city,
        "state": state,
        "categories_searched": categories[:3],
        "search_results_found": len(all_results),
        "suppliers_found": len(inserted),
        "suppliers": inserted,
    }
