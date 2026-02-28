from unittest.mock import MagicMock, patch

from src.core.menu.matcher import match_ingredient, add_ingredient


# --- Unit tests for match_ingredient ---


def test_match_ingredient_finds_match():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(
        data=[
            {"id": "aaa", "parent": "cheese"},
            {"id": "bbb", "parent": "spinach"},
            {"id": "ccc", "parent": "tomatoes"},
        ]
    )

    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {
        "matched_parent": "cheese",
        "confidence": "high",
        "reasoning": "Mozzarella is a type of cheese",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]

    with patch("src.core.menu.matcher.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )
        result = match_ingredient(mock_client, "mozzarella")

    assert result["matched_parent"] == "cheese"
    assert result["commodity_id"] == "aaa"
    assert result["confidence"] == "high"


def test_match_ingredient_no_match():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(
        data=[{"id": "aaa", "parent": "cheese"}]
    )

    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {
        "matched_parent": None,
        "confidence": "low",
        "reasoning": "Sriracha is a hot sauce, no matching category",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]

    with patch("src.core.menu.matcher.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )
        result = match_ingredient(mock_client, "sriracha")

    assert result["matched_parent"] is None
    assert result["commodity_id"] is None


def test_match_ingredient_empty_registry():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(data=[])

    result = match_ingredient(mock_client, "anything")

    assert result["matched_parent"] is None
    assert result["commodity_id"] is None
    assert result["reasoning"] == "No commodities in registry"


def test_match_ingredient_llm_returns_nonexistent_parent():
    """LLM returns a parent name that doesn't exist in registry."""
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(
        data=[{"id": "aaa", "parent": "cheese"}]
    )

    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {
        "matched_parent": "dairy",
        "confidence": "medium",
        "reasoning": "Closest match",
    }
    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]

    with patch("src.core.menu.matcher.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )
        result = match_ingredient(mock_client, "yogurt")

    # "dairy" not in registry, so commodity_id is None
    assert result["matched_parent"] == "dairy"
    assert result["commodity_id"] is None


# --- Unit tests for add_ingredient ---


def make_add_client(
    commodity_data=None, rc_data=None, insert_data=None, update_data=None
):
    """Build a mock supabase client with table routing for add_ingredient tests."""
    mock_client = MagicMock()

    commodities_table = MagicMock()
    rc_table = MagicMock()

    def table_router(name):
        if name == "commodities":
            return commodities_table
        if name == "restaurant_commodities":
            return rc_table
        return MagicMock()

    mock_client.table.side_effect = table_router

    # commodities.select("has_price_data").eq("id", ...).single().execute()
    if commodity_data is not None:
        commodities_table.select.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=commodity_data
        )

    # restaurant_commodities.select("id, status").eq("restaurant_id", ...).eq("commodity_id", ...).execute()
    if rc_data is not None:
        rc_table.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=rc_data
        )

    # For "other" path: .select().eq().eq().eq().execute()
    rc_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=rc_data or []
    )

    if insert_data is not None:
        rc_table.insert.return_value.execute.return_value = MagicMock(data=insert_data)

    if update_data is not None:
        rc_table.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=update_data
        )

    return mock_client


def test_add_ingredient_matched_with_price_data():
    mock_client = make_add_client(
        commodity_data={"has_price_data": True},
        rc_data=[],
        insert_data=[{"id": "new-row", "status": "tracked"}],
    )

    match_result = {
        "matched_parent": "cheese",
        "commodity_id": "aaa",
        "confidence": "high",
        "reasoning": "Mozzarella is cheese",
    }

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "mozzarella")

    assert result["status"] == "tracked"
    assert result["match"]["matched_parent"] == "cheese"


def test_add_ingredient_matched_without_price_data():
    mock_client = make_add_client(
        commodity_data={"has_price_data": False},
        rc_data=[],
        insert_data=[{"id": "new-row", "status": "other"}],
    )

    match_result = {
        "matched_parent": "chicken",
        "commodity_id": "bbb",
        "confidence": "high",
        "reasoning": "Match",
    }

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "chicken breast")

    assert result["status"] == "other"


def test_add_ingredient_no_match_goes_to_other():
    mock_client = make_add_client(
        rc_data=[],
        insert_data=[{"id": "new-row", "status": "other"}],
    )

    match_result = {
        "matched_parent": None,
        "commodity_id": None,
        "confidence": "low",
        "reasoning": "No match",
    }

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "sriracha")

    assert result["status"] == "other"


def test_add_ingredient_already_tracked():
    mock_client = make_add_client(
        commodity_data={"has_price_data": True},
        rc_data=[{"id": "existing", "status": "tracked"}],
    )

    match_result = {
        "matched_parent": "cheese",
        "commodity_id": "aaa",
        "confidence": "high",
        "reasoning": "Match",
    }

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "parmesan")

    assert result["status"] == "already_tracked"


def test_add_ingredient_promotes_from_other_to_tracked():
    mock_client = make_add_client(
        commodity_data={"has_price_data": True},
        rc_data=[{"id": "existing", "status": "other"}],
        update_data=[{"id": "existing", "status": "tracked"}],
    )

    match_result = {
        "matched_parent": "arugula",
        "commodity_id": "ccc",
        "confidence": "high",
        "reasoning": "Match",
    }

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "baby arugula")

    assert result["status"] == "tracked"
    assert result["promoted"] is True
