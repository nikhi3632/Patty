import base64

from src.core.menu.parser import (
    build_vision_content,
    normalize_ingredient,
)


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
