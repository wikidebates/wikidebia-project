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
