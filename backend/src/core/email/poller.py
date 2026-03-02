"""Poll Gmail for inbound replies to tracked email threads.

Checks all threads in 'waiting_reply' state, fetches new messages,
stores inbound replies, and updates thread state to 'draft_ready'.
"""

import sys
import os
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from src.core.email.gmail_client import get_gmail_service, get_thread_messages

logger = logging.getLogger(__name__)

FOLLOWUP_DAYS = 3
MAX_FOLLOWUPS = 2


def poll_inbox(supabase_client) -> dict:
    """Check for new inbound replies across all active threads.

    Returns a summary of what was found and processed.
    """
    service = get_gmail_service()
    if not service:
        return {"error": "Gmail API not configured"}

    # Get all threads that might receive replies (including closed — for re-open)
    threads = (
        supabase_client.table("email_threads")
        .select("id, gmail_thread_id, restaurant_id, supplier_id, state")
        .not_.is_("gmail_thread_id", "null")
        .execute()
    )

    if not threads.data:
        return {"checked": 0, "new_replies": 0, "updated_thread_ids": []}

    new_replies = 0
    updated_thread_ids = []
    reopened_thread_ids = []

    for thread in threads.data:
        gmail_thread_id = thread.get("gmail_thread_id")
        if not gmail_thread_id:
            continue

        try:
            found = check_thread_for_replies(
                service, supabase_client, thread["id"], gmail_thread_id, thread["state"]
            )
            new_replies += found
            if found > 0:
                updated_thread_ids.append(thread["id"])
                if thread["state"] == "closed":
                    reopened_thread_ids.append(thread["id"])
        except Exception as exc:
            logger.warning("Failed to check thread %s: %s", thread["id"], exc)

    return {
        "checked": len(threads.data),
        "new_replies": new_replies,
        "updated_thread_ids": updated_thread_ids,
        "reopened_thread_ids": reopened_thread_ids,
    }


def check_thread_for_replies(
    service, supabase_client, thread_id: str, gmail_thread_id: str, thread_state: str
) -> int:
    """Check a single thread for new inbound messages.

    Returns the number of new inbound messages found.
    Re-opens closed threads if a new reply arrives.
    """
    # Get all messages in this Gmail thread
    messages = get_thread_messages(service, gmail_thread_id)

    # Get message IDs we've already stored
    existing = (
        supabase_client.table("email_messages")
        .select("gmail_message_id")
        .eq("thread_id", thread_id)
        .execute()
    )
    seen_ids = {row["gmail_message_id"] for row in existing.data}

    # Find the authenticated user's email to distinguish inbound vs outbound
    profile = service.users().getProfile(userId="me").execute()
    our_email = profile.get("emailAddress", "").lower()

    new_inbound = 0

    for msg in messages:
        if msg["gmail_message_id"] in seen_ids:
            continue

        sender_email = extract_email_address(msg["sender"]).lower()
        is_inbound = sender_email != our_email

        supabase_client.table("email_messages").insert(
            {
                "thread_id": thread_id,
                "direction": "inbound" if is_inbound else "outbound",
                "gmail_message_id": msg["gmail_message_id"],
                "sender": msg["sender"],
                "recipient": msg["recipient"],
                "subject": msg["subject"],
                "body": msg["body"],
            }
        ).execute()

        if is_inbound:
            new_inbound += 1

    # If we found inbound replies, update thread state
    if new_inbound > 0:
        supabase_client.table("email_threads").update({"state": "draft_ready"}).eq(
            "id", thread_id
        ).execute()

        if thread_state == "closed":
            logger.info("Re-opened closed thread %s after new reply", thread_id)

    return new_inbound


def check_followups(supabase_client) -> dict:
    """Find threads waiting for a reply longer than FOLLOWUP_DAYS.

    Returns {"nudge": [...], "close": [...]} — thread IDs that need
    a follow-up nudge vs ones that should be auto-closed (exceeded MAX_FOLLOWUPS).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=FOLLOWUP_DAYS)).isoformat()

    stale = (
        supabase_client.table("email_threads")
        .select("id, updated_at")
        .in_("state", ["waiting_reply", "outreach_sent"])
        .lt("updated_at", cutoff)
        .execute()
    )

    nudge_ids = []
    close_ids = []

    for thread in stale.data:
        # Count outbound messages after the last inbound (= follow-up count)
        messages = (
            supabase_client.table("email_messages")
            .select("direction, created_at")
            .eq("thread_id", thread["id"])
            .order("created_at", desc=True)
            .execute()
        )
        followups = 0
        for msg in messages.data:
            if msg["direction"] == "inbound":
                break
            if msg["direction"] == "outbound":
                followups += 1

        if followups >= MAX_FOLLOWUPS:
            now = datetime.now(timezone.utc).isoformat()
            supabase_client.table("email_threads").update(
                {
                    "state": "closed",
                    "closed_reason": f"No reply after {followups} follow-ups",
                    "closed_outcome": "no_response",
                    "updated_at": now,
                }
            ).eq("id", thread["id"]).execute()
            close_ids.append(thread["id"])
            logger.info(
                "Auto-closed thread %s after %d follow-ups", thread["id"], followups
            )
        else:
            supabase_client.table("email_threads").update({"state": "draft_ready"}).eq(
                "id", thread["id"]
            ).execute()
            nudge_ids.append(thread["id"])
            logger.info(
                "Follow-up needed for thread %s (last updated %s, followups=%d)",
                thread["id"],
                thread["updated_at"],
                followups,
            )

    return {"nudge": nudge_ids, "close": close_ids}


def extract_email_address(from_header: str) -> str:
    """Extract the bare email from a From header like 'John Doe <john@example.com>'."""
    if "<" in from_header and ">" in from_header:
        return from_header.split("<")[1].split(">")[0]
    return from_header.strip()
