from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_translation_packet as packet_module
import wikidebia_translation_patch as patch_module
from wikidebia_update import sha_object


def _fixture(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    source = workspace / "content-reviewed-copy"
    (workspace / "reviews/en").mkdir(parents=True)
    source.mkdir()
    metadata = {"debate": {"entity_id": "debate"}, "arguments": [
        {"entity_id": "A1", "canonical_title": "Argument un"},
        {"entity_id": "A2", "canonical_title": "Argument deux"},
    ]}
    content = {"debate": {"id": "debate"}, "arguments": [
        {"id": "A1", "summary": "Source un"}, {"id": "A2", "summary": "Source deux"},
    ]}
    review = {
        "schema": packet_module.TRANSLATION_REVIEW_SCHEMA,
        "debate_id": "debat_test", "work_id": "EDIT-TEST-001", "status": "draft",
        "review_sha256": None, "prepared_content_reviewed_copy_sha256": "tree",
        "section_mapping": {},
        "arguments": [
            {"id": "A1", "review_unit_id": "U001", "translation": {
                "status": "pending", "canonical_title": "Argument one",
                "french": {"metadata": metadata["arguments"][0], "content": content["arguments"][0]},
            }},
            {"id": "A2", "review_unit_id": "U002", "translation": {
                "status": "pending", "canonical_title": "Argument two",
                "french": {"metadata": metadata["arguments"][1], "content": content["arguments"][1]},
            }},
        ],
        "review_units": [
            {"id": "U001", "page_ids": ["A1"], "status": "pending", "reviewer": "", "reviewed_at": None, "note": "", "max_risk_level": "low"},
            {"id": "U002", "page_ids": ["A2"], "status": "pending", "reviewer": "", "reviewed_at": None, "note": "", "max_risk_level": "low"},
        ],
        "vocabulary": [{"concept_id": "K1", "fr": "égalité", "en": "equality", "kind": "noun", "capitalization_policy": "lowercase", "usages": [{"page_id": "A1"}], "status": "pending"}],
        "relation_labels": [{"id": "E1", "source_page_id": "debate", "target_node_id": "A1", "relation": "pro", "source_text": "Texte", "translated_text": "Text", "equivalent_to_french": False}],
    }
    review_path = workspace / "reviews/en/translation_review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    meta = {"content_reviewed_copy": {"tree_sha256": "tree"}}
    for module in (packet_module, patch_module):
        monkeypatch.setattr(module, "_load_workspace", lambda *args: (workspace, meta))
    monkeypatch.setattr(packet_module, "_assert_content_copy", lambda *args: source)
    monkeypatch.setattr(packet_module, "_source_snapshot", lambda *args: (
        {"graph": {"nodes": []}}, metadata, content, {"entries": []},
    ))
    return project, workspace, review_path


def test_patch_merges_only_unit_and_preserves_french(tmp_path: Path, monkeypatch):
    project, workspace, review_path = _fixture(tmp_path, monkeypatch)
    prepared = patch_module.prepare_patch(project, "debat_test", "EDIT-TEST-001", "U001")
    path = project / prepared["patch_path"]
    patch = json.loads(path.read_text())
    patch["arguments"][0]["translation"]["canonical_title"] = "Improved argument one"
    patch["arguments"][0]["translation"]["status"] = "approved"
    path.write_text(json.dumps(patch), encoding="utf-8")

    sealed = patch_module.seal_patch(
        project, "debat_test", "EDIT-TEST-001", "U001",
        reviewer="Reviewer", note="Complete bilingual unit review", unit_status="approved",
    )
    result = patch_module.apply_patch(
        project, "debat_test", "EDIT-TEST-001", "U001",
        confirm_patch_sha256=sealed["patch_sha256"],
    )

    review = json.loads(review_path.read_text())
    assert review["arguments"][0]["translation"]["canonical_title"] == "Improved argument one"
    assert review["arguments"][0]["translation"]["french"]["content"]["summary"] == "Source un"
    assert review["arguments"][1]["translation"]["canonical_title"] == "Argument two"
    assert review["review_units"][0]["status"] == "approved"
    receipt = json.loads((workspace / "audits/translation-patches/U001-application.json").read_text())
    unsigned = dict(receipt)
    assert unsigned.pop("receipt_sha256") == sha_object(unsigned)
    assert result["french_fields_mutated"] is False
    repeated = patch_module.apply_patch(
        project, "debat_test", "EDIT-TEST-001", "U001",
        confirm_patch_sha256=sealed["patch_sha256"],
    )
    assert repeated["status"] == "already_applied"


def test_seal_rejects_french_field_injection(tmp_path: Path, monkeypatch):
    project, _workspace, _review_path = _fixture(tmp_path, monkeypatch)
    prepared = patch_module.prepare_patch(project, "debat_test", "EDIT-TEST-001", "U001")
    path = project / prepared["patch_path"]
    patch = json.loads(path.read_text())
    patch["arguments"][0]["translation"]["french"] = {"content": {"summary": "tampered"}}
    path.write_text(json.dumps(patch), encoding="utf-8")

    with pytest.raises(patch_module.TranslationPatchError, match="blocs français"):
        patch_module.seal_patch(
            project, "debat_test", "EDIT-TEST-001", "U001",
            reviewer="Reviewer", note="Complete bilingual unit review", unit_status="approved",
        )
