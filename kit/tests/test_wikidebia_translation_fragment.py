from __future__ import annotations

import json
from pathlib import Path

import wikidebia_translation_fragment as fragment
from wikidebia_update import sha_object


def _fixture(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    review_path = workspace / "reviews/en/translation_review.json"
    review_path.parent.mkdir(parents=True)
    arguments = []
    packet_arguments = []
    for index in (1, 2):
        page_id = f"A{index}"
        french = {
            "metadata": {"entity_id": page_id, "canonical_title": f"Argument {index}"},
            "content": {"id": page_id, "summary": f"Source française {index}"},
        }
        translation = {
            "status": "pending",
            "canonical_title": f"Argument {index}",
            "displayed_title": f"Argument {index}",
            "citations": [],
            "french": french,
        }
        arguments.append({"id": page_id, "review_unit_id": "U001", "translation": translation})
        packet_translation = dict(translation)
        packet_translation.pop("french")
        packet_arguments.append({
            "id": page_id,
            "translation": packet_translation,
            "current_french": french,
            "current_source_sha256": str(index) * 64,
            "prepared_source_sha256": str(index) * 64,
            "source_changed": False,
            "filler": "x" * 3000,
        })
    review = {
        "schema": "translation-review",
        "debate_id": "debat_test",
        "work_id": "EDIT-TEST-001",
        "status": "draft",
        "review_sha256": None,
        "arguments": arguments,
        "review_units": [{
            "id": "U001", "page_ids": ["A1", "A2"], "status": "pending",
            "reviewer": "", "reviewed_at": None, "note": "",
        }],
        "vocabulary": [{
            "concept_id": "K1", "fr": "égalité", "en": "equality",
            "usages": [{"page_id": "A1"}],
        }],
        "relation_labels": [{
            "id": "E1", "source_page_id": "A1", "target_node_id": "A2",
            "source_text": "soutient", "translated_text": "supports",
        }],
    }
    review_path.write_text(json.dumps(review), encoding="utf-8")

    def fake_packet(_root, _debate, _work, unit_id):
        value = {
            "packet_sha256": "p" * 64,
            "unit": {"id": unit_id},
            "arguments": packet_arguments,
            "vocabulary": review["vocabulary"],
            "relation_labels": review["relation_labels"],
        }
        path = workspace / f"audits/translation-packets/{unit_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return value

    monkeypatch.setattr(fragment, "_load_workspace", lambda *args: (
        workspace, {"status": "en_translation_review_ready"},
    ))
    monkeypatch.setattr(fragment, "build_packet", fake_packet)
    return project, workspace, review_path


def _approve_fragment(path: Path) -> None:
    value = json.loads(path.read_text())
    value["translation"]["status"] = "approved"
    value["translation"]["canonical_title"] += " translated"
    value["translation"]["displayed_title"] += " translated"
    path.write_text(json.dumps(value), encoding="utf-8")


def test_next_fragment_contains_one_argument_and_reduces_context(tmp_path: Path, monkeypatch):
    project, _workspace, _review_path = _fixture(tmp_path, monkeypatch)

    result = fragment.prepare_next_fragment(project, "debat_test", "EDIT-TEST-001")

    assert result["status"] == "argument_fragment_prepared"
    assert result["page_id"] == "A1"
    assert result["argument_context_bytes"] < result["unit_packet_bytes"]
    context = json.loads((project / result["context_path"]).read_text())
    assert context["argument_source"]["id"] == "A1"
    assert "translation" not in context["argument_source"]
    assert context["fragment"]["translation"]["status"] == "pending"


def test_two_prepared_arguments_apply_independently(tmp_path: Path, monkeypatch):
    project, _workspace, review_path = _fixture(tmp_path, monkeypatch)
    prepared = {}
    for page_id in ("A1", "A2"):
        result = fragment.prepare_fragment(
            project, "debat_test", "EDIT-TEST-001", "U001", page_id,
        )
        path = project / result["fragment_path"]
        _approve_fragment(path)
        prepared[page_id] = path

    for page_id in ("A1", "A2"):
        sealed = fragment.seal_fragment(
            project, "debat_test", "EDIT-TEST-001", "U001", page_id,
            reviewer="Reviewer", note="Argument translated and reviewed",
        )
        result = fragment.apply_fragment(
            project, "debat_test", "EDIT-TEST-001", "U001", page_id,
            confirm_fragment_sha256=sealed["fragment_sha256"],
        )
        assert result["status"] == "applied"
        assert result["french_fields_mutated"] is False

    review = json.loads(review_path.read_text())
    assert [row["translation"]["status"] for row in review["arguments"]] == [
        "approved", "approved",
    ]
    assert review["arguments"][0]["translation"]["french"]["content"]["summary"] == "Source française 1"
    repeated = fragment.apply_fragment(
        project, "debat_test", "EDIT-TEST-001", "U001", "A2",
        confirm_fragment_sha256=json.loads(prepared["A2"].read_text())["fragment_sha256"],
    )
    assert repeated["status"] == "already_applied"


def test_seal_rejects_french_relationship_injection(tmp_path: Path, monkeypatch):
    project, _workspace, _review_path = _fixture(tmp_path, monkeypatch)
    result = fragment.prepare_fragment(
        project, "debat_test", "EDIT-TEST-001", "U001", "A1",
    )
    path = project / result["fragment_path"]
    value = json.loads(path.read_text())
    value["translation"]["status"] = "approved"
    value["translation"]["justifications"] = []
    path.write_text(json.dumps(value), encoding="utf-8")

    try:
        fragment.seal_fragment(
            project, "debat_test", "EDIT-TEST-001", "U001", "A1",
            reviewer="Reviewer", note="Argument translated and reviewed",
        )
    except fragment.TranslationFragmentError as exc:
        assert "relationship_field_forbidden" in str(exc)
    else:
        raise AssertionError("l’injection relationnelle aurait dû être refusée")


def test_application_receipt_is_signed_and_bound_to_argument(tmp_path: Path, monkeypatch):
    project, workspace, _review_path = _fixture(tmp_path, monkeypatch)
    prepared = fragment.prepare_fragment(
        project, "debat_test", "EDIT-TEST-001", "U001", "A1",
    )
    path = project / prepared["fragment_path"]
    _approve_fragment(path)
    sealed = fragment.seal_fragment(
        project, "debat_test", "EDIT-TEST-001", "U001", "A1",
        reviewer="Reviewer", note="Argument translated and reviewed",
    )
    fragment.apply_fragment(
        project, "debat_test", "EDIT-TEST-001", "U001", "A1",
        confirm_fragment_sha256=sealed["fragment_sha256"],
    )

    receipt = json.loads((workspace / "audits/translation-fragments/A1-application.json").read_text())
    body = dict(receipt)
    assert body.pop("receipt_sha256") == sha_object(body)
    assert receipt["page_id"] == "A1"
    assert receipt["argument_before_sha256"] != receipt["argument_after_sha256"]
