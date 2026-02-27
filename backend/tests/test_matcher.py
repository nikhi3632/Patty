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


def test_add_ingredient_matched():
    mock_client = MagicMock()

    # match_ingredient returns a match
    match_result = {
        "matched_parent": "cheese",
        "commodity_id": "aaa",
        "confidence": "high",
        "reasoning": "Mozzarella is cheese",
    }

    # No existing tracked item
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(data=[])
    # Insert returns a row
    mock_client.table().insert().execute.return_value = MagicMock(
        data=[{"id": "new-row", "status": "tracked"}]
    )

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "mozzarella")

    assert result["status"] == "tracked"
    assert result["match"]["matched_parent"] == "cheese"


def test_add_ingredient_no_match_goes_to_other():
    mock_client = MagicMock()

    match_result = {
        "matched_parent": None,
        "commodity_id": None,
        "confidence": "low",
        "reasoning": "No match",
    }

    mock_client.table().select().eq().eq().eq().execute.return_value = MagicMock(
        data=[]
    )
    mock_client.table().insert().execute.return_value = MagicMock(
        data=[{"id": "new-row", "status": "other"}]
    )

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "sriracha")

    assert result["status"] == "other"


def test_add_ingredient_already_tracked():
    mock_client = MagicMock()

    match_result = {
        "matched_parent": "cheese",
        "commodity_id": "aaa",
        "confidence": "high",
        "reasoning": "Match",
    }

    # Already exists
    mock_client.table().select().eq().eq().execute.return_value = MagicMock(
        data=[{"id": "existing"}]
    )

    with patch("src.core.menu.matcher.match_ingredient", return_value=match_result):
        result = add_ingredient(mock_client, "rest-1", "parmesan")

    assert result["status"] == "already_tracked"
