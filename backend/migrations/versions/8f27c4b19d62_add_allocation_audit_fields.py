"""Add allocation audit fields.

Revision ID: 8f27c4b19d62
Revises: 6da8640f44e0
"""

from alembic import op
import sqlalchemy as sa


revision = "8f27c4b19d62"
down_revision = "6da8640f44e0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "allocations",
        sa.Column("submitted_by", sa.Integer(), nullable=True),
    )

    op.add_column(
        "allocations",
        sa.Column("decided_by", sa.Integer(), nullable=True),
    )

    op.add_column(
        "allocations",
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "allocations",
        sa.Column(
            "rejection_reason",
            sa.String(length=500),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_allocations_submitted_by_users",
        "allocations",
        "users",
        ["submitted_by"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_foreign_key(
        "fk_allocations_decided_by_users",
        "allocations",
        "users",
        ["decided_by"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint(
        "fk_allocations_decided_by_users",
        "allocations",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_allocations_submitted_by_users",
        "allocations",
        type_="foreignkey",
    )

    op.drop_column("allocations", "rejection_reason")
    op.drop_column("allocations", "decided_at")
    op.drop_column("allocations", "decided_by")
    op.drop_column("allocations", "submitted_by")
