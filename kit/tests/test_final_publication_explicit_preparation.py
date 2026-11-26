"""Read-only signed plan preparation and explicit final publication authorization."""
from __future__ import annotations

import json
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

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


def _prepared_publication(project, monkeypatch):
    release = project / "release"
    release.mkdir()
    (release / "manifest.json").write_text("{}", encoding="utf-8")
    state_dir = final._state_dir(project, "demo", "EDIT-20261121-001")
    baseline = {"fr": {"mode": "published_checkpoint_state"}}
    baseline["baseline_sha256"] = final._canonical(baseline, "baseline_sha256")
    _write(state_dir / "baseline.json", baseline)
    plans = {f"{name}_plan": {"plan_sha256": token * 64} for name, token in (
        ("en", "e"), ("fr", "f"), ("safety", "5"),
    )}
    times = iter(("2026-11-26T14:00:00Z", "2026-11-26T14:01:00Z", "2026-11-26T14:02:00Z"))
    observed = {"status": "ready", "remote_snapshots": [{"revision_id": 42}],
                "english_plan_sha256": "e" * 64, "french_plan_sha256": "f" * 64, "safety_plan_sha256": "5" * 64}

    def observe(*args):
        preflight = {**observed, "checked_at": next(times)}
        preflight["preflight_sha256"] = final._canonical(preflight, "preflight_sha256")
        return preflight

    monkeypatch.setattr(final, "seal_workflow_release_baseline", lambda *args, **kwargs: baseline)
    monkeypatch.setattr(final, "_load_or_build_plans", lambda *args, **kwargs: plans)
    monkeypatch.setattr(final, "_load_saved_plans", lambda *args: plans)
    monkeypatch.setattr(final, "_observe_preflight", observe)
    prepared = final.prepare_final_release(project, "demo", "EDIT-20261121-001", release)
    return release, state_dir, prepared, observed


def test_interruption_after_revalidation_keeps_the_same_approval(tmp_path, monkeypatch):
    release, state_dir, prepared, _ = _prepared_publication(tmp_path, monkeypatch)
    preflight_path = state_dir / "preflight.json"
    original = preflight_path.read_bytes()
    approved = prepared["preflight_sha256"]

    def interrupt(*args, **kwargs):
        assert kwargs["revalidation"]["checked_at"] == "2026-11-26T14:01:00Z"
        raise KeyboardInterrupt

    with monkeypatch.context() as interruption:
        interruption.setattr(final, "_authorization", interrupt)
        with pytest.raises(KeyboardInterrupt):
            final.publish_final_release(tmp_path, "demo", "EDIT-20261121-001", release,
                                        confirm_preflight_sha256=approved)
    assert preflight_path.read_bytes() == original
    assert not (state_dir / "authorization.json").exists()
    assert final.prepare_final_release(tmp_path, "demo", "EDIT-20261121-001", release) == prepared

    # Stop before the publisher. This run must reach authorization with the
    # original hash, even though both read-only checks have a newer timestamp.
    monkeypatch.setattr(final, "_migrate_english_publication_order", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        final.publish_final_release(tmp_path, "demo", "EDIT-20261121-001", release,
                                    confirm_preflight_sha256=approved)
    authorization = json.loads((state_dir / "authorization.json").read_text())
    assert authorization["preflight_sha256"] == approved
    assert authorization["preflight_revalidated_at"] == "2026-11-26T14:02:00Z"
    assert authorization["revalidated_preflight_sha256"] != approved
    assert preflight_path.read_bytes() == original


def test_remote_change_preserves_approval_without_authorizing_writes(tmp_path, monkeypatch):
    release, state_dir, prepared, observed = _prepared_publication(tmp_path, monkeypatch)
    original = (state_dir / "preflight.json").read_bytes()
    observed["remote_snapshots"] = [{"revision_id": 43}]
    with pytest.raises(final.FinalPublicationError, match="État distant changé"):
        final.publish_final_release(tmp_path, "demo", "EDIT-20261121-001", release,
                                    confirm_preflight_sha256=prepared["preflight_sha256"])
    assert (state_dir / "preflight.json").read_bytes() == original
    assert not (state_dir / "authorization.json").exists()


def test_legacy_interruption_presents_the_replacement_for_a_new_approval(tmp_path, monkeypatch):
    release, state_dir, prepared, _ = _prepared_publication(tmp_path, monkeypatch)
    plans = final._load_saved_plans(tmp_path, state_dir)
    refreshed = final._preflight(tmp_path, state_dir, plans)
    assert refreshed["preflight_sha256"] != prepared["preflight_sha256"]
    recovered = final.prepare_final_release(tmp_path, "demo", "EDIT-20261121-001", release)
    assert recovered["preflight_sha256"] == refreshed["preflight_sha256"]
    assert recovered["preparation_sha256"] == final._canonical(recovered, "preparation_sha256")

    with pytest.raises(final.FinalPublicationError, match="différente de la préparation"):
        final.publish_final_release(tmp_path, "demo", "EDIT-20261121-001", release,
                                    confirm_preflight_sha256=prepared["preflight_sha256"])
    assert not (state_dir / "authorization.json").exists()


def test_second_publisher_cannot_enter_the_same_debate(tmp_path, monkeypatch):
    workflow._save_workflow(tmp_path, {
        "schema": workflow.WORKFLOW_SCHEMA, "debate_id": "demo", "work_id": "EDIT-20261121-001",
        "phase": "publication_prepared", "status": "publication_prepared",
    })
    monkeypatch.setattr(workflow, "_current_workspace_meta", lambda *args: (tmp_path, {}))
    monkeypatch.setattr(workflow, "reconcile_published_workspace", lambda *args: None)
    entered, done = Event(), Event()

    def publish(*args, **kwargs):
        entered.set()
        assert done.wait(timeout=5)
        return {"status": "published"}

    monkeypatch.setattr(workflow, "publish_final_release", publish)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(workflow.publish_prepared_workflow, tmp_path, "demo", "a" * 64)
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(workflow.WorkflowError, match="déjà en cours"):
                workflow.publish_prepared_workflow(tmp_path, "demo", "a" * 64)
            with pytest.raises(workflow.WorkflowError, match="déjà en cours"):
                workflow.publish_preserved_workflow(tmp_path, "demo", "EDIT-20261121-001")
            with workflow._final_publication_lock(tmp_path, "another_debate"):
                pass
        finally:
            done.set()
        assert first.result(timeout=5)["status"] == "published"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks and signals")
def test_publication_lock_is_released_when_the_process_is_killed(tmp_path):
    code = """
import os, signal, sys
from pathlib import Path
from wikidebia_review_workflow import _final_publication_lock
with _final_publication_lock(Path(sys.argv[1]), 'demo'):
    os.kill(os.getpid(), signal.SIGKILL)
"""
    child = subprocess.run([sys.executable, "-c", code, str(tmp_path)], cwd=SCRIPTS, timeout=10)
    assert child.returncode == -signal.SIGKILL
    assert (tmp_path / ".state/locks/final-publication-demo.lock").is_file()
    with workflow._final_publication_lock(tmp_path, "demo"):
        pass


@pytest.mark.parametrize("status,code", [("blocked_final_publication", 2), ("publication_prepared", 2), ("published", 0)])
def test_workflow_publish_cli_reports_an_incomplete_publication_as_failure(tmp_path, monkeypatch, status, code):
    monkeypatch.setattr(workflow, "publish_prepared_workflow", lambda *a, **k: {"status": status})
    assert workflow.main(["--project-root", str(tmp_path), "--machine-readable", "workflow-publish",
                          "demo", "--confirm-preflight-sha256", "a" * 64]) == code
