"""Persist service and browser latency on assistant messages.

Revision ID: 20260715_0009
Revises: 20260715_0008
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0009"
down_revision: str | None = "20260715_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversation_messages",
        sa.Column("retrieval_latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_messages",
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
    )
    op.add_column(
        "conversation_messages",
        sa.Column("browser_end_to_end_latency_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversation_messages", "browser_end_to_end_latency_ms")
    op.drop_column("conversation_messages", "total_latency_ms")
    op.drop_column("conversation_messages", "retrieval_latency_ms")
