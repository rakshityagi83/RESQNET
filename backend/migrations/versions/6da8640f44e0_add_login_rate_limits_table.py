
"""Add login rate limits table.

Revision ID: 6da8640f44e0
Revises: fd93bb412aad
"""

from alembic import op
import sqlalchemy as sa


revision = "6da8640f44e0"
down_revision = "fd93bb412aad"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "login_rate_limits",
        sa.Column(
            "key_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "failed_attempts",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "window_started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "blocked_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("key_hash"),
    )


def downgrade() -> None:
    op.drop_table("login_rate_limits")
