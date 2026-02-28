import base64
from unittest.mock import MagicMock, patch

from src.core.menu.parser import (
    build_vision_content,
    normalize_ingredient,
    get_parent_categories,
    get_past_corrections,
    build_corrections_prompt,
    format_parent_list,
    call_vision_llm,
    resolve_commodity_ids,
    store_parse_results,
    parse_menu,
)


# --- Unit tests for build_vision_content ---


def test_build_vision_content_with_image():
    files = [{"data": b"fake png", "file_type": "image/png", "file_name": "menu.png"}]
    content = build_vision_content(files, "Extract ingredients")
    assert len(content) == 2
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"
    assert content[0]["source"]["data"] == base64.standard_b64encode(
        b"fake png"
    ).decode("utf-8")


def test_build_vision_content_with_pdf():
    files = [
        {"data": b"fake pdf", "file_type": "application/pdf", "file_name": "menu.pdf"}
    ]
    content = build_vision_content(files, "Extract ingredients")
    assert content[0]["type"] == "document"
    assert content[0]["source"]["media_type"] == "application/pdf"


def test_build_vision_content_multiple_files():
    files = [
        {"data": b"img1", "file_type": "image/png", "file_name": "page1.png"},
        {"data": b"img2", "file_type": "image/jpeg", "file_name": "page2.jpg"},
        {"data": b"doc", "file_type": "application/pdf", "file_name": "full.pdf"},
    ]
    content = build_vision_content(files, "Extract ingredients")
    assert len(content) == 4
    assert content[0]["type"] == "image"
    assert content[1]["type"] == "image"
    assert content[2]["type"] == "document"
    assert content[3]["type"] == "text"


def test_normalize_ingredient():
    assert normalize_ingredient("  Mozzarella Cheese  ") == "mozzarella cheese"
    assert normalize_ingredient("OLIVE OIL") == "olive oil"
    assert normalize_ingredient("  ") == ""


# --- Unit tests for get_parent_categories ---


def test_get_parent_categories():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(
        data=[
            {"parent": "tomatoes", "aliases": ["tomato"]},
            {"parent": "chicken", "aliases": ["poultry"]},
            {"parent": "tomatoes", "aliases": ["tomato"]},  # duplicate
            {"parent": "apples", "aliases": []},
        ]
    )

    parents = get_parent_categories(mock_client)
    assert len(parents) == 3
    assert parents[0] == {"parent": "apples", "aliases": []}
    assert parents[1] == {"parent": "chicken", "aliases": ["poultry"]}
    assert parents[2] == {"parent": "tomatoes", "aliases": ["tomato"]}


def test_get_parent_categories_empty():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(data=[])

    parents = get_parent_categories(mock_client)
    assert parents == []


# --- Unit tests for format_parent_list ---


def test_format_parent_list_with_aliases():
    entries = [
        {"parent": "cattle", "aliases": ["beef", "steak"]},
        {"parent": "chicken", "aliases": []},
    ]
    result = format_parent_list(entries)
    assert "cattle (beef, steak)" in result
    assert "- chicken\n" in result or result.endswith("- chicken")


def test_format_parent_list_empty():
    assert format_parent_list([]) == ""


# --- Unit tests for past corrections ---


def test_get_past_corrections_returns_user_added():
    mock_client = MagicMock()
    mock_client.table().select().eq().execute.return_value = MagicMock(
        data=[
            {"raw_ingredient_name": "butter", "status": "tracked"},
            {"raw_ingredient_name": "sriracha", "status": "other"},
        ]
    )

    corrections = get_past_corrections(mock_client)
    assert len(corrections) == 1
    assert corrections[0]["name"] == "butter"
    assert corrections[0]["action"] == "added_to_tracked"


def test_get_past_corrections_empty():
    mock_client = MagicMock()
    mock_client.table().select().eq().execute.return_value = MagicMock(data=[])

    corrections = get_past_corrections(mock_client)
    assert corrections == []


def test_build_corrections_prompt_with_data():
    corrections = [
        {"name": "butter", "action": "added_to_tracked"},
        {"name": "kale", "action": "added_to_tracked"},
    ]
    result = build_corrections_prompt(corrections)
    assert "butter" in result
    assert "kale" in result
    assert "previously missed" in result


def test_build_corrections_prompt_empty():
    assert build_corrections_prompt([]) == ""


# --- Unit tests for resolve_commodity_ids ---


def test_resolve_commodity_ids():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(
        data=[
            {
                "id": "aaa",
                "parent": "tomatoes",
                "has_price_data": True,
                "aliases": ["tomato"],
            },
            {
                "id": "bbb",
                "parent": "tomatoes",
                "has_price_data": True,
                "aliases": ["tomato"],
            },
            {
                "id": "ccc",
                "parent": "chicken",
                "has_price_data": False,
                "aliases": ["poultry"],
            },
        ]
    )

    result = resolve_commodity_ids(mock_client, ["tomatoes", "chicken", "unicorn"])
    assert result == {
        "tomatoes": {"id": "aaa", "has_price_data": True},
        "chicken": {"id": "ccc", "has_price_data": False},
    }


def test_resolve_commodity_ids_via_alias():
    """'beef' should resolve to 'cattle' commodity via alias."""
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(
        data=[
            {
                "id": "aaa",
                "parent": "cattle",
                "has_price_data": True,
                "aliases": ["beef", "steak", "veal"],
            },
            {
                "id": "bbb",
                "parent": "sheep",
                "has_price_data": True,
                "aliases": ["lamb", "mutton"],
            },
        ]
    )

    result = resolve_commodity_ids(mock_client, ["beef", "lamb", "unicorn"])
    assert "beef" in result
    assert result["beef"]["id"] == "aaa"
    assert "lamb" in result
    assert result["lamb"]["id"] == "bbb"
    assert "unicorn" not in result


# --- Unit tests for call_vision_llm ---


def test_call_vision_llm_parses_tool_use():
    mock_tool_block = MagicMock()
    mock_tool_block.type = "tool_use"
    mock_tool_block.input = {"tracked": ["tomatoes", "chicken"], "other": ["olive oil"]}

    mock_response = MagicMock()
    mock_response.content = [mock_tool_block]

    with patch("src.core.menu.parser.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )
        result = call_vision_llm(
            [{"data": b"img", "file_type": "image/png", "file_name": "m.png"}],
            [
                {"parent": "tomatoes", "aliases": []},
                {"parent": "chicken", "aliases": ["poultry"]},
                {"parent": "cattle", "aliases": ["beef"]},
            ],
        )

    assert result == {"tracked": ["tomatoes", "chicken"], "other": ["olive oil"]}


def test_call_vision_llm_no_tool_use_returns_empty():
    mock_text_block = MagicMock()
    mock_text_block.type = "text"

    mock_response = MagicMock()
    mock_response.content = [mock_text_block]

    with patch("src.core.menu.parser.anthropic") as mock_anthropic:
        mock_anthropic.Anthropic.return_value.messages.create.return_value = (
            mock_response
        )
        result = call_vision_llm(
            [{"data": b"img", "file_type": "image/png", "file_name": "m.png"}],
            [{"parent": "tomatoes", "aliases": []}],
        )

    assert result == {"tracked": [], "other": []}


# --- Unit tests for store_parse_results ---


def test_store_parse_results_first_upload():
    mock_client = MagicMock()

    commodities_table = MagicMock()
    rc_table = MagicMock()
    parses_table = MagicMock()

    def table_router(name):
        if name == "commodities":
            return commodities_table
        if name == "restaurant_commodities":
            return rc_table
        if name == "menu_parses":
            return parses_table
        return MagicMock()

    mock_client.table.side_effect = table_router

    # resolve_commodity_ids: return commodity IDs + has_price_data
    commodities_table.select.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "aaa", "parent": "tomatoes", "has_price_data": True, "aliases": []},
            {"id": "bbb", "parent": "chicken", "has_price_data": True, "aliases": []},
        ]
    )

    # "other" items: select returns empty (none exist yet)
    rc_table.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[]
    )

    # insert returns 2 rows
    rc_table.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": 1}, {"id": 2}]
    )

    result = store_parse_results(
        mock_client,
        "rest-1",
        ["tomatoes", "chicken"],
        ["olive oil", "truffle"],
        {"tracked": ["tomatoes", "chicken"], "other": ["olive oil", "truffle"]},
    )

    assert result["tracked"] == 2
    assert result["other"] == 2


def test_store_parse_results_classifies_by_price_data():
    """Matched commodity with has_price_data=false → status 'other'."""
    mock_client = MagicMock()

    commodities_table = MagicMock()
    rc_table = MagicMock()
    parses_table = MagicMock()

    def table_router(name):
        if name == "commodities":
            return commodities_table
        if name == "restaurant_commodities":
            return rc_table
        if name == "menu_parses":
            return parses_table
        return MagicMock()

    mock_client.table.side_effect = table_router

    # tomatoes has price data, chicken does not
    commodities_table.select.return_value.execute.return_value = MagicMock(
        data=[
            {"id": "aaa", "parent": "tomatoes", "has_price_data": True, "aliases": []},
            {"id": "bbb", "parent": "chicken", "has_price_data": False, "aliases": []},
        ]
    )

    result = store_parse_results(
        mock_client,
        "rest-1",
        ["tomatoes", "chicken"],
        [],
        {"tracked": ["tomatoes", "chicken"], "other": []},
    )

    # tomatoes → tracked, chicken → other (matched but no data)
    assert result["tracked"] == 1
    assert result["other"] == 1

    # Verify the upsert calls used correct statuses
    upsert_calls = rc_table.upsert.call_args_list
    assert len(upsert_calls) == 2
    assert upsert_calls[0][0][0]["status"] == "tracked"
    assert upsert_calls[1][0][0]["status"] == "other"


def test_store_parse_results_resolves_other_against_registry():
    """'other' items that match registry (directly or via alias) get commodity_id."""
    mock_client = MagicMock()

    commodities_table = MagicMock()
    rc_table = MagicMock()
    parses_table = MagicMock()

    def table_router(name):
        if name == "commodities":
            return commodities_table
        if name == "restaurant_commodities":
            return rc_table
        if name == "menu_parses":
            return parses_table
        return MagicMock()

    mock_client.table.side_effect = table_router

    # Registry: cauliflower (direct), cattle with alias "beef"
    commodities_table.select.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "aaa",
                "parent": "cauliflower",
                "has_price_data": True,
                "aliases": [],
            },
            {
                "id": "bbb",
                "parent": "cattle",
                "has_price_data": True,
                "aliases": ["beef", "steak"],
            },
        ]
    )

    # No existing other items
    rc_table.select.return_value.eq.return_value.eq.return_value.in_.return_value.execute.return_value = MagicMock(
        data=[]
    )
    rc_table.insert.return_value.execute.return_value = MagicMock(data=[{"id": 1}])

    result = store_parse_results(
        mock_client,
        "rest-1",
        [],  # no tracked from LLM
        ["cauliflower", "beef", "saffron"],  # all in "other" from LLM
        {"tracked": [], "other": ["cauliflower", "beef", "saffron"]},
    )

    # cauliflower + beef resolved → tracked (has_price_data=true)
    # saffron unmatched → other
    assert result["tracked"] == 2
    assert result["other"] == 1


def test_store_parse_results_skips_unmatched_parents():
    mock_client = MagicMock()

    # No commodities in DB
    mock_client.table("commodities").select().execute.return_value = MagicMock(data=[])
    mock_client.table(
        "restaurant_commodities"
    ).select().eq().eq().eq().execute.return_value = MagicMock(data=[])

    result = store_parse_results(
        mock_client,
        "rest-1",
        ["unicorn_fruit"],
        [],
        {"tracked": ["unicorn_fruit"], "other": []},
    )

    assert result["tracked"] == 0


def test_store_parse_results_skips_empty_other():
    mock_client = MagicMock()
    mock_client.table("commodities").select().execute.return_value = MagicMock(data=[])

    result = store_parse_results(
        mock_client, "rest-1", [], ["  ", ""], {"tracked": [], "other": ["  ", ""]}
    )

    assert result["other"] == 0


# --- Unit tests for parse_menu ---


def test_parse_menu_empty_commodities():
    mock_client = MagicMock()
    mock_client.table().select().execute.return_value = MagicMock(data=[])

    result = parse_menu(mock_client, "rest-1")
    assert result["tracked"] == 0
    assert result["other"] == 0


def test_parse_menu_no_menu_files():
    mock_client = MagicMock()

    # get_parent_categories returns parents with aliases
    parents_response = MagicMock(data=[{"parent": "tomatoes", "aliases": []}])
    # fetch_menu_files returns empty
    files_response = MagicMock(data=[])

    def table_side_effect(name):
        mock_table = MagicMock()
        if name == "commodities":
            mock_table.select().execute.return_value = parents_response
        elif name == "menu_files":
            mock_table.select().eq().execute.return_value = files_response
        return mock_table

    mock_client.table.side_effect = table_side_effect

    result = parse_menu(mock_client, "rest-1")
    assert result["tracked"] == 0
    assert result["other"] == 0


def test_parse_menu_demotes_unmatched_tracked_to_other():
    """LLM returns a tracked parent not in the registry — should fall to other."""
    mock_client = MagicMock()

    parents_response = MagicMock(
        data=[
            {"parent": "tomatoes", "aliases": []},
            {"parent": "chicken", "aliases": ["poultry"]},
        ]
    )
    files_response = MagicMock(
        data=[
            {
                "storage_path": "menus/r1/food.png",
                "file_type": "image/png",
                "file_name": "food.png",
            }
        ]
    )
    mock_client.storage.from_().download.return_value = b"fake image"

    def table_side_effect(name):
        mock_table = MagicMock()
        if name == "commodities":
            mock_table.select().execute.return_value = parents_response
        elif name == "menu_files":
            mock_table.select().eq().execute.return_value = files_response
        return mock_table

    mock_client.table.side_effect = table_side_effect

    llm_response = {
        "tracked": ["tomatoes", "unicorn_fruit"],
        "other": ["saffron"],
    }

    with patch("src.core.menu.parser.call_vision_llm", return_value=llm_response):
        with patch("src.core.menu.parser.store_parse_results") as mock_store:
            mock_store.return_value = {"tracked": 1, "other": 2}
            parse_menu(mock_client, "rest-1")

            call_args = mock_store.call_args
            # "tomatoes" stays tracked, "unicorn_fruit" demoted to other
            assert call_args[0][2] == ["tomatoes"]
            assert call_args[0][3] == ["saffron", "unicorn_fruit"]
