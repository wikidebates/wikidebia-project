from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_translation_resume as resume
from wikidebia_update import sha_object


def _signed(value, field):
    body = dict(value)
    body.pop(field, None)
    value[field] = sha_object(body)
    return value


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path, monkeypatch, *, patch_status="draft", application=False):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    review = {"status": "draft", "arguments": [{"id": "A1", "translation": {"status": "pending"}}]}
    _write(workspace / "reviews/en/translation_review.json", review)
    _write(workspace / "audits/en_translation_worklist.json", _signed({
        "schema": "worklist", "units": [{"unit_id": "U001"}], "worklist_sha256": None,
    }, "worklist_sha256"))
    _write(workspace / "audits/translation-next.json", _signed({
        "schema": "selection", "status": "unit_prepared", "unit_id": "U001",
        "selection_sha256": None,
    }, "selection_sha256"))
    _write(workspace / "audits/translation-packets/U001.json", _signed({
        "schema": "packet", "counts": {"arguments": 2}, "packet_sha256": None,
    }, "packet_sha256"))
    patch = {
        "schema": "patch", "status": patch_status, "base_packet_sha256": "p" * 64,
        "patch_sha256": None,
    }
    if patch_status == "sealed":
        patch["patch_sha256"] = sha_object({key: value for key, value in patch.items() if key != "patch_sha256"})
    _write(workspace / "reviews/en/unit-patches/U001.json", patch)
    if application:
        _write(workspace / "audits/translation-patches/U001-application.json", _signed({
            "schema": "application", "patch_sha256": patch["patch_sha256"],
            "receipt_sha256": None,
        }, "receipt_sha256"))
    monkeypatch.setattr(resume, "_load_workspace", lambda *args: (
        workspace, {"status": "en_translation_review_ready", "workspace_sha256": "w" * 64},
    ))
    return project, workspace, patch


def test_capsule_is_small_signed_and_points_to_editable_patch(tmp_path: Path, monkeypatch):
    project, workspace, _patch = _fixture(tmp_path, monkeypatch)

    result = resume.write_resume_capsule(
        project, "debat_test", "EDIT-TEST-001", event="next_unit_prepared",
    )

    assert result["active_unit_id"] == "U001"
    assert result["next_action"] == "edit_translation_patch"
    assert result["next_command"] is None
    assert result["edit_path"].endswith("reviews/en/unit-patches/U001.json")
    assert result["capsule_size_bytes"] < 5000
    saved = json.loads((workspace / "audits/translation-resume.json").read_text())
    body = dict(saved)
    assert body.pop("capsule_sha256") == sha_object(body)
    assert "Translated text" not in json.dumps(saved)


def test_capsule_gives_exact_apply_command_for_sealed_patch(tmp_path: Path, monkeypatch):
    project, _workspace, patch = _fixture(tmp_path, monkeypatch, patch_status="sealed")

    result = resume.write_resume_capsule(project, "debat_test", "EDIT-TEST-001")

    assert result["next_action"] == "apply_translation_patch"
    assert result["next_command"].endswith(
        "--confirm-patch-sha256 " + patch["patch_sha256"]
    )


def test_capsule_advances_after_matching_application_receipt(tmp_path: Path, monkeypatch):
    project, _workspace, _patch = _fixture(
        tmp_path, monkeypatch, patch_status="sealed", application=True,
    )

    result = resume.write_resume_capsule(project, "debat_test", "EDIT-TEST-001")

    assert result["next_action"] == "prepare_next_unit"
    assert result["next_command"] == (
        "./wikidebia corpus-workspace-translation-next debat_test --work-id EDIT-TEST-001"
    )


def test_capsule_rejects_tampered_signed_artifact(tmp_path: Path, monkeypatch):
    project, workspace, _patch = _fixture(tmp_path, monkeypatch)
    path = workspace / "audits/translation-next.json"
    value = json.loads(path.read_text())
    value["unit_id"] = "U999"
    _write(path, value)

    with pytest.raises(resume.TranslationResumeError, match="Signature invalide"):
        resume.write_resume_capsule(project, "debat_test", "EDIT-TEST-001")


def test_capsule_points_to_active_argument_fragment(tmp_path: Path, monkeypatch):
    project, workspace, _patch = _fixture(tmp_path, monkeypatch)
    _write(workspace / "audits/translation-fragment-next.json", _signed({
        "schema": "fragment-selection", "status": "argument_fragment_prepared",
        "unit_id": "U001", "page_id": "A1", "selection_sha256": None,
    }, "selection_sha256"))
    _write(workspace / "reviews/en/argument-fragments/A1.json", {
        "schema": "fragment", "status": "draft", "base_argument_sha256": "a" * 64,
        "fragment_sha256": None,
    })

    result = resume.write_resume_capsule(
        project, "debat_test", "EDIT-TEST-001", unit_id="U001", page_id="A1",
    )

    assert result["active_page_id"] == "A1"
    assert result["next_action"] == "edit_translation_argument_fragment"
    assert result["edit_path"].endswith("reviews/en/argument-fragments/A1.json")
