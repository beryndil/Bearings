"""Unit tests for ``scripts/consistency_lint.py`` (master item 3.1).

The script is the cross-system convention guard; these tests exercise
each rule's positive (clean fixture) and negative (violation fixture)
paths so a future tweak to the rule can't quietly weaken the gate
without a test failure.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Final

import pytest

# Resolve the script as a module — it is not import-installed (lives
# under ``scripts/``, not ``src/``), so we load via spec.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_SCRIPT_PATH: Final[Path] = _REPO_ROOT / "scripts" / "consistency_lint.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("consistency_lint", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["consistency_lint"] = module
    spec.loader.exec_module(module)
    return module


cl = _load_script_module()


# ---------------------------------------------------------------------------
# End-to-end: the live repo passes every rule.
# ---------------------------------------------------------------------------


def test_live_repo_is_clean() -> None:
    """The current repo state has zero findings across every rule."""
    findings = cl.run_rules(_REPO_ROOT, cl.ALL_RULES)
    assert findings == [], "\n".join(f.render(_REPO_ROOT) for f in findings)


# ---------------------------------------------------------------------------
# Rule 1 — route handler naming
# ---------------------------------------------------------------------------


def _write_route(tmp_path: Path, body: str) -> Path:
    routes_dir = tmp_path / "src" / "bearings" / "web" / "routes"
    routes_dir.mkdir(parents=True, exist_ok=True)
    path = routes_dir / "fixture.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_route_naming_clean(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int) -> dict[str, int]:
    return {"id": thing_id}

@router.post("/api/things")
async def create_thing() -> dict[str, str]:
    return {"ok": "yes"}
""",
    )
    assert cl.check_route_handler_naming(tmp_path) == []


def test_route_naming_rejects_camel_case(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def getThing(thing_id: int) -> dict[str, int]:
    return {"id": thing_id}
""",
    )
    findings = cl.check_route_handler_naming(tmp_path)
    assert len(findings) == 1
    assert "snake_case" in findings[0].message


def test_route_naming_rejects_unknown_verb(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def fetch_thing(thing_id: int) -> dict[str, int]:
    return {"id": thing_id}
""",
    )
    findings = cl.check_route_handler_naming(tmp_path)
    assert len(findings) == 1
    assert "fetch" in findings[0].message
    assert "approved verb vocabulary" in findings[0].message


def test_route_naming_ignores_undecorated_helpers(tmp_path: Path) -> None:
    """Module-level helpers without ``@router`` decorators are not handlers."""
    _write_route(
        tmp_path,
        '''
from fastapi import APIRouter
router = APIRouter()

def fetchThing(thing_id: int) -> dict[str, int]:
    """Free helper — not registered as a route, so the rule skips it."""
    return {"id": thing_id}
''',
    )
    assert cl.check_route_handler_naming(tmp_path) == []


# ---------------------------------------------------------------------------
# Rule 2 — error response shape
# ---------------------------------------------------------------------------


def test_error_shape_accepts_string_literal(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter, HTTPException, status
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int) -> dict[str, int]:
    if thing_id < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="negative id")
    return {"id": thing_id}
""",
    )
    assert cl.check_error_shape(tmp_path) == []


def test_error_shape_accepts_fstring(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter, HTTPException, status
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int) -> dict[str, int]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"item {thing_id} not found",
    )
""",
    )
    assert cl.check_error_shape(tmp_path) == []


def test_error_shape_accepts_str_call(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter, HTTPException, status
router = APIRouter()

@router.post("/api/things")
async def create_thing() -> dict[str, int]:
    try:
        return {"id": 1}
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
""",
    )
    assert cl.check_error_shape(tmp_path) == []


def test_error_shape_accepts_or_fallback(tmp_path: Path) -> None:
    """The ``result.detail or "fallback"`` pattern (BoolOp) is allowed."""
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter, HTTPException, status
router = APIRouter()

class _Result:
    detail: str | None = None

@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int) -> dict[str, int]:
    result = _Result()
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=result.detail or f"no thing matches {thing_id!r}",
    )
""",
    )
    assert cl.check_error_shape(tmp_path) == []


def test_error_shape_rejects_dict_detail(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter, HTTPException, status
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int) -> dict[str, int]:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"reason": "not found", "id": thing_id},
    )
""",
    )
    findings = cl.check_error_shape(tmp_path)
    assert len(findings) == 1
    assert "string-typed" in findings[0].message


def test_error_shape_rejects_missing_detail(tmp_path: Path) -> None:
    _write_route(
        tmp_path,
        """
from fastapi import APIRouter, HTTPException, status
router = APIRouter()

@router.get("/api/things/{thing_id}")
async def get_thing(thing_id: int) -> dict[str, int]:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
""",
    )
    findings = cl.check_error_shape(tmp_path)
    assert len(findings) == 1
    assert "missing" in findings[0].message


# ---------------------------------------------------------------------------
# Rule 3 — SQL conventions
# ---------------------------------------------------------------------------


def _write_schema(tmp_path: Path, sql: str) -> Path:
    db_dir = tmp_path / "src" / "bearings" / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    path = db_dir / "schema.sql"
    path.write_text(sql, encoding="utf-8")
    return path


def test_sql_conventions_clean(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        """
CREATE TABLE IF NOT EXISTS widgets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_widgets_name ON widgets(name);

CREATE TABLE IF NOT EXISTS widget_tags (
    widget_id   INTEGER NOT NULL,
    tag_id      INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (widget_id, tag_id),
    FOREIGN KEY (widget_id) REFERENCES widgets(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)    REFERENCES tags(id)    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_widget_tags_tag_id ON widget_tags(tag_id);
""",
    )
    assert cl.check_sql_conventions(tmp_path) == []


def test_sql_rejects_non_id_first_column(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        """
CREATE TABLE IF NOT EXISTS widgets (
    name        TEXT NOT NULL,
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL
);
""",
    )
    findings = cl.check_sql_conventions(tmp_path)
    assert len(findings) == 1
    assert "first column is 'name'" in findings[0].message


def test_sql_rejects_fk_without_on_delete(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        """
CREATE TABLE IF NOT EXISTS widgets (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER,
    FOREIGN KEY (parent_id) REFERENCES widgets(id)
);
""",
    )
    findings = cl.check_sql_conventions(tmp_path)
    assert len(findings) == 1
    assert "ON DELETE" in findings[0].message


def test_sql_rejects_misnamed_index(tmp_path: Path) -> None:
    _write_schema(
        tmp_path,
        """
CREATE TABLE IF NOT EXISTS widgets (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS widgets_by_name ON widgets(name);
""",
    )
    findings = cl.check_sql_conventions(tmp_path)
    assert len(findings) == 1
    assert "idx_widgets_" in findings[0].message


# ---------------------------------------------------------------------------
# Rule 4 — Svelte prop conventions
# ---------------------------------------------------------------------------


def _write_svelte(tmp_path: Path, body: str, name: str = "Widget.svelte") -> Path:
    components_dir = tmp_path / "frontend" / "src" / "lib" / "components" / "fixture"
    components_dir.mkdir(parents=True, exist_ok=True)
    path = components_dir / name
    path.write_text(body, encoding="utf-8")
    return path


def test_svelte_clean_destructured(tmp_path: Path) -> None:
    _write_svelte(
        tmp_path,
        """
<script lang="ts">
  interface Props {
    label: string;
  }
  const { label }: Props = $props();
</script>

<span>{label}</span>
""",
    )
    assert cl.check_svelte_props(tmp_path) == []


def test_svelte_clean_named_for_discriminated_union(tmp_path: Path) -> None:
    """``const props: Props = $props()`` is also accepted (discriminated unions)."""
    _write_svelte(
        tmp_path,
        """
<script lang="ts">
  type Props = { kind: "a"; payload: number } | { kind: "b" };
  const props: Props = $props();
</script>

{#if props.kind === "a"}
  <span>{props.payload}</span>
{/if}
""",
    )
    assert cl.check_svelte_props(tmp_path) == []


def test_svelte_clean_propless_component(tmp_path: Path) -> None:
    """Components that don't call ``$props()`` are unaffected."""
    _write_svelte(
        tmp_path,
        """
<script lang="ts">
  let count = $state(0);
</script>

<button onclick={() => count++}>{count}</button>
""",
    )
    assert cl.check_svelte_props(tmp_path) == []


def test_svelte_rejects_missing_props_interface(tmp_path: Path) -> None:
    _write_svelte(
        tmp_path,
        """
<script lang="ts">
  const { label } = $props();
</script>

<span>{label}</span>
""",
    )
    findings = cl.check_svelte_props(tmp_path)
    assert len(findings) >= 1
    rules = {f.message for f in findings}
    assert any("interface Props" in m or "type Props" in m for m in rules)


def test_svelte_rejects_export_let_legacy(tmp_path: Path) -> None:
    _write_svelte(
        tmp_path,
        """
<script lang="ts">
  export let label: string;
</script>

<span>{label}</span>
""",
    )
    findings = cl.check_svelte_props(tmp_path)
    assert any("export let" in f.message for f in findings)


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def test_main_returns_zero_on_clean_repo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cl.main(["--repo-root", str(_REPO_ROOT)])
    assert rc == cl.EXIT_OK
    captured = capsys.readouterr()
    assert "clean" in captured.err


def test_main_returns_one_on_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_schema(
        tmp_path,
        """
CREATE TABLE IF NOT EXISTS widgets (
    name TEXT NOT NULL,
    id   INTEGER PRIMARY KEY
);
""",
    )
    rc = cl.main(["--repo-root", str(tmp_path), "--rule", cl.RULE_SQL_ORDERING])
    assert rc == cl.EXIT_FINDINGS
    captured = capsys.readouterr()
    assert cl.RULE_SQL_ORDERING in captured.out


def test_main_rule_filter_isolates_one_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--rule X`` runs only X; other rule violations are not surfaced."""
    # SQL rule violation present but we only ask for the route-naming rule.
    _write_schema(
        tmp_path,
        """
CREATE TABLE IF NOT EXISTS widgets (
    name TEXT NOT NULL
);
""",
    )
    rc = cl.main(["--repo-root", str(tmp_path), "--rule", cl.RULE_ROUTE_NAMING])
    assert rc == cl.EXIT_OK
    captured = capsys.readouterr()
    assert cl.RULE_SQL_ORDERING not in captured.out
