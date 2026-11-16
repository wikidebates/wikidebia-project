"""Execution receipt identity must be checked before work closure."""
from __future__ import annotations

import pytest
import wikidebia_work_close as closure


@pytest.mark.parametrize("field,value", [
    ("debate_id", "foreign"),
    ("work_id", "EDIT-20261113-999"),
    ("comparison_id", "REMOTE-20261115-999"),
    ("mode", "invalid"),
])
def test_execution_receipt_identity_or_scope_rejected(tmp_path, monkeypatch, field, value):
    receipt = {
        "schema": closure.EXECUTION_RECEIPT_SCHEMA,
        "debate_id": "example",
        "work_id": "EDIT-20261113-002",
        "comparison_id": "REMOTE-20261115-001",
        "mode": "en",
    }
    receipt[field] = value
    receipt["receipt_sha256"] = closure._canonical(receipt, "receipt_sha256")
    execution_dir = (tmp_path / ".state/remote-executions/example"
                     / "EDIT-20261113-002/REMOTE-20261115-001")
    execution_dir.mkdir(parents=True)
    for filename in ("execution-receipt.json", "execution-preflight.json",
                     "execution-authorization.json", "execution-events.jsonl"):
        (execution_dir / filename).write_text("{}", encoding="utf-8")
    workspace = tmp_path / "workspace"
    (workspace / "release-copy").mkdir(parents=True)
    monkeypatch.setattr(closure, "_load_workspace", lambda *args: (
        workspace, {"status": "remote_execution_completed",
                    "release_copy": {"tree_sha256": "tree"},
                    "remote_execution": {"mode": "en"}}))
    monkeypatch.setattr(closure, "full_tree_sha256", lambda path: "tree")
    original_load = closure.load_json
    monkeypatch.setattr(closure, "load_json", lambda path, label: (
        receipt if path.name == "execution-receipt.json" else original_load(path, label)))
    with pytest.raises(closure.WorkClosureError, match="autre débat|Périmètre"):
        closure._load_execution(tmp_path, "example", "EDIT-20261113-002",
                                "REMOTE-20261115-001", receipt["receipt_sha256"])
