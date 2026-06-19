"""Unit tests for ``bearings.agent.workflow_watcher``.

Covers:
- :func:`_extract_session_id_from_path` — path → session_id mapping.
- :func:`_parse_journal` — JSON parsing + field extraction.
- :class:`WorkflowWatcher` — poll loop, deduplication, terminal detection.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from bearings.agent.workflow_watcher import (
    WorkflowProgressPublisher,
    WorkflowState,
    WorkflowWatcher,
    _extract_session_id_from_path,
    _parse_journal,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_journal(
    tmp_path: Path,
    *,
    sdk_uuid: str,
    run_id: str,
    workflow_name: str = "test-workflow",
    status: str = "running",
    current_phase: str | None = "Phase 1",
    agents: list[dict[str, object]] | None = None,
    start_time: int = 1_000_000_000_000,
) -> Path:
    """Write a minimal workflow journal to ``tmp_path`` and return its path."""
    slug = "test-project"
    wf_dir = tmp_path / slug / sdk_uuid / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    path = wf_dir / f"{run_id}.json"

    progress: list[dict[str, object]] = []
    if current_phase is not None:
        progress.append({"type": "workflow_phase", "index": 1, "title": current_phase})
    if agents:
        for i, ag in enumerate(agents, start=1):
            progress.append(
                {
                    "type": "workflow_agent",
                    "index": i,
                    "label": ag.get("label", f"agent-{i}"),
                    "phaseIndex": 1,
                    "phaseTitle": current_phase,
                    "agentId": ag.get("agentId", f"a{i:016x}"),
                    "state": ag.get("state", "queued"),
                }
            )

    data: dict[str, object] = {
        "runId": run_id,
        "workflowName": workflow_name,
        "status": status,
        "startTime": start_time,
        "workflowProgress": progress,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _make_publisher() -> MagicMock:
    """Return a mock :class:`WorkflowProgressPublisher`."""
    mock = MagicMock(spec=WorkflowProgressPublisher)
    return mock


# ---------------------------------------------------------------------------
# _extract_session_id_from_path
# ---------------------------------------------------------------------------


class TestExtractSessionIdFromPath:
    """``_extract_session_id_from_path`` maps UUID dirs to ses_<hex> ids."""

    def test_valid_uuid_path(self, tmp_path: Path) -> None:
        sdk_uuid = "5974a568-f5a9-8d8f-4cc9-f4b66e18ff43"
        path = tmp_path / "slug" / sdk_uuid / "workflows" / "wf_abc.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        result = _extract_session_id_from_path(path)
        assert result == "ses_5974a568f5a98d8f4cc9f4b66e18ff43"

    def test_path_too_short_returns_none(self) -> None:
        # Only 2 components — not deep enough
        path = Path("/wf_abc.json")
        result = _extract_session_id_from_path(path)
        assert result is None

    def test_invalid_uuid_returns_none(self, tmp_path: Path) -> None:
        # The UUID-position directory is not a valid UUID
        path = tmp_path / "slug" / "not-a-uuid" / "workflows" / "wf_abc.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        result = _extract_session_id_from_path(path)
        assert result is None


# ---------------------------------------------------------------------------
# _parse_journal
# ---------------------------------------------------------------------------


class TestParseJournal:
    """``_parse_journal`` extracts workflow state from a journal file."""

    def test_running_workflow(self, tmp_path: Path) -> None:
        sdk_uuid = "65646623-b36b-455f-a9a7-dcaec9224ea4"
        session_id = "ses_65646623b36b455fa9a7dcaec9224ea4"
        path = _make_journal(
            tmp_path,
            sdk_uuid=sdk_uuid,
            run_id="wf_test01",
            status="running",
            current_phase="Verify",
            agents=[
                {"state": "done"},
                {"state": "running"},
                {"state": "queued"},
            ],
            start_time=1_700_000_000_000,
        )
        result = _parse_journal(path, session_id)
        assert result is not None
        assert result.run_id == "wf_test01"
        assert result.status == "running"
        assert result.current_phase == "Verify"
        assert result.agents_done == 1
        assert result.agents_running == 1
        assert result.agents_queued == 1
        assert result.started_at == 1_700_000_000_000

    def test_completed_workflow(self, tmp_path: Path) -> None:
        path = _make_journal(
            tmp_path,
            sdk_uuid="5974a568-f5a9-8d8f-4cc9-f4b66e18ff43",
            run_id="wf_done01",
            status="completed",
            agents=[{"state": "done"}, {"state": "done"}],
        )
        result = _parse_journal(path, "ses_5974a568f5a98d8f4cc9f4b66e18ff43")
        assert result is not None
        assert result.status == "completed"
        assert result.agents_done == 2

    def test_killed_workflow(self, tmp_path: Path) -> None:
        path = _make_journal(
            tmp_path,
            sdk_uuid="5974a568-f5a9-8d8f-4cc9-f4b66e18ff43",
            run_id="wf_killed01",
            status="killed",
        )
        result = _parse_journal(path, "ses_5974a568f5a98d8f4cc9f4b66e18ff43")
        assert result is not None
        assert result.status == "killed"

    def test_no_phase_in_progress(self, tmp_path: Path) -> None:
        path = _make_journal(
            tmp_path,
            sdk_uuid="5974a568-f5a9-8d8f-4cc9-f4b66e18ff43",
            run_id="wf_nophase",
            current_phase=None,
        )
        result = _parse_journal(path, "ses_5974a568f5a98d8f4cc9f4b66e18ff43")
        assert result is not None
        assert result.current_phase is None

    def test_missing_run_id_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "test_no_run_id.json"
        path.write_text(json.dumps({"status": "running"}), encoding="utf-8")
        result = _parse_journal(path, "ses_00000000000000000000000000000000")
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("{not valid json", encoding="utf-8")
        result = _parse_journal(path, "ses_00000000000000000000000000000000")
        assert result is None

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "nonexistent.json"
        result = _parse_journal(path, "ses_00000000000000000000000000000000")
        assert result is None


# ---------------------------------------------------------------------------
# WorkflowWatcher
# ---------------------------------------------------------------------------


class TestWorkflowWatcherPollOnce:
    """``WorkflowWatcher._poll_once`` detects and fans out workflow changes."""

    def test_new_file_fans_out_event(self, tmp_path: Path) -> None:
        sdk_uuid = "5974a568-f5a9-8d8f-4cc9-f4b66e18ff43"
        session_id = "ses_5974a568f5a98d8f4cc9f4b66e18ff43"
        _make_journal(
            tmp_path,
            sdk_uuid=sdk_uuid,
            run_id="wf_abc001",
            status="running",
        )
        publisher = _make_publisher()
        watcher = WorkflowWatcher(publisher, projects_root=tmp_path, poll_interval_s=1.0)
        watcher._poll_once()

        publisher.publish_workflow_progress.assert_called_once()
        state: WorkflowState = publisher.publish_workflow_progress.call_args[0][0]
        assert state.run_id == "wf_abc001"
        assert state.session_id == session_id
        assert state.status == "running"

    def test_unchanged_file_not_re_emitted(self, tmp_path: Path) -> None:
        sdk_uuid = "5974a568-f5a9-8d8f-4cc9-f4b66e18ff43"
        _make_journal(
            tmp_path,
            sdk_uuid=sdk_uuid,
            run_id="wf_abc002",
            status="running",
        )
        publisher = _make_publisher()
        watcher = WorkflowWatcher(publisher, projects_root=tmp_path, poll_interval_s=1.0)
        watcher._poll_once()
        watcher._poll_once()  # second poll with same mtime → no new event

        # Still only one call despite two polls
        assert publisher.publish_workflow_progress.call_count == 1

    def test_terminal_status_emitted_once_then_skipped(self, tmp_path: Path) -> None:
        sdk_uuid = "5974a568-f5a9-8d8f-4cc9-f4b66e18ff43"
        path = _make_journal(
            tmp_path,
            sdk_uuid=sdk_uuid,
            run_id="wf_done02",
            status="completed",
        )
        publisher = _make_publisher()
        watcher = WorkflowWatcher(publisher, projects_root=tmp_path, poll_interval_s=1.0)
        watcher._poll_once()  # emits terminal event

        # Touch the file to change mtime
        path.write_text(path.read_text() + " ", encoding="utf-8")
        watcher._poll_once()  # file changed but run_id in _done → skipped

        assert publisher.publish_workflow_progress.call_count == 1
        state: WorkflowState = publisher.publish_workflow_progress.call_args[0][0]
        assert state.status == "completed"

    def test_killed_status_fans_out(self, tmp_path: Path) -> None:
        sdk_uuid = "5974a568-f5a9-8d8f-4cc9-f4b66e18ff43"
        _make_journal(
            tmp_path,
            sdk_uuid=sdk_uuid,
            run_id="wf_killed02",
            status="killed",
        )
        publisher = _make_publisher()
        watcher = WorkflowWatcher(publisher, projects_root=tmp_path, poll_interval_s=1.0)
        watcher._poll_once()

        publisher.publish_workflow_progress.assert_called_once()
        state: WorkflowState = publisher.publish_workflow_progress.call_args[0][0]
        assert state.status == "killed"

    def test_missing_projects_root_is_silent(self, tmp_path: Path) -> None:
        publisher = _make_publisher()
        watcher = WorkflowWatcher(
            publisher,
            projects_root=tmp_path / "nonexistent",
            poll_interval_s=1.0,
        )
        watcher._poll_once()  # must not raise
        publisher.publish_workflow_progress.assert_not_called()

    def test_multiple_sessions_multiple_workflows(self, tmp_path: Path) -> None:
        uuid_a = "5974a568-f5a9-8d8f-4cc9-f4b66e18ff43"
        uuid_b = "65646623-b36b-455f-a9a7-dcaec9224ea4"
        _make_journal(tmp_path, sdk_uuid=uuid_a, run_id="wf_multi01", status="running")
        _make_journal(tmp_path, sdk_uuid=uuid_b, run_id="wf_multi02", status="running")
        publisher = _make_publisher()
        watcher = WorkflowWatcher(publisher, projects_root=tmp_path, poll_interval_s=1.0)
        watcher._poll_once()

        assert publisher.publish_workflow_progress.call_count == 2
        session_ids = {
            c[0][0].session_id for c in publisher.publish_workflow_progress.call_args_list
        }
        assert "ses_5974a568f5a98d8f4cc9f4b66e18ff43" in session_ids
        assert "ses_65646623b36b455fa9a7dcaec9224ea4" in session_ids


class TestWorkflowWatcherInit:
    """``WorkflowWatcher`` constructor validation."""

    def test_zero_poll_interval_raises(self) -> None:
        publisher = _make_publisher()
        with pytest.raises(ValueError, match="poll_interval_s must be > 0"):
            WorkflowWatcher(publisher, poll_interval_s=0.0)

    def test_negative_poll_interval_raises(self) -> None:
        publisher = _make_publisher()
        with pytest.raises(ValueError, match="poll_interval_s must be > 0"):
            WorkflowWatcher(publisher, poll_interval_s=-1.0)


class TestWorkflowProgressPublisherProtocol:
    """The ``WorkflowProgressPublisher`` Protocol is satisfied at runtime."""

    def test_mock_satisfies_protocol(self) -> None:
        publisher = _make_publisher()
        # ``@runtime_checkable`` lets isinstance work
        assert isinstance(publisher, WorkflowProgressPublisher)
