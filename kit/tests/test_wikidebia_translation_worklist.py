from __future__ import annotations

import json
from pathlib import Path

import wikidebia_translation_worklist as worklist
from wikidebia_update import sha_object


METADATA = {
    "debate": {"entity_id": "debate", "canonical_title": "Débat test"},
    "A1": {"entity_id": "A1", "canonical_title": "Argument un"},
    "A2": {"entity_id": "A2", "canonical_title": "Argument deux"},
}
CONTENT = {
    "debate": {"id": "debate", "introduction": "Source"},
    "A1": {"id": "A1", "summary": "Source un"},
    "A2": {"id": "A2", "summary": "Source deux"},
}


def _review(metadata, content, *, second_status="pending", unit_status="pending"):
    def translation(page_id, status_value, embedded_content):
        return {
            "id": page_id,
            "translation": {
                "status": status_value,
                "french": {"metadata": metadata[page_id], "content": embedded_content},
                "citations": [],
                "citation_passages": [],
            },
        }

    return {
        "schema": worklist.TRANSLATION_REVIEW_SCHEMA,
        "debate_id": "debat_test",
        "work_id": "EDIT-TEST-001",
        "status": "draft",
        "prepared_content_reviewed_copy_sha256": "source-tree",
        "debate": {
            "status": "approved",
            "french": {"metadata": metadata["debate"], "content": content["debate"]},
        },
        "arguments": [
            translation("A1", "approved", content["A1"]),
            translation("A2", second_status, content["A2"]),
        ],
        "review_units": [
            {"id": "U001", "page_ids": ["A1"], "target_size": 1, "max_risk_level": "low", "status": "approved"},
            {"id": "U002", "page_ids": ["A2"], "target_size": 1, "max_risk_level": "high", "status": unit_status},
        ],
        "vocabulary": [
            {"concept_id": "K1", "status": "approved", "idiomatic_equivalent": True, "same_concept": True},
            {"concept_id": "K2", "status": "pending", "idiomatic_equivalent": False, "same_concept": False},
        ],
        "relation_labels": [
            {"id": "edge:E1", "translated_text": "", "equivalent_to_french": False},
        ],
        "global_review": {
            "all_entities_translated": False,
            "all_equivalences_reviewed": True,
            "all_selected_sources_verified": True,
            "relations_and_occurrences_unchanged": True,
            "no_final_pages_generated": True,
            "remote_access_not_used": True,
            "blocking_issues": [],
        },
        "review_sha256": None,
    }


def _fixture(tmp_path: Path, monkeypatch, review):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    source = workspace / "content-reviewed-copy"
    (workspace / "reviews/en").mkdir(parents=True)
    source.mkdir()
    (workspace / "reviews/en/translation_review.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata_lock = {
        "debate": METADATA["debate"],
        "arguments": [METADATA["A1"], METADATA["A2"]],
    }
    content_lock = {
        "debate": CONTENT["debate"],
        "arguments": [CONTENT["A1"], CONTENT["A2"]],
    }
    registry = {"graph": {"nodes": [{"id": "A1", "status": "active"}, {"id": "A2", "status": "active"}]}}
    monkeypatch.setattr(worklist, "_load_workspace", lambda *args: (
        workspace,
        {"status": "en_translation_review_ready", "content_reviewed_copy": {"tree_sha256": "source-tree"}},
    ))
    monkeypatch.setattr(worklist, "_assert_content_copy", lambda *args: source)
    monkeypatch.setattr(
        worklist, "_source_snapshot",
        lambda *args: (registry, metadata_lock, content_lock, {"entries": []}),
    )
    return project, workspace


def test_worklist_contains_only_pending_units_and_global_tasks(tmp_path: Path, monkeypatch):
    review = _review(METADATA, CONTENT)
    project, workspace = _fixture(tmp_path, monkeypatch, review)

    result = worklist.build_worklist(project, "debat_test", "EDIT-TEST-001")

    assert result["counts"] == {
        "arguments_total": 2,
        "arguments_to_review": 1,
        "arguments_ready": 1,
        "units_total": 2,
        "units_to_review": 1,
        "vocabulary_to_review": 1,
        "relation_labels_to_review": 1,
    }
    assert result["units"][0]["unit_id"] == "U002"
    assert result["units"][0]["page_ids"] == ["A2"]
    assert "A1" not in result["source_hashes"]
    assert result["vocabulary"] == ["K2"]
    assert result["relation_labels"] == ["edge:E1"]
    saved = json.loads((workspace / "audits/en_translation_worklist.json").read_text(encoding="utf-8"))
    unsigned = dict(saved)
    claimed = unsigned.pop("worklist_sha256")
    assert claimed == sha_object(unsigned)
    assert (workspace / "audits/en_translation_worklist.md").is_file()


def test_worklist_detects_changed_french_source_in_closed_unit(tmp_path: Path, monkeypatch):
    embedded_content = {key: dict(value) for key, value in CONTENT.items()}
    embedded_content["A1"] = {"id": "A1", "summary": "Ancienne source"}
    review = _review(METADATA, embedded_content, second_status="approved", unit_status="approved")
    review["vocabulary"] = []
    review["relation_labels"] = []
    review["global_review"]["all_entities_translated"] = True
    project, _workspace = _fixture(tmp_path, monkeypatch, review)

    result = worklist.build_worklist(project, "debat_test", "EDIT-TEST-001")

    assert result["counts"]["arguments_to_review"] == 1
    assert result["units"][0]["unit_id"] == "U001"
    assert result["units"][0]["reasons_by_page"]["A1"] == ["french_source_changed"]
    assert result["source_hashes"]["A1"]["prepared_sha256"] != result["source_hashes"]["A1"]["current_sha256"]


def test_complete_draft_points_directly_to_finalization(tmp_path: Path, monkeypatch):
    review = _review(METADATA, CONTENT, second_status="approved", unit_status="approved")
    review["vocabulary"] = []
    review["relation_labels"] = []
    review["global_review"]["all_entities_translated"] = True
    project, _workspace = _fixture(tmp_path, monkeypatch, review)

    result = worklist.build_worklist(project, "debat_test", "EDIT-TEST-001")

    assert result["complete"] is True
    assert result["units"] == []
    assert result["source_hashes"] == {}
    assert result["next_command"] == (
        "./wikidebia corpus-workspace-translation debat_test --work-id EDIT-TEST-001 --finalize"
    )
