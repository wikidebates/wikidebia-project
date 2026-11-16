"""Fail-closed tests for discovery of a signed local release candidate."""
from __future__ import annotations

import pytest
from wikidebia_review_workflow import _find_unique_releasable_work, WorkflowError


def test_no_workspaces_refuses_automatic_adoption(tmp_path):
    with pytest.raises(WorkflowError, match="Aucun Work"):
        _find_unique_releasable_work(tmp_path, "example")


def test_malformed_workspace_is_not_adopted(tmp_path):
    directory = tmp_path / ".state/editorial-workspaces/example/EDIT-20261113-002"
    directory.mkdir(parents=True)
    (directory / "workspace.json").write_text('{"status":"release_ready"}', encoding="utf-8")
    with pytest.raises(WorkflowError, match="Aucun Work"):
        _find_unique_releasable_work(tmp_path, "example")


def _candidate(tmp_path, monkeypatch, work_id, *, signed=True):
    import wikidebia_review_workflow as workflow
    directory = tmp_path / ".state/editorial-workspaces/example" / work_id
    (directory / "release-copy").mkdir(parents=True)
    (directory / "workspace.json").write_text("{}", encoding="utf-8")
    receipt_path = (tmp_path / ".state/corpus-releases/example" / work_id
                    / "release-receipt.json")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text("{}", encoding="utf-8")
    meta = {
        "debate_id": "example", "work_id": work_id,
        "status": "release_ready", "workspace_sha256": "valid",
        "release_copy": {"tree_sha256": "tree"},
    }
    receipt = {
        "debate_id": "example", "work_id": work_id,
        "release_copy_tree_sha256": "tree", "publication_started": False,
    }
    receipt["receipt_sha256"] = workflow._sha256_bytes(workflow._canonical_json(receipt))
    if not signed:
        receipt["receipt_sha256"] = "bad"
    original_load = workflow.load_json

    def load(path, label):
        if path == directory / "workspace.json":
            return meta
        if path == receipt_path:
            return receipt
        return original_load(path, label)

    return directory, load


def test_unique_valid_candidate_is_selected(tmp_path, monkeypatch):
    import wikidebia_review_workflow as workflow
    directory, load = _candidate(tmp_path, monkeypatch, "EDIT-20261113-002")
    monkeypatch.setattr(workflow, "load_json", load)
    monkeypatch.setattr(workflow, "workspace_receipt_hash", lambda meta: "valid")
    monkeypatch.setattr(workflow, "full_tree_sha256", lambda path: "tree")
    assert workflow._find_unique_releasable_work(tmp_path, "example") == directory.name


def test_two_valid_candidates_require_explicit_choice(tmp_path, monkeypatch):
    import wikidebia_review_workflow as workflow
    first, load_first = _candidate(tmp_path, monkeypatch, "EDIT-20261113-002")
    second, load_second = _candidate(tmp_path, monkeypatch, "EDIT-20261113-003")
    original_load = workflow.load_json

    def load(path, label):
        if path in {first / "workspace.json",
                    tmp_path / ".state/corpus-releases/example" / first.name / "release-receipt.json"}:
            return load_first(path, label)
        return load_second(path, label)

    monkeypatch.setattr(workflow, "load_json", load)
    monkeypatch.setattr(workflow, "workspace_receipt_hash", lambda meta: "valid")
    monkeypatch.setattr(workflow, "full_tree_sha256", lambda path: "tree")
    with pytest.raises(WorkflowError, match="Plusieurs Work"):
        workflow._find_unique_releasable_work(tmp_path, "example")


def test_invalid_receipt_hash_is_rejected(tmp_path, monkeypatch):
    import wikidebia_review_workflow as workflow
    _, load = _candidate(tmp_path, monkeypatch, "EDIT-20261113-002", signed=False)
    monkeypatch.setattr(workflow, "load_json", load)
    monkeypatch.setattr(workflow, "workspace_receipt_hash", lambda meta: "valid")
    monkeypatch.setattr(workflow, "full_tree_sha256", lambda path: "tree")
    with pytest.raises(WorkflowError, match="Aucun Work"):
        workflow._find_unique_releasable_work(tmp_path, "example")
