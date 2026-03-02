from unittest.mock import patch, MagicMock
from src.core.email.agent import (
    run_procurement_agent,
    execute_tool,
    tool_get_thread_history,
    tool_get_restaurant_profile,
    tool_get_supplier_profile,
    tool_get_price_data,
)


# --- Tool implementations ---


def test_tool_get_thread_history():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=[
            {"direction": "outbound", "sender": "patty@gmail.com", "body": "Hello"},
            {"direction": "inbound", "sender": "supplier@co.com", "body": "Hi there"},
        ]
    )
    result = tool_get_thread_history(mock_sb, "t1")
    assert len(result["messages"]) == 2
    assert result["messages"][0]["direction"] == "outbound"


def test_tool_get_price_data():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.ilike.return_value.execute.return_value = MagicMock(
        data=[
            {
                "parent": "chicken",
                "signal": "strong_down",
                "trend_signals": [
                    {"source": "mars", "change_pct": "-15.2", "z_score": "-2.8", "market": "Chicago"},
                ],
            }
        ]
    )
    result = tool_get_price_data(mock_sb, "chicken", "r1")
    assert result["trends"][0]["signal"] == "strong_down"
    assert result["trends"][0]["details"][0]["change_pct"] == "-15.2"


def test_tool_get_price_data_no_data():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.ilike.return_value.execute.return_value = MagicMock(
        data=[]
    )
    result = tool_get_price_data(mock_sb, "truffles", "r1")
    assert "No trend data" in result["data"]


def test_tool_get_restaurant_profile():
    mock_sb = MagicMock()

    mock_restaurant = MagicMock()
    mock_restaurant.data = {"name": "Il Porcellino", "address": "59 W Hubbard", "cuisine_type": "Italian"}

    mock_tracked = MagicMock()
    mock_tracked.data = [
        {
            "raw_ingredient_name": "chicken breast",
            "status": "tracked",
            "commodities": {"parent": "chicken", "display_name": "Chicken"},
        }
    ]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "restaurants":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_restaurant
        elif table_name == "restaurant_commodities":
            mock_t.select.return_value.eq.return_value.eq.return_value.is_.return_value.execute.return_value = mock_tracked
        return mock_t

    mock_sb.table.side_effect = table_router

    result = tool_get_restaurant_profile(mock_sb, "r1")
    assert result["restaurant"]["name"] == "Il Porcellino"
    assert result["tracked_ingredients"][0]["commodity"] == "chicken"


def test_tool_get_supplier_profile():
    mock_sb = MagicMock()

    mock_supplier = MagicMock()
    mock_supplier.data = {
        "name": "Fresh Farms",
        "email": "sales@fresh.com",
        "contact_name": "Jane",
        "contact_title": "Sales",
        "phone": "555-1234",
        "website": "https://freshfarms.com",
        "categories": ["produce", "dairy"],
    }

    mock_link = MagicMock()
    mock_link.data = [{"distance_miles": 12.5}]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "suppliers":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_supplier
        elif table_name == "restaurant_suppliers":
            mock_t.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_link
        return mock_t

    mock_sb.table.side_effect = table_router

    result = tool_get_supplier_profile(mock_sb, "s1", "r1")
    assert result["supplier"]["name"] == "Fresh Farms"
    assert result["distance_miles"] == 12.5


def test_execute_tool_unknown():
    result = execute_tool(MagicMock(), "unknown_tool", {})
    assert "Unknown tool" in result["error"]


# --- Agent flow ---


def test_run_agent_thread_not_found():
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
        data=None
    )
    result = run_procurement_agent(mock_sb, "nonexistent")
    assert result["error"] == "Thread not found"


def test_run_agent_no_inbound_message():
    mock_sb = MagicMock()

    mock_thread = MagicMock()
    mock_thread.data = {
        "id": "t1",
        "restaurant_id": "r1",
        "supplier_id": "s1",
        "state": "draft_ready",
        "gmail_thread_id": "gt1",
    }

    mock_no_msgs = MagicMock()
    mock_no_msgs.data = []

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "email_threads":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_thread
        elif table_name == "email_messages":
            mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_no_msgs
        return mock_t

    mock_sb.table.side_effect = table_router

    result = run_procurement_agent(mock_sb, "t1")
    assert result["error"] == "No inbound message to respond to"


@patch("src.core.email.agent.anthropic.Anthropic")
@patch("src.core.email.agent.get")
def test_run_agent_draft_reply(mock_get, mock_anthropic_cls):
    mock_get.return_value = "fake-key"

    # Simulate Claude calling draft_reply directly (no tool gathering first)
    mock_draft_block = MagicMock()
    mock_draft_block.type = "tool_use"
    mock_draft_block.name = "draft_reply"
    mock_draft_block.input = {
        "subject": "Re: Pricing Inquiry",
        "body": "Thank you for your interest. We'd love to discuss pricing.",
        "reasoning": "Supplier expressed interest, moving toward a meeting.",
    }

    mock_response = MagicMock()
    mock_response.content = [mock_draft_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls.return_value = mock_client

    mock_sb = MagicMock()

    mock_thread = MagicMock()
    mock_thread.data = {
        "id": "t1",
        "restaurant_id": "r1",
        "supplier_id": "s1",
        "state": "draft_ready",
        "gmail_thread_id": "gt1",
    }

    mock_inbound = MagicMock()
    mock_inbound.data = [
        {"body": "We can offer competitive pricing.", "sender": "supplier@co.com", "subject": "Re: Inquiry"}
    ]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "email_threads":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_thread
        elif table_name == "email_messages":
            mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_inbound
        return mock_t

    mock_sb.table.side_effect = table_router

    result = run_procurement_agent(mock_sb, "t1")
    assert result["action"] == "draft"
    assert "pricing" in result["body"].lower()
    assert result["reasoning"] != ""


@patch("src.core.email.agent.anthropic.Anthropic")
@patch("src.core.email.agent.get")
def test_run_agent_escalate(mock_get, mock_anthropic_cls):
    mock_get.return_value = "fake-key"

    mock_escalate_block = MagicMock()
    mock_escalate_block.type = "tool_use"
    mock_escalate_block.name = "escalate"
    mock_escalate_block.input = {
        "reason": "Supplier sent a contract with pricing terms that require owner review.",
    }

    mock_response = MagicMock()
    mock_response.content = [mock_escalate_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls.return_value = mock_client

    mock_sb = MagicMock()

    mock_thread = MagicMock()
    mock_thread.data = {
        "id": "t1",
        "restaurant_id": "r1",
        "supplier_id": "s1",
        "state": "draft_ready",
        "gmail_thread_id": "gt1",
    }

    mock_inbound = MagicMock()
    mock_inbound.data = [
        {"body": "Please sign the attached agreement.", "sender": "supplier@co.com", "subject": "Contract"}
    ]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "email_threads":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_thread
        elif table_name == "email_messages":
            mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_inbound
        return mock_t

    mock_sb.table.side_effect = table_router

    result = run_procurement_agent(mock_sb, "t1")
    assert result["action"] == "escalate"
    assert "contract" in result["reason"].lower()


@patch("src.core.email.agent.anthropic.Anthropic")
@patch("src.core.email.agent.get")
def test_run_agent_tool_use_loop(mock_get, mock_anthropic_cls):
    """Test that the agent calls tools, gets results, then drafts a reply."""
    mock_get.return_value = "fake-key"

    # First call: agent requests thread history
    mock_tool_call = MagicMock()
    mock_tool_call.type = "tool_use"
    mock_tool_call.name = "get_thread_history"
    mock_tool_call.id = "tool-1"
    mock_tool_call.input = {"thread_id": "t1"}

    mock_response_1 = MagicMock()
    mock_response_1.content = [mock_tool_call]

    # Second call: agent drafts reply after getting tool results
    mock_draft_block = MagicMock()
    mock_draft_block.type = "tool_use"
    mock_draft_block.name = "draft_reply"
    mock_draft_block.input = {
        "subject": "Re: Pricing",
        "body": "Based on our conversation, we'd like to schedule a call.",
        "reasoning": "Supplier is interested, time to move to a call.",
    }

    mock_response_2 = MagicMock()
    mock_response_2.content = [mock_draft_block]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]
    mock_anthropic_cls.return_value = mock_client

    mock_sb = MagicMock()

    mock_thread = MagicMock()
    mock_thread.data = {
        "id": "t1",
        "restaurant_id": "r1",
        "supplier_id": "s1",
        "state": "draft_ready",
        "gmail_thread_id": "gt1",
    }

    mock_inbound = MagicMock()
    mock_inbound.data = [
        {"body": "Sounds great, what quantities?", "sender": "supplier@co.com", "subject": "Re: Inquiry"}
    ]

    mock_history = MagicMock()
    mock_history.data = [
        {"direction": "outbound", "sender": "patty@gmail.com", "body": "Hello"},
        {"direction": "inbound", "sender": "supplier@co.com", "body": "Sounds great"},
    ]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "email_threads":
            mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_thread
        elif table_name == "email_messages":
            # First call: get latest inbound (for the prompt)
            # Second call: get thread history (tool)
            mock_t.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_inbound
            mock_t.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_history
        return mock_t

    mock_sb.table.side_effect = table_router

    result = run_procurement_agent(mock_sb, "t1")
    assert result["action"] == "draft"
    assert "call" in result["body"].lower()

    # Verify Claude was called twice (tool call + draft)
    assert mock_client.messages.create.call_count == 2
