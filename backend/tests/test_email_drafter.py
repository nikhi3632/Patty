from unittest.mock import patch, MagicMock
from src.core.email.drafter import build_trend_summary, draft_email, draft_all_emails


# --- build_trend_summary ---


def test_trend_summary_only_downward():
    trends = [
        {
            "parent": "tomatoes",
            "signal": "strong_down",
            "trend_signals": [
                {"source": "mars", "change_pct": "-12.5", "z_score": "-2.5"},
            ],
        },
        {
            "parent": "cheese",
            "signal": "moderate_up",
            "trend_signals": [
                {"source": "mars", "change_pct": "8.3", "z_score": "1.6"},
                {"source": "nass", "change_pct": "5.1", "z_score": "1.2"},
            ],
        },
    ]
    result = build_trend_summary(trends)
    assert "tomatoes: wholesale prices down 12.5%" in result
    assert "significant move" in result  # z >= 2.0 for tomatoes
    assert "cheese" not in result  # upward trends are omitted


def test_trend_summary_nass_fallback():
    trends = [
        {
            "parent": "wheat",
            "signal": "moderate_down",
            "trend_signals": [
                {"source": "nass", "change_pct": "-7.2", "z_score": "-1.8"},
            ],
        },
    ]
    result = build_trend_summary(trends)
    assert "wheat: commodity prices down 7.2%" in result


def test_trend_summary_empty():
    result = build_trend_summary([])
    assert "monitoring" in result.lower()


def test_trend_summary_upward_only_returns_fallback():
    trends = [
        {
            "parent": "cheese",
            "signal": "moderate_up",
            "trend_signals": [
                {"source": "mars", "change_pct": "8.3", "z_score": "1.6"},
            ],
        },
    ]
    result = build_trend_summary(trends)
    assert "monitoring" in result.lower()


def test_trend_summary_stable_skipped():
    trends = [
        {
            "parent": "garlic",
            "signal": "stable",
            "trend_signals": [
                {"source": "mars", "change_pct": "0.5", "z_score": "0.1"},
                {"source": "nass", "change_pct": "0.2", "z_score": "0.05"},
            ],
        }
    ]
    result = build_trend_summary(trends)
    assert "monitoring" in result.lower()  # stable items are skipped


# --- draft_email ---


@patch("src.core.email.drafter.get")
@patch("src.core.email.drafter.anthropic.Anthropic")
def test_draft_email_success(mock_anthropic_cls, mock_get):
    mock_get.side_effect = lambda k: {
        "ANTHROPIC_API_KEY": "fake",
        "FROM_EMAIL": "test@gmail.com",
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

    mock_links = MagicMock()
    mock_links.data = [
        {"suppliers": {"id": "s1", "name": "A", "email": "a@a.com"}},
        {"suppliers": {"id": "s2", "name": "B", "email": None}},
        {"suppliers": {"id": "s3", "name": "C", "email": "c@c.com"}},
    ]

    mock_delete = MagicMock()
    mock_delete.data = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurant_suppliers":
            mock_t.select.return_value.eq.return_value.execute.return_value = mock_links
        elif table_name == "emails":
            mock_t.delete.return_value.eq.return_value.in_.return_value.execute.return_value = mock_delete
        return mock_t

    mock_sb.table.side_effect = table_router

    result = draft_all_emails(mock_sb, "rest-1")
    assert result["drafted"] == 2
    assert result["skipped"] == 1
    assert "B" in result["skipped_names"]
