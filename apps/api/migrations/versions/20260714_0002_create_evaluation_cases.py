"""Create evaluation case persistence.

Revision ID: 20260714_0002
Revises: 20260714_0001
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0002"
down_revision: str | None = "20260714_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_filenames", sa.JSON(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_evaluation_cases_knowledge_base_id",
        "evaluation_cases",
        ["knowledge_base_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evaluation_cases_knowledge_base_id", table_name="evaluation_cases")
    op.drop_table("evaluation_cases")
