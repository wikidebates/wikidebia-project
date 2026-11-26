"""Recover interrupted migration of an already authorized publication."""
from __future__ import annotations

import copy
import signal
import subprocess
import sys
from pathlib import Path

import pytest

import wikidebia_final_publication as final
import wikidebia_workspace_status as workspace_status
from test_final_publication_debate_first_21646 import _action


DEBATE = "demo"
WORK = "EDIT-20261126-001"
ORDER = "publication-order-migrations"
KIT_CHANGE = "kit-change-plan-migrations"


def _observed_preflight(project, plans):
    preflight = {
        "status": "ready", "remote_snapshots": [],
        "english_plan_sha256": plans["en_plan"]["plan_sha256"],
        "french_plan_sha256": plans["fr_plan"]["plan_sha256"],
        "safety_plan_sha256": plans["safety_plan"]["plan_sha256"],
    }
    preflight["preflight_sha256"] = final._canonical(preflight, "preflight_sha256")
    return preflight


def _authorized_state(tmp_path, monkeypatch, kind=KIT_CHANGE):
    state = final._state_dir(tmp_path, DEBATE, WORK)
    baseline = {"debate_id": DEBATE, "work_id": WORK, "fr": {"mode": "published_checkpoint_state"}}
    baseline["baseline_sha256"] = final._canonical(baseline, "baseline_sha256")
    final.write_json(state / "baseline.json", baseline)
    argument, debate = _action("A0001", "argument"), _action(DEBATE, "debate")
    en = {
        "actions": [argument, debate] if kind == ORDER else [debate, argument],
        "package_fingerprints": {"kit": "current" if kind == ORDER else "previous"},
    }
    en["plan_sha256"] = final._canonical(en, "plan_sha256")
    for name, plan in (("english-publication", en), ("french-update", {"plan_sha256": "f" * 64}),
                       ("safety-update", {"plan_sha256": "5" * 64})):
        final.write_json(state / f"{name}-config.json", {"operation": {}, "version": "previous"})
        final.write_json(state / f"{name}-plan.json", plan)
    plans = final._load_saved_plans(tmp_path, state)
    monkeypatch.setattr(final, "_observe_preflight", _observed_preflight)
    preflight = final._preflight(tmp_path, state, plans)
    authorization = final._authorization(state, baseline, preflight)
    preparation = {"debate_id": DEBATE, "work_id": WORK, "status": "publication_prepared",
                   "release_copy_tree_sha256": "a" * 64, "baseline_sha256": baseline["baseline_sha256"],
                   "preflight_sha256": preflight["preflight_sha256"]}
    preparation["preparation_sha256"] = final._canonical(preparation, "preparation_sha256")
    final.write_json(state / "publication-preparation.json", preparation)
    return state, baseline, plans, preflight, authorization


class ProcessStopped(BaseException):
    """A terminated process cannot run the migration exception handler."""


def _simulate_mediawiki(monkeypatch, state, plans, enter_publisher):
    successor = copy.deepcopy(plans["en_plan"])
    successor.update(package_fingerprints={"kit": "current"})

    class Publisher:
        def __init__(self, *args):
            pass

        def _package_fingerprints(self):
            return {"kit": "current"}

        def build_plan(self):
            return copy.deepcopy(successor)

        def publish(self, **kwargs):
            enter_publisher(**kwargs)

    def config(*args):
        return state / "english-publication-config.json", {"operation": {}, "version": "current"}

    monkeypatch.setattr(final, "_english_config", config)
    monkeypatch.setattr(final, "build_adapter", lambda *args: object())
    monkeypatch.setattr(final, "GenericPublisher", Publisher)


@pytest.mark.parametrize("kind", [ORDER, KIT_CHANGE])
@pytest.mark.parametrize("boundary", [*final.PLAN_MIGRATION_FILES, "migration.json"])
def test_resume_restores_before_rebuilding_an_interrupted_migration(tmp_path, monkeypatch, kind, boundary):
    state, baseline, plans, preflight, authorization = _authorized_state(tmp_path, monkeypatch, kind)
    approved = preflight["preflight_sha256"]
    original = {name: (state / name).read_bytes() for name in final.PLAN_MIGRATION_FILES}
    enter = []

    def reach_publisher(**kwargs):
        assert not (state / final.PENDING_PLAN_MIGRATION).exists()
        assert kwargs["plan"]["actions"][0]["page_type"] == "debate"
        enter.append(kwargs["confirmation"])
        raise ProcessStopped

    _simulate_mediawiki(monkeypatch, state, plans, reach_publisher)
    migrate = final._migrate_english_publication_order if kind == ORDER else final._migrate_english_plan_after_kit_change
    writer = final.write_json

    def interrupt_after_write(path, value):
        writer(path, value)
        if path.name == boundary:
            raise ProcessStopped

    with monkeypatch.context() as interrupted:
        interrupted.setattr(final, "write_json", interrupt_after_write)
        with pytest.raises(ProcessStopped):
            migrate(tmp_path, DEBATE, tmp_path, state, baseline, plans, preflight, authorization)
    history, digest = final.pending_plan_migration(state)
    assert digest == approved
    assert not enter

    # Status selects the previous approved digest even if a successor digest
    # already exists in the live preflight file.
    monkeypatch.setattr(workspace_status, "_load_workspace", lambda *args: (tmp_path, {
        "status": "release_ready", "release_copy": {"tree_sha256": "a" * 64},
    }))
    status = workspace_status.summarize_workspace(tmp_path, DEBATE, WORK)
    assert status["status"] == "final_publication_migration_pending"
    assert status["next_command"].endswith(f"--confirm-preflight-sha256 {approved}")

    before_retry = {name: (state / name).read_bytes() for name in final.PLAN_MIGRATION_FILES}
    with pytest.raises(final.FinalPublicationError, match="préflight sauvegardé"):
        final.publish_final_release(tmp_path, DEBATE, WORK, tmp_path, confirm_preflight_sha256="0" * 64)
    assert all((state / name).read_bytes() == data for name, data in before_retry.items())

    load_plans = final._load_saved_plans

    def load_restored(*args):
        assert all((state / name).read_bytes() == data for name, data in original.items())
        return load_plans(*args)

    monkeypatch.setattr(final, "_load_saved_plans", load_restored)
    with pytest.raises(ProcessStopped):
        final.publish_final_release(tmp_path, DEBATE, WORK, tmp_path, confirm_preflight_sha256=approved)
    assert len(enter) == 1
    rollback = final.load_json(history / "rollback.json")
    assert rollback["rollback_sha256"] == final._canonical(rollback, "rollback_sha256")
    assert not (history / "migration.json").exists()
    assert (history / "uncommitted-migration.json").exists() == (boundary == "migration.json")
    assert len(list((state / kind).glob("*/migration.json"))) == 1
    successor = final.load_json(state / "preflight.json")["preflight_sha256"]
    status = workspace_status.summarize_workspace(tmp_path, DEBATE, WORK)
    assert status["status"] == "final_publication_resume"
    assert status["publication_preflight_sha256"] == successor != approved


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL requires POSIX")
def test_killed_migration_can_be_restored_even_if_the_first_rollback_is_interrupted(tmp_path, monkeypatch):
    state, _, _, preflight, _ = _authorized_state(tmp_path, monkeypatch)
    code = """
import os, signal, sys
from pathlib import Path
from wikidebia_final_publication import _plan_migration, write_json
state = Path(sys.argv[1])
with _plan_migration(state, 'kit-change-plan-migrations'):
    write_json(state / 'preflight.json', {'incomplete': True})
    os.kill(os.getpid(), signal.SIGKILL)
"""
    scripts = Path(final.__file__).resolve().parent
    killed = subprocess.run([sys.executable, "-c", code, str(state)], cwd=scripts, timeout=10)
    assert killed.returncode == -signal.SIGKILL
    history, digest = final.pending_plan_migration(state)
    assert digest == preflight["preflight_sha256"]
    replace = final.os.replace

    def stop_after_first_restoration(source, target):
        replace(source, target)
        if target == state / final.PLAN_MIGRATION_FILES[0]:
            raise ProcessStopped

    with monkeypatch.context() as interrupted:
        interrupted.setattr(final.os, "replace", stop_after_first_restoration)
        with pytest.raises(ProcessStopped):
            final._rollback_plan_migration(state, history)
    assert final.pending_plan_migration(state) == (history, digest)

    final._rollback_plan_migration(state, history)
    assert all((state / name).read_bytes() == (history / name).read_bytes()
               for name in final.PLAN_MIGRATION_FILES)
    assert final.pending_plan_migration(state) is None


def test_altered_migration_backup_blocks_restoration(tmp_path, monkeypatch):
    state, _, _, preflight, _ = _authorized_state(tmp_path, monkeypatch)
    with pytest.raises(ProcessStopped):
        with final._plan_migration(state, KIT_CHANGE) as history:
            raise ProcessStopped
    (history / "english-publication-plan.json").write_text("{}", encoding="utf-8")
    before = {name: (state / name).read_bytes() for name in final.PLAN_MIGRATION_FILES}
    with pytest.raises(final.FinalPublicationError, match="incomplète ou modifiée"):
        final.publish_final_release(tmp_path, DEBATE, WORK, tmp_path,
                                    confirm_preflight_sha256=preflight["preflight_sha256"])
    assert (state / final.PENDING_PLAN_MIGRATION).exists()
    assert all((state / name).read_bytes() == content for name, content in before.items())


def test_migration_error_restores_the_previous_evidence_before_returning(tmp_path, monkeypatch):
    state, _, _, _, _ = _authorized_state(tmp_path, monkeypatch)
    original = (state / "preflight.json").read_bytes()
    with pytest.raises(OSError, match="test failure"):
        with final._plan_migration(state, KIT_CHANGE) as history:
            final.write_json(state / "preflight.json", {"incomplete": True})
            raise OSError("test failure")
    assert (state / "preflight.json").read_bytes() == original
    assert not (state / final.PENDING_PLAN_MIGRATION).exists()
    assert final.load_json(history / "rollback.json")["status"] == "restored"
