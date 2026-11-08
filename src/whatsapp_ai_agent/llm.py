"""Optional OpenAI-compatible chat-completions tool-calling adapter.

External invocation is opt-in. The deterministic engine remains the required CI path.
"""

import json
from typing import Any

import httpx

from whatsapp_ai_agent.config import Settings

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
                "required": required,
            },
        },
    }
    for name, description, properties, required in [
        ("list_services", "List demo services", {}, []),
        ("get_service_details", "Read one service", {"code": {"type": "string"}}, ["code"]),
        ("get_business_hours", "Read opening hours", {}, []),
        ("get_business_information", "Read business info", {}, []),
        ("search_faq", "Look up a FAQ answer", {"query": {"type": "string"}}, ["query"]),
        ("get_availability", "List available demo slots for a date and service",
         {"date": {"type": "string"}, "service": {"type": "string"}}, ["date", "service"]),
    ]
]


class LLMUnavailable(Exception):
    pass


class LLMAdapter:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def decide(self, messages: list[dict[str, Any]]) -> dict:
        if self.settings.llm_provider != "openai-compatible":
            raise LLMUnavailable("Deterministic mode does not call an LLM")
        url = self.settings.llm_api_base.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.settings.llm_model,
            "messages": messages[-12:],
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0,
            "max_tokens": self.settings.llm_max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=12, transport=self.transport) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": "Bearer " + self.settings.llm_api_key},
                )
                response.raise_for_status()
                result = response.json()
                choice = result["choices"][0]["message"]
                if not isinstance(choice, dict):
                    raise ValueError("Malformed model message")
                calls = choice.get("tool_calls") or []
                if len(calls) > self.settings.llm_max_tool_calls:
                    raise ValueError("Too many tool calls")
                for call in calls:
                    if call.get("function", {}).get("name") not in {
                        t["function"]["name"] for t in TOOLS
                    }:
                        raise ValueError("Unapproved tool")
                    args = json.loads(call["function"]["arguments"])
                    if not isinstance(args, dict):
                        raise ValueError("Invalid tool arguments")
                return choice
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMUnavailable("LLM response unavailable or invalid") from exc
