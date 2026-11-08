"""Duration-aware bookings, operator approvals, retention and inbound throttling."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.orm import Session

from whatsapp_ai_agent.database import make_engine
from whatsapp_ai_agent.models import Message, utcnow


def send(client, contact, message):
    response = client.post("/demo/message", json={
        "contact": contact, "message": message, "message_id": uuid.uuid4().hex,
    })
    assert response.status_code == 200, response.text
    return response.json()


def next_weekday():
    day = datetime.utcnow().date() + timedelta(days=2)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.isoformat()


def test_duration_blocks_overlapping_bookings(client):
    day = next_weekday()
    assert "Reply CONFIRM" in send(client, "one", "book styling " + day + " 10:00")["reply"]
    assert "confirmed" in send(client, "one", "CONFIRM")["reply"]
    assert "unavailable" in send(client, "two", "book consultation " + day + " 10:30")["reply"]
    assert "Reply CONFIRM" in send(client, "three", "book consultation " + day + " 11:00")["reply"]
    assert "unavailable" in send(client, "four", "book styling " + day + " 16:30")["reply"].lower()


def test_available_slots_reflect_existing_bookings(client):
    day = next_weekday()
    send(client, "one", "book styling " + day + " 10:00")
    send(client, "one", "CONFIRM")
    answer = send(client, "two", "availability " + day)
    slots = answer["tools"][0]["result"]["available_slots"]
    assert day + " 10:00" not in slots
    assert day + " 10:30" not in slots
    assert day + " 11:00" in slots


def test_cancel_requires_human_approval_and_cannot_reuse_token(client):
    day = next_weekday()
    send(client, "owner", "book styling " + day + " 10:00")
    send(client, "owner", "CONFIRM")
    headers = {"x-admin-api-key": "unit-test-admin-secret"}
    appointment = client.get("/admin/appointments", headers=headers).json()["appointments"][0]
    path = "/admin/appointments/" + str(appointment["id"])
    assert client.post(path + "/cancel", headers=headers).status_code == 403
    token = client.post(path + "/cancellation-approval", headers=headers).json()["approval_token"]
    assert client.post(path + "/cancel", headers={
        **headers, "x-approval-token": "bad-token"
    }).status_code == 403
    assert client.post(path + "/cancel", headers={
        **headers, "x-approval-token": token
    }).json()["cancelled"] is True
    assert client.post(path + "/cancel", headers={
        **headers, "x-approval-token": token
    }).status_code == 404
    assert "Reply CONFIRM" in send(client, "new", "book consultation " + day + " 10:00")["reply"]
    assert "confirmed" in send(client, "new", "CONFIRM")["reply"]


def test_rate_limit_blocks_excess_and_allows_handoff(client):
    for _ in range(10):
        assert send(client, "visitor", "hours")["reply"]
    assert send(client, "visitor", "hours")["reply"] is None
    assert "paused" in send(client, "visitor", "HUMAN")["reply"]


def test_purge_history_requires_admin_and_respects_retention(client, settings):
    send(client, "one", "hours")
    engine = make_engine(settings.database_url)
    with Session(engine) as session:
        session.execute(update(Message).values(created_at=utcnow() - timedelta(days=45)))
        session.commit()
    assert client.post("/admin/purge-history").status_code == 403
    result = client.post("/admin/purge-history", headers={
        "x-admin-api-key": "unit-test-admin-secret"
    }).json()
    assert result["purged_messages"] == 2
    assert result["retention_days"] == 30
    assert client.get("/demo/history", params={"contact": "one"}).json()["messages"] == []
