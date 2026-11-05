from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_translation_memory as memory


def _fixture(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    source = workspace / "content-reviewed-copy"
    (workspace / "reviews/en").mkdir(parents=True)
    source.mkdir()
    metadata = {"arguments": [
        {
            "entity_id": "A1",
            "canonical_title": "  Argument   partagé  ",
            "source_import_sha256": "a" * 64,
        },
        {
            "entity_id": "A2",
            "canonical_title": "Argument unique",
            "source_import_sha256": "b" * 64,
        },
    ]}
    content = {"arguments": [
        {"id": "A1", "summary": "Source un", "import_sha256": "a" * 64},
        {"id": "A2", "summary": "Source deux", "import_sha256": "b" * 64},
    ]}
    review = {
        "schema": memory.TRANSLATION_REVIEW_SCHEMA,
        "debate_id": "debat_test",
        "work_id": "EDIT-TEST-001",
        "status": "approved",
        "finalized_at": "2026-11-05T10:00:00+00:00",
        "arguments": [
            {"id": "A1", "translation": {
                "status": "approved",
                "canonical_title": "Shared argument",
                "summary": "Translated one",
                "citations": [{"id": "A1-C001", "translated_citation": "Quoted text"}],
                "french": {"content": content["arguments"][0]},
                "existing_english_update": {"observed_revision_id": 12},
            }},
            {"id": "A2", "translation": {
                "status": "approved",
                "canonical_title": "Unique argument",
                "summary": "Translated two",
                "french": {"content": content["arguments"][1]},
            }},
        ],
        "review_sha256": None,
    }
    review["review_sha256"] = memory.translation_review_sha256(review)
    review_path = workspace / "reviews/en/translation_review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    monkeypatch.setattr(memory, "_load_workspace", lambda *args: (
        workspace, {"content_reviewed_copy": {"tree_sha256": "tree"}},
    ))
    monkeypatch.setattr(memory, "_assert_content_copy", lambda *args: source)
    monkeypatch.setattr(memory, "_source_snapshot", lambda *args: (
        {}, metadata, content, {},
    ))
    return project, workspace, review_path, metadata, content


def test_export_builds_signed_content_addressed_memory(tmp_path: Path, monkeypatch):
    project, _workspace, _review_path, _metadata, _content = _fixture(tmp_path, monkeypatch)

    result = memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))
    verified = memory.verify_memory(project, Path("translation-memory"))

    assert result["entries_added"] == 2
    assert result["entries_reused"] == 0
    assert verified["entries"] == 2
    index = json.loads((project / "translation-memory/index.json").read_text())
    assert memory._signed(index, "index_sha256")
    assert [row["memory_key"] for row in index["entries"]] == sorted(
        row["memory_key"] for row in index["entries"]
    )
    first = json.loads((project / "translation-memory" / index["entries"][0]["object_path"]).read_text())
    assert memory._signed(first, "entry_sha256")
    assert "french" not in first["translation"]
    assert "existing_english_update" not in first["translation"]
    assert result["remote_write_performed"] is False


def test_export_is_idempotent(tmp_path: Path, monkeypatch):
    project, _workspace, _review_path, _metadata, _content = _fixture(tmp_path, monkeypatch)
    first = memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))

    second = memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))

    assert second["entries_added"] == 0
    assert second["entries_reused"] == 2
    assert second["index_sha256"] == first["index_sha256"]


def test_export_refuses_divergent_translation_for_same_source(tmp_path: Path, monkeypatch):
    project, _workspace, review_path, _metadata, _content = _fixture(tmp_path, monkeypatch)
    memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))
    review = json.loads(review_path.read_text())
    review["arguments"][0]["translation"]["summary"] = "A conflicting translation"
    review["review_sha256"] = memory.translation_review_sha256(review)
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(memory.TranslationMemoryError, match="divergentes"):
        memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))


def test_verify_rejects_tampered_object(tmp_path: Path, monkeypatch):
    project, _workspace, _review_path, _metadata, _content = _fixture(tmp_path, monkeypatch)
    memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))
    index = json.loads((project / "translation-memory/index.json").read_text())
    path = project / "translation-memory" / index["entries"][0]["object_path"]
    entry = json.loads(path.read_text())
    entry["translation"]["summary"] = "Tampered"
    path.write_text(json.dumps(entry), encoding="utf-8")

    with pytest.raises(memory.TranslationMemoryError, match="invalide"):
        memory.verify_memory(project, Path("translation-memory"))


def test_reuse_applies_exact_entry_remaps_ids_and_rejects_stale(tmp_path: Path, monkeypatch):
    project, workspace, review_path, metadata, content = _fixture(tmp_path, monkeypatch)
    memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))
    review = json.loads(review_path.read_text())
    review["status"] = "draft"
    review["review_sha256"] = None
    review["arguments"][0]["id"] = "B9"
    review["arguments"][0]["translation"] = {
        "status": "pending",
        "canonical_title": "",
        "page_origin": "new",
        "existing_english_update": {"observed_revision_id": 99},
        "french": {"content": {"id": "B9", "summary": "Current French"}},
    }
    review["arguments"][1]["translation"] = {
        "status": "pending", "canonical_title": "", "french": {"content": {}},
    }
    review_path.write_text(json.dumps(review), encoding="utf-8")
    metadata["arguments"][0]["entity_id"] = "B9"
    content["arguments"][0]["id"] = "B9"
    metadata["arguments"][1]["source_import_sha256"] = "c" * 64
    content["arguments"][1]["import_sha256"] = "c" * 64

    result = memory.reuse_review(
        project, "debat_test", "EDIT-TEST-001", Path("translation-memory"),
    )

    updated = json.loads(review_path.read_text())
    first = updated["arguments"][0]["translation"]
    assert result["matched"] == 1
    assert result["stale_rejected"] == 1
    assert first["canonical_title"] == "Shared argument"
    assert first["citations"][0]["id"] == "B9-C001"
    assert first["french"]["content"]["summary"] == "Current French"
    assert first["page_origin"] == "new"
    assert first["existing_english_update"]["observed_revision_id"] == 99
    assert updated["arguments"][1]["translation"]["status"] == "pending"
    receipt = json.loads((workspace / "audits/translation-memory/reuse.json").read_text())
    assert memory._signed(receipt, "receipt_sha256")
    review_by_id = {row["id"]: row for row in updated["arguments"]}
    reused, stale = memory.verified_reuse_coverage(
        workspace,
        review_by_id,
        {row["entity_id"]: row for row in metadata["arguments"]},
        {row["id"]: row for row in content["arguments"]},
    )
    assert [row["page_id"] for row in reused] == ["B9"]
    assert [row["page_id"] for row in stale] == ["A2"]


def test_reuse_refuses_divergent_already_approved_translation(tmp_path: Path, monkeypatch):
    project, _workspace, review_path, _metadata, _content = _fixture(tmp_path, monkeypatch)
    memory.export_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))
    review = json.loads(review_path.read_text())
    review["status"] = "draft"
    review["review_sha256"] = None
    review["arguments"][0]["translation"]["summary"] = "Manual divergent approval"
    review_path.write_text(json.dumps(review), encoding="utf-8")

    with pytest.raises(memory.TranslationMemoryError, match="approuvée divergente"):
        memory.reuse_review(project, "debat_test", "EDIT-TEST-001", Path("translation-memory"))
