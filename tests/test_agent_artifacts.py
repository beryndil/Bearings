"""Tests for the Phase-1 File Display auto-register hook.

The hook lives at `bearings.agent._artifacts.maybe_auto_register_image_artifact`
and is wired into `turn_executor.execute_turn` so a successful `Write`
of an image-MIME file under `settings.artifacts.serve_roots` registers
an artifact row and injects `![filename](/api/artifacts/{id})` into the
assistant's reply. Verifies the linked Bearings session
(`edaae9bad976411a86e8674665a3dac4`) Phase 1 contract end-to-end:

  * happy path — image Write ⇒ artifact row + injected markdown +
    streamed Token event for live subscribers;
  * non-image Write — text/markdown file ⇒ no row, no injection;
  * non-Write tool — Read/Edit ⇒ no row, no injection;
  * failed Write (`ok=False`) ⇒ no row, no injection;
  * path outside `serve_roots` ⇒ no row, no injection;
  * `artifacts_cfg=None` (no settings wired) ⇒ no row, no injection;
  * relative path — defensive, the SDK normally sends absolute paths,
    but a stray relative path must not register.

The fixtures here mirror `tests/test_runner.py`'s `ScriptedAgent` /
`db` shape so the assertions ride the same runner contract: a real
sqlite DB, a programmable event stream, and the runner's worker
draining one prompt at a time.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiosqlite
import pytest

from bearings.agent.events import (
    AgentEvent,
    MessageComplete,
    MessageStart,
    ToolCallEnd,
    ToolCallStart,
)
from bearings.agent.runner import SessionRunner
from bearings.agent.session import AgentSession
from bearings.config import ArtifactsCfg
from bearings.db import store
from bearings.db._artifacts import list_artifacts
from bearings.db._common import init_db

# Minimal valid PNG: 8-byte signature + IHDR chunk for a 1×1 image.
# Plenty for `mimetypes.guess_type` (which keys off the `.png`
# extension, not magic bytes) but real enough that `_hash_file` reads
# something deterministic.
_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
)


class ScriptedAgent(AgentSession):
    """Stripped-down stub from `test_runner.py`: yields one
    pre-programmed event sequence per turn. Tests in this file run a
    single turn each, so the script-list shape is one entry deep."""

    def __init__(self, session_id: str, scripts: list[list[AgentEvent]]) -> None:
        super().__init__(session_id, working_dir="/tmp", model="m")
        self._scripts = scripts
        self.prompts: list[str] = []

    async def stream(self, prompt: str) -> AsyncIterator[AgentEvent]:
        self.prompts.append(prompt)
        script = self._scripts.pop(0) if self._scripts else []
        for event in script:
            yield event


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    conn = await init_db(tmp_path / "artifacts-runner.sqlite")
    await store.create_session(conn, working_dir="/tmp", model="m", title="t")
    yield conn
    await conn.close()


@pytest.fixture
def serve_root(tmp_path: Path) -> Path:
    """Per-test artifacts root. The runner's `ArtifactsCfg` is pinned
    here so any path written outside `tmp_path` falls outside the
    allowlist and the hook refuses to register it — the same shape the
    real config uses (`$XDG_DATA_HOME/bearings/artifacts`)."""
    root = tmp_path / "artifacts"
    root.mkdir()
    return root


def _artifacts_cfg(serve_root: Path) -> ArtifactsCfg:
    """Mint a config pinned to a single per-test root. The default
    `max_register_size_mb=100` is generous enough that the test PNGs
    never trip the cap; tests that exercise the cap construct their
    own."""
    return ArtifactsCfg(
        artifacts_dir=serve_root,
        serve_roots=[serve_root],
    )


async def _session_id(conn: aiosqlite.Connection) -> str:
    rows = await store.list_sessions(conn)
    return rows[0]["id"]


def _write_script(
    sid: str,
    msg_id: str,
    *,
    tool_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    ok: bool = True,
    output: str = "wrote",
) -> list[AgentEvent]:
    """Canonical 5-event turn that exercises the hook: MessageStart →
    ToolCallStart → ToolCallEnd → MessageComplete (no token text — we
    want the hook's injection to be the *only* content in `buf`, so
    assertions about the persisted message content are unambiguous).
    """
    return [
        MessageStart(session_id=sid, message_id=msg_id),
        ToolCallStart(
            session_id=sid,
            tool_call_id=tool_id,
            name=tool_name,
            input=tool_input,
        ),
        ToolCallEnd(
            session_id=sid,
            tool_call_id=tool_id,
            ok=ok,
            output=output if ok else None,
            error=None if ok else "boom",
        ),
        MessageComplete(session_id=sid, message_id=msg_id, cost_usd=None),
    ]


async def _drain_until_complete(
    queue: asyncio.Queue[Any], timeout: float = 2.0
) -> list[dict[str, Any]]:
    """Pull envelopes off a runner subscriber queue until a
    `message_complete` lands. Returns the payload dicts in arrival
    order so tests can pattern-match on the synthetic Token frame the
    hook injects."""
    payloads: list[dict[str, Any]] = []
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise AssertionError("message_complete did not arrive within timeout")
        env = await asyncio.wait_for(queue.get(), timeout=remaining)
        payloads.append(env.payload)
        if env.payload["type"] == "message_complete":
            return payloads


async def _run_one_turn(runner: SessionRunner, prompt: str = "do it") -> list[dict[str, Any]]:
    queue, _ = await runner.subscribe(0)
    runner.start()
    try:
        await runner.submit_prompt(prompt)
        return await _drain_until_complete(queue)
    finally:
        await runner.shutdown()


@pytest.mark.asyncio
async def test_image_write_under_serve_root_auto_registers(
    db: aiosqlite.Connection, serve_root: Path
) -> None:
    """Phase-1 happy path: a successful `Write` to an image under
    `serve_roots` registers an artifact, injects the markdown image
    into the persisted message content, and emits a synthetic Token
    so live subscribers render it without waiting for a reload."""
    sid = await _session_id(db)
    image = serve_root / "diagram.png"
    image.write_bytes(_PNG_BYTES)

    script = _write_script(
        sid,
        "msg-1",
        tool_id="tool-1",
        tool_name="Write",
        tool_input={"file_path": str(image)},
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        artifacts_cfg=_artifacts_cfg(serve_root),
    )
    payloads = await _run_one_turn(runner)

    # Exactly one artifact row was registered.
    rows = await list_artifacts(db, sid)
    assert len(rows) == 1
    artifact = rows[0]
    assert artifact["filename"] == "diagram.png"
    assert artifact["mime_type"] == "image/png"
    assert artifact["size_bytes"] == len(_PNG_BYTES)
    assert artifact["path"] == str(image.resolve())

    # Injected markdown lives in the persisted assistant message AND
    # arrived as a synthetic Token frame on the live wire.
    expected_md = f"![diagram.png](/api/artifacts/{artifact['id']})"
    persisted = await store.list_messages(db, sid)
    assistant = next(row for row in persisted if row["role"] == "assistant")
    assert expected_md in assistant["content"]

    token_payloads = [p for p in payloads if p["type"] == "token"]
    assert any(expected_md in p["text"] for p in token_payloads), (
        "expected synthetic Token frame carrying the auto-registered "
        f"artifact markdown; saw: {[p.get('text') for p in token_payloads]}"
    )


@pytest.mark.asyncio
async def test_non_image_write_does_not_register(
    db: aiosqlite.Connection, serve_root: Path
) -> None:
    """Phase-1 scope is image-MIME only. A `Write` of a markdown file
    (or any non-image type) under `serve_roots` does not register and
    does not inject. The Phase 3-4 office / PDF previews handle those
    types separately."""
    sid = await _session_id(db)
    notes = serve_root / "notes.md"
    notes.write_text("# nope\n")

    script = _write_script(
        sid,
        "msg-2",
        tool_id="tool-2",
        tool_name="Write",
        tool_input={"file_path": str(notes)},
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        artifacts_cfg=_artifacts_cfg(serve_root),
    )
    await _run_one_turn(runner)

    assert await list_artifacts(db, sid) == []
    persisted = await store.list_messages(db, sid)
    assistant = next(row for row in persisted if row["role"] == "assistant")
    assert "/api/artifacts/" not in assistant["content"]


@pytest.mark.asyncio
async def test_non_write_tool_does_not_register(db: aiosqlite.Connection, serve_root: Path) -> None:
    """Read / Edit / Bash tools must not auto-register, even if their
    input dict happens to carry a path argument that points at an
    image. Phase 1 is intentionally narrow: only the `Write` tool
    auto-registers. Edit-tool support is deferred."""
    sid = await _session_id(db)
    image = serve_root / "diagram.png"
    image.write_bytes(_PNG_BYTES)

    script = _write_script(
        sid,
        "msg-3",
        tool_id="tool-3",
        tool_name="Read",
        tool_input={"file_path": str(image)},
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        artifacts_cfg=_artifacts_cfg(serve_root),
    )
    await _run_one_turn(runner)
    assert await list_artifacts(db, sid) == []


@pytest.mark.asyncio
async def test_failed_write_does_not_register(db: aiosqlite.Connection, serve_root: Path) -> None:
    """A `Write` that ended with `ok=False` produced no file the
    server can serve. The hook bails before touching the FS so a
    failed call doesn't leave a phantom artifact row."""
    sid = await _session_id(db)
    image = serve_root / "diagram.png"
    image.write_bytes(_PNG_BYTES)

    script = _write_script(
        sid,
        "msg-4",
        tool_id="tool-4",
        tool_name="Write",
        tool_input={"file_path": str(image)},
        ok=False,
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        artifacts_cfg=_artifacts_cfg(serve_root),
    )
    await _run_one_turn(runner)
    assert await list_artifacts(db, sid) == []


@pytest.mark.asyncio
async def test_path_outside_serve_root_does_not_register(
    db: aiosqlite.Connection, tmp_path: Path, serve_root: Path
) -> None:
    """An image written outside the configured roots — even one the
    SDK could plausibly produce — is not registerable. This is the
    same gate `routes_artifacts.register_artifact` enforces; the hook
    must respect it identically so the auto path can't widen what the
    HTTP path is allowed to expose."""
    sid = await _session_id(db)
    outside = tmp_path / "outside-root.png"
    outside.write_bytes(_PNG_BYTES)

    script = _write_script(
        sid,
        "msg-5",
        tool_id="tool-5",
        tool_name="Write",
        tool_input={"file_path": str(outside)},
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        artifacts_cfg=_artifacts_cfg(serve_root),
    )
    await _run_one_turn(runner)
    assert await list_artifacts(db, sid) == []


@pytest.mark.asyncio
async def test_no_artifacts_cfg_disables_hook(db: aiosqlite.Connection, serve_root: Path) -> None:
    """Runners constructed without `artifacts_cfg` (today: every test
    that doesn't opt in, plus any future harness that bypasses
    `ws_agent`) treat the hook as inert. No magic global config —
    `None` is the off switch."""
    sid = await _session_id(db)
    image = serve_root / "diagram.png"
    image.write_bytes(_PNG_BYTES)

    script = _write_script(
        sid,
        "msg-6",
        tool_id="tool-6",
        tool_name="Write",
        tool_input={"file_path": str(image)},
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        # artifacts_cfg defaults to None
    )
    await _run_one_turn(runner)
    assert await list_artifacts(db, sid) == []


@pytest.mark.asyncio
async def test_relative_path_does_not_register(db: aiosqlite.Connection, serve_root: Path) -> None:
    """Defensive: the SDK normally hands absolute paths, but if a
    relative path slips through, the hook must refuse to register
    rather than resolve it against the runner's CWD (which is
    arbitrary in tests and would otherwise grant access to whatever
    `Path.cwd()` happens to be)."""
    sid = await _session_id(db)
    image = serve_root / "diagram.png"
    image.write_bytes(_PNG_BYTES)

    script = _write_script(
        sid,
        "msg-7",
        tool_id="tool-7",
        tool_name="Write",
        tool_input={"file_path": "diagram.png"},  # relative
    )
    runner = SessionRunner(
        sid,
        ScriptedAgent(sid, scripts=[script]),
        db,
        artifacts_cfg=_artifacts_cfg(serve_root),
    )
    await _run_one_turn(runner)
    assert await list_artifacts(db, sid) == []
