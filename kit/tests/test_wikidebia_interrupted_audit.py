from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest
import wikidebia_interrupted_audit as audit
import wikidebia_remote_execute as execution
from test_wikidebia_remote_execute import make_approved_fixture


def _interrupted(tmp_path):
    project, debate_id, work_id, comparison_id, approved, adapter, text = make_approved_fixture(tmp_path)
    prepared = execution.prepare_execution(
        project, debate_id, work_id, comparison_id, approved["acceptance_sha256"], adapter=adapter
    )
    root = project / ".state/remote-executions" / debate_id / work_id / comparison_id
    authorization = {
        "schema": execution.AUTHORIZATION_SCHEMA, "debate_id": debate_id,
        "work_id": work_id, "comparison_id": comparison_id,
        "plan_sha256": json.loads((project / ".state/remote-comparisons" / debate_id / work_id / comparison_id / "update-plan.json").read_text())["plan_sha256"],
        "acceptance_sha256": approved["acceptance_sha256"],
        "preflight_sha256": prepared["preflight_sha256"], "mode": "all",
        "execution_started": True, "remote_write_authorized": True,
    }
    authorization["authorization_sha256"] = execution._canonical(authorization, "authorization_sha256")
    (root / "execution-authorization.json").write_text(json.dumps(authorization), encoding="utf-8")
    return project, debate_id, work_id, comparison_id, prepared, adapter, text, root


def test_audit_reports_remote_matches_without_writing_or_releasing(tmp_path):
    project, debate_id, work_id, comparison_id, prepared, adapter, text, root = _interrupted(tmp_path)
    adapter.pages[("fr", "Argument final")] = (123, text)
    before = list(adapter.events)
    result = audit.audit_interrupted_execution(
        project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter
    )
    assert result["status"] == "requires_manual_reconciliation"
    assert result["observed_matching_or_absent_count"] == 1
    assert result["observed_matching_content_count"] == 1
    assert result["observed_absent_delete_count"] == 0
    assert result["unresolved_operation_count"] == 0
    assert result["recovery_decision"] == "observed_final_state_only"
    assert result["automatic_replay_allowed"] is False
    assert result["attribution_verified"] is False
    assert result["remote_write_performed"] is False
    assert result["execution_receipt_reconstructed"] is False
    assert not any(e[0] in {"write", "move", "delete"} for e in adapter.events[len(before):])
    assert (root / "interrupted-audit.json").is_file()
    assert not (root / "execution-receipt.json").exists()


def test_audit_rejects_tampered_authorization_without_remote_access(tmp_path):
    project, debate_id, work_id, comparison_id, prepared, adapter, _, root = _interrupted(tmp_path)
    path = root / "execution-authorization.json"
    value = json.loads(path.read_text())
    value["work_id"] = "EDIT-OTHER-999"
    path.write_text(json.dumps(value), encoding="utf-8")
    before = list(adapter.events)
    with pytest.raises(execution.RemoteExecutionError, match="altérée"):
        audit.audit_interrupted_execution(
            project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter
        )
    assert adapter.events == before


def test_audit_refuses_to_overwrite_existing_evidence(tmp_path):
    project, debate_id, work_id, comparison_id, prepared, adapter, _, root = _interrupted(tmp_path)
    (root / "interrupted-audit.json").write_text("{}", encoding="utf-8")
    before = list(adapter.events)
    with pytest.raises(execution.RemoteExecutionError, match="Audit précédent"):
        audit.audit_interrupted_execution(
            project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter
        )
    assert adapter.events == before


def test_audit_classifies_unresolved_remote_operations(tmp_path):
    project, debate_id, work_id, comparison_id, prepared, adapter, _, root = _interrupted(tmp_path)
    result = audit.audit_interrupted_execution(
        project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter
    )
    assert result["unresolved_operation_count"] == 1
    assert result["recovery_decision"] == "requires_fresh_comparison_and_acceptance"
    assert result["automatic_replay_allowed"] is False
    assert result["fresh_plan_required_before_any_write"] is True
    assert not (root / "execution-receipt.json").exists()
