"""Mocked Meta transport and LLM tool-calling validations."""

import hashlib
import hmac
import json
from datetime import datetime, timedelta

import httpx
import pytest

from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.llm import LLMAdapter, LLMUnavailable
from whatsapp_ai_agent.meta import MetaClient, MetaDeliveryError, OutboundBlocked
from whatsapp_ai_agent.security import pseudonymize, verify_webhook_signature


def test_signature_uses_original_bytes():
    raw = b'{"a":1}'
    digest = "sha256=" + hmac.new(b"secret", raw, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(raw, digest, "secret")
    assert not verify_webhook_signature(b'{"a": 1}', digest, "secret")
    assert not verify_webhook_signature(raw, None, "secret")
    assert not verify_webhook_signature(raw, digest, "")


def test_pseudonym_is_deterministic_and_hides_input():
    assert pseudonymize("5551234567", "key") == pseudonymize("5551234567", "key")
    assert "5551234567" not in pseudonymize("5551234567", "key")


@pytest.mark.asyncio
async def test_send_blocked_by_default():
    settings = Settings(_env_file=None)
    with pytest.raises(OutboundBlocked):
        await MetaClient(settings).send_text("12345678901", "hi", datetime.utcnow())


@pytest.mark.asyncio
async def test_meta_mock_send_and_rate_limit():
    hits = []

    def handler(request):
        hits.append(request)
        if len(hits) == 1:
            return httpx.Response(429)
        return httpx.Response(200, json={"messages": [{"id": "wamid.mock"}]})

    settings = Settings(_env_file=None, enable_real_send=True, meta_access_token="fake",
                        meta_app_secret="fake", meta_phone_number_id="123")
    response = await MetaClient(settings, httpx.MockTransport(handler)).send_text(
        "12345678901", "hello", datetime.utcnow() - timedelta(minutes=5)
    )
    assert response["messages"][0]["id"] == "wamid.mock"
    assert len(hits) == 2
    assert "graph.facebook.com" in str(hits[0].url)


@pytest.mark.asyncio
async def test_out_of_window_blocked():
    settings = Settings(_env_file=None, enable_real_send=True, meta_access_token="fake",
                        meta_app_secret="fake", meta_phone_number_id="123")
    with pytest.raises(OutboundBlocked):
        await MetaClient(settings).send_text(
            "12345678901", "hello", datetime.utcnow() - timedelta(days=2)
        )


@pytest.mark.asyncio
async def test_meta_mock_http_failure():
    settings = Settings(_env_file=None, enable_real_send=True, meta_access_token="fake",
                        meta_app_secret="fake", meta_phone_number_id="123")
    with pytest.raises(MetaDeliveryError):
        await MetaClient(settings, httpx.MockTransport(
            lambda request: httpx.Response(400)
        )).send_text("12345678901", "hello", datetime.utcnow())


@pytest.mark.asyncio
async def test_llm_read_only_tool_call():
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "role": "assistant", "tool_calls": [{
                "type": "function", "function": {
                    "name": "list_services", "arguments": "{}"
                }
            }]
        }}]})

    settings = Settings(_env_file=None, llm_provider="openai-compatible",
                        llm_api_key="test", llm_model="offline-test")
    result = await LLMAdapter(settings, httpx.MockTransport(handler)).decide([
        {"role": "user", "content": "services"}
    ])
    assert result["tool_calls"][0]["function"]["name"] == "list_services"
    assert calls[0]["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_llm_cannot_call_unapproved_tool():
    settings = Settings(_env_file=None, llm_provider="openai-compatible",
                        llm_api_key="test", llm_model="offline-test")
    response = {"choices": [{"message": {"tool_calls": [{
        "function": {"name": "execute_shell", "arguments": "{}"}
    }]}}]}
    with pytest.raises(LLMUnavailable):
        await LLMAdapter(settings, httpx.MockTransport(
            lambda request: httpx.Response(200, json=response)
        )).decide([{"role": "user", "content": "hack"}])


def test_configuration_fails_closed():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env="production", demo_enabled=True)
    with pytest.raises(ValueError):
        Settings(_env_file=None, enable_real_send=True)
    with pytest.raises(ValueError):
        Settings(_env_file=None, llm_provider="openai-compatible")
