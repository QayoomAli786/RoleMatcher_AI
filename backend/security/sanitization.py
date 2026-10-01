"""Input and file-upload sanitisation for CareerCopilot AI."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Magic-byte signatures ────────────────────────────────────────────────────

_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # ZIP-based OOXML
    ".txt": [],  # text has no reliable magic bytes; rely on extension check
}

# ── Prompt-injection patterns ────────────────────────────────────────────────

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*(system|instruction|prompt)\s*>", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?above", re.IGNORECASE),
    re.compile(r"\bDAN\b\s*(mode|prompt|jailbreak)", re.IGNORECASE),
]

# Characters that are safe to keep in user prose
_SAFE_RE = re.compile(r"[^\w\s.,;:!?\"'@#%&()\-/\\+\n\r\t]", re.UNICODE)


# ── File upload sanitisation ─────────────────────────────────────────────────


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


# ── Prompt-injection / sanitisation ──────────────────────────────────────────


def detect_prompt_injection(text: str) -> bool:
    """Return True if the text matches known prompt-injection patterns."""
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def sanitize_user_input(text: str, *, max_length: int = 10_000) -> str:
    """Strip or escape potentially dangerous content from user-supplied text.

    - Enforces a hard length limit.
    - Flags (but does not strip) prompt-injection attempts for logging.
    - Escapes control characters while keeping normal prose readable.
    """
    if len(text) > max_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input too long ({len(text):,} chars). Max allowed is {max_length:,}.",
        )

    if detect_prompt_injection(text):
        logger.warning("Potential prompt injection detected in user input (length=%d)", len(text))

    # Remove null bytes and most control chars, keeping newlines / tabs
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return cleaned


def escape_for_llm(text: str) -> str:
    """Escape special characters in user content before it is embedded into an LLM prompt.

    Wraps user text in XML-style delimiters so the model can distinguish
    user data from instruction text, reducing prompt-injection surface.
    """
    safe = text.replace("\\", "\\\\").replace("<", "&lt;").replace(">", "&gt;")
    return f"<user_content>\n{safe}\n</user_content>"


def sanitize_filename(name: str) -> str:
    """Remove path separators and dangerous characters from a filename."""
    return re.sub(r"[^\w.\-]", "_", Path(name).name)[:255]
