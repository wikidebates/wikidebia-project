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
