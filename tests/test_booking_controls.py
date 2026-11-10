"""Duration-aware bookings, operator approvals, retention and inbound throttling."""

import asyncio
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from whatsapp_ai_agent.agent import Agent
from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.database import make_engine, make_session_factory
from whatsapp_ai_agent.models import Message, ToolExecution, utcnow


def send(client, contact, message):
    response = client.post(
        "/demo/message",
        json={
            "contact": contact,
            "message": message,
            "message_id": uuid.uuid4().hex,
        },
    )
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
    assert (
        client.post(
            path + "/cancel", headers={**headers, "x-approval-token": "bad-token"}
        ).status_code
        == 403
    )
    assert (
        client.post(path + "/cancel", headers={**headers, "x-approval-token": token}).json()[
            "cancelled"
        ]
        is True
    )
    assert (
        client.post(path + "/cancel", headers={**headers, "x-approval-token": token}).status_code
        == 404
    )
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
    result = client.post(
        "/admin/purge-history", headers={"x-admin-api-key": "unit-test-admin-secret"}
    ).json()
    assert result["purged_messages"] == 2
    assert result["retention_days"] == 30
    assert client.get("/demo/history", params={"contact": "one"}).json()["messages"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("interruption", ["STOP", "HUMAN"])
async def test_llm_reply_is_suppressed_after_interruption(client, settings, interruption):
    # An existing conversation permits STOP/HUMAN to commit during the provider await.
    send(client, "operator-test", "services")
    llm_settings = Settings(
        _env_file=None,
        database_url=settings.database_url,
        admin_api_key=settings.admin_api_key,
        llm_provider="openai-compatible",
        llm_api_key="mock-only",
        llm_model="mock-only",
    )
    started = asyncio.Event()
    resume = asyncio.Event()
    captured = []

    class PausedProvider(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            captured.append(json.loads(request.content))
            started.set()
            await asyncio.wait_for(resume.wait(), timeout=5)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "tool_calls": [
                                    {
                                        "type": "function",
                                        "function": {
                                            "name": "get_business_hours",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            )

    factory = make_session_factory(make_engine(settings.database_url))
    with factory() as slow_session:
        future = asyncio.create_task(
            Agent(llm_settings).process(
                slow_session,
                "operator-test",
                "What are your hours today?",
                "slow-llm-" + interruption,
                llm_transport=PausedProvider(),
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        with factory() as control_session:
            control = await Agent(settings).process(
                control_session,
                "operator-test",
                interruption,
                "control-" + interruption,
            )
        assert control["state"] in {"opted_out", "human"}
        resume.set()
        result = await asyncio.wait_for(future, timeout=5)
        assert result["reply"] is None
        assert result["tools"] == []

    assert captured[0]["messages"][-1]["content"] == "What are your hours today?"
    history = client.get("/demo/history", params={"contact": "operator-test"}).json()
    assert not any(
        message["direction"] == "out" and "09:00" in message["body"]
        for message in history["messages"]
    )
    assert not any(tool["name"] == "get_business_hours" for tool in history["tools"])


def test_concurrent_cancellation_cannot_reuse_approval(client, settings):
    day = next_weekday()
    send(client, "owner", "book consultation " + day + " 10:00")
    send(client, "owner", "CONFIRM")
    headers = {"x-admin-api-key": "unit-test-admin-secret"}
    appointment = client.get("/admin/appointments", headers=headers).json()["appointments"][0]
    path = "/admin/appointments/" + str(appointment["id"])
    token = client.post(path + "/cancellation-approval", headers=headers).json()["approval_token"]
    barrier = Barrier(2)

    def cancel():
        barrier.wait(timeout=5)
        return client.post(path + "/cancel", headers={**headers, "x-approval-token": token})

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(cancel)
        right = pool.submit(cancel)
        responses = [left.result(timeout=10), right.result(timeout=10)]

    statuses = sorted(response.status_code for response in responses)
    assert statuses in ([200, 403], [200, 404])
    rows = client.get("/admin/appointments", headers=headers).json()["appointments"]
    assert rows[0]["status"] == "cancelled"
    with Session(make_engine(settings.database_url)) as session:
        audit_rows = session.scalars(
            select(ToolExecution).where(ToolExecution.tool == "human_cancel_appointment")
        ).all()
        assert len(audit_rows) == 1
