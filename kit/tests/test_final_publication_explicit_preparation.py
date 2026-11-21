"""Read-only signed plan preparation and explicit final publication authorization."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_final_publication as final
import wikidebia_review_workflow as workflow


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def test_prepare_signs_exact_plans_without_permission_to_write(tmp_path, monkeypatch):
    root = tmp_path
    release = root / "release"
    release.mkdir()
    (release / "manifest.json").write_text("{}", encoding="utf-8")
    plans = {
        "en_plan": {"plan_sha256": "e" * 64},
        "fr_plan": {"plan_sha256": "f" * 64},
        "safety_plan": {"plan_sha256": "s" * 64},
    }
    calls = []
    monkeypatch.setattr(final, "seal_workflow_release_baseline", lambda *a, **k: {
        "baseline_sha256": "b" * 64, "fr": {"mode": "published_checkpoint_state"},
    })
    def builder(*args, **kwargs):
        calls.append("plans")
        return plans
    def checker(project, state, config):
        calls.append("preflight")
        return {"preflight_sha256": "p" * 64, "remote_snapshots": []}
    monkeypatch.setattr(final, "_load_or_build_plans", builder)
    monkeypatch.setattr(final, "_preflight", checker)
    value = final.prepare_final_release(root, "demo", "EDIT-20261121-001", release)
    assert calls == ["plans", "preflight"]
    assert value["preflight_sha256"] == "p" * 64
    assert value["en_plan_sha256"] == "e" * 64
    assert value["fr_plan_sha256"] == "f" * 64
    assert value["remote_write_authorized"] is False
    assert value["remote_write_performed"] is False
    path = root / ".state/final-publication/demo/EDIT-20261121-001/publication-preparation.json"
    assert path.exists()
    assert not (path.parent / "authorization.json").exists()
    assert value["preparation_sha256"] == final._canonical(value, "preparation_sha256")


def test_publish_rejects_missing_confirmation_without_preflight_or_write(tmp_path):
    with pytest.raises(final.FinalPublicationError, match="Empreinte du préflight signé obligatoire"):
        final.publish_final_release(
            tmp_path, "demo", "EDIT-20261121-001", tmp_path,
        )
    assert not (tmp_path / ".state/final-publication").exists()


def test_explicit_workflow_publish_cannot_start_from_editorial_review(tmp_path):
    workflow._save_workflow(tmp_path, {
        "schema": workflow.WORKFLOW_SCHEMA,
        "debate_id": "demo", "phase": "en_translation_review",
        "status": "awaiting_review", "work_id": "EDIT-20261121-001",
    })
    with pytest.raises(workflow.WorkflowError, match="Aucune publication finale préparée"):
        workflow.publish_prepared_workflow(tmp_path, "demo", "a" * 64)


def test_workflow_publish_requires_64_character_confirmation(tmp_path):
    workflow._save_workflow(tmp_path, {
        "schema": workflow.WORKFLOW_SCHEMA, "debate_id": "demo",
        "phase": "publication_prepared", "status": "publication_prepared",
        "work_id": "EDIT-20261121-001",
    })
    with pytest.raises(workflow.WorkflowError, match="Empreinte SHA-256"):
        workflow.publish_prepared_workflow(tmp_path, "demo", "wrong")
