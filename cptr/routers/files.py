"""Managed file uploads: blob storage + DB metadata.

POST   /api/files         multipart upload → storage + DB → { id, url }
GET    /api/files/{id}    stream from storage (cache headers)
DELETE /api/files/{id}    verify ownership → delete storage + DB
"""

from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, Request, UploadFile, File as FastAPIFile, HTTPException
from fastapi.responses import Response

from cptr.models.files import File
from cptr.utils.config import now_ms
from cptr.utils.storage import get_storage

router = APIRouter(prefix="/api/files", tags=["files"])

# 10 MB max upload
MAX_UPLOAD_SIZE = 10 * 1024 * 1024


@router.post("")
async def upload(request: Request, file: UploadFile = FastAPIFile(...)):
    """Upload a file. Returns { id, url }."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "File too large (max 10 MB)")

    user_id = getattr(request.state, "auth", None)
    user_id = user_id.user_id if user_id else None

    content_type = file.content_type or "application/octet-stream"
    file_hash = hashlib.sha256(data).hexdigest()
    original_name = file.filename or "upload"
    _, ext = os.path.splitext(original_name)

    record = await File.create(
        user_id=user_id,
        filename=original_name,
        meta={
            "content_type": content_type,
            "size": len(data),
        },
        created_at=now_ms(),
    )

    await get_storage().put(record.id, data)

    # Include original extension in URL so browsers / tools can infer file type
    url_path = f"/api/files/{record.id}{ext}" if ext else f"/api/files/{record.id}"
    return {"id": record.id, "url": url_path, "content_type": content_type}


@router.get("/{file_id_ext:path}")
async def get_upload(file_id_ext: str, request: Request):
    """Serve an uploaded file. Public (no auth); UUID is unguessable.

    Accepts both /api/files/{uuid} and /api/files/{uuid}.{ext} so that
    URLs with file extensions work correctly.
    """
    # Strip any extension from the path to get the bare UUID
    file_id, _ = os.path.splitext(file_id_ext)

    record = await File.get_by_id(file_id)
    if not record:
        # Fallback: check if it's a real file path on the filesystem.
        # This allows inline markdown images using absolute paths to render.
        # We must authenticate the user first to prevent arbitrary local file disclosure.
        from cptr.utils.config import check_access, load_config
        client_host = request.client.host if request.client else "127.0.0.1"
        jwt_token = request.cookies.get("cptr_session")
        header_name = load_config().get("auth", {}).get("header", "Remote-User")
        remote_user = request.headers.get(header_name)

        auth = check_access(
            client_host=client_host,
            jwt_token=jwt_token,
            remote_user_header=remote_user,
        )
        if not auth:
            raise HTTPException(401, "Unauthorized")

        from pathlib import Path
        # Handle Windows absolute paths (e.g. C:/...) vs Unix absolute paths
        if len(file_id_ext) >= 2 and file_id_ext[1] == ":":
            target = Path(file_id_ext).resolve()
        elif file_id_ext.startswith("/") or file_id_ext.startswith("\\"):
            target = Path(file_id_ext).resolve()
        else:
            target = Path("/" + file_id_ext).resolve()

        if target.is_file():
            import mimetypes
            from fastapi.responses import FileResponse
            media_type, _ = mimetypes.guess_type(str(target))
            return FileResponse(
                path=str(target),
                media_type=media_type or "application/octet-stream",
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "Content-Disposition": f'inline; filename="{target.name}"',
                },
            )

        raise HTTPException(404, "Not found")

    data = await get_storage().get(record.id)
    if data is None:
        raise HTTPException(404, "Blob missing")

    content_type = (record.meta or {}).get("content_type", "application/octet-stream")

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Content-Disposition": f'inline; filename="{record.filename}"',
        },
    )


@router.delete("/{file_id_ext:path}")
async def delete_upload(file_id_ext: str, request: Request):
    """Delete an uploaded file. Must be the owner."""
    file_id, _ = os.path.splitext(file_id_ext)

    record = await File.get_by_id(file_id)
    if not record:
        raise HTTPException(404, "Not found")

    auth = getattr(request.state, "auth", None)
    if not auth or auth.user_id != record.user_id:
        raise HTTPException(403, "Not your file")

    await get_storage().delete(record.id)
    await File.delete_by_id(record.id)

    return {"ok": True}
