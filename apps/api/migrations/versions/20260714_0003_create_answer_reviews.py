"""Create human answer review persistence.

Revision ID: 20260714_0003
Revises: 20260714_0002
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0003"
down_revision: str | None = "20260714_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "answer_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evaluation_case_id", sa.Uuid(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("citation_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("citation_filenames", sa.JSON(), nullable=False),
        sa.Column("answer_verdict", sa.String(length=20), nullable=False),
        sa.Column("citation_verdict", sa.String(length=20), nullable=False),
        sa.Column("refusal_verdict", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"],
            ["evaluation_cases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_answer_reviews_evaluation_case_id",
        "answer_reviews",
        ["evaluation_case_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_answer_reviews_evaluation_case_id", table_name="answer_reviews")
    op.drop_table("answer_reviews")
