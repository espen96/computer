"""Workspace model: one row per user+path, stores tabs/groups/layout."""

from __future__ import annotations

import time
import uuid

from sqlalchemy import BigInteger, Boolean, Column, ForeignKey, Text, UniqueConstraint, select, delete
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from cptr.models.base import Base
from cptr.utils.db import get_db


def _uuid() -> str:
    return str(uuid.uuid4())


class Workspace(Base):
    """Per-workspace state. One row per (user, filesystem path)."""

    __tablename__ = "workspaces"

    id = Column(Text, primary_key=True, default=_uuid)
    user_id = Column(Text, ForeignKey("users.id"), nullable=False)
    path = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    data = Column(JSON, nullable=False, default=dict)  # tabs, groups, split, fileBrowserCwd
    is_chat = Column(Boolean, nullable=False, default=False)  # chat-mode workspace
    created_at = Column(BigInteger, nullable=False)
    updated_at = Column(BigInteger, nullable=True)

    __table_args__ = (UniqueConstraint("user_id", "path", name="uq_workspace_user_path"),)

    # ── Class methods ────────────────────────────────────────

    @staticmethod
    async def get_by_user(user_id: str, include_chat: bool = False) -> list[Workspace]:
        """List all workspaces for a user. Excludes chat workspaces by default."""
        async with await get_db() as db:
            stmt = select(Workspace).where(Workspace.user_id == user_id)
            if not include_chat:
                stmt = stmt.where(Workspace.is_chat == False)
            result = await db.execute(stmt.order_by(Workspace.created_at))
            return list(result.scalars().all())

    @staticmethod
    async def get_by_path(user_id: str, path: str) -> Workspace | None:
        """Get a single workspace by user + path."""
        async with await get_db() as db:
            result = await db.execute(
                select(Workspace).where(
                    Workspace.user_id == user_id,
                    Workspace.path == path,
                )
            )
            return result.scalar_one_or_none()

    @staticmethod
    async def upsert(user_id: str, path: str, name: str, data: dict) -> Workspace:
        """Create or update a workspace."""
        async with await get_db() as db:
            result = await db.execute(
                select(Workspace).where(
                    Workspace.user_id == user_id,
                    Workspace.path == path,
                )
            )
            ws = result.scalar_one_or_none()
            now = int(time.time())
            if ws:
                ws.name = name
                ws.data = data
                ws.updated_at = now
            else:
                ws = Workspace(
                    user_id=user_id,
                    path=path,
                    name=name,
                    data=data,
                    created_at=now,
                    updated_at=now,
                )
                db.add(ws)
            await db.commit()
            return ws

    @staticmethod
    async def delete_by_path(user_id: str, path: str) -> bool:
        """Delete a workspace. Returns True if it existed."""
        async with await get_db() as db:
            result = await db.execute(
                delete(Workspace).where(
                    Workspace.user_id == user_id,
                    Workspace.path == path,
                )
            )
            await db.commit()
            return result.rowcount > 0

    @staticmethod
    async def delete_by_user(user_id: str) -> None:
        """Delete all workspaces for a user."""
        async with await get_db() as db:
            await db.execute(delete(Workspace).where(Workspace.user_id == user_id))
            await db.commit()

    @staticmethod
    async def rename(user_id: str, path: str, name: str) -> bool:
        """Update only the display name of a workspace. Returns True if found."""
        async with await get_db() as db:
            result = await db.execute(
                select(Workspace).where(
                    Workspace.user_id == user_id,
                    Workspace.path == path,
                )
            )
            ws = result.scalar_one_or_none()
            if not ws:
                return False
            ws.name = name
            ws.updated_at = int(time.time())
            await db.commit()
            return True

    @staticmethod
    async def get_chat_workspaces(user_id: str) -> list[Workspace]:
        """List all chat-mode workspaces for a user, most recent first."""
        async with await get_db() as db:
            result = await db.execute(
                select(Workspace)
                .where(Workspace.user_id == user_id, Workspace.is_chat == True)
                .order_by(Workspace.created_at.desc())
            )
            return list(result.scalars().all())

    @staticmethod
    async def upsert_chat(user_id: str, path: str, name: str, data: dict | None = None) -> Workspace:
        """Create or update a chat-mode workspace."""
        async with await get_db() as db:
            result = await db.execute(
                select(Workspace).where(
                    Workspace.user_id == user_id,
                    Workspace.path == path,
                )
            )
            ws = result.scalar_one_or_none()
            now = int(time.time())
            if ws:
                ws.name = name
                if data is not None:
                    ws.data = data
                ws.updated_at = now
            else:
                ws = Workspace(
                    user_id=user_id,
                    path=path,
                    name=name,
                    data=data or {},
                    is_chat=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(ws)
            await db.commit()
            return ws
