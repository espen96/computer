"""Add is_chat flag to workspaces for chat-mode workspaces.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-18
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspaces", sa.Column("is_chat", sa.Boolean(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("workspaces", "is_chat")
