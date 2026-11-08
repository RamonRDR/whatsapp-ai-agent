
"""Fictional appointment availability with unique 30-minute resource locks."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from whatsapp_ai_agent.models import AppointmentSlot, Service, utcnow


def slot_units(slot: str, duration_minutes: int) -> list[str]:
    if duration_minutes <= 0 or duration_minutes % 30:
        raise ValueError("Demo service duration must be a multiple of 30 minutes")
    start = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    return [
        (start + timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M")
        for offset in range(0, duration_minutes, 30)
    ]


def valid_slot(slot: str, duration_minutes: int, now: datetime | None = None) -> bool:
    try:
        start = datetime.strptime(slot, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    now = now or utcnow()
    end = start + timedelta(minutes=duration_minutes)
    return bool(
        duration_minutes > 0 and duration_minutes % 30 == 0
        and now < start < now + timedelta(days=60)
        and start.weekday() < 5 and start.hour >= 9
        and start.minute in {0, 30}
        and end.date() == start.date()
        and end <= start.replace(hour=17, minute=0)
    )


def is_available(session: Session, slot: str, duration_minutes: int) -> bool:
    if not valid_slot(slot, duration_minutes):
        return False
    units = slot_units(slot, duration_minutes)
    taken = session.scalar(
        select(AppointmentSlot.slot).where(AppointmentSlot.slot.in_(units)).limit(1)
    )
    return taken is None


def available_for_date(session: Session, day: str, code: str = "consultation") -> dict:
    service = session.get(Service, code)
    if service is None:
        return {"error": "Service not found"}
    try:
        date = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return {"error": "Invalid date"}
    slots = []
    for hour in range(9, 17):
        for minute in (0, 30):
            slot = date.replace(hour=hour, minute=minute).strftime("%Y-%m-%d %H:%M")
            if is_available(session, slot, service.duration_minutes):
                slots.append(slot)
    return {"date": day, "service": code, "available_slots": slots}
