from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

import wikidebia_translation_checkpoint as checkpoint
from wikidebia_update import sha_object


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(root: Path) -> Path:
    workspace = root / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    meta = {
        "schema": "workspace",
        "debate_id": "debat_test",
        "work_id": "EDIT-TEST-001",
        "status": "en_translation_review_ready",
        "workspace_sha256": "w" * 64,
    }
    _write(workspace / "workspace.json", meta)
    _write(workspace / "reviews/en/translation_review.json", {
        "debate_id": "debat_test", "work_id": "EDIT-TEST-001",
        "status": "draft", "arguments": [{"id": "A1", "large": "x" * 20000}],
    })
    _write(workspace / "content-reviewed-copy/data/lock.json", {"locked": True})
    _write(workspace / "content-reviewed-copy/pages/A1.wiki", b"French source")
    _write(workspace / "private/credentials.json", {"secret": "must-not-leave"})
    return workspace


def _fake_load(project_root: Path, debate_id: str, work_id: str):
    workspace = project_root / ".state/editorial-workspaces" / debate_id / work_id
    return workspace, json.loads((workspace / "workspace.json").read_text())


def test_export_is_deterministic_signed_compressed_and_excludes_private_files(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    _fixture(project)
    monkeypatch.setattr(checkpoint, "_load_workspace", _fake_load)

    first = checkpoint.export_checkpoint(project, "debat_test", "EDIT-TEST-001")
    second = checkpoint.export_checkpoint(project, "debat_test", "EDIT-TEST-001")

    assert first["archive_sha256"] == second["archive_sha256"]
    assert first["checkpoint_sha256"] == second["checkpoint_sha256"]
    assert first["archive_bytes"] < first["expanded_bytes"]
    archive_path = project / first["archive_path"]
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert checkpoint.MANIFEST_NAME in names
        assert "workspace/private/credentials.json" not in names
        manifest = json.loads(archive.read(checkpoint.MANIFEST_NAME))
    body = dict(manifest)
    assert body.pop("checkpoint_sha256") == sha_object(body)
    assert manifest["contains_secrets"] is False


def test_restore_recreates_missing_workspace_and_is_idempotent(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    _fixture(source)
    monkeypatch.setattr(checkpoint, "_load_workspace", _fake_load)
    exported = checkpoint.export_checkpoint(source, "debat_test", "EDIT-TEST-001")
    archive = source / exported["archive_path"]
    target = tmp_path / "target"

    restored = checkpoint.restore_checkpoint(target, archive)
    repeated = checkpoint.restore_checkpoint(target, archive)

    assert restored["mode"] == "created_workspace"
    assert restored["restored_files"] >= 4
    assert repeated["mode"] == "completed_existing_workspace"
    assert repeated["restored_files"] == 0
    workspace = target / restored["workspace_path"]
    assert (workspace / "content-reviewed-copy/pages/A1.wiki").read_text() == "French source"
    assert not (workspace / "private/credentials.json").exists()


def test_restore_refuses_to_overwrite_divergent_existing_review(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    _fixture(source)
    monkeypatch.setattr(checkpoint, "_load_workspace", _fake_load)
    exported = checkpoint.export_checkpoint(source, "debat_test", "EDIT-TEST-001")
    archive = source / exported["archive_path"]
    target = tmp_path / "target"
    workspace = _fixture(target)
    review = workspace / "reviews/en/translation_review.json"
    review.write_text('{"newer": true}', encoding="utf-8")

    with pytest.raises(checkpoint.TranslationCheckpointError, match="diverge"):
        checkpoint.restore_checkpoint(target, archive)

    assert review.read_text() == '{"newer": true}'


def test_restore_rejects_zip_path_traversal(tmp_path: Path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../outside", "bad")
        output.writestr(checkpoint.MANIFEST_NAME, "{}")

    with pytest.raises(checkpoint.TranslationCheckpointError, match="dangereux"):
        checkpoint.restore_checkpoint(tmp_path / "project", archive)


def test_restore_rejects_symlinked_existing_parent(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    _fixture(source)
    monkeypatch.setattr(checkpoint, "_load_workspace", _fake_load)
    exported = checkpoint.export_checkpoint(source, "debat_test", "EDIT-TEST-001")
    archive = source / exported["archive_path"]
    target = tmp_path / "target"
    workspace = _fixture(target)
    content = workspace / "content-reviewed-copy"
    outside = tmp_path / "outside"
    outside.mkdir()
    for path in sorted(content.rglob("*"), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    content.rmdir()
    content.symlink_to(outside, target_is_directory=True)

    with pytest.raises(checkpoint.TranslationCheckpointError, match="symbolique"):
        checkpoint.restore_checkpoint(target, archive)

    assert list(outside.iterdir()) == []
