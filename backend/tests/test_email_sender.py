from unittest.mock import patch, MagicMock
from src.core.email.sender import (
    send_email,
    plain_to_html,
    build_maps_link,
    lookup_restaurant_website,
)


@patch(
    "src.core.email.sender.lookup_restaurant_website",
    return_value="http://testrestaurant.com",
)
@patch("src.core.email.sender.get")
@patch("src.core.email.sender.get_gmail_service")
def test_send_email_success(mock_gmail, mock_get, mock_lookup):
    mock_get.side_effect = lambda k: {
        "TEST_EMAIL_OVERRIDE": "test@test.com",
        "GOOGLE_PLACES_API_KEY": "fake-google-key",
    }.get(k, "")

    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "gmail-msg-123",
        "threadId": "gmail-thread-456",
    }
    mock_gmail.return_value = mock_service

    mock_sb = MagicMock()

    mock_email = MagicMock()
    mock_email.data = {
        "id": "e1",
        "restaurant_id": "r1",
        "supplier_id": "s1",
        "to_email": "supplier@real.com",
        "from_email": "anamnikhilesh@gmail.com",
        "subject": "Pricing Inquiry",
        "body": "Hello...",
        "status": "generated",
    }

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "name": "Test Restaurant",
        "address": "123 Main St",
        "lat": 41.89,
        "lng": -87.63,
    }

    mock_supplier = MagicMock()
    mock_supplier.data = {
        "name": "Fresh Foods Co",
        "website": "https://freshfoods.com",
    }

    mock_update = MagicMock()
    mock_update.data = [{"id": "e1", "status": "sent"}]

    mock_thread_insert = MagicMock()
    mock_thread_insert.data = [{"id": "thread-001"}]

    mock_msg_insert = MagicMock()
    mock_msg_insert.data = [{"id": "msg-001"}]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "emails":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_email
            mock_t.update.return_value.eq.return_value.execute.return_value = (
                mock_update
            )
        elif table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_supplier
        elif table_name == "email_threads":
            mock_t.insert.return_value.execute.return_value = mock_thread_insert
        elif table_name == "email_messages":
            mock_t.insert.return_value.execute.return_value = mock_msg_insert
        return mock_t

    mock_sb.table.side_effect = table_router

    result = send_email(mock_sb, "e1")
    assert result["sent"] is True
    assert result["gmail_message_id"] == "gmail-msg-123"
    assert result["gmail_thread_id"] == "gmail-thread-456"
    assert result["thread_id"] == "thread-001"
    assert result["routed_to"] == "test@test.com"


@patch("src.core.email.sender.lookup_restaurant_website", return_value="")
@patch("src.core.email.sender.get")
@patch("src.core.email.sender.get_gmail_service")
def test_send_email_no_override_uses_real_email(mock_gmail, mock_get, mock_lookup):
    mock_get.side_effect = lambda k: {
        "TEST_EMAIL_OVERRIDE": "",
    }.get(k, "")

    mock_service = MagicMock()
    mock_service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "gmail-msg-789",
        "threadId": "gmail-thread-012",
    }
    mock_gmail.return_value = mock_service

    mock_sb = MagicMock()

    mock_email = MagicMock()
    mock_email.data = {
        "id": "e2",
        "restaurant_id": "r1",
        "supplier_id": "s2",
        "to_email": "supplier@real.com",
        "from_email": "anamnikhilesh@gmail.com",
        "subject": "Hi",
        "body": "Hello",
        "status": "draft",
    }

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "name": "My Place",
        "address": "456 Oak Ave",
        "lat": None,
        "lng": None,
    }

    mock_supplier = MagicMock()
    mock_supplier.data = {"name": "Local Dairy", "website": None}

    mock_update = MagicMock()
    mock_update.data = [{"id": "e2", "status": "sent"}]

    mock_thread_insert = MagicMock()
    mock_thread_insert.data = [{"id": "thread-002"}]

    mock_msg_insert = MagicMock()
    mock_msg_insert.data = [{"id": "msg-002"}]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "emails":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_email
            mock_t.update.return_value.eq.return_value.execute.return_value = (
                mock_update
            )
        elif table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_supplier
        elif table_name == "email_threads":
            mock_t.insert.return_value.execute.return_value = mock_thread_insert
        elif table_name == "email_messages":
            mock_t.insert.return_value.execute.return_value = mock_msg_insert
        return mock_t

    mock_sb.table.side_effect = table_router

    result = send_email(mock_sb, "e2")
    assert result["routed_to"] == "supplier@real.com"


def test_send_email_already_sent():
    mock_sb = MagicMock()

    mock_email = MagicMock()
    mock_email.data = {"id": "e3", "status": "sent"}

    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_email

    result = send_email(mock_sb, "e3")
    assert result["error"] == "Email already sent"


@patch("src.core.email.sender.get_gmail_service")
def test_send_email_no_gmail_credentials(mock_gmail):
    mock_gmail.return_value = None

    mock_sb = MagicMock()

    mock_email = MagicMock()
    mock_email.data = {"id": "e4", "status": "generated"}

    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_email

    result = send_email(mock_sb, "e4")
    assert result["error"] == "Gmail API not configured — missing credentials or token"


# --- plain_to_html ---


@patch("src.core.email.sender.get")
def test_plain_to_html_paragraphs(mock_get):
    mock_get.return_value = "fake-key"
    body = "Hello there.\n\nThis is paragraph two.\n\nBest regards."
    result = plain_to_html(body, "Test Cafe", "123 Main St")
    assert "<p>Hello there.</p>" in result
    assert "<p>This is paragraph two.</p>" in result
    assert "<p>Best regards.</p>" in result
    assert "Test Cafe" in result
    assert "123 Main St" in result


@patch("src.core.email.sender.get")
def test_plain_to_html_escapes_html(mock_get):
    mock_get.return_value = ""
    body = "Price is <$5 & we offer 10% off."
    result = plain_to_html(body, "Joe's <Grill>", "456 Oak & Pine")
    assert "&lt;$5" in result
    assert "&amp; we offer" in result
    assert "Joe&#x27;s &lt;Grill&gt;" in result
    assert "Oak &amp; Pine" in result


@patch("src.core.email.sender.get")
def test_plain_to_html_preserves_line_breaks(mock_get):
    mock_get.return_value = "fake-key"
    body = "Line one\nLine two\n\nNew paragraph"
    result = plain_to_html(body, "Cafe", "Addr")
    assert "Line one<br>Line two" in result
    assert "<p>New paragraph</p>" in result


@patch("src.core.email.sender.get")
def test_plain_to_html_with_supplier_website(mock_get):
    mock_get.return_value = "fake-key"
    result = plain_to_html(
        "Hello.",
        "My Restaurant",
        "123 St",
        supplier_website="https://supplier.com",
        supplier_name="Great Supplier",
    )
    assert "https://supplier.com" in result
    assert "Great Supplier" in result
    assert "visited your website" in result


@patch("src.core.email.sender.get")
def test_plain_to_html_with_map(mock_get):
    mock_get.return_value = "fake-google-key"
    result = plain_to_html(
        "Hello.",
        "My Restaurant",
        "123 Main St, Chicago",
        restaurant_lat=41.89,
        restaurant_lng=-87.63,
    )
    assert "maps.googleapis.com/maps/api/staticmap" in result
    assert "google.com/maps/search" in result
    assert "Our Location" in result


@patch("src.core.email.sender.get")
def test_plain_to_html_no_map_without_key(mock_get):
    mock_get.return_value = ""
    result = plain_to_html("Hello.", "Cafe", "123 St")
    assert "staticmap" not in result


def test_build_maps_link():
    link = build_maps_link("59 W Hubbard St, Chicago")
    assert "google.com/maps/search" in link
    assert "59+W+Hubbard" in link


# --- lookup_restaurant_website ---


@patch("src.core.email.sender.get")
@patch("src.core.email.sender.httpx.get")
def test_lookup_restaurant_website_success(mock_http_get, mock_get):
    mock_get.return_value = "fake-google-key"

    find_resp = MagicMock()
    find_resp.json.return_value = {
        "candidates": [{"place_id": "abc123"}],
        "status": "OK",
    }

    details_resp = MagicMock()
    details_resp.json.return_value = {
        "result": {"website": "http://ilporcellinochicago.com/"},
        "status": "OK",
    }

    mock_http_get.side_effect = [find_resp, details_resp]

    result = lookup_restaurant_website("Il Porcellino", "59 W Hubbard St, Chicago")
    assert result == "http://ilporcellinochicago.com/"


@patch("src.core.email.sender.get")
def test_lookup_restaurant_website_no_key(mock_get):
    mock_get.return_value = ""
    result = lookup_restaurant_website("Test", "123 St")
    assert result == ""


@patch("src.core.email.sender.get")
@patch("src.core.email.sender.httpx.get")
def test_lookup_restaurant_website_no_candidates(mock_http_get, mock_get):
    mock_get.return_value = "fake-key"

    find_resp = MagicMock()
    find_resp.json.return_value = {"candidates": [], "status": "ZERO_RESULTS"}
    mock_http_get.return_value = find_resp

    result = lookup_restaurant_website("Nonexistent Place", "000 Nowhere")
    assert result == ""


@patch("src.core.email.sender.get")
def test_plain_to_html_with_restaurant_website(mock_get):
    mock_get.return_value = "fake-key"
    result = plain_to_html(
        "Hello.",
        "My Restaurant",
        "123 St",
        restaurant_website="http://myrestaurant.com",
    )
    assert "http://myrestaurant.com" in result
