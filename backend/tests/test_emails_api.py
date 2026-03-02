import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

RESTAURANT_ID = "00000000-0000-0000-0000-000000000001"
EMAIL_ID = "00000000-0000-0000-0000-000000000099"


@patch("src.api.routes.supabase")
def test_list_emails(mock_sb):
    rows = [
        {"id": "e1", "subject": "Pricing Inquiry", "status": "generated"},
        {"id": "e2", "subject": "Follow Up", "status": "sent"},
    ]
    mock_sb.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=rows
    )

    resp = client.get(f"/api/restaurants/{RESTAURANT_ID}/emails")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 2


@patch("src.api.routes.supabase")
def test_list_emails_filtered(mock_sb):
    rows = [{"id": "e1", "subject": "Pricing", "status": "generated"}]
    mock_sb.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.execute.return_value = MagicMock(
        data=rows
    )

    resp = client.get(f"/api/restaurants/{RESTAURANT_ID}/emails?status=generated")
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1


@patch("src.api.routes.supabase")
def test_update_email_subject_and_body(mock_sb):
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": EMAIL_ID,
                "subject": "New Subject",
                "body": "New body",
                "status": "generated",
            }
        ]
    )

    resp = client.patch(
        f"/api/emails/{EMAIL_ID}",
        json={"subject": "New Subject", "body": "New body"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["subject"] == "New Subject"


@patch("src.api.routes.supabase")
def test_update_email_status_to_draft(mock_sb):
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": EMAIL_ID, "status": "draft"}]
    )

    resp = client.patch(f"/api/emails/{EMAIL_ID}", json={"status": "draft"})
    assert resp.status_code == 200


@patch("src.api.routes.supabase")
def test_update_email_bad_status(mock_sb):
    resp = client.patch(f"/api/emails/{EMAIL_ID}", json={"status": "invalid"})
    assert resp.status_code == 400


@patch("src.api.routes.supabase")
def test_update_email_no_fields(mock_sb):
    resp = client.patch(f"/api/emails/{EMAIL_ID}", json={})
    assert resp.status_code == 400


@patch("src.api.routes.supabase")
def test_update_email_not_found(mock_sb):
    mock_sb.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )

    resp = client.patch(f"/api/emails/{EMAIL_ID}", json={"subject": "Test"})
    assert resp.status_code == 404


@patch("src.api.routes.send_email")
def test_send_email_endpoint(mock_send):
    mock_send.return_value = {
        "sent": True,
        "gmail_message_id": "msg-123",
        "gmail_thread_id": "thread-456",
        "thread_id": "t-001",
        "routed_to": "test@test.com",
    }

    resp = client.post(f"/api/emails/{EMAIL_ID}/send")
    assert resp.status_code == 200
    assert resp.json()["data"]["sent"] is True


@patch("src.api.routes.send_email")
def test_send_email_endpoint_error(mock_send):
    mock_send.return_value = {"error": "Already sent"}

    resp = client.post(f"/api/emails/{EMAIL_ID}/send")
    assert resp.status_code == 400


@patch("src.api.routes.supabase")
def test_revert_email(mock_sb):
    mock_email = MagicMock()
    mock_email.data = {
        "subject_original": "Original Subject",
        "body_original": "Original body",
    }

    mock_updated = MagicMock()
    mock_updated.data = [
        {"id": EMAIL_ID, "subject": "Original Subject", "body": "Original body"}
    ]

    call_count = [0]

    def table_router(table_name):
        mock_t = MagicMock()
        if table_name == "emails":
            call_count[0] += 1
            if call_count[0] == 1:
                mock_t.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_email
            else:
                mock_t.update.return_value.eq.return_value.execute.return_value = (
                    mock_updated
                )
        return mock_t

    mock_sb.table.side_effect = table_router

    resp = client.post(f"/api/emails/{EMAIL_ID}/revert")
    assert resp.status_code == 200
    assert resp.json()["data"]["subject"] == "Original Subject"


@patch("src.api.routes.draft_all_emails")
def test_generate_emails(mock_draft):
    mock_draft.return_value = {
        "restaurant_id": RESTAURANT_ID,
        "drafted": 5,
        "skipped": 1,
        "skipped_names": ["No Email Co"],
        "emails": [{"id": "e1"}, {"id": "e2"}],
    }

    resp = client.post(f"/api/restaurants/{RESTAURANT_ID}/emails/generate")
    assert resp.status_code == 200
    assert resp.json()["data"]["drafted"] == 5
