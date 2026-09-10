"""Add order_id to inventory_reservations for order linkage.

Revision ID: 0010_inventory_reservation_order_link
Revises: 0009_order_foundation
Create Date: 2026-09-02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_inv_resv_order"
down_revision: str | None = "0009_order_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_reservations",
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_inventory_reservations_order",
        "inventory_reservations",
        ["order_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_inventory_reservations_order", table_name="inventory_reservations")
    op.drop_column("inventory_reservations", "order_id")