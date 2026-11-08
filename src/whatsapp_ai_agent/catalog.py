"""Structured, fictional catalog; all tool outputs are bounded and grounded."""

from sqlalchemy.orm import Session

from whatsapp_ai_agent.models import Service

BUSINESS = {
    "name": "Demo Studio",
    "address": "123 Example Street, Demo City (fictional)",
    "hours": "Monday to Friday, 09:00-17:00",
    "cancellation": "Please contact the studio for cancellation details.",
}
FAQ = {
    "parking": "Parking information has not been provided.",
    "payment": "Payment methods have not been configured.",
    "location": BUSINESS["address"],
    "cancel": BUSINESS["cancellation"],
}
SEED = [
    ("consultation", "Consultation", "Introductory consultation", 30, 5000),
    ("styling", "Styling", "Basic styling appointment", 60, 9000),
    ("followup", "Follow-up", "Short review appointment", 30, 3000),
]


def seed_catalog(session: Session) -> None:
    for code, name, description, duration, price in SEED:
        if session.get(Service, code) is None:
            session.add(
                Service(
                    code=code,
                    name=name,
                    description=description,
                    duration_minutes=duration,
                    price_cents=price,
                )
            )
    session.commit()


def list_services(session: Session) -> list[dict]:
    return [
        {
            "code": s.code,
            "name": s.name,
            "duration_minutes": s.duration_minutes,
            "price_cents": s.price_cents,
        }
        for s in session.query(Service).order_by(Service.code).all()
    ]


def get_service_details(session: Session, code: str) -> dict:
    s = session.get(Service, code)
    if s is None:
        return {"error": "Service not found"}
    return {
        "code": s.code,
        "name": s.name,
        "description": s.description,
        "duration_minutes": s.duration_minutes,
        "price_cents": s.price_cents,
    }


def search_faq(query: str) -> dict:
    q = query.lower().strip()
    if len(q) > 200:
        return {"error": "Query too long"}
    for key, value in FAQ.items():
        if key in q:
            return {"answer": value}
    return {"answer": "This information is not registered. Ask a human operator."}
