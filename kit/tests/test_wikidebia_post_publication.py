from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_post_publication as post
from wikidebia_corpus_build import full_tree_sha256
from wikidebia_editorial_workspace import workspace_receipt_hash
from wikidebia_update import sha_object


DEBATE = "debat_test"
WORK = "EDIT-TEST-001"


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _signed(value: dict, field: str) -> dict:
    value[field] = sha_object(value)
    return value


def _fixture(project: Path) -> tuple[Path, dict]:
    workspace = project / f".state/editorial-workspaces/{DEBATE}/{WORK}"
    release = workspace / "release-copy"
    release.mkdir(parents=True)
    (release / "manifest.json").write_text('{"pages": []}\n', encoding="utf-8")
    active = project / f"corpus/{DEBATE}"
    active.mkdir(parents=True)
    (active / "manifest.json").write_text('{"pages": []}\n', encoding="utf-8")
    tree = full_tree_sha256(release)
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0",
        "schema_version": "1.0",
        "debate_id": DEBATE,
        "work_id": WORK,
        "status": "release_ready",
        "release_copy": {"tree_sha256": tree},
        "workspace_sha256": None,
    }
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    _write(workspace / "workspace.json", meta)
    baseline = _signed({
        "schema": post.BASELINE_SCHEMA,
        "schema_version": "1.0",
        "debate_id": DEBATE,
        "work_id": WORK,
        "release": {"release_copy_tree_sha256": tree},
    }, "baseline_sha256")
    publication = _signed({
        "schema": post.FINAL_PUBLICATION_SCHEMA,
        "schema_version": "1.0",
        "debate_id": DEBATE,
        "work_id": WORK,
        "status": "published",
        "baseline_sha256": baseline["baseline_sha256"],
        "installed_release": {
            "status": "installed",
            "path": f"corpus/{DEBATE}",
            "tree_sha256": tree,
        },
    }, "receipt_sha256")
    final_root = project / f".state/final-publication/{DEBATE}/{WORK}"
    _write(final_root / "baseline.json", baseline)
    _write(final_root / "publication-receipt.json", publication)
    _write(project / f".state/workflows/{DEBATE}/workflow.json", {
        "schema": post.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": DEBATE,
        "work_id": WORK,
        "phase": "published",
        "status": "published",
        "final_publication": publication,
    })
    return workspace, meta


def test_reconciliation_seals_terminal_workspace_and_is_idempotent(tmp_path: Path):
    workspace, _ = _fixture(tmp_path)

    first = post.reconcile_published_workspace(tmp_path, DEBATE, WORK)
    second = post.reconcile_published_workspace(tmp_path, DEBATE, WORK)

    assert first["status"] == "published"
    assert first["reconciliation"] == "completed"
    assert second["reconciliation"] == "reused"
    assert first["receipt_sha256"] == second["receipt_sha256"]
    meta = json.loads((workspace / "workspace.json").read_text())
    assert meta["status"] == "published"
    assert meta["workspace_sha256"] == workspace_receipt_hash(meta)
    assert meta["final_publication"]["remote_write_performed_during_reconciliation"] is False


def test_interruption_after_receipt_resumes_same_transition(tmp_path: Path, monkeypatch):
    workspace, _ = _fixture(tmp_path)
    original = post.write_json

    def interrupted(path: Path, value):
        if path == workspace / "workspace.json":
            raise OSError("simulated interruption")
        original(path, value)

    monkeypatch.setattr(post, "write_json", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        post.reconcile_published_workspace(tmp_path, DEBATE, WORK)
    receipt_path = (
        tmp_path / f".state/post-publication/{DEBATE}/{WORK}/reconciliation-receipt.json"
    )
    first_receipt = json.loads(receipt_path.read_text())
    monkeypatch.setattr(post, "write_json", original)

    result = post.reconcile_published_workspace(tmp_path, DEBATE, WORK)

    assert result["reconciliation"] == "resumed"
    assert result["receipt_sha256"] == first_receipt["receipt_sha256"]


def test_reconciliation_blocks_divergent_installed_corpus(tmp_path: Path):
    workspace, before = _fixture(tmp_path)
    (tmp_path / f"corpus/{DEBATE}/manifest.json").write_text("changed", encoding="utf-8")

    with pytest.raises(post.PostPublicationError, match="corpus actif"):
        post.reconcile_published_workspace(tmp_path, DEBATE, WORK)

    assert json.loads((workspace / "workspace.json").read_text()) == before
    assert not (tmp_path / ".state/post-publication").exists()
