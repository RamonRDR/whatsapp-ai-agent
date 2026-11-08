"""HTTP transport: demo, official webhook, authenticated operator endpoints."""

import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from importlib.resources import files

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.agent import Agent
from whatsapp_ai_agent.catalog import seed_catalog
from whatsapp_ai_agent.config import Settings, get_settings
from whatsapp_ai_agent.database import Base, make_engine, make_session_factory
from whatsapp_ai_agent.meta import MetaClient, MetaDeliveryError, OutboundBlocked
from whatsapp_ai_agent.models import (
    AppointmentRequest, Contact, Conversation, DeliveryStatus, HumanHandoff, Message,
    ToolExecution, utcnow,
)
from whatsapp_ai_agent.security import pseudonymize, verify_webhook_signature


class DemoInput(BaseModel):
    contact: str = Field(default="demo-user", min_length=1, max_length=80, pattern=r"^[\w-]+$")
    message: str = Field(min_length=1, max_length=4096)
    message_id: str | None = Field(default=None, max_length=100)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="WhatsApp AI Agent", version="0.1.0",
                  description="Offline demo and opt-in official WhatsApp Cloud API bridge")
    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    # Local bootstrap; production deployments should use Alembic upgrade head.
    if settings.app_env == "local":
        Base.metadata.create_all(bind=engine)
        with factory() as session:
            seed_catalog(session)
    agent = Agent(settings)

    def db() -> Iterator[Session]:
        with factory() as session:
            yield session

    def admin(x_admin_api_key: str | None = Header(default=None)) -> None:
        import hmac
        if not x_admin_api_key or not hmac.compare_digest(
            settings.admin_api_key, x_admin_api_key
        ):
            raise HTTPException(status_code=403, detail="Forbidden")

    def ensure_demo() -> None:
        if not settings.demo_enabled or settings.app_env != "local":
            raise HTTPException(status_code=404, detail="Demo is disabled")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "mode": "demo" if settings.demo_enabled else "api"}

    @app.get("/demo", response_class=HTMLResponse, dependencies=[Depends(ensure_demo)])
    def demo_page() -> str:
        return files("whatsapp_ai_agent").joinpath("static/demo.html").read_text("utf-8")

    @app.post("/demo/message", dependencies=[Depends(ensure_demo)])
    async def demo_message(payload: DemoInput, session: Session = Depends(db)) -> dict:
        try:
            return await agent.process(session, identity=payload.contact,
                                       body=payload.message,
                                       external_id=payload.message_id or uuid.uuid4().hex)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/demo/history", dependencies=[Depends(ensure_demo)])
    def demo_history(contact: str = "demo-user", session: Session = Depends(db)) -> dict:
        if not contact or len(contact) > 80:
            raise HTTPException(status_code=422, detail="Invalid contact")
        key = pseudonymize("demo:" + contact, settings.admin_api_key)
        person = session.scalar(select(Contact).where(Contact.pseudonym == key))
        if person is None:
            return {"messages": [], "tools": []}
        conv = session.scalar(select(Conversation).where(Conversation.contact_id == person.id))
        if conv is None:
            return {"messages": [], "tools": []}
        messages = session.scalars(select(Message).where(
            Message.conversation_id == conv.id
        ).order_by(Message.id.desc()).limit(60)).all()
        tools = session.scalars(select(ToolExecution).where(
            ToolExecution.conversation_id == conv.id
        ).order_by(ToolExecution.id.desc()).limit(30)).all()
        return {"messages": [{"direction": m.direction, "body": m.body}
                             for m in reversed(messages)],
                "tools": [{"name": t.tool, "details": t.details}
                          for t in reversed(tools)]}

    @app.post("/demo/reset", dependencies=[Depends(ensure_demo), Depends(admin)])
    def demo_reset(session: Session = Depends(db)) -> dict:
        for table in (DeliveryStatus, ToolExecution, HumanHandoff, Message,
                      AppointmentRequest, Conversation, Contact):
            session.execute(delete(table))
        session.commit()
        return {"reset": True}

    @app.get("/webhooks/whatsapp", response_class=PlainTextResponse)
    def verify_webhook(request: Request) -> str:
        query = request.query_params
        import hmac
        if (not settings.webhook_verify_token or query.get("hub.mode") != "subscribe"
                or not hmac.compare_digest(
                    query.get("hub.verify_token", ""), settings.webhook_verify_token
                )):
            raise HTTPException(status_code=403, detail="Invalid verification token")
        return query.get("hub.challenge", "")

    @app.post("/webhooks/whatsapp")
    async def receive_webhook(request: Request, session: Session = Depends(db)) -> dict:
        size = request.headers.get("content-length")
        if size and (not size.isdigit() or int(size) > 65536):
            raise HTTPException(status_code=413, detail="Payload too large")
        raw = await request.body()
        if len(raw) > 65536:
            raise HTTPException(status_code=413, detail="Payload too large")
        signature = request.headers.get("x-hub-signature-256")
        if not verify_webhook_signature(raw, signature, settings.meta_app_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="Malformed JSON") from exc
        if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
            raise HTTPException(status_code=422, detail="Unknown webhook object")
        processed, ignored = 0, 0
        for entry in data.get("entry", []) if isinstance(data.get("entry"), list) else []:
            if not isinstance(entry, dict):
                ignored += 1
                continue
            changes = entry.get("changes")
            if not isinstance(changes, list):
                ignored += 1
                continue
            for change in changes:
                if not isinstance(change, dict) or change.get("field") != "messages":
                    ignored += 1
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    ignored += 1
                    continue
                for status in value.get("statuses", []) if isinstance(
                    value.get("statuses"), list
                ) else []:
                    if isinstance(status, dict) and isinstance(status.get("id"), str):
                        row = session.scalar(select(DeliveryStatus).where(
                            DeliveryStatus.external_id == status["id"]))
                        if row is None:
                            row = DeliveryStatus(external_id=status["id"][:128], status="unknown")
                            session.add(row)
                        row.status = str(status.get("status", "unknown"))[:32]
                        session.commit()
                for message in value.get("messages", []) if isinstance(
                    value.get("messages"), list
                ) else []:
                    if not isinstance(message, dict):
                        ignored += 1
                        continue
                    sender, msgid = message.get("from"), message.get("id")
                    if not isinstance(sender, str) or not isinstance(msgid, str):
                        ignored += 1
                        continue
                    if message.get("type") != "text" or not isinstance(
                        message.get("text"), dict
                    ):
                        ignored += 1
                        continue
                    content = message["text"].get("body")
                    if not isinstance(content, str) or not 1 <= len(content) <= 4096:
                        ignored += 1
                        continue
                    try:
                        dt = datetime.utcfromtimestamp(int(message.get("timestamp", 0)))
                        if dt.year < 2020:
                            dt = utcnow()
                    except (ValueError, OverflowError, TypeError):
                        dt = utcnow()
                    try:
                        result = await agent.process(
                            session, identity=sender, body=content,
                            external_id=msgid, channel="meta", timestamp=dt
                        )
                    except ValueError:
                        ignored += 1
                        continue
                    if result["duplicate"]:
                        ignored += 1
                        continue
                    processed += 1
                    if result["reply"] and settings.enable_real_send:
                        try:
                            await MetaClient(settings).send_text(sender, result["reply"], dt)
                        except (MetaDeliveryError, OutboundBlocked, ValueError):
                            # Deliberately no retry in webhook: no duplicate sends.
                            # Production-grade outbound delivery needs a durable outbox.
                            ignored += 1
        return {"processed": processed, "ignored": ignored}

    @app.get("/admin/handoffs", dependencies=[Depends(admin)])
    def handoffs(session: Session = Depends(db)) -> dict:
        rows = session.scalars(select(HumanHandoff).where(
            HumanHandoff.status == "open"
        ).order_by(HumanHandoff.id)).all()
        return {"handoffs": [{"id": r.id, "conversation_id": r.conversation_id,
                              "reason": r.reason} for r in rows]}

    @app.post("/admin/handoffs/{handoff_id}/resume", dependencies=[Depends(admin)])
    def resume(handoff_id: int, session: Session = Depends(db)) -> dict:
        row = session.get(HumanHandoff, handoff_id)
        if row is None or row.status != "open":
            raise HTTPException(status_code=404, detail="Open handoff not found")
        conv = session.get(Conversation, row.conversation_id)
        if conv is None or conv.contact.opted_out:
            raise HTTPException(status_code=409, detail="Cannot resume")
        row.status = "closed"
        conv.state = "automated"
        session.commit()
        return {"resumed": True}

    @app.get("/admin/appointments", dependencies=[Depends(admin)])
    def appointments(session: Session = Depends(db)) -> dict:
        rows = session.scalars(select(AppointmentRequest).order_by(
            AppointmentRequest.id)).all()
        return {"appointments": [{"id": a.id, "service": a.service_code,
                                  "slot": a.slot, "status": a.status} for a in rows]}

    return app


app = create_app()
