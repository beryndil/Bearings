"""Database layer for Bearings v1.

Per ``docs/architecture-v1.md`` §1.1.3, the ``bearings.db`` package owns the
SQLite schema and per-resource query modules. The ``connection`` module
exposes the bootstrap entry points downstream items import; the canonical
DDL lives in ``schema.sql`` and is read once per process.

Re-exporting the two bootstrap callables here is the only re-export wall in
this package (the architecture doc explicitly forbids a god ``store.py``);
keeping the public surface visible from ``bearings.db`` itself avoids the
``from bearings.db.connection import ...`` boilerplate at every call site.
"""

from __future__ import annotations

from bearings.db.connection import get_connection_factory, load_schema

__all__ = ["get_connection_factory", "load_schema"]
