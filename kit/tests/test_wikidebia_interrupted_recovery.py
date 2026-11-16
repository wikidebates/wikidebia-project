from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest
import wikidebia_interrupted_audit as audit
import wikidebia_interrupted_recovery as recovery
import wikidebia_remote_execute as execution
from test_wikidebia_interrupted_audit import _interrupted


def _audited(tmp_path):
    project, debate_id, work_id, comparison_id, prepared, adapter, _, root = _interrupted(tmp_path)
    result = audit.audit_interrupted_execution(
        project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter
    )
    return project, debate_id, work_id, comparison_id, root, result


def test_recovery_creates_new_readonly_comparison_without_approving(monkeypatch, tmp_path):
    project, debate_id, work_id, old_id, root, result = _audited(tmp_path)
    calls = []
    def fake_compare(*args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "plan_ready", "comparison_id": "REMOTE-20261116-999", "remote_write_performed": False}
    monkeypatch.setattr(recovery, "compare_workspace", fake_compare)
    source_path = project / ".state/remote-comparisons" / debate_id / work_id / old_id / "comparison-receipt.json"
    scope = json.loads(source_path.read_text())["scope"]
    output = recovery.prepare_fresh_recovery_comparison(
        project, debate_id, work_id, old_id, scope=scope, comparison_id="REMOTE-20261116-999"
    )
    assert len(calls) == 1
    assert calls[0][1]["adapter"] is None
    assert calls[0][1]["scope"] == scope
    assert output["recovery_source_audit_sha256"] == result["audit_sha256"]
    assert output["original_execution_replayed"] is False
    assert output["new_plan_automatically_approved"] is False
    assert output["remote_write_performed"] is False
    assert not (root / "execution-receipt.json").exists()


def test_recovery_refuses_tampered_audit_before_remote_access(monkeypatch, tmp_path):
    project, debate_id, work_id, old_id, root, _ = _audited(tmp_path)
    path = root / "interrupted-audit.json"
    data = json.loads(path.read_text())
    data["attribution_verified"] = True
    path.write_text(json.dumps(data))
    monkeypatch.setattr(recovery, "compare_workspace", lambda *a, **kw: pytest.fail("remote access"))
    with pytest.raises(execution.RemoteExecutionError, match="Empreinte de l’audit"):
        recovery.prepare_fresh_recovery_comparison(project, debate_id, work_id, old_id)


def test_recovery_refuses_same_comparison_id_before_remote_access(monkeypatch, tmp_path):
    project, debate_id, work_id, old_id, root, _ = _audited(tmp_path)
    monkeypatch.setattr(recovery, "compare_workspace", lambda *a, **kw: pytest.fail("remote access"))
    with pytest.raises(execution.RemoteExecutionError, match="nouvel identifiant"):
        recovery.prepare_fresh_recovery_comparison(project, debate_id, work_id, old_id, comparison_id=old_id)
