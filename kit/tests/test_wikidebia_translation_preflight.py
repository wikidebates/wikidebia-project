from __future__ import annotations

import json
from pathlib import Path

import wikidebia_translation_preflight as preflight
from wikidebia_update import sha_object


def _documents():
    translation = {
        "status": "approved",
        "canonical_title": "A valid argument title",
        "displayed_title": "A valid argument title",
        "page_origin": "new",
        "source_page_origin": "preexisting",
        "preserved_parameters": {},
    }
    packet = {
        "packet_sha256": "p" * 64,
        "arguments": [{
            "id": "A1", "translation": dict(translation), "source_changed": False,
        }],
    }
    patch = {
        "base_packet_sha256": "p" * 64,
        "arguments": [{"id": "A1", "translation": dict(translation)}],
        "vocabulary": [{
            "concept_id": "K1", "fr": "égalité", "en": "equality",
            "kind": "noun", "en_kind": "noun",
        }],
        "relation_labels": [{"id": "E1", "translated_text": "supports"}],
    }
    return patch, packet


def test_mechanical_preflight_accepts_clean_patch_and_writes_signed_report(tmp_path: Path, monkeypatch):
    patch, packet = _documents()
    workspace = tmp_path / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(preflight, "_load_workspace", lambda *args: (workspace, {}))

    result = preflight.run_preflight(
        tmp_path, "debat_test", "EDIT-TEST-001", "U001",
        patch=patch, packet=packet,
    )

    assert result["status"] == "passed"
    assert result["semantic_review_performed"] is False
    saved = json.loads((workspace / "audits/translation-preflight/U001.json").read_text())
    unsigned = dict(saved)
    assert unsigned.pop("preflight_sha256") == sha_object(unsigned)


def test_mechanical_preflight_reports_only_deterministic_defects():
    patch, packet = _documents()
    packet["arguments"][0]["source_changed"] = True
    translation = patch["arguments"][0]["translation"]
    translation["canonical_title"] = "Bad title."
    translation["preserved_parameters"] = {"justification-warnings": {"present": True, "value": ""}}
    translation["justifications"] = ""
    patch["vocabulary"][0]["en"] = "Equality"
    patch["relation_labels"][0]["translated_text"] = ""

    findings = preflight.analyze_patch(patch, packet)
    codes = {row["code"] for row in findings}

    assert "french_source_changed" in codes
    assert "title_terminal_period" in codes
    assert "work_context_modified" in codes
    assert "relationship_field_forbidden" in codes
    assert "vocabulary_common_keyword_initial_uppercase" in codes
    assert "relation_label_empty" in codes


def test_mechanical_preflight_rejects_control_characters_and_outer_whitespace():
    patch, packet = _documents()
    patch["arguments"][0]["translation"]["displayed_title"] = " title\x01 "

    findings = preflight.analyze_patch(patch, packet)
    codes = {row["code"] for row in findings}

    assert "outer_whitespace" in codes
    assert "control_character" in codes
