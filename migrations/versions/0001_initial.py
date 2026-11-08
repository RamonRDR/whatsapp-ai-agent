"""Initial domain schema.

Revision ID: 0001
Revises:
"""

from alembic import op

from whatsapp_ai_agent import models  # noqa: F401
from whatsapp_ai_agent.database import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name not in {"appointment_slots", "admin_approvals"}]
    Base.metadata.create_all(bind=op.get_bind(), tables=tables, checkfirst=True)


def downgrade() -> None:
    tables = [table for table in Base.metadata.sorted_tables if table.name not in {"appointment_slots", "admin_approvals"}]
    Base.metadata.drop_all(bind=op.get_bind(), tables=tables, checkfirst=True)
