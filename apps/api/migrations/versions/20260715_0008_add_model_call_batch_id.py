"""Add batch correlation to model-call metadata.

Revision ID: 20260715_0008
Revises: 20260714_0007
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260715_0008"
down_revision: str | None = "20260714_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("model_calls", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.create_index("ix_model_calls_batch_id", "model_calls", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_model_calls_batch_id", table_name="model_calls")
    op.drop_column("model_calls", "batch_id")
