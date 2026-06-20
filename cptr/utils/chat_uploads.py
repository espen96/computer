"""Virtual directory utility for chat-uploaded files."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select

from cptr.models import Chat, ChatMessage, File
from cptr.utils.db import get_db
from cptr.utils.storage import get_storage


def deduplicate_filename(name: str, seen: dict[str, int]) -> str:
    """Handle filename collisions by appending -2, -3, etc."""
    if name not in seen:
        seen[name] = 1
        return name

    base, ext = os.path.splitext(name)
    while True:
        seen[name] += 1
        candidate = f"{base}-{seen[name]}{ext}"
        if candidate not in seen:
            seen[candidate] = 1
            return candidate


def find_virtual_info(path: str) -> tuple[bool, bool, str | None, str | None]:
    """Analyze a path to see if it is in the virtual .cptr/chat_uploads directory.

    Returns (is_under_virtual_dir, is_virtual_dir_itself, filename, workspace_path).
    """
    try:
        # Resolve target path. Path.resolve() works on any valid string
        target = Path(path).resolve()
    except Exception:
        return False, False, None, None

    # Check if target or any of its parents has name 'chat_uploads' and its parent has name '.cptr'
    parts = target.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".cptr" and parts[i + 1] == "chat_uploads":
            workspace_path = Path(*parts[:i])
            virtual_dir = workspace_path / ".cptr" / "chat_uploads"

            if target == virtual_dir:
                return True, True, None, str(workspace_path)

            try:
                relative = target.relative_to(virtual_dir)
                if relative.parts:
                    return True, False, relative.parts[0], str(workspace_path)
            except ValueError:
                pass

    return False, False, None, None


async def _get_workspace_uploads_map(workspace: str) -> dict[str, dict]:
    """Build a mapping of virtual_filename -> {id, name, content_type, size, created_at}
    for a given workspace.
    """
    # Canonicalize workspace path to compare with metadata
    try:
        canonical_workspace = str(Path(workspace).resolve())
    except Exception:
        canonical_workspace = workspace

    async with await get_db() as db:
        # Get chats
        result = await db.execute(select(Chat))
        chats = result.scalars().all()
        chat_ids = []
        for c in chats:
            if c.meta and c.meta.get("workspace"):
                try:
                    c_ws = str(Path(c.meta["workspace"]).resolve())
                except Exception:
                    c_ws = c.meta["workspace"]
                if c_ws == canonical_workspace:
                    chat_ids.append(c.id)

        if not chat_ids:
            return {}

        # Get messages
        msg_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.chat_id.in_(chat_ids))
            .order_by(ChatMessage.created_at.asc())
        )
        messages = msg_result.scalars().all()

        # Gather all file IDs to fetch in one query
        file_ids = []
        attachments = []
        for msg in messages:
            files = (msg.meta or {}).get("files", [])
            if not isinstance(files, list):
                continue
            for f in files:
                if isinstance(f, dict) and f.get("id"):
                    file_ids.append(f["id"])
                    attachments.append((f, msg.created_at))

        # Fetch file records
        file_meta_map = {}
        if file_ids:
            file_result = await db.execute(select(File).where(File.id.in_(file_ids)))
            for record in file_result.scalars().all():
                file_meta_map[record.id] = {
                    "content_type": (record.meta or {}).get("content_type", "application/octet-stream"),
                    "size": (record.meta or {}).get("size", 0),
                }

        # Deduplicate and build mapping
        seen = {}
        uploads_map = {}
        processed_file_ids = set()
        for f, created_at in attachments:
            file_id = f["id"]
            if file_id in processed_file_ids:
                continue
            processed_file_ids.add(file_id)

            original_name = f.get("name") or "file"

            # Fetch MIME / size from DB record, or fallback to attachment fields, or defaults
            db_meta = file_meta_map.get(file_id, {})
            content_type = f.get("content_type") or db_meta.get("content_type") or "application/octet-stream"
            size = f.get("size") or db_meta.get("size") or 0

            # Suffix deduplication
            virtual_name = deduplicate_filename(original_name, seen)

            uploads_map[virtual_name] = {
                "id": file_id,
                "name": original_name,
                "content_type": content_type,
                "size": size,
                "created_at": created_at,
            }

        return uploads_map


async def get_chat_upload_entries(workspace: str) -> list[dict]:
    """Get entries inside the virtual chat_uploads directory for a workspace."""
    uploads_map = await _get_workspace_uploads_map(workspace)
    entries = []
    for virtual_name, info in uploads_map.items():
        dt = datetime.fromtimestamp(info["created_at"] / 1000.0, tz=timezone.utc)
        modified = dt.isoformat()
        entries.append({
            "name": virtual_name,
            "type": "file",
            "size": info["size"],
            "modified": modified,
        })
    # Sort files alphabetically
    entries.sort(key=lambda e: e["name"].lower())
    return entries


async def resolve_chat_upload(workspace: str, filename: str) -> dict | None:
    """Resolve a virtual filename to its metadata and record:
    {id, name, content_type, size, created_at}
    """
    uploads_map = await _get_workspace_uploads_map(workspace)
    return uploads_map.get(filename)


async def read_chat_upload_bytes(workspace: str, filename: str) -> bytes | None:
    """Read the content bytes of a chat upload."""
    info = await resolve_chat_upload(workspace, filename)
    if not info:
        return None
    return await get_storage().get(info["id"])
