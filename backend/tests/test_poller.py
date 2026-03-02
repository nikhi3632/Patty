from unittest.mock import patch, MagicMock
from src.core.email.poller import (
    poll_inbox,
    check_thread_for_replies,
    extract_email_address,
)


@patch("src.core.email.poller.get_gmail_service")
def test_poll_inbox_no_service(mock_service):
    mock_service.return_value = None
    result = poll_inbox(MagicMock())
    assert result["error"] == "Gmail API not configured"


@patch("src.core.email.poller.get_gmail_service")
def test_poll_inbox_no_threads(mock_service):
    mock_service.return_value = MagicMock()
    mock_sb = MagicMock()
    mock_sb.table.return_value.select.return_value.not_.is_.return_value.execute.return_value = MagicMock(
        data=[]
    )
    result = poll_inbox(mock_sb)
    assert result["checked"] == 0
    assert result["new_replies"] == 0


@patch("src.core.email.poller.get_thread_messages")
def test_check_thread_new_inbound(mock_get_msgs):
    mock_get_msgs.return_value = [
        {
            "gmail_message_id": "msg-outbound",
            "sender": "patty@gmail.com",
            "recipient": "supplier@example.com",
            "subject": "Pricing Inquiry",
            "body": "Hello...",
            "timestamp_ms": 1000,
        },
        {
            "gmail_message_id": "msg-inbound",
            "sender": "supplier@example.com",
            "recipient": "patty@gmail.com",
            "subject": "Re: Pricing Inquiry",
            "body": "Yes, we can help.",
            "timestamp_ms": 2000,
        },
    ]

    mock_service = MagicMock()
    mock_service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "patty@gmail.com"
    }

    mock_sb = MagicMock()

    # Already stored the outbound message
    mock_existing = MagicMock()
    mock_existing.data = [{"gmail_message_id": "msg-outbound"}]
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_existing

    mock_insert = MagicMock()
    mock_insert.data = [{"id": "new-msg-id"}]
    mock_sb.table.return_value.insert.return_value.execute.return_value = mock_insert

    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "t1", "state": "draft_ready"}]
    )

    found = check_thread_for_replies(
        mock_service, mock_sb, "t1", "gmail-thread-1", "waiting_reply"
    )
    assert found == 1


@patch("src.core.email.poller.get_thread_messages")
def test_check_thread_no_new_messages(mock_get_msgs):
    mock_get_msgs.return_value = [
        {
            "gmail_message_id": "msg-outbound",
            "sender": "patty@gmail.com",
            "recipient": "supplier@example.com",
            "subject": "Pricing Inquiry",
            "body": "Hello...",
            "timestamp_ms": 1000,
        },
    ]

    mock_service = MagicMock()
    mock_service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "patty@gmail.com"
    }

    mock_sb = MagicMock()
    mock_existing = MagicMock()
    mock_existing.data = [{"gmail_message_id": "msg-outbound"}]
    mock_sb.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_existing

    found = check_thread_for_replies(
        mock_service, mock_sb, "t1", "gmail-thread-1", "waiting_reply"
    )
    assert found == 0


def test_extract_email_address_with_name():
    assert extract_email_address("John Doe <john@example.com>") == "john@example.com"


def test_extract_email_address_bare():
    assert extract_email_address("john@example.com") == "john@example.com"
