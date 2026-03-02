"""Create notifications for email thread events."""

import logging

logger = logging.getLogger(__name__)


def notify(
    supabase_client,
    restaurant_id: str,
    thread_id: str,
    type: str,
    title: str,
    body: str | None = None,
):
    """Insert a notification row."""
    supabase_client.table("notifications").insert(
        {
            "restaurant_id": restaurant_id,
            "thread_id": thread_id,
            "type": type,
            "title": title,
            "body": body,
        }
    ).execute()
    logger.info("Notification: %s — %s", type, title)
