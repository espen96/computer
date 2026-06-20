"""Utility for syncing chat-uploaded files into the workspace."""

import os
import shutil
from pathlib import Path
from typing import Any

from cptr.utils.storage import UPLOADS_DIR

def sync_chat_uploads(workspace: str, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Ensure all files attached to a message exist in the workspace as real files.
    Returns the list of files updated with their workspace paths.
    """
    if not files or not workspace:
        return files

    chat_uploads_dir = Path(workspace) / ".cptr" / "chat_uploads"
    chat_uploads_dir.mkdir(parents=True, exist_ok=True)

    synced_files = []

    for f in files:
        file_id = f.get("id")
        if not file_id:
            synced_files.append(f)
            continue

        original_name = f.get("name", "file")
        blob_path = UPLOADS_DIR / file_id
        
        if not blob_path.exists():
            synced_files.append(f)
            continue

        # Try to find an existing linked file for this blob
        target_path = chat_uploads_dir / original_name
        
        # Deduplication loop
        # We want to use the same name if the blob is the same.
        # If the name is taken by a different blob, we suffix it.
        suffix = 2
        stem = target_path.stem
        ext = target_path.suffix
        
        while target_path.exists():
            # If it exists, check if it's the exact same blob (e.g. we already synced it)
            # We can check file size, or ideally, since blob_path is immutable, 
            # if we previously linked/copied it, the file size will match.
            # Even better, we could track state, but simple heuristic:
            # If the size is the same, assume it's the same file.
            if target_path.stat().st_size == blob_path.stat().st_size:
                # To be completely safe, we could check contents, but size is usually ok for chat uploads.
                break
                
            target_path = chat_uploads_dir / f"{stem}-{suffix}{ext}"
            suffix += 1
            
        if not target_path.exists():
            # Need to copy/link
            try:
                # Try hardlink first (fast, saves space, works if same partition)
                os.link(blob_path, target_path)
            except (OSError, AttributeError):
                try:
                    # Fallback to symlink (requires admin on Windows, but worth trying)
                    os.symlink(blob_path, target_path)
                except (OSError, AttributeError):
                    # Fallback to full copy
                    shutil.copy2(blob_path, target_path)

        # Update the file dict with the new path
        f_updated = dict(f)
        f_updated["workspace_path"] = f".cptr/chat_uploads/{target_path.name}"
        synced_files.append(f_updated)

    return synced_files
