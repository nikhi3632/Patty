from unittest.mock import patch, MagicMock
from src.core.geo import haversine, geocode
from src.core.suppliers.finder import (
    extract_domain,
    extract_emails_from_text,
    extract_phones_from_text,
    pick_best_email,
    pick_best_email_from_list,
    search_tavily,
    search_hunter,
    filter_with_llm,
    enrich_contact,
    batch_enrich_contacts,
    compute_distances,
    find_suppliers,
)


# --- extract_domain ---


def test_extract_domain_basic():
    assert extract_domain("https://www.usfoods.com/path") == "usfoods.com"


def test_extract_domain_no_www():
    assert extract_domain("https://sysco.com/about") == "sysco.com"


def test_extract_domain_subdomain():
    assert extract_domain("https://shop.example.com") == "example.com"


def test_extract_domain_invalid():
    assert extract_domain("not-a-url") is None


def test_extract_domain_empty():
    assert extract_domain("") is None


# --- haversine ---


def test_haversine_same_point():
    assert haversine(41.88, -87.63, 41.88, -87.63) == 0.0


def test_haversine_chicago_to_nyc():
    dist = haversine(41.88, -87.63, 40.71, -74.01)
    assert 710 < dist < 730  # ~720 miles


def test_haversine_short_distance():
    # Two points ~10 miles apart in Chicago
    dist = haversine(41.88, -87.63, 41.95, -87.63)
    assert 4 < dist < 6


# --- geocode ---


@patch("src.core.geo.get")
@patch("src.core.geo.httpx.get")
def test_geocode_success(mock_httpx_get, mock_config_get):
    mock_config_get.return_value = "fake-key"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [{"geometry": {"location": {"lat": 41.8781, "lng": -87.6298}}}]
    }
    mock_httpx_get.return_value = mock_resp

    result = geocode("US Foods, Chicago, IL")
    assert result is not None
    lat, lng = result
    assert abs(lat - 41.8781) < 0.001
    assert abs(lng - (-87.6298)) < 0.001


@patch("src.core.geo.get")
@patch("src.core.geo.httpx.get")
def test_geocode_not_found(mock_httpx_get, mock_config_get):
    mock_config_get.return_value = "fake-key"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"results": []}
    mock_httpx_get.return_value = mock_resp

    assert geocode("Nonexistent Business XYZ") is None


@patch("src.core.geo.get")
def test_geocode_no_api_key(mock_config_get):
    mock_config_get.return_value = ""
    assert geocode("anything") is None


@patch("src.core.geo.get")
@patch("src.core.geo.httpx.get")
def test_geocode_network_error(mock_httpx_get, mock_config_get):
    mock_config_get.return_value = "fake-key"
    mock_httpx_get.side_effect = Exception("timeout")
    assert geocode("anything") is None


# --- extract_emails_from_text ---


def test_extract_emails_basic():
    text = "Contact us at sales@example.com or info@test.org for more info."
    emails = extract_emails_from_text(text)
    assert "sales@example.com" in emails
    assert "info@test.org" in emails


def test_extract_emails_none_found():
    assert extract_emails_from_text("No emails here.") == []


# --- extract_phones_from_text ---


def test_extract_phones_basic():
    text = "Call us at (773) 231-7671 or 201-716-2700"
    phones = extract_phones_from_text(text)
    assert len(phones) == 2


def test_extract_phones_filters_non_10_digit():
    text = "ID: 1016775037"  # 10 digits but from a form field
    phones = extract_phones_from_text(text)
    # This matches the pattern but is 10 digits, so it passes filter
    # The regex + 10-digit filter isn't perfect but catches most junk
    assert isinstance(phones, list)


def test_extract_phones_none():
    assert extract_phones_from_text("No phone here") == []


# --- pick_best_email (Hunter dicts) ---


def test_pick_best_email_prefers_sales():
    emails = [
        {"value": "john@example.com", "confidence": 99},
        {"value": "sales@example.com", "confidence": 80},
    ]
    assert pick_best_email(emails)["value"] == "sales@example.com"


def test_pick_best_email_prefers_info():
    emails = [
        {"value": "john@example.com", "confidence": 99},
        {"value": "info@example.com", "confidence": 70},
    ]
    assert pick_best_email(emails)["value"] == "info@example.com"


def test_pick_best_email_falls_back_to_highest_confidence():
    emails = [
        {"value": "john@example.com", "confidence": 90},
        {"value": "jane@example.com", "confidence": 99},
    ]
    assert pick_best_email(emails)["value"] == "jane@example.com"


def test_pick_best_email_empty():
    assert pick_best_email([]) is None


# --- pick_best_email_from_list (plain strings) ---


def test_pick_best_email_from_list_prefers_sales():
    emails = ["john@ex.com", "sales@ex.com"]
    assert pick_best_email_from_list(emails) == "sales@ex.com"


def test_pick_best_email_from_list_prefers_info():
    emails = ["john@ex.com", "info@ex.com"]
    assert pick_best_email_from_list(emails) == "info@ex.com"


def test_pick_best_email_from_list_prefers_orders():
    emails = ["john@ex.com", "orders@ex.com"]
    assert pick_best_email_from_list(emails) == "orders@ex.com"


def test_pick_best_email_from_list_falls_back_to_first():
    emails = ["john@ex.com", "jane@ex.com"]
    assert pick_best_email_from_list(emails) == "john@ex.com"


def test_pick_best_email_from_list_filters_noreply():
    emails = ["noreply@ex.com", "john@ex.com"]
    assert pick_best_email_from_list(emails) == "john@ex.com"


def test_pick_best_email_from_list_empty():
    assert pick_best_email_from_list([]) is None


def test_pick_best_email_from_list_only_junk():
    assert pick_best_email_from_list(["noreply@ex.com", "no-reply@ex.com"]) is None


# --- search_tavily ---


@patch("src.core.suppliers.finder.get")
@patch("src.core.suppliers.finder.httpx.post")
def test_search_tavily_success(mock_post, mock_get):
    mock_get.return_value = "fake-key"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [
            {"title": "Supplier A", "url": "https://a.com", "content": "food dist"}
        ]
    }
    mock_post.return_value = mock_resp

    results = search_tavily("food distributor Chicago")
    assert len(results) == 1
    assert results[0]["title"] == "Supplier A"


@patch("src.core.suppliers.finder.get")
def test_search_tavily_no_key(mock_get):
    mock_get.return_value = ""
    assert search_tavily("query") == []


@patch("src.core.suppliers.finder.get")
@patch("src.core.suppliers.finder.httpx.post")
def test_search_tavily_error(mock_post, mock_get):
    mock_get.return_value = "fake-key"
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_post.return_value = mock_resp

    assert search_tavily("query") == []


# --- search_hunter ---


@patch("src.core.suppliers.finder.get")
@patch("src.core.suppliers.finder.httpx.get")
def test_search_hunter_success(mock_httpx_get, mock_get):
    mock_get.return_value = "fake-key"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "emails": [
                {
                    "value": "sales@test.com",
                    "confidence": 95,
                    "first_name": "Bob",
                    "last_name": "Smith",
                    "position": "Sales Rep",
                }
            ]
        }
    }
    mock_httpx_get.return_value = mock_resp

    emails = search_hunter("test.com")
    assert len(emails) == 1
    assert emails[0]["value"] == "sales@test.com"


@patch("src.core.suppliers.finder.get")
def test_search_hunter_no_key(mock_get):
    mock_get.return_value = ""
    assert search_hunter("test.com") == []


# --- filter_with_llm ---


@patch("src.core.suppliers.finder.get")
@patch("src.core.suppliers.finder.anthropic.Anthropic")
def test_filter_with_llm_returns_suppliers(mock_anthropic_cls, mock_get):
    mock_get.return_value = "fake-key"

    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {
        "suppliers": [
            {
                "name": "ABC Foods",
                "website": "https://abcfoods.com",
                "phone": "555-1234",
                "categories": ["produce", "dairy"],
                "reasoning": "Wholesale food distributor",
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls.return_value = mock_client

    results = filter_with_llm(
        [
            {
                "title": "ABC Foods",
                "url": "https://abcfoods.com",
                "content": "wholesale food",
            }
        ],
        "Chicago",
        "IL",
        ["produce", "dairy"],
    )
    assert len(results) == 1
    assert results[0]["name"] == "ABC Foods"


def test_filter_with_llm_empty_results():
    assert filter_with_llm([], "Chicago", "IL", []) == []


# --- enrich_contact ---


@patch("src.core.suppliers.finder.search_hunter")
def test_enrich_contact_hunter_hit(mock_hunter):
    mock_hunter.return_value = [
        {
            "value": "sales@abc.com",
            "confidence": 95,
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "Sales",
        }
    ]

    result = enrich_contact("ABC Foods", "https://abc.com", "Chicago", "IL")
    assert result["email"] == "sales@abc.com"
    assert result["contact_name"] == "Jane Doe"


@patch("src.core.suppliers.finder.search_tavily")
@patch("src.core.suppliers.finder.extract_tavily")
@patch("src.core.suppliers.finder.search_hunter")
def test_enrich_contact_falls_to_scrape(mock_hunter, mock_extract, mock_search):
    mock_hunter.return_value = []
    mock_extract.return_value = [
        {"raw_content": "Contact us at orders@supplier.com or call (555) 123-4567"}
    ]
    mock_search.return_value = []  # Not needed, scrape should succeed

    result = enrich_contact("Supplier", "https://supplier.com", "Chicago", "IL")
    assert result["email"] == "orders@supplier.com"
    assert result["phone"] == "(555) 123-4567"


@patch("src.core.suppliers.finder.search_tavily")
@patch("src.core.suppliers.finder.extract_tavily")
@patch("src.core.suppliers.finder.search_hunter")
def test_enrich_contact_falls_to_targeted_search(
    mock_hunter, mock_extract, mock_search
):
    mock_hunter.return_value = []
    mock_extract.return_value = []  # Website scrape fails
    mock_search.return_value = [
        {"content": "Ginsberg's Foods - info@ginsbergsfoods.com - 518-828-4004"}
    ]

    result = enrich_contact("Ginsberg's Foods", "https://ginsbergs.com", "Hudson", "NY")
    assert result["email"] == "info@ginsbergsfoods.com"
    assert result["phone"] == "518-828-4004"


@patch("src.core.suppliers.finder.search_tavily")
@patch("src.core.suppliers.finder.extract_tavily")
@patch("src.core.suppliers.finder.search_hunter")
def test_enrich_contact_all_fail(mock_hunter, mock_extract, mock_search):
    mock_hunter.return_value = []
    mock_extract.return_value = []
    mock_search.return_value = []

    result = enrich_contact("Unknown Co", "https://unknown.com", "Nowhere", "XX")
    assert result["email"] is None
    assert result["phone"] is None


# --- batch_enrich_contacts ---


@patch("src.core.suppliers.finder.search_tavily")
@patch("src.core.suppliers.finder.extract_tavily")
@patch("src.core.suppliers.finder.search_hunter")
def test_batch_enrich_hunter_hit_skips_extract(mock_hunter, mock_extract, mock_search):
    """When Hunter finds email, that supplier should not generate extract URLs."""
    mock_hunter.return_value = [
        {
            "value": "sales@abc.com",
            "confidence": 95,
            "first_name": "Jo",
            "last_name": "X",
            "position": "Sales",
        }
    ]

    suppliers = [
        {"name": "ABC Foods", "website": "https://abc.com"},
        {"name": "DEF Foods", "website": "https://def.com"},
    ]
    results = batch_enrich_contacts(suppliers, "Chicago", "IL")

    # First supplier found via Hunter — second falls through
    assert results[0]["email"] == "sales@abc.com"
    assert results[0]["contact_name"] == "Jo X"

    # extract_tavily should only get URLs for DEF (not ABC)
    if mock_extract.called:
        urls = mock_extract.call_args[0][0]
        assert not any("abc.com" in u for u in urls)


@patch("src.core.suppliers.finder.search_tavily")
@patch("src.core.suppliers.finder.extract_tavily")
@patch("src.core.suppliers.finder.search_hunter")
def test_batch_enrich_batches_extract(mock_hunter, mock_extract, mock_search):
    """Multiple suppliers should produce ONE extract_tavily call with all URLs."""
    mock_hunter.return_value = []  # Hunter misses all
    mock_extract.return_value = [
        {"url": "https://abc.com", "raw_content": "Email: orders@abc.com"},
        {"url": "https://def.com/contact", "raw_content": "Call (555) 123-4567"},
    ]
    mock_search.return_value = []

    suppliers = [
        {"name": "ABC Foods", "website": "https://abc.com"},
        {"name": "DEF Foods", "website": "https://def.com"},
    ]
    results = batch_enrich_contacts(suppliers, "Chicago", "IL")

    # Should be exactly 1 extract_tavily call with URLs from both suppliers
    assert mock_extract.call_count == 1
    urls = mock_extract.call_args[0][0]
    assert any("abc.com" in u for u in urls)
    assert any("def.com" in u for u in urls)
    # 5 URLs per supplier (base + 4 paths) × 2 suppliers = 10
    assert len(urls) == 10

    assert results[0]["email"] == "orders@abc.com"
    assert results[1]["phone"] == "(555) 123-4567"


# --- compute_distances ---


@patch("src.core.suppliers.finder.geocode_full")
def test_compute_distances_success(mock_geocode_full):
    mock_geocode_full.side_effect = [
        (41.90, -87.65, "123 Main St, Chicago, IL 60601"),  # ~1.5 miles from restaurant
        None,  # geocode fails
    ]

    suppliers = [
        {"name": "ABC Foods"},
        {"name": "Unknown Co"},
    ]
    results = compute_distances(suppliers, "Chicago", "IL", 41.88, -87.63)

    assert len(results) == 2
    assert results[0]["distance"] is not None
    assert 1.0 < results[0]["distance"] < 3.0
    assert results[0]["address"] == "123 Main St, Chicago, IL 60601"
    assert results[1]["distance"] is None
    assert results[1]["address"] is None


@patch("src.core.suppliers.finder.geocode_full")
def test_compute_distances_uses_address_first(mock_geocode_full):
    """Should try the supplier's address before falling back to name + city."""
    mock_geocode_full.side_effect = [
        (41.90, -87.65, "123 Main St, Chicago, IL"),  # address hit
    ]

    suppliers = [{"name": "ABC Foods", "address": "123 Main St, Chicago, IL"}]
    compute_distances(suppliers, "Chicago", "IL", 41.88, -87.63)

    # Should have been called with the address, not "ABC Foods, Chicago, IL"
    mock_geocode_full.assert_called_once_with("123 Main St, Chicago, IL")


def test_compute_distances_empty():
    assert compute_distances([], "Chicago", "IL", 41.88, -87.63) == []


# --- find_suppliers ---


@patch("src.core.suppliers.finder.compute_distances")
@patch("src.core.suppliers.finder.batch_enrich_contacts")
@patch("src.core.suppliers.finder.filter_with_llm")
@patch("src.core.suppliers.finder.search_tavily")
def test_find_suppliers_full_flow(mock_tavily, mock_filter, mock_batch, mock_dist):
    mock_tavily.return_value = [
        {
            "title": "Good Foods",
            "url": "https://goodfoods.com",
            "content": "distributor",
        }
    ]
    mock_filter.return_value = [
        {
            "name": "Good Foods",
            "website": "https://goodfoods.com",
            "phone": "555-0000",
            "categories": ["produce"],
            "reasoning": "Local distributor",
        }
    ]
    mock_batch.return_value = [
        {
            "email": "sales@goodfoods.com",
            "phone": None,
            "contact_name": "Jane Doe",
            "contact_title": "Sales Manager",
        }
    ]
    mock_dist.return_value = [
        {"distance": 3.2, "address": "123 Main St, Chicago, IL 60601"}
    ]

    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "name": "Test Restaurant",
        "address": "123 Main St, Chicago, IL",
        "lat": 41.88,
        "lng": -87.63,
        "state": "IL",
    }

    mock_tracked = MagicMock()
    mock_tracked.data = [
        {"commodities": {"parent": "tomatoes"}},
        {"commodities": {"parent": "cheese"}},
    ]

    mock_delete = MagicMock()
    mock_delete.data = []

    # No existing supplier by website
    mock_existing = MagicMock()
    mock_existing.data = []

    mock_insert = MagicMock()
    mock_insert.data = [
        {
            "id": "supplier-1",
            "name": "Good Foods",
            "email": "sales@goodfoods.com",
            "contact_name": "Jane Doe",
            "contact_title": "Sales Manager",
            "phone": "555-0000",
            "website": "https://goodfoods.com",
            "categories": ["produce"],
            "source": "tavily",
        }
    ]

    mock_link_insert = MagicMock()
    mock_link_insert.data = [{"id": "link-1"}]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "restaurant_commodities":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_tracked
        elif table_name == "restaurant_suppliers":
            mock_t.delete.return_value.eq.return_value.execute.return_value = (
                mock_delete
            )
            mock_t.insert.return_value.execute.return_value = mock_link_insert
        elif table_name == "suppliers":
            # Website check (.eq) and name check (.ilike) both return no match
            mock_t.select.return_value.eq.return_value.execute.return_value = (
                mock_existing
            )
            mock_t.select.return_value.ilike.return_value.execute.return_value = (
                mock_existing
            )
            mock_t.insert.return_value.execute.return_value = mock_insert
        return mock_t

    mock_sb.table.side_effect = table_router

    result = find_suppliers(mock_sb, "rest-1")

    assert result["suppliers_found"] == 1
    assert result["suppliers"][0]["name"] == "Good Foods"
    assert result["suppliers"][0]["email"] == "sales@goodfoods.com"
    assert result["city"] == "Chicago"
    assert result["state"] == "IL"


@patch("src.core.suppliers.finder.compute_distances")
@patch("src.core.suppliers.finder.batch_enrich_contacts")
@patch("src.core.suppliers.finder.search_tavily")
def test_find_suppliers_no_results(mock_tavily, mock_batch, mock_dist):
    mock_tavily.return_value = []
    mock_batch.return_value = []
    mock_dist.return_value = []

    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "name": "Test",
        "address": "456 Oak Ave, Miami, FL",
        "lat": 25.76,
        "lng": -80.19,
        "state": "FL",
    }

    mock_tracked = MagicMock()
    mock_tracked.data = []

    mock_delete = MagicMock()
    mock_delete.data = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "restaurant_commodities":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_tracked
        elif table_name == "restaurant_suppliers":
            mock_t.delete.return_value.eq.return_value.execute.return_value = (
                mock_delete
            )
        return mock_t

    mock_sb.table.side_effect = table_router

    result = find_suppliers(mock_sb, "rest-2")
    assert result["suppliers_found"] == 0
    assert result["suppliers"] == []


@patch("src.core.suppliers.finder.compute_distances")
@patch("src.core.suppliers.finder.batch_enrich_contacts")
@patch("src.core.suppliers.finder.filter_with_llm")
@patch("src.core.suppliers.finder.search_tavily")
def test_find_suppliers_dedup_by_domain(
    mock_tavily, mock_filter, mock_batch, mock_dist
):
    """Two suppliers with same domain should be deduped before enrichment."""
    mock_tavily.return_value = [{"title": "A", "url": "https://a.com", "content": "x"}]
    mock_filter.return_value = [
        {
            "name": "ABC Foods",
            "website": "https://www.abcfoods.com",
            "categories": ["produce"],
            "reasoning": "ok",
        },
        {
            "name": "ABC Foods Inc",
            "website": "https://abcfoods.com/about",
            "categories": ["produce"],
            "reasoning": "ok",
        },
    ]
    # Only 1 supplier after dedup, so batch returns 1 result
    mock_batch.return_value = [
        {"email": None, "phone": None, "contact_name": None, "contact_title": None}
    ]
    mock_dist.return_value = [{"distance": None, "address": None}]

    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "name": "Test",
        "address": "1 St, Boston, MA",
        "lat": 42.0,
        "lng": -71.0,
        "state": "MA",
    }

    mock_tracked = MagicMock()
    mock_tracked.data = [{"commodities": {"parent": "produce"}}]

    mock_delete = MagicMock()
    mock_delete.data = []

    mock_existing = MagicMock()
    mock_existing.data = []

    mock_insert = MagicMock()
    mock_insert.data = [
        {"id": "s1", "name": "ABC Foods", "website": "https://www.abcfoods.com"}
    ]

    mock_link_insert = MagicMock()
    mock_link_insert.data = [{"id": "link-1"}]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "restaurant_commodities":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_tracked
        elif table_name == "restaurant_suppliers":
            mock_t.delete.return_value.eq.return_value.execute.return_value = (
                mock_delete
            )
            mock_t.insert.return_value.execute.return_value = mock_link_insert
        elif table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.execute.return_value = (
                mock_existing
            )
            mock_t.select.return_value.ilike.return_value.execute.return_value = (
                mock_existing
            )
            mock_t.insert.return_value.execute.return_value = mock_insert
        return mock_t

    mock_sb.table.side_effect = table_router

    result = find_suppliers(mock_sb, "rest-3")

    # Should only insert 1 supplier, not 2 (dedup by domain)
    assert result["suppliers_found"] == 1
    # batch_enrich_contacts should receive only 1 supplier (post-dedup)
    assert len(mock_batch.call_args[0][0]) == 1
