"""Gmail API client — authenticate, send, and read emails.

Uses OAuth2 Desktop flow with offline refresh tokens.
Credentials file: backend/gmail_credentials.json
Token file: backend/token.json
"""

import os
import re
import base64

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..")
CREDENTIALS_PATH = os.path.join(BACKEND_DIR, "gmail_credentials.json")
TOKEN_PATH = os.path.join(BACKEND_DIR, "token.json")


def get_gmail_service():
    """Return an authenticated Gmail API service object, or None if not configured.

    Loads credentials from local files first, falls back to env vars
    (GMAIL_CREDENTIALS_JSON, GMAIL_TOKEN_JSON) for deployed environments.
    """
    # Ensure credential files exist — write from env vars if needed
    if not os.path.exists(CREDENTIALS_PATH):
        env_creds = os.environ.get("GMAIL_CREDENTIALS_JSON")
        if env_creds:
            with open(CREDENTIALS_PATH, "w") as f:
                f.write(env_creds)
        else:
            return None

    if not os.path.exists(TOKEN_PATH):
        env_token = os.environ.get("GMAIL_TOKEN_JSON")
        if env_token:
            with open(TOKEN_PATH, "w") as f:
                f.write(env_token)

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
        else:
            return None

    return build("gmail", "v1", credentials=creds)


def get_thread_messages(service, gmail_thread_id: str) -> list[dict]:
    """Fetch all messages in a Gmail thread.

    Returns a list of parsed message dicts with keys:
    gmail_message_id, sender, recipient, subject, body, timestamp_ms
    """
    thread = (
        service.users()
        .threads()
        .get(userId="me", id=gmail_thread_id, format="full")
        .execute()
    )

    results = []
    for msg in thread.get("messages", []):
        parsed = parse_gmail_message(msg)
        if parsed:
            results.append(parsed)
    return results


def parse_gmail_message(msg: dict) -> dict:
    """Parse a raw Gmail API message into a clean dict."""
    headers = {h["name"].lower(): h["value"] for h in msg["payload"]["headers"]}

    body = extract_body(msg["payload"])

    return {
        "gmail_message_id": msg["id"],
        "sender": headers.get("from", ""),
        "recipient": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "body": body,
        "timestamp_ms": int(msg.get("internalDate", 0)),
    }


def extract_body(payload: dict) -> str:
    """Extract plain text body from a Gmail message payload.

    Handles multipart messages — prefers text/plain, falls back to text/html.
    """
    mime_type = payload.get("mimeType", "")

    # Simple single-part message
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return strip_quoted_reply(decode_base64(data))

    # Multipart — recurse into parts
    parts = payload.get("parts", [])
    plain_text = ""
    html_text = ""

    for part in parts:
        part_mime = part.get("mimeType", "")
        if part_mime == "text/plain":
            data = part.get("body", {}).get("data", "")
            if data:
                plain_text = decode_base64(data)
        elif part_mime == "text/html":
            data = part.get("body", {}).get("data", "")
            if data:
                html_text = decode_base64(data)
        elif part_mime.startswith("multipart/"):
            # Nested multipart — recurse
            nested = extract_body(part)
            if nested:
                return nested

    if plain_text:
        return strip_quoted_reply(plain_text)
    if html_text:
        # Rough HTML→text: strip tags
        text = re.sub(r"<[^>]+>", "", html_text)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        return strip_quoted_reply(text.strip())

    return ""


def decode_base64(data: str) -> str:
    """Decode Gmail's URL-safe base64 encoded content."""
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def strip_quoted_reply(text: str) -> str:
    """Remove quoted reply text from an email body.

    Strips everything after common quote markers:
    - "On Mon, Jan 1, 2026 at 10:00 AM ... wrote:"
    - Lines starting with ">"
    - "---------- Forwarded message ----------"
    """
    # Cut at "On ... wrote:" pattern
    match = re.search(r"\nOn .+wrote:\s*$", text, re.MULTILINE)
    if match:
        text = text[: match.start()].rstrip()

    # Cut at forwarded message marker
    match = re.search(r"\n-{5,}\s*Forwarded message\s*-{5,}", text)
    if match:
        text = text[: match.start()].rstrip()

    # Remove lines starting with ">" (inline quotes)
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        if line.startswith(">"):
            break
        cleaned.append(line)

    return "\n".join(cleaned).strip()
