"""Duration locks and human cancellation approvals.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("appointment_slots"):
        op.create_table(
            "appointment_slots",
            sa.Column("slot", sa.String(length=40), primary_key=True),
            sa.Column(
                "appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=False
            ),
        )
        op.create_index(
            "ix_appointment_slots_appointment_id", "appointment_slots", ["appointment_id"]
        )
    if not inspector.has_table("admin_approvals"):
        op.create_table(
            "admin_approvals",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "appointment_id", sa.Integer(), sa.ForeignKey("appointments.id"), nullable=False
            ),
            sa.Column("token_digest", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("consumed", sa.Boolean(), nullable=False),
        )
        op.create_index("ix_admin_approvals_appointment_id", "admin_approvals", ["appointment_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("admin_approvals"):
        op.drop_index("ix_admin_approvals_appointment_id", table_name="admin_approvals")
        op.drop_table("admin_approvals")
    if inspector.has_table("appointment_slots"):
        op.drop_index("ix_appointment_slots_appointment_id", table_name="appointment_slots")
        op.drop_table("appointment_slots")
