# mypy: disable-error-code=explicit-any
"""Pydantic wire shapes for ``routes/uploads.py`` (item 1.10).

Per ``docs/architecture-v1.md`` §1.1.5 the misc-API uploads endpoint
accepts ``multipart/form-data`` and returns a JSON metadata envelope.
The behavior docs are silent on the wire shape; the contract is
decided-and-documented in
``src/bearings/config/constants.py`` §"Uploads".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UploadOut(BaseModel):
    """One upload row, as returned by POST/GET endpoints."""

    model_config = ConfigDict(extra="forbid")

    id: int
    sha256: str
    filename: str
    mime_type: str
    size: int
    created_at: int


class UploadListOut(BaseModel):
    """Response shape for ``GET /api/uploads``."""

    model_config = ConfigDict(extra="forbid")

    uploads: list[UploadOut]


__all__ = ["UploadListOut", "UploadOut"]
