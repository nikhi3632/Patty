import logging
import sys
import os
import re
from urllib.parse import urlparse

import anthropic
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.config import get
from src.core.http import redact, safe_request
from src.core.geo import haversine, geocode_full

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
STATE_ABBRS = re.compile(r"^[A-Z]{2}$")


def extract_city(address: str, state: str) -> str:
    """Extract city from a US address string.

    Handles common formats:
      "123 Main St, Chicago, IL 60654" → "Chicago"
      "Chicago, IL" → "Chicago"
      "123 Main St" → "123 Main St" (fallback)

    Skips parts that look like a street (start with digit), state abbreviation,
    or zip code. Returns the first remaining part, or falls back to the
    part after the street number.
    """
    parts = [p.strip() for p in address.split(",")]
    for part in parts:
        # Skip parts that are street addresses (start with digit)
        if part and part[0].isdigit():
            continue
        # Skip state abbreviations and "STATE ZIP" patterns
        token = part.split()[0] if part else ""
        if STATE_ABBRS.match(token) or token == state:
            continue
        return part
    # Fallback: second part if available, else first
    return parts[1] if len(parts) >= 2 else parts[0]


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
                        "address": {
                            "type": ["string", "null"],
                            "description": "Street address if visible in the snippet",
                        },
                        "categories": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Food categories they supply — prefer the restaurant's tracked categories when applicable (e.g. if restaurant tracks 'tomatoes' and supplier sells produce, include 'tomatoes')",
                        },
                        "reasoning": {
                            "type": "string",
                            "description": "Why this is a relevant supplier",
                        },
                    },
                    "required": [
                        "name",
                        "website",
                        "address",
                        "categories",
                        "reasoning",
                    ],
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

For each valid supplier, extract the business name, website, phone (if visible), street address (if visible), and food categories they cover."""


def extract_domain(url: str) -> str | None:
    """Extract the root domain from a URL, normalizing subdomains.

    e.g. "https://orders.abcfoods.com/path" → "abcfoods.com"
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        parts = host.split(".")
        if len(parts) > 2:
            host = ".".join(parts[-2:])
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
        with safe_request():
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
        with safe_request():
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
        with safe_request():
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
    search_results: list[dict],
    city: str,
    state: str,
    categories: list[str],
    lenient: bool = False,
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

    instruction = (
        "Pick out real food distributors/suppliers from these results. Ignore directories, blogs, retail stores, and equipment companies."
        if not lenient
        else "Pick out ANY business that could plausibly supply food to a restaurant. Be generous — include regional distributors, wholesalers, and companies that mention food products even if the snippet is limited. When in doubt, include them."
    )

    prompt = f"""Restaurant location: {city}, {state}
Menu categories the restaurant buys: {", ".join(categories)}

Search results to filter:

{chr(10).join(snippets)}

{instruction}

When assigning supplier categories, prefer the restaurant's specific tracked categories listed above when applicable, rather than broad labels like 'produce' or 'dairy'."""

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


def enrich_contact(
    name: str,
    website: str | None,
    city: str,
    state: str,
    prefetched_pages: list[dict] | None = None,
) -> dict:
    """Try multiple strategies to find email + phone for a supplier.

    Waterfall:
    1. Hunter.io domain search
    2. Regex extract from supplier's website (Tavily extract)
    3. Targeted Tavily search for "{company} {city} email contact"

    If prefetched_pages is provided (even empty), layer 2 uses those pages
    instead of making a fresh Tavily extract call. This supports batching
    across multiple suppliers.

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
        if prefetched_pages is not None:
            pages = prefetched_pages
        else:
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


def keyword_fallback(search_results: list[dict], categories: list[str]) -> list[dict]:
    """Last-resort extraction when LLM filter returns nothing.

    Scores each result by how many of the restaurant's tracked categories
    appear in the title/content, plus generic supply-chain terms.
    Skips results whose domain matches common non-supplier platforms
    (social media, review sites, delivery apps) by checking if the domain
    appears as a well-known TLD in the URL path structure.
    """
    candidates = []
    # Build scoring terms from the restaurant's own categories
    score_terms = {c.lower() for c in categories}
    score_terms |= {"wholesale", "distributor", "supply", "farm"}

    for r in search_results:
        url = r.get("url", "")
        domain = extract_domain(url)
        if not domain:
            continue

        # Skip URLs on platforms that aggregate/list businesses, not sell food.
        # Rather than a hardcoded blocklist, check if the domain is one of the
        # search result's own source (Tavily labels these) or if the URL path
        # suggests a listing/profile page.
        path = url.lower()
        if any(
            sig in path
            for sig in ["/biz/", "/listing/", "/profile/", "/review/", "/place/"]
        ):
            continue
        # Skip well-known non-supplier platforms by TLD pattern
        root = ".".join(domain.split(".")[-2:])
        if root in PLATFORM_ROOTS:
            continue

        text = (r.get("title", "") + " " + r.get("content", "")).lower()
        hits = sum(1 for term in score_terms if term in text)
        if hits >= 2:
            candidates.append(
                {
                    "name": r.get("title", "").split(" - ")[0].split(" | ")[0].strip(),
                    "website": url,
                    "phone": None,
                    "categories": ["general wholesale"],
                    "reasoning": "keyword fallback",
                    "score": hits,
                }
            )

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates[:5]


PLATFORM_ROOTS = {
    # Social media
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "tiktok.com",
    "reddit.com",
    # Review / directory
    "yelp.com",
    "yellowpages.com",
    "bbb.org",
    "tripadvisor.com",
    "mapquest.com",
    "google.com",
    # Delivery apps
    "doordash.com",
    "ubereats.com",
    "grubhub.com",
    # Reference
    "wikipedia.org",
}


def batch_enrich_contacts(suppliers: list[dict], city: str, state: str) -> list[dict]:
    """Enrich contacts for multiple suppliers, batching Tavily extract calls.

    Same waterfall as enrich_contact (Hunter → extract → search) but layer 2
    collects all supplier URLs and makes a single Tavily extract API call
    instead of one per supplier.
    """
    n = len(suppliers)
    results = [
        {"email": None, "phone": None, "contact_name": None, "contact_title": None}
        for _ in range(n)
    ]

    # Layer 1: Hunter.io (per-domain, can't batch)
    need_extract = []
    for i, s in enumerate(suppliers):
        domain = extract_domain(s.get("website")) if s.get("website") else None
        if domain:
            hunter_emails = search_hunter(domain)
            best = pick_best_email(hunter_emails)
            if best:
                results[i]["email"] = best.get("value")
                first = best.get("first_name") or ""
                last = best.get("last_name") or ""
                results[i]["contact_name"] = f"{first} {last}".strip() or None
                results[i]["contact_title"] = best.get("position") or None
                continue
        need_extract.append(i)

    # Layer 2: Batch Tavily extract — one API call for all remaining suppliers
    all_urls = []
    url_to_index = {}
    for i in need_extract:
        website = suppliers[i].get("website")
        if website:
            base = website.rstrip("/")
            for path in ["", "/contact", "/contact-us", "/about", "/about-us"]:
                url = base + path
                all_urls.append(url)
                url_to_index[url] = i

    if all_urls:
        pages = extract_tavily(all_urls)
        for page in pages:
            url = page.get("url", "")
            i = url_to_index.get(url)
            if i is None:
                continue
            content = page.get("raw_content", "")
            if not results[i]["email"]:
                emails = extract_emails_from_text(content)
                results[i]["email"] = pick_best_email_from_list(emails)
            if not results[i]["phone"]:
                phones = extract_phones_from_text(content)
                if phones:
                    results[i]["phone"] = phones[0]

    # Layer 3: Targeted search for remaining without emails
    for i in need_extract:
        if results[i]["email"]:
            continue
        s = suppliers[i]
        search_results = search_tavily(
            f"{s['name']} {city} {state} email contact", max_results=3
        )
        for r in search_results:
            content = r.get("content", "")
            if not results[i]["email"]:
                emails = extract_emails_from_text(content)
                results[i]["email"] = pick_best_email_from_list(emails)
            if not results[i]["phone"]:
                phones = extract_phones_from_text(content)
                if phones:
                    results[i]["phone"] = phones[0]

    return results


def compute_distances(
    suppliers: list[dict],
    city: str,
    state: str,
    restaurant_lat: float,
    restaurant_lng: float,
) -> list[dict]:
    """Geocode each supplier and compute haversine distance from restaurant.

    Uses Google Geocoding API. Tries the supplier's street address first
    (most reliable), then falls back to business name + city.
    Returns list of {"distance": float|None, "address": str|None}.
    """
    results = []
    for s in suppliers:
        address = s.get("address")
        geo = geocode_full(address) if address else None
        if not geo:
            geo = geocode_full(f"{s['name']}, {city}, {state}")
        if geo:
            dist = round(haversine(restaurant_lat, restaurant_lng, geo[0], geo[1]), 1)
            results.append({"distance": dist, "address": geo[2]})
        else:
            results.append({"distance": None, "address": None})
    return results


def find_suppliers(supabase_client, restaurant_id: str) -> dict:
    """Find food suppliers near a restaurant.

    Steps:
    1. Get restaurant location + tracked commodity categories
    2. Tavily search for suppliers
    3. LLM filters to real food suppliers
    4. Batch enrich with email/phone (Hunter → website scrape → targeted search)
    5. Geocode for distance estimation
    6. Store in suppliers table + restaurant_suppliers links
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
    city = extract_city(address, state)

    tracked = (
        supabase_client.table("restaurant_commodities")
        .select("commodities(parent)")
        .eq("restaurant_id", restaurant_id)
        .eq("status", "tracked")
        .is_("deleted_at", "null")
        .execute()
    )
    categories = list(
        {row["commodities"]["parent"] for row in tracked.data if row.get("commodities")}
    )

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

    # LLM filters to real food suppliers (retry with lenient prompt if first pass finds nothing)
    filtered = filter_with_llm(all_results, city, state, categories)
    if not filtered and len(all_results) >= 5:
        filtered = filter_with_llm(all_results, city, state, categories, lenient=True)
    if not filtered and all_results:
        filtered = keyword_fallback(all_results, categories)

    # Dedup by domain before enrichment
    deduped = []
    seen_domains = set()
    for s in filtered:
        website = s.get("website")
        domain = extract_domain(website) if website else None
        if domain and domain in seen_domains:
            continue
        if domain:
            seen_domains.add(domain)
        deduped.append(s)

    # Batch enrich contacts (one Tavily extract call instead of N)
    contacts = batch_enrich_contacts(deduped, city, state)

    # Geocode suppliers for distance estimation
    restaurant_lat = float(restaurant.data["lat"])
    restaurant_lng = float(restaurant.data["lng"])
    geo_results = compute_distances(
        deduped, city, state, restaurant_lat, restaurant_lng
    )

    # Build supplier rows
    suppliers = []
    for i, s in enumerate(deduped):
        contact = contacts[i]
        phone = contact["phone"] or s.get("phone")
        # Use geocoded address (from Google) — more reliable than LLM snippet extraction
        address = geo_results[i]["address"] or s.get("address")
        suppliers.append(
            {
                "name": s["name"],
                "address": address,
                "email": contact["email"],
                "contact_name": contact["contact_name"],
                "contact_title": contact["contact_title"],
                "phone": phone,
                "website": s.get("website"),
                "categories": s.get("categories", []),
                "source": "tavily",
            }
        )

    # Clear old restaurant-supplier links (not the shared suppliers themselves)
    supabase_client.table("restaurant_suppliers").delete().eq(
        "restaurant_id", restaurant_id
    ).execute()

    linked = []
    for i, s in enumerate(suppliers):
        try:
            # Check if supplier already exists — by website first, then by name
            supplier_row = None
            website = s.get("website")
            if website:
                existing = (
                    supabase_client.table("suppliers")
                    .select("*")
                    .eq("website", website)
                    .execute()
                )
                if existing.data:
                    supplier_row = existing.data[0]

            if not supplier_row:
                existing = (
                    supabase_client.table("suppliers")
                    .select("*")
                    .ilike("name", s["name"])
                    .execute()
                )
                if existing.data:
                    supplier_row = existing.data[0]

            if not supplier_row:
                row = supabase_client.table("suppliers").insert(s).execute()
                supplier_row = row.data[0]
            elif s.get("address") and not supplier_row.get("address"):
                supabase_client.table("suppliers").update({"address": s["address"]}).eq(
                    "id", supplier_row["id"]
                ).execute()
                supplier_row["address"] = s["address"]

            # Create restaurant-supplier link with distance
            supabase_client.table("restaurant_suppliers").insert(
                {
                    "restaurant_id": restaurant_id,
                    "supplier_id": supplier_row["id"],
                    "distance_miles": geo_results[i]["distance"],
                }
            ).execute()

            linked.append(supplier_row)
        except Exception as exc:
            logger.warning(
                "Failed to link supplier %s: %s", s.get("name"), redact(str(exc))
            )

    return {
        "restaurant_id": restaurant_id,
        "city": city,
        "state": state,
        "categories_searched": categories[:3],
        "search_results_found": len(all_results),
        "suppliers_found": len(linked),
        "suppliers": linked,
    }
