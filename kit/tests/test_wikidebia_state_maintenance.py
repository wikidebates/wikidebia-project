from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_state_maintenance as maintenance
from wikidebia_editorial_workspace import workspace_receipt_hash
from wikidebia_update import sha_object


DEBATE = "debat_test"
WORK = "EDIT-TEST-001"
BACKUP = f"{WORK}.review-import-backup-deadbeef"


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(project: Path) -> Path:
    workspace = project / f".state/editorial-workspaces/{DEBATE}/{WORK}"
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0",
        "schema_version": "1.0",
        "debate_id": DEBATE,
        "work_id": WORK,
        "status": "published",
        "workspace_sha256": None,
    }
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    _write(workspace / "workspace.json", meta)
    receipt = {
        "schema": maintenance.POST_PUBLICATION_SCHEMA,
        "schema_version": "1.0",
        "debate_id": DEBATE,
        "work_id": WORK,
        "status": "published",
        "workspace_sha256": meta["workspace_sha256"],
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    _write(
        project / f".state/post-publication/{DEBATE}/{WORK}/reconciliation-receipt.json",
        receipt,
    )
    backup = project / f".state/editorial-workspaces/{DEBATE}/{BACKUP}"
    backup.mkdir(parents=True)
    (backup / "evidence.txt").write_text("historical evidence\n", encoding="utf-8")
    return backup


def test_dry_run_measures_state_and_selects_only_proven_terminal_backup(tmp_path: Path):
    backup = _fixture(tmp_path)

    plan = maintenance.build_plan(tmp_path)

    assert plan["candidate_count"] == 1
    assert plan["candidates"][0]["path"] == backup.relative_to(tmp_path).as_posix()
    assert plan["reclaimable_logical_bytes"] > 0
    assert plan["reclaimable_allocated_bytes"] > 0
    assert plan["state_usage"]["allocated_bytes_unique_inodes"] > 0
    assert plan["plan_sha256"] == sha_object({
        key: value for key, value in plan.items() if key != "plan_sha256"
    })
    assert backup.is_dir()


def test_apply_requires_exact_plan_and_writes_idempotent_receipt(tmp_path: Path):
    backup = _fixture(tmp_path)
    plan = maintenance.build_plan(tmp_path)
    plan_path = tmp_path / ".state/maintenance-plan.json"
    _write(plan_path, plan)

    with pytest.raises(maintenance.StateMaintenanceError, match="confirmation"):
        maintenance.apply_plan(tmp_path, plan_path, "0" * 64)
    assert backup.is_dir()

    first = maintenance.apply_plan(tmp_path, plan_path, plan["plan_sha256"])
    second = maintenance.apply_plan(tmp_path, plan_path, plan["plan_sha256"])

    assert first == second
    assert first["status"] == "completed"
    assert first["deleted_count"] == 1
    assert not backup.exists()
    assert first["receipt_sha256"] == sha_object({
        key: value for key, value in first.items() if key != "receipt_sha256"
    })


def test_changed_backup_is_never_deleted(tmp_path: Path):
    backup = _fixture(tmp_path)
    plan = maintenance.build_plan(tmp_path)
    plan_path = tmp_path / ".state/maintenance-plan.json"
    _write(plan_path, plan)
    (backup / "evidence.txt").write_text("changed after plan\n", encoding="utf-8")

    with pytest.raises(maintenance.StateMaintenanceError, match="modifiée"):
        maintenance.apply_plan(tmp_path, plan_path, plan["plan_sha256"])

    assert backup.is_dir()
    assert not list((tmp_path / ".state/state-maintenance").glob("*/deletion-receipt.json"))


def test_non_terminal_workspace_blocks_cleanup_candidate(tmp_path: Path):
    backup = _fixture(tmp_path)
    workspace_json = tmp_path / f".state/editorial-workspaces/{DEBATE}/{WORK}/workspace.json"
    meta = json.loads(workspace_json.read_text())
    meta["status"] = "release_ready"
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    _write(workspace_json, meta)

    plan = maintenance.build_plan(tmp_path)

    assert plan["candidate_count"] == 0
    assert plan["blocked"] == [{
        "path": backup.relative_to(tmp_path).as_posix(),
        "reason": "terminal_proof_or_tree_invalid",
    }]


def test_interruption_after_quarantine_deletion_resumes_from_checkpoint(
    tmp_path: Path, monkeypatch,
):
    backup = _fixture(tmp_path)
    plan = maintenance.build_plan(tmp_path)
    plan_path = tmp_path / ".state/maintenance-plan.json"
    _write(plan_path, plan)
    original = maintenance.shutil.rmtree

    def interrupted(path: Path):
        original(path)
        raise OSError("simulated interruption after deletion")

    monkeypatch.setattr(maintenance.shutil, "rmtree", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        maintenance.apply_plan(tmp_path, plan_path, plan["plan_sha256"])
    assert not backup.exists()
    item = next((tmp_path / ".state/state-maintenance").glob("*/items/0001.json"))
    assert json.loads(item.read_text())["status"] == "quarantined"
    monkeypatch.setattr(maintenance.shutil, "rmtree", original)

    receipt = maintenance.apply_plan(tmp_path, plan_path, plan["plan_sha256"])

    assert receipt["status"] == "completed"
    assert receipt["deleted_count"] == 1
