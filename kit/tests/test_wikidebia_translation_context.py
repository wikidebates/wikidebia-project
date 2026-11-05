from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_translation_context as context
from wikidebia_update import sha_object


def _signed(value, field):
    body = dict(value)
    body.pop(field, None)
    value[field] = sha_object(body)
    return value


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _fixture(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    workspace = project / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    _write(workspace / "reviews/en/translation_review.json", {
        "status": "draft", "large_review_context": "x" * 20000,
    })
    packet = _signed({
        "schema": "packet", "arguments": [{"id": "A1", "source": "f" * 1000}],
        "packet_sha256": None,
    }, "packet_sha256")
    _write(workspace / "audits/translation-packets/U001.json", packet)
    _write(workspace / "reviews/en/unit-patches/U001.json", {
        "schema": "patch", "status": "draft",
        "base_packet_sha256": packet["packet_sha256"],
        "arguments": [{"id": "A1", "translation": {"canonical_title": "Title"}}],
    })
    _write(workspace / "audits/translation-resume.json", _signed({
        "schema": "capsule", "active_unit_id": "U001", "capsule_sha256": None,
    }, "capsule_sha256"))
    monkeypatch.setattr(context, "_load_workspace", lambda *args: (workspace, {}))
    return project, workspace


def test_compact_context_records_real_byte_savings_without_payload(tmp_path: Path, monkeypatch):
    project, workspace = _fixture(tmp_path, monkeypatch)

    result = context.build_translation_context(
        project, "debat_test", "EDIT-TEST-001", "U001",
    )

    assert result["mode"] == "compact"
    assert result["telemetry"]["avoided_context_bytes"] > 15000
    assert result["telemetry"]["avoided_ratio"] > 0.7
    saved = json.loads((project / result["context_path"]).read_text())
    assert "payload" not in saved
    assert result["context_size_bytes"] < 3000
    ledger = json.loads((project / result["telemetry_path"]).read_text())
    body = dict(ledger)
    assert body.pop("telemetry_sha256") == sha_object(body)
    assert ledger["totals"]["events"] == 1


def test_same_context_state_is_not_counted_twice(tmp_path: Path, monkeypatch):
    project, _workspace = _fixture(tmp_path, monkeypatch)
    first = context.build_translation_context(project, "debat_test", "EDIT-TEST-001", "U001")

    second = context.build_translation_context(project, "debat_test", "EDIT-TEST-001", "U001")

    assert second["telemetry_totals"]["events"] == 1
    assert second["telemetry_sha256"] == first["telemetry_sha256"]


def test_full_mode_writes_payload_to_file_but_returns_compact_summary(tmp_path: Path, monkeypatch):
    project, _workspace = _fixture(tmp_path, monkeypatch)

    result = context.build_translation_context(
        project, "debat_test", "EDIT-TEST-001", "U001", output_mode="full",
    )

    saved = json.loads((project / result["context_path"]).read_text())
    assert saved["payload"]["packet"]["arguments"][0]["id"] == "A1"
    assert "payload" not in result
    assert result["mode"] == "full"


def test_context_rejects_tampered_packet(tmp_path: Path, monkeypatch):
    project, workspace = _fixture(tmp_path, monkeypatch)
    path = workspace / "audits/translation-packets/U001.json"
    value = json.loads(path.read_text())
    value["arguments"][0]["id"] = "TAMPERED"
    _write(path, value)

    with pytest.raises(context.TranslationContextError, match="Empreinte invalide"):
        context.build_translation_context(project, "debat_test", "EDIT-TEST-001", "U001")
