# mypy: disable-error-code=explicit-any
"""Pending-operations REST endpoints (gap-cycle-03-010, N-10/R-3).

Thin HTTP adapter over :mod:`bearings.bearings_dir.pending`.  All
``.bearings/pending.toml`` I/O — including the POSIX-atomic write — lives
in the domain layer; this module maps domain exceptions to HTTP status
codes and nothing else.

Routes:

* ``GET /api/pending`` — list all pending operations for a project root.
  Returns ``list[PendingOpOut]`` (canonical source for PendingOpsCard /
  PendingOpsBadge).  Returns an empty list when the file does not exist.

* ``POST /api/pending/{name}/resolve`` — remove the named entry (resolved
  semantic).  Returns 204 on success; 404 when the name is absent.

* ``DELETE /api/pending/{name}`` — remove the named entry (dismissed
  semantic).  Behaviorally identical to the resolve endpoint; v0.17.x
  distinguished resolved vs dismissed via a flag, v1 does not.

Error responses:

* 404 — the named op is not present (or the file does not exist).
* 500 — OS-level write failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from bearings.bearings_dir import pending as bdir_pending

router = APIRouter()


# ---------------------------------------------------------------------------
# Wire shape — PendingOpOut
# ---------------------------------------------------------------------------


class PendingOpOut(BaseModel):
    """One row from ``.bearings/pending.toml`` as returned by the API."""

    name: str
    description: str
    started_at: str
    command: str | None = None
    dir: str | None = None


def _op_to_out(name: str, data: dict[str, Any]) -> PendingOpOut:
    """Convert a raw TOML op dict to :class:`PendingOpOut`."""
    return PendingOpOut(
        name=name,
        description=str(data.get("description", "")),
        started_at=str(data.get("started_at", "")),
        command=str(data["command"]) if "command" in data else None,
        dir=str(data["dir"]) if "dir" in data else None,
    )


# ---------------------------------------------------------------------------
# GET /api/pending
# ---------------------------------------------------------------------------


@router.get(
    "/api/pending",
    response_model=list[PendingOpOut],
    summary="List pending operations for a project",
    description=(
        "Returns all pending operations from ``.bearings/pending.toml`` "
        "in the given project directory, sorted oldest-first by "
        "``started_at``. Returns an empty list when the file does not "
        "exist (directory not yet onboarded, or no ops recorded)."
    ),
    operation_id="list-pending-ops",
)
async def list_pending_ops(
    directory: Annotated[
        str,
        Query(description="Absolute path to the project root."),
    ],
) -> list[PendingOpOut]:
    """Return all pending ops for *directory*, oldest-first."""
    _, ops = bdir_pending.load_ops(Path(directory))
    items = [_op_to_out(name, data) for name, data in ops.items()]
    # Sort oldest-first by started_at (ISO 8601 lex order is correct).
    items.sort(key=lambda op: op.started_at)
    return items


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def _remove(directory: str, name: str) -> None:
    """Delegate op removal to the domain layer, mapping exceptions to HTTP."""
    try:
        bdir_pending.remove_op(Path(directory), name)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no pending op named {name!r}",
        ) from None
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"could not update pending.toml: {exc}",
        ) from exc


@router.post(
    "/api/pending/{name}/resolve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark a pending operation as resolved",
    description=(
        "Removes the named entry from ``.bearings/pending.toml`` for "
        "the given project directory and persists the file. Returns 204 "
        "on success; 404 when the name is absent."
    ),
    operation_id="resolve-pending-op",
)
async def resolve_pending_op(
    name: str,
    directory: str = Query(..., description="Absolute path to the project root."),
) -> None:
    """Remove the named pending operation (resolved semantic)."""
    _remove(directory, name)


@router.delete(
    "/api/pending/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dismiss a pending operation",
    description=(
        "Removes the named entry from ``.bearings/pending.toml`` for "
        "the given project directory and persists the file. Behaviorally "
        "identical to the resolve endpoint. Returns 204 on success; 404 "
        "when the name is absent."
    ),
    operation_id="delete-pending-op",
)
async def delete_pending_op(
    name: str,
    directory: str = Query(..., description="Absolute path to the project root."),
) -> None:
    """Remove the named pending operation (dismissed semantic)."""
    _remove(directory, name)


__all__ = ["router"]
