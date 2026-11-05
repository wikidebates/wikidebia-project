from __future__ import annotations

import json
from pathlib import Path

import wikidebia_translation_packet as packet
from wikidebia_update import sha_object


def _fixture(tmp_path: Path, monkeypatch, *, changed: bool = False):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    source = workspace / "content-reviewed-copy"
    (workspace / "reviews/en").mkdir(parents=True)
    source.mkdir()
    metadata = {
        "debate": {"entity_id": "debate", "canonical_title": "Débat"},
        "arguments": [
            {"entity_id": "A1", "canonical_title": "Argument un", "sections": ["Société"]},
            {"entity_id": "A2", "canonical_title": "Argument deux", "sections": ["Politique"]},
        ],
    }
    content = {
        "debate": {"id": "debate"},
        "arguments": [
            {"id": "A1", "summary": "Source courante"},
            {"id": "A2", "summary": "Autre source"},
        ],
    }
    embedded_a1 = {"id": "A1", "summary": "Ancienne source" if changed else "Source courante"}
    review = {
        "schema": packet.TRANSLATION_REVIEW_SCHEMA,
        "debate_id": "debat_test", "work_id": "EDIT-TEST-001", "status": "draft",
        "prepared_content_reviewed_copy_sha256": "tree",
        "section_mapping": {"Société": "Society", "Politique": "Politics"},
        "arguments": [
            {"id": "A1", "review_unit_id": "U001", "translation": {
                "status": "pending", "canonical_title": "Argument one",
                "french": {"metadata": metadata["arguments"][0], "content": embedded_a1},
            }},
            {"id": "A2", "review_unit_id": "U002", "translation": {
                "status": "approved", "canonical_title": "Argument two",
                "french": {"metadata": metadata["arguments"][1], "content": content["arguments"][1]},
            }},
        ],
        "review_units": [
            {"id": "U001", "page_ids": ["A1"], "max_risk_level": "medium", "status": "pending"},
            {"id": "U002", "page_ids": ["A2"], "max_risk_level": "low", "status": "approved"},
        ],
        "vocabulary": [
            {"concept_id": "K1", "usages": [{"page_id": "A1"}]},
            {"concept_id": "K2", "usages": [{"page_id": "A2"}]},
        ],
        "relation_labels": [
            {"id": "E1", "source_page_id": "debate", "target_node_id": "A1"},
            {"id": "E2", "source_page_id": "A2", "target_node_id": "A2"},
        ],
        "review_sha256": None,
    }
    (workspace / "reviews/en/translation_review.json").write_text(
        json.dumps(review, ensure_ascii=False), encoding="utf-8",
    )
    monkeypatch.setattr(packet, "_load_workspace", lambda *args: (
        workspace, {"content_reviewed_copy": {"tree_sha256": "tree"}},
    ))
    monkeypatch.setattr(packet, "_assert_content_copy", lambda *args: source)
    monkeypatch.setattr(packet, "_source_snapshot", lambda *args: (
        {"graph": {"nodes": []}}, metadata, content, {"entries": []},
    ))
    return project, workspace


def test_packet_contains_only_requested_unit_context(tmp_path: Path, monkeypatch):
    project, workspace = _fixture(tmp_path, monkeypatch)

    result = packet.build_packet(project, "debat_test", "EDIT-TEST-001", "U001")

    assert [row["id"] for row in result["arguments"]] == ["A1"]
    assert "french" not in result["arguments"][0]["translation"]
    assert result["arguments"][0]["current_french"]["content"]["summary"] == "Source courante"
    assert [row["concept_id"] for row in result["vocabulary"]] == ["K1"]
    assert [row["id"] for row in result["relation_labels"]] == ["E1"]
    saved = json.loads((workspace / "audits/translation-packets/U001.json").read_text())
    unsigned = dict(saved)
    assert unsigned.pop("packet_sha256") == sha_object(unsigned)
    assert result["remote_access_performed"] is False


def test_packet_marks_changed_locked_french_source(tmp_path: Path, monkeypatch):
    project, _workspace = _fixture(tmp_path, monkeypatch, changed=True)

    result = packet.build_packet(project, "debat_test", "EDIT-TEST-001", "U001")

    assert result["counts"]["changed_french_sources"] == 1
    argument = result["arguments"][0]
    assert argument["source_changed"] is True
    assert argument["prepared_source_sha256"] != argument["current_source_sha256"]
