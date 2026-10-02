"""File-upload validation for CareerCopilot AI."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from backend.core.config import get_settings

settings = get_settings()

# ── Magic-byte signatures ────────────────────────────────────────────────────

_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # ZIP-based OOXML
    ".txt": [],  # text has no reliable magic bytes; rely on extension check
}


async def sanitize_file_upload(file: UploadFile) -> bytes:
    """Read the upload, enforce size limits and validate magic bytes.

    Returns the raw bytes if valid, otherwise raises HTTP 400/422.
    """
    content = await file.read()
    size = len(content)
    max_bytes = settings.max_upload_size_bytes

    if size > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large ({size:,} bytes). Max allowed is {max_bytes:,} bytes.",
        )

    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

    # Determine expected extension
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower()

    if ext not in settings.allowed_upload_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{ext}' not allowed. Accepted: {settings.allowed_upload_extensions}",
        )

    # Verify magic bytes (skip for .txt which has no reliable signature)
    expected_magic = _MAGIC_BYTES.get(ext)
    if expected_magic:
        if not any(content[:len(sig)].startswith(sig) for sig in expected_magic):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"File content does not match expected '{ext}' format (magic byte check failed).",
            )

    return content
