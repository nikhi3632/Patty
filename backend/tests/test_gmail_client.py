from src.core.email.gmail_client import (
    extract_body,
    strip_quoted_reply,
    decode_base64,
    parse_gmail_message,
)
import base64


def encode(text):
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_body_plain_text():
    payload = {
        "mimeType": "text/plain",
        "body": {"data": encode("Hello from supplier")},
    }
    assert extract_body(payload) == "Hello from supplier"


def test_extract_body_multipart():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": encode("Plain text body")},
            },
            {
                "mimeType": "text/html",
                "body": {"data": encode("<p>HTML body</p>")},
            },
        ],
    }
    assert extract_body(payload) == "Plain text body"


def test_extract_body_html_fallback():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/html",
                "body": {"data": encode("<p>Only HTML</p>")},
            },
        ],
    }
    assert "Only HTML" in extract_body(payload)


def test_extract_body_nested_multipart():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/plain",
                        "body": {"data": encode("Nested plain")},
                    },
                ],
            },
        ],
    }
    assert extract_body(payload) == "Nested plain"


def test_strip_quoted_reply_on_wrote():
    text = "Thanks for reaching out!\n\nOn Mon, Jan 1, 2026 at 10:00 AM John wrote:"
    assert strip_quoted_reply(text) == "Thanks for reaching out!"


def test_strip_quoted_reply_angle_brackets():
    text = "Sounds good.\n> Previous message\n> More quoted text"
    assert strip_quoted_reply(text) == "Sounds good."


def test_strip_quoted_reply_forwarded():
    text = "FYI\n---------- Forwarded message ----------\nOriginal content"
    assert strip_quoted_reply(text) == "FYI"


def test_strip_quoted_reply_no_quotes():
    text = "Just a clean reply with no quotes."
    assert strip_quoted_reply(text) == "Just a clean reply with no quotes."


def test_decode_base64():
    encoded = base64.urlsafe_b64encode(b"Hello world").decode()
    assert decode_base64(encoded) == "Hello world"


def test_parse_gmail_message():
    msg = {
        "id": "msg-123",
        "internalDate": "1709000000000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "supplier@example.com"},
                {"name": "To", "value": "patty@gmail.com"},
                {"name": "Subject", "value": "Re: Pricing Inquiry"},
            ],
            "body": {"data": encode("We can offer $2.10/lb")},
        },
    }
    parsed = parse_gmail_message(msg)
    assert parsed["gmail_message_id"] == "msg-123"
    assert parsed["sender"] == "supplier@example.com"
    assert parsed["recipient"] == "patty@gmail.com"
    assert parsed["subject"] == "Re: Pricing Inquiry"
    assert "2.10/lb" in parsed["body"]
