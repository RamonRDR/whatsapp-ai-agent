"""Stateful, auditable conversation engine with read-only LLM tool calling.

Write operations are only performed by deterministic explicit confirmation.
"""

import json
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from importlib.resources import files

from whatsapp_ai_agent.availability import available_for_date, is_available, slot_units, valid_slot
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from whatsapp_ai_agent.catalog import BUSINESS, get_service_details, list_services, search_faq
from whatsapp_ai_agent.config import Settings
from whatsapp_ai_agent.llm import LLMAdapter, LLMUnavailable
from whatsapp_ai_agent.models import (
    AppointmentRequest,
    AppointmentSlot,
    Contact,
    Conversation,
    HumanHandoff,
    Message,
    Service,
    ToolExecution,
    utcnow,
)
from whatsapp_ai_agent.security import new_token, pseudonymize
from whatsapp_ai_agent.telemetry import emit


class Agent:
    def __init__(self, settings: Settings):
        self.settings = settings

    @staticmethod
    def _tool(session: Session, name: str, args: dict[str, Any]) -> dict:
        if name == "list_services" and not args:
            return {"services": list_services(session)}
        if (
            name == "get_service_details"
            and set(args) == {"code"}
            and isinstance(args["code"], str)
            and len(args["code"]) <= 80
        ):
            return get_service_details(session, args["code"])
        if name == "get_business_hours" and not args:
            return {"hours": BUSINESS["hours"]}
        if name == "get_business_information" and not args:
            return dict(BUSINESS)
        if name == "search_faq" and set(args) == {"query"} and isinstance(args["query"], str):
            return search_faq(args["query"])

        if (name == "get_availability" and set(args) == {"date", "service"}
                and all(isinstance(value, str) for value in args.values())):
            if len(args["date"]) <= 10 and len(args["service"]) <= 80:
                return available_for_date(session, args["date"], args["service"])
        raise ValueError("Invalid or unauthorized tool call")

    @staticmethod
    def _log_tool(
        session: Session, conv: Conversation, name: str, detail: str, success: bool = True
    ) -> None:
        session.add(
            ToolExecution(conversation_id=conv.id, tool=name, details=detail[:250], success=success)
        )

    @staticmethod
    def _handoff(session: Session, conv: Conversation, reason: str) -> str:
        conv.state = "human"
        conv.pending_service = None
        conv.pending_slot = None
        conv.pending_action = None
        conv.confirmation_token = None
        session.add(HumanHandoff(conversation_id=conv.id, reason=reason[:200]))
        return "I have requested a human operator. Automated replies are now paused."


    def _confirm(self, session: Session, conv: Conversation) -> str:
        code, slot = conv.pending_service, conv.pending_slot
        # The pending confirmation is consumed once, regardless of outcome.
        conv.pending_action = None
        conv.confirmation_token = None
        conv.pending_service = None
        conv.pending_slot = None
        if not code or not slot:
            return "The request expired or is invalid. Please start again."
        service = session.get(Service, code)
        if service is None:
            return "This service is no longer available."
        if not valid_slot(slot, service.duration_minutes):
            return "The request expired or is invalid. Please start again."
        if not is_available(session, slot, service.duration_minutes):
            return "This slot is no longer available. Please choose another."
        appointment = AppointmentRequest(
            contact_id=conv.contact_id, service_code=code,
            slot=slot, status="confirmed"
        )
        session.add(appointment)
        session.flush()
        for unit in slot_units(slot, service.duration_minutes):
            session.add(AppointmentSlot(slot=unit, appointment_id=appointment.id))
        self._log_tool(session, conv, "confirm_appointment", code + " " + slot)
        return "Your demo appointment is confirmed: " + code + " on " + slot + "."

    async def process(
        self,
        session: Session,
        identity: str,
        body: str,
        external_id: str,
        channel: str = "demo",
        timestamp: datetime | None = None,
        llm_transport: Any = None,
    ) -> dict:
        if not identity or len(identity) > 100 or not external_id or len(external_id) > 128:
            raise ValueError("Invalid message identifiers")
        if not isinstance(body, str) or not body.strip() or len(body) > 4096:
            raise ValueError("Message must contain between 1 and 4096 characters")
        if channel not in {"demo", "meta"}:
            raise ValueError("Unknown channel")
        existing = session.scalar(
            select(Message).where(Message.channel == channel, Message.external_id == external_id)
        )
        if existing:
            return {"duplicate": True, "reply": None, "tools": [], "state": "unchanged"}
        key = pseudonymize(channel + ":" + identity, self.settings.admin_api_key)
        contact = session.scalar(select(Contact).where(Contact.pseudonym == key))
        if contact is None:
            contact = Contact(pseudonym=key)
            session.add(contact)
            session.flush()
        conv = session.scalar(select(Conversation).where(Conversation.contact_id == contact.id))
        if conv is None:
            conv = Conversation(contact_id=contact.id)
            session.add(conv)
            session.flush()
        effective_time = timestamp or utcnow()
        is_stale = bool(conv.last_inbound_at and effective_time < conv.last_inbound_at)
        if not is_stale:
            conv.last_inbound_at = effective_time
        session.add(
            Message(
                conversation_id=conv.id,
                channel=channel,
                external_id=external_id,
                direction="in",
                body=body,
            )
        )
        tools: list[dict] = []
        text = body.strip()
        lower = text.casefold()
        recent = session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == conv.id,
                Message.direction == "in",
                Message.created_at >= utcnow() - timedelta(minutes=1),
            )
        ) or 0
        reply: str | None

        if is_stale:
            reply = None
        elif lower in {"stop", "unsubscribe", "opt out"}:
            contact.opted_out = True
            conv.state = "opted_out"
            reply = None
        elif contact.opted_out:
            reply = None
        elif conv.state == "human":
            reply = None
        elif recent >= self.settings.inbound_rate_limit and lower not in {
            "human", "agent", "operator", "atendimento humano", "humano"
        }:
            self._log_tool(session, conv, "rate_limit", "Inbound per-minute limit", False)
            reply = None
        elif lower in {"human", "agent", "operator", "atendimento humano", "humano"}:
            reply = self._handoff(session, conv, "User requested human assistance")
        elif conv.pending_action == "book":
            if lower in {"confirm", "yes confirm", "confirmar", "confirmo"}:
                reply = self._confirm(session, conv)
            elif lower in {"no", "cancel", "não", "nao"}:
                conv.pending_action = None
                conv.confirmation_token = None
                conv.pending_service = None
                conv.pending_slot = None
                reply = "Your pending booking request was discarded."
            else:
                reply = "Reply CONFIRM to book, or NO to discard this request."
        elif lower.startswith(("cancel appointment", "cancel booking", "cancelar agendamento")):
            reply = self._handoff(session, conv, "Cancellation needs human authorization")
        elif lower.startswith(("book ", "agendar ")):
            match = re.fullmatch(
                r"(?:book|agendar)\s+([a-zA-Z0-9_-]{1,80})\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})",
                lower,
            )
            if not match:
                reply = "Use: book consultation YYYY-MM-DD HH:MM (demo weekdays 09:00-17:00)."
            else:
                code, day, hm = match.groups()
                slot = day + " " + hm
                service = session.get(Service, code)
                if service is None:
                    reply = "Service not found. Ask for the services list."
                elif not valid_slot(slot, service.duration_minutes):
                    reply = "Invalid or unavailable demo time. Choose a future weekday 09:00-16:30."
                elif not is_available(session, slot, service.duration_minutes):
                    reply = "That time is unavailable. Choose another slot."
                else:
                    conv.pending_service = code
                    conv.pending_slot = slot
                    conv.pending_action = "book"
                    conv.confirmation_token = new_token()
                    reply = (
                        "Confirm demo booking for "
                        + code
                        + " on "
                        + slot
                        + "? Reply CONFIRM or NO."
                    )

        elif "available" in lower or "horário livre" in lower or "availability" in lower:
            date_match = re.search(r"\d{4}-\d{2}-\d{2}", lower)
            if date_match:
                result = available_for_date(session, date_match.group(0))
                reply = json.dumps(result, ensure_ascii=False)
            else:
                result = {
                    "rule": "Future weekdays 09:00-16:30, every 30 minutes",
                    "note": "Ask availability YYYY-MM-DD for actual free slots.",
                }
                reply = result["rule"] + ". " + result["note"]
            self._log_tool(session, conv, "get_availability", "Demo availability")
            tools.append({"name": "get_availability", "result": result})
        elif self.settings.llm_provider == "openai-compatible":
            # The LLM can select read-only tools only. Its free-text claims are not trusted.
            try:
                history = session.scalars(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.id.desc())
                    .limit(8)
                ).all()
                messages = [
                    {
                        "role": "system",
                        "content": files("whatsapp_ai_agent").joinpath(
                            "prompts/system.txt"
                        ).read_text("utf-8"),
                    },
                    *[
                        {
                            "role": "user" if m.direction == "in" else "assistant",
                            "content": m.body[:1000],
                        }
                        for m in reversed(history)
                    ],
                ]
                result = await LLMAdapter(self.settings, llm_transport).decide(messages)
                calls = result.get("tool_calls") or []
                for call in calls:
                    name = call["function"]["name"]
                    args = json.loads(call["function"]["arguments"])
                    output = self._tool(session, name, args)
                    tools.append({"name": name, "result": output})
                    self._log_tool(session, conv, name, json.dumps(args)[:250])
                reply = (
                    json.dumps(tools, ensure_ascii=False)[:1800]
                    if tools
                    else "Please ask about hours, services or type HUMAN for assistance."
                )
            except (LLMUnavailable, ValueError, KeyError, TypeError):
                reply = "The AI provider is unavailable. Type HUMAN for assistance."
        else:
            name: str | None = None
            args: dict = {}
            if any(x in lower for x in ("hours", "open", "horário", "funcionamento")):
                name = "get_business_hours"
            elif any(x in lower for x in ("address", "where", "endereço", "localização")):
                name = "get_business_information"
            elif any(x in lower for x in ("services", "serviços", "price", "preço", "cost")):
                name = "list_services"
            elif any(x in lower for x in ("parking", "payment", "cancel policy")):
                name, args = "search_faq", {"query": lower}
            if name:
                output = self._tool(session, name, args)
                self._log_tool(session, conv, name, json.dumps(args)[:250])
                tools.append({"name": name, "result": output})
                reply = json.dumps(output, ensure_ascii=False)
            else:
                reply = (
                    "I can list services, opening hours, and help request a demo booking. "
                    "Type HUMAN if you would prefer an operator."
                )

        if reply:
            session.add(
                Message(
                    conversation_id=conv.id,
                    channel=channel,
                    external_id="out-" + external_id,
                    direction="out",
                    body=reply[:4096],
                )
            )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            # Unique constraints prevent both duplicate processing and concurrent double-booking.
            return {"duplicate": True, "reply": None, "tools": [], "state": "conflict"}
        emit("conversation_processed", channel=channel, conversation_id=conv.id,
             state=conv.state, tools_count=len(tools), has_reply=bool(reply))
        return {"duplicate": False, "reply": reply, "tools": tools, "state": conv.state}
