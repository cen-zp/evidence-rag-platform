"""Add model-call cost snapshots.

Revision ID: 20260714_0007
Revises: 20260714_0006
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0007"
down_revision: str | None = "20260714_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_calls", sa.Column("input_cost_per_million_tokens", sa.Float(), nullable=True)
    )
    op.add_column(
        "model_calls", sa.Column("output_cost_per_million_tokens", sa.Float(), nullable=True)
    )
    op.add_column("model_calls", sa.Column("estimated_cost", sa.Float(), nullable=True))
    op.add_column("model_calls", sa.Column("cost_currency", sa.String(length=12), nullable=True))


def downgrade() -> None:
    op.drop_column("model_calls", "cost_currency")
    op.drop_column("model_calls", "estimated_cost")
    op.drop_column("model_calls", "output_cost_per_million_tokens")
    op.drop_column("model_calls", "input_cost_per_million_tokens")
