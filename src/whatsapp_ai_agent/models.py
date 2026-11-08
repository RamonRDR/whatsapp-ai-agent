"""Domain models. Phone numbers are pseudonymized at persistence boundary."""

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from whatsapp_ai_agent.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Contact(Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    pseudonym: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), unique=True)
    state: Mapped[str] = mapped_column(String(32), default="automated")
    pending_service: Mapped[str | None] = mapped_column(String(80))
    pending_slot: Mapped[str | None] = mapped_column(String(40))
    pending_action: Mapped[str | None] = mapped_column(String(32))
    confirmation_token: Mapped[str | None] = mapped_column(String(64))
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    contact: Mapped[Contact] = relationship()


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("channel", "external_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    external_id: Mapped[str] = mapped_column(String(128))
    direction: Mapped[str] = mapped_column(String(12))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Service(Base):
    __tablename__ = "services"
    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price_cents: Mapped[int | None] = mapped_column(Integer)


class AppointmentRequest(Base):
    __tablename__ = "appointments"
    # Overlap locking is enforced by unique AppointmentSlot records, not appointment start slots.
    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    service_code: Mapped[str] = mapped_column(ForeignKey("services.code"))
    slot: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(16), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class HumanHandoff(Base):
    __tablename__ = "human_handoffs"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    reason: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    tool: Mapped[str] = mapped_column(String(80))
    details: Mapped[str] = mapped_column(String(250))
    success: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DeliveryStatus(Base):
    __tablename__ = "delivery_statuses"
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AppointmentSlot(Base):
    """Unique half-hour resource lock covering a booked service's full duration."""

    __tablename__ = "appointment_slots"
    slot: Mapped[str] = mapped_column(String(40), primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)


class AdminApproval(Base):
    """Single-use, short-lived approval for an operator cancellation."""

    __tablename__ = "admin_approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int] = mapped_column(ForeignKey("appointments.id"), index=True)
    token_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
