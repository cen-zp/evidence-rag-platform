"""Add local users, sessions, and knowledge-base ownership.

Revision ID: 20260714_0005
Revises: 20260714_0004
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260714_0005"
down_revision: str | None = "20260714_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"], unique=True)
    op.add_column("knowledge_bases", sa.Column("owner_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_knowledge_bases_owner_id_users",
        "knowledge_bases",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_knowledge_bases_owner_id", "knowledge_bases", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_bases_owner_id", table_name="knowledge_bases")
    op.drop_constraint("fk_knowledge_bases_owner_id_users", "knowledge_bases", type_="foreignkey")
    op.drop_column("knowledge_bases", "owner_id")
    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
