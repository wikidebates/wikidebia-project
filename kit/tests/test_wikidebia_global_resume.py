from __future__ import annotations

import json
from pathlib import Path

import wikidebia_global_resume as resume
from wikidebia_corpus_build import canonical_json, sha256_bytes
from wikidebia_update import sha_object


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _workspace(project: Path, debate_id: str, work_id: str) -> Path:
    root = project / ".state/editorial-workspaces" / debate_id / work_id
    _write(root / "workspace.json", {"placeholder": True})
    return root


def _summary(debate_id: str, work_id: str, status: str = "remote_plan_ready"):
    return {
        "debate_id": debate_id,
        "work_id": work_id,
        "status": status,
        "phase": "complete" if status == "work_closed" else "remote_plan",
        "workspace_sha256": "w" * 64,
        "next_action": "prepare_remote_plan_review",
        "next_command": "./wikidebia exact-next-command",
        "next_remote_read_possible": False,
        "next_remote_write_possible": False,
    }


def _workflow(
    project: Path,
    debate_id: str,
    *,
    phase: str = "initialize_graph",
    status: str = "running",
    work_id: str | None = None,
    pending_review: dict | None = None,
) -> Path:
    path = project / ".state/workflows" / debate_id / "workflow.json"
    _write(path, {
        "schema": resume.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "debate_title": "L'avenir de l'humanité ?",
        "work_id": work_id,
        "phase": phase,
        "status": status,
        "snapshot_path": ".state/snapshot" if phase == "initialize_graph" else None,
        "pending_review": pending_review,
    })
    return path


def _published(project: Path, debate_id: str, work_id: str) -> dict:
    receipt = {
        "schema": resume.FINAL_PUBLICATION_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "published",
        "completed_at": "2026-11-06T00:00:00+00:00",
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    workflow = {
        "schema": resume.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "phase": "published",
        "status": "published",
        "final_publication": receipt,
    }
    _write(project / f".state/workflows/{debate_id}/workflow.json", workflow)
    _write(
        project / f".state/final-publication/{debate_id}/{work_id}/publication-receipt.json",
        receipt,
    )
    return receipt


def test_single_active_work_is_selected_and_journal_is_deduplicated(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_test", "EDIT-TEST-001")
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: _summary(debate_id, work_id),
    )

    first = resume.discover_resume(project)
    second = resume.discover_resume(project)

    assert first["status"] == "ready"
    assert first["selected"]["next_command"] == "./wikidebia exact-next-command"
    assert second["journal_event_count"] == 1
    registry = json.loads((project / ".state/resume/registry.json").read_text())
    body = dict(registry)
    assert body.pop("registry_sha256") == sha_object(body)
    assert registry["active_count"] == 1
    assert registry["remote_access_performed"] is False


def test_preworkspace_workflow_is_discovered_and_resumable(tmp_path: Path):
    project = tmp_path / "project"
    _workflow(project, "debat_test")

    first = resume.discover_resume(project)
    second = resume.discover_resume(project)

    assert first["status"] == "ready"
    assert first["selected"]["work_id"] is None
    assert first["selected"]["phase"] == "initialize_graph"
    assert first["selected"]["next_action"] == "continue_editorial_workflow"
    assert first["selected"]["next_command"] == (
        "./wikidebia workflow 'L'\"'\"'avenir de l'\"'\"'humanité ?' --debate-id debat_test"
    )
    assert second["journal_event_count"] == 1
    assert first["selected"]["remote_access_performed"] is False
    assert first["selected"]["next_remote_read_possible"] is True
    assert first["selected"]["next_remote_write_possible"] is False


def test_preworkspace_pending_review_points_to_existing_handoff(tmp_path: Path):
    project = tmp_path / "project"
    _workflow(
        project,
        "debat_test",
        phase="graph_review",
        status="awaiting_review",
        work_id="EDIT-TEST-001",
        pending_review={
            "review_type": "graph_review",
            "package_path": "outgoing/debat_test_graph_review.zip",
        },
    )

    result = resume.discover_resume(project)

    assert result["selected"]["next_action"] == "complete_pending_review"
    assert result["selected"]["next_command"] == "./wikidebia review-import debat_test"
    assert result["selected"]["edit_path"] == "outgoing/debat_test_graph_review.zip"
    assert result["selected"]["next_remote_read_possible"] is True
    assert result["selected"]["next_remote_write_possible"] is True
    assert result["selected"]["remote_write_performed"] is False


def test_workspace_entry_supersedes_matching_preworkspace_workflow(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    work_id = "EDIT-TEST-001"
    _workflow(project, "debat_test", phase="promote_and_workspace", work_id=work_id)
    _workspace(project, "debat_test", work_id)
    monkeypatch.setattr(
        resume,
        "summarize_workspace",
        lambda _root, debate_id, selected_work_id: _summary(debate_id, selected_work_id),
    )

    result = resume.discover_resume(project)

    assert result["active_count"] == 1
    assert result["selected"]["workspace_path"].endswith(work_id)
    assert "workflow_path" not in result["selected"]


def test_workspace_keeps_verified_french_review_handoff(tmp_path: Path, monkeypatch):
    for review_type, workspace_status in (
        ("fr_metadata_review", "workspace_initialized"),
        ("fr_content_review", "fr_titles_applied"),
    ):
        project = tmp_path / review_type
        work_id = "EDIT-TEST-001"
        _workspace(project, "debat_test", work_id)
        archive = project / f"outgoing/debat_test_{review_type}.zip"
        archive.parent.mkdir(parents=True)
        archive.write_bytes((review_type + " package").encode())
        _workflow(
            project, "debat_test", phase=review_type, status="awaiting_review",
            work_id=work_id,
            pending_review={
                "review_type": review_type,
                "package_path": str(archive.relative_to(project)),
                "archive_sha256": sha256_bytes(archive.read_bytes()),
            },
        )
        monkeypatch.setattr(
            resume, "summarize_workspace",
            lambda _root, debate_id, selected_work_id, status=workspace_status:
                _summary(debate_id, selected_work_id, status),
        )

        result = resume.discover_resume(project)

        assert result["active_count"] == 1
        assert result["selected"]["workspace_path"].endswith(work_id)
        assert result["selected"]["next_action"] == "complete_pending_review"
        assert result["selected"]["next_command"] == "./wikidebia review-import debat_test"
        assert result["selected"]["edit_path"] == str(archive.relative_to(project))
        assert result["selected"]["workflow_review_type"] == review_type
        assert result["selected"]["next_remote_write_possible"] is True


def test_workspace_restores_missing_pending_review_package(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    work_id = "EDIT-TEST-001"
    _workspace(project, "debat_test", work_id)
    _workflow(
        project, "debat_test", phase="fr_metadata_review", status="awaiting_review",
        work_id=work_id,
        pending_review={
            "review_type": "fr_metadata_review",
            "package_path": "outgoing/missing.zip",
            "archive_sha256": "a" * 64,
        },
    )
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, selected_work_id:
            _summary(debate_id, selected_work_id, "workspace_initialized"),
    )

    result = resume.discover_resume(project)

    assert result["selected"]["next_action"] == "restore_pending_review_package"
    assert result["selected"]["resume_warning"] == "pending_review_package_missing_or_stale"
    assert result["selected"]["next_command"].startswith("./wikidebia workflow ")
    assert "edit_path" not in result["selected"]


def test_stale_workflow_handoff_cannot_override_advanced_workspace(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    work_id = "EDIT-TEST-001"
    _workspace(project, "debat_test", work_id)
    archive = project / "outgoing/stale.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"stale")
    _workflow(
        project, "debat_test", phase="fr_content_review", status="awaiting_review",
        work_id=work_id,
        pending_review={
            "review_type": "fr_content_review",
            "package_path": "outgoing/stale.zip",
            "archive_sha256": sha256_bytes(b"stale"),
        },
    )
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, selected_work_id:
            _summary(debate_id, selected_work_id, "remote_plan_ready"),
    )

    result = resume.discover_resume(project)

    assert result["selected"]["next_action"] == "prepare_remote_plan_review"
    assert "edit_path" not in result["selected"]


def test_terminal_preworkspace_workflow_is_journaled_but_not_active(tmp_path: Path):
    project = tmp_path / "project"
    _workflow(
        project,
        "debat_test",
        phase="already_translated",
        status="completed_existing_translation",
    )

    result = resume.discover_resume(project)

    assert result["status"] == "no_active_work"
    assert result["active_count"] == 0
    assert result["journal_event_count"] == 1


def test_multiple_active_works_require_compact_explicit_selection(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_a", "EDIT-TEST-001")
    _workspace(project, "debat_b", "EDIT-TEST-002")
    _workspace(project, "debat_c", "EDIT-TEST-003")
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: _summary(
            debate_id, work_id, "work_closed" if debate_id == "debat_c" else "remote_plan_ready",
        ),
    )

    result = resume.discover_resume(project)
    selected = resume.discover_resume(project, debate_id="debat_b")

    assert result["status"] == "multiple_active_works"
    assert result["active_count"] == 2
    assert len(result["choices"]) == 2
    assert selected["status"] == "ready"
    assert selected["selected"]["work_id"] == "EDIT-TEST-002"
    assert selected["journal_event_count"] == 3


def test_matching_translation_capsule_overrides_generic_workspace_step(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    workspace = _workspace(project, "debat_test", "EDIT-TEST-001")
    review = {"status": "draft", "arguments": [{"id": "A1"}]}
    _write(workspace / "reviews/en/translation_review.json", review)
    capsule = {
        "schema": "wikidebia-translation-resume-capsule-1.0",
        "debate_id": "debat_test",
        "work_id": "EDIT-TEST-001",
        "workspace_sha256": "w" * 64,
        "review_content_sha256": sha256_bytes(canonical_json(review)),
        "active_unit_id": "U001",
        "next_action": "edit_translation_patch",
        "next_command": None,
        "edit_path": ".state/patch.json",
        "capsule_sha256": None,
    }
    capsule["capsule_sha256"] = sha_object({
        key: value for key, value in capsule.items() if key != "capsule_sha256"
    })
    _write(workspace / "audits/translation-resume.json", capsule)
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: {
            **_summary(debate_id, work_id, "en_translation_review_ready"),
            "phase": "english_translation",
            "next_action": "finalize_english_translation_review",
        },
    )

    result = resume.discover_resume(project)

    assert result["selected"]["next_action"] == "edit_translation_patch"
    assert result["selected"]["active_unit_id"] == "U001"
    assert result["selected"]["edit_path"] == ".state/patch.json"


def test_corrupt_registry_and_event_do_not_block_reconstruction(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_test", "EDIT-TEST-001")
    _write(project / ".state/resume/registry.json", {"tampered": True})
    _write(project / ".state/resume/events/not-a-signature.json", {"tampered": True})
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: _summary(debate_id, work_id),
    )

    result = resume.discover_resume(project)

    assert result["status"] == "ready"
    assert result["ignored_invalid_event_count"] == 1
    assert result["journal_event_count"] == 1
    repaired = json.loads((project / ".state/resume/registry.json").read_text())
    assert repaired["schema"] == resume.REGISTRY_SCHEMA


def test_transaction_backup_workspace_is_ignored_without_blocking_valid_work(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_test", "EDIT-TEST-001")
    _workspace(project, "debat_test", "EDIT-TEST-001.review-import-backup-deadbeef")
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: _summary(debate_id, work_id),
    )

    result = resume.discover_resume(project)

    assert result["status"] == "ready"
    assert result["selected"]["work_id"] == "EDIT-TEST-001"
    assert result["active_count"] == 1
    assert result["ignored_workspace_count"] == 1
    registry = json.loads((project / ".state/resume/registry.json").read_text())
    assert registry["ignored_workspaces"] == [{
        "workspace_path": (
            ".state/editorial-workspaces/debat_test/"
            "EDIT-TEST-001.review-import-backup-deadbeef"
        ),
        "reason": "invalid_identity",
    }]


def test_signed_published_workflow_exposes_stale_release_ready_workspace(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_test", "EDIT-TEST-001")
    receipt = _published(project, "debat_test", "EDIT-TEST-001")
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: {
            **_summary(debate_id, work_id, "release_ready"),
            "phase": "release",
            "next_action": "finalize_workspace_read_only",
        },
    )

    result = resume.discover_resume(project)

    assert result["status"] == "ready"
    assert result["active_count"] == 1
    assert result["selected"]["status"] == "publication_reconciliation_required"
    assert result["selected"]["next_action"] == "reconcile_published_workspace"
    assert result["selected"]["next_command"] == (
        "./wikidebia corpus-workspace-reconcile-publication debat_test "
        "--work-id EDIT-TEST-001"
    )
    event_path = next((project / ".state/resume/events").glob("*.json"))
    event = json.loads(event_path.read_text())
    assert event["state"]["status"] == "publication_reconciliation_required"
    assert event["state"]["active"] is True
    assert event["state"]["publication_receipt_sha256"] == receipt["receipt_sha256"]


def test_reconciled_published_workspace_is_terminal(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_test", "EDIT-TEST-001")
    _published(project, "debat_test", "EDIT-TEST-001")
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: {
            **_summary(debate_id, work_id, "published"),
            "phase": "complete",
            "next_action": "complete",
        },
    )

    result = resume.discover_resume(project)

    assert result["status"] == "no_active_work"
    assert result["active_count"] == 0


def test_tampered_publication_receipt_does_not_hide_active_workspace(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _workspace(project, "debat_test", "EDIT-TEST-001")
    _published(project, "debat_test", "EDIT-TEST-001")
    receipt_path = (
        project / ".state/final-publication/debat_test/EDIT-TEST-001/publication-receipt.json"
    )
    receipt = json.loads(receipt_path.read_text())
    receipt["status"] = "tampered"
    _write(receipt_path, receipt)
    monkeypatch.setattr(
        resume, "summarize_workspace",
        lambda _root, debate_id, work_id: _summary(debate_id, work_id, "release_ready"),
    )

    result = resume.discover_resume(project)

    assert result["status"] == "ready"
    assert result["selected"]["status"] == "release_ready"
