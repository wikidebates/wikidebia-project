from __future__ import annotations

import json
from pathlib import Path

import pytest

import wikidebia_translation_next as next_unit
from wikidebia_update import sha_object


def _worklist(*, units, complete=False, digest="w" * 64):
    return {
        "units": units,
        "complete": complete,
        "worklist_sha256": digest,
        "worklist_path": ".state/worklist.json",
        "next_command": "./wikidebia finalize" if complete else None,
    }


def test_next_unit_prepares_first_pending_unit_with_memory(tmp_path: Path, monkeypatch):
    workspace = tmp_path / ".state/editorial-workspaces/debat_test/EDIT-TEST-001"
    workspace.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(next_unit, "_load_workspace", lambda *args: (workspace, {}))
    monkeypatch.setattr(next_unit, "build_worklist", lambda *args: _worklist(units=[
        {"unit_id": "U002", "max_risk_level": "high"},
        {"unit_id": "U003", "max_risk_level": "low"},
    ]))
    monkeypatch.setattr(next_unit, "build_packet", lambda *args, **kwargs: (
        calls.append((args, kwargs)) or {
            "packet_sha256": "p" * 64,
            "packet_path": ".state/U002.json",
            "counts": {"unit_arguments": 8, "arguments": 3, "memory_reused": 5},
        }
    ))
    monkeypatch.setattr(next_unit, "prepare_patch", lambda *args: {
        "patch_path": ".state/U002-patch.json",
        "base_packet_sha256": "p" * 64,
    })

    result = next_unit.prepare_next_unit(
        tmp_path, "debat_test", "EDIT-TEST-001", memory_root=Path("memory"),
    )

    assert result["status"] == "unit_prepared"
    assert result["unit_id"] == "U002"
    assert result["counts"]["memory_reused"] == 5
    assert calls[0][1] == {"reuse_memory": True, "memory_root": Path("memory")}
    assert "--unit-id U002 --seal" in result["seal_command_template"]
    saved = json.loads((workspace / "audits/translation-next.json").read_text())
    unsigned = dict(saved)
    assert unsigned.pop("selection_sha256") == sha_object(unsigned)
    assert result["remote_write_performed"] is False


def test_next_unit_returns_finalization_without_building_packet(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(next_unit, "_load_workspace", lambda *args: (workspace, {}))
    monkeypatch.setattr(
        next_unit, "build_worklist",
        lambda *args: _worklist(units=[], complete=True),
    )
    monkeypatch.setattr(
        next_unit, "build_packet",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("unexpected packet")),
    )

    result = next_unit.prepare_next_unit(tmp_path, "debat_test", "EDIT-TEST-001")

    assert result["status"] == "complete"
    assert result["unit_id"] is None
    assert result["next_command"] == "./wikidebia finalize"


def test_next_unit_reports_global_review_when_no_unit_remains(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(next_unit, "_load_workspace", lambda *args: (workspace, {}))
    monkeypatch.setattr(
        next_unit, "build_worklist",
        lambda *args: _worklist(units=[], complete=False),
    )

    result = next_unit.prepare_next_unit(tmp_path, "debat_test", "EDIT-TEST-001")

    assert result["status"] == "global_review_required"
    assert result["unit_id"] is None


def test_next_unit_refuses_to_overwrite_patch_for_older_packet(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(next_unit, "_load_workspace", lambda *args: (workspace, {}))
    monkeypatch.setattr(next_unit, "build_worklist", lambda *args: _worklist(
        units=[{"unit_id": "U001", "max_risk_level": "low"}],
    ))
    monkeypatch.setattr(next_unit, "build_packet", lambda *args, **kwargs: {
        "packet_sha256": "p" * 64, "packet_path": "packet.json", "counts": {},
    })
    monkeypatch.setattr(next_unit, "prepare_patch", lambda *args: {
        "patch_path": "patch.json", "base_packet_sha256": "o" * 64,
    })

    with pytest.raises(next_unit.TranslationNextError, match="ancien paquet"):
        next_unit.prepare_next_unit(tmp_path, "debat_test", "EDIT-TEST-001")
