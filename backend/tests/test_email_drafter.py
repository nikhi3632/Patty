from unittest.mock import patch, MagicMock
from src.core.email.drafter import build_trend_summary, draft_email, draft_all_emails


# --- build_trend_summary ---


def test_trend_summary_with_mars_data():
    trends = [
        {
            "parent": "tomatoes",
            "signal": "strong_down",
            "mars_change_pct": "-12.5",
            "nass_change_pct": None,
        },
        {
            "parent": "cheese",
            "signal": "moderate_up",
            "mars_change_pct": "8.3",
            "nass_change_pct": "5.1",
        },
    ]
    result = build_trend_summary(trends)
    assert "tomatoes: wholesale prices down 12.5%" in result
    assert "cheese: wholesale prices up 8.3%" in result


def test_trend_summary_nass_fallback():
    trends = [
        {
            "parent": "wheat",
            "signal": "moderate_down",
            "mars_change_pct": None,
            "nass_change_pct": "-7.2",
        },
    ]
    result = build_trend_summary(trends)
    assert "wheat: commodity prices down 7.2%" in result


def test_trend_summary_empty():
    result = build_trend_summary([])
    assert "monitoring" in result.lower()


def test_trend_summary_no_pct():
    trends = [
        {
            "parent": "garlic",
            "signal": "stable",
            "mars_change_pct": None,
            "nass_change_pct": None,
        }
    ]
    result = build_trend_summary(trends)
    assert "monitoring" in result.lower()


# --- draft_email ---


@patch("src.core.email.drafter.get")
@patch("src.core.email.drafter.anthropic.Anthropic")
def test_draft_email_success(mock_anthropic_cls, mock_get):
    mock_get.side_effect = lambda k: {
        "ANTHROPIC_API_KEY": "fake",
        "FROM_EMAIL": "test@resend.dev",
    }.get(k, "")

    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {
        "subject": "Partnership Inquiry — Il Porcellino",
        "body": "Dear Sales Team,\n\nWe are reaching out...",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls.return_value = mock_client

    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {
        "name": "Il Porcellino",
        "address": "59 W Hubbard St, Chicago",
    }

    mock_supplier = MagicMock()
    mock_supplier.data = {
        "name": "Smart Foods",
        "email": "sales@smart.com",
        "contact_name": "Jane",
        "contact_title": "Sales",
        "categories": ["produce"],
    }

    mock_trends = MagicMock()
    mock_trends.data = []

    mock_insert = MagicMock()
    mock_insert.data = [
        {"id": "email-1", "subject": "Partnership Inquiry", "status": "generated"}
    ]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_supplier
        elif table_name == "trends":
            mock_t.select.return_value.eq.return_value.execute.return_value = (
                mock_trends
            )
        elif table_name == "emails":
            mock_t.insert.return_value.execute.return_value = mock_insert
        return mock_t

    mock_sb.table.side_effect = table_router

    result = draft_email(mock_sb, "rest-1", "supp-1")
    assert "email" in result
    assert result["email"]["status"] == "generated"


def test_draft_email_no_supplier_email():
    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {"name": "Test", "address": "123 St"}

    mock_supplier = MagicMock()
    mock_supplier.data = {"name": "No Email Co", "email": None, "categories": []}

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_supplier
        return mock_t

    mock_sb.table.side_effect = table_router

    result = draft_email(mock_sb, "rest-1", "supp-1")
    assert result["error"] == "Supplier has no email address"


# --- draft_all_emails ---


@patch("src.core.email.drafter.draft_email")
def test_draft_all_emails(mock_draft):
    mock_draft.return_value = {"email": {"id": "e1", "status": "generated"}}

    mock_sb = MagicMock()

    mock_suppliers = MagicMock()
    mock_suppliers.data = [
        {"id": "s1", "name": "A", "email": "a@a.com"},
        {"id": "s2", "name": "B", "email": None},
        {"id": "s3", "name": "C", "email": "c@c.com"},
    ]

    mock_delete = MagicMock()
    mock_delete.data = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_suppliers
        elif table_name == "emails":
            mock_t.delete.return_value.eq.return_value.in_.return_value.execute.return_value = mock_delete
        return mock_t

    mock_sb.table.side_effect = table_router

    result = draft_all_emails(mock_sb, "rest-1")
    assert result["drafted"] == 2
    assert result["skipped"] == 1
    assert "B" in result["skipped_names"]
