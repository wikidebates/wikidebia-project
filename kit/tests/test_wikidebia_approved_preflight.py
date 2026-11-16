from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest
import wikidebia_approved_preflight as approved_preflight
import wikidebia_remote_execute as execution
from test_wikidebia_remote_execute import make_approved_fixture


def test_signed_acceptance_prepares_readonly_preflight(tmp_path):
    project, debate_id, work_id, comparison_id, approved, adapter, _ = make_approved_fixture(tmp_path)
    result = approved_preflight.prepare_approved_preflight(
        project, debate_id, work_id, comparison_id, adapter=adapter,
    )
    assert result["status"] == "ready"
    assert result["accepted_plan_verified"] is True
    assert result["execution_authorized"] is False
    assert result["execution_started_by_command"] is False
    assert result["remote_write_performed"] is False
    assert not any(event[0] in {"write", "move", "delete"} for event in adapter.events)
    root = execution._execution_dir(project, debate_id, work_id, comparison_id)
    assert (root / "preflight-receipt.json").is_file()
    assert not (root / "execution-authorization.json").exists()
    events_before = list(adapter.events)
    again = approved_preflight.prepare_approved_preflight(
        project, debate_id, work_id, comparison_id, adapter=adapter,
    )
    assert again["preflight_reused"] is True
    assert adapter.events == events_before


def test_missing_acceptance_blocks_preflight_without_remote_access(monkeypatch, tmp_path):
    project, debate_id, work_id, comparison_id, approved, adapter, _ = make_approved_fixture(tmp_path)
    acceptance = (
        project / ".state" / "remote-plan-reviews" / debate_id / work_id
        / comparison_id / "plan-acceptance.json"
    )
    acceptance.unlink()
    monkeypatch.setattr(
        approved_preflight, "prepare_execution",
        lambda *a, **kw: pytest.fail("preflight must not run"),
    )
    with pytest.raises(execution.RemoteExecutionError):
        approved_preflight.prepare_approved_preflight(
            project, debate_id, work_id, comparison_id, adapter=adapter,
        )
    assert not execution._execution_dir(project, debate_id, work_id, comparison_id).exists()
