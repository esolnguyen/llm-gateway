"""Utility functions for the Azure OpenAI backend."""
import base64
from typing import Final

MIME_PDF: Final[str] = "application/pdf"
MIME_PNG: Final[str] = "image/png"
MIME_JPEG: Final[str] = "image/jpeg"
MIME_WEBP: Final[str] = "image/webp"
MIME_UNKNOWN: Final[str] = "application/octet-stream"

PDF_MAGIC: Final[bytes] = b"%PDF"
PNG_MAGIC: Final[bytes] = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final[bytes] = b"\xff\xd8\xff"
RIFF_MAGIC: Final[bytes] = b"RIFF"
WEBP_MAGIC: Final[bytes] = b"WEBP"


def guess_mime(file_bytes: bytes) -> str:
    if not file_bytes:
        return MIME_UNKNOWN
    if file_bytes.startswith(PDF_MAGIC):
        return MIME_PDF
    if file_bytes.startswith(PNG_MAGIC):
        return MIME_PNG
    if file_bytes.startswith(JPEG_MAGIC):
        return MIME_JPEG
    if len(file_bytes) >= 12 and file_bytes[:4] == RIFF_MAGIC and file_bytes[8:12] == WEBP_MAGIC:
        return MIME_WEBP
    return MIME_UNKNOWN


def data_url(file_bytes: bytes, mime: str) -> str:
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"
