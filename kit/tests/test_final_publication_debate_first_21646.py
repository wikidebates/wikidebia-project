import json
from pathlib import Path

import wikidebia_final_publication as final


def _action(page_id: str, page_type: str, operation: str = "create", revision=None):
    row = {
        "operation_id": "workflow_final_publish_en",
        "kind": "full_page",
        "language": "en",
        "page_id": page_id,
        "page_type": page_type,
        "title": f"Title {page_id}",
        "source_path": "output/en/debate/debate.wiki" if page_type == "debate" else f"output/en/arguments/{page_id}.wiki",
        "parameter": None,
        "local_file_sha256": f"file-{page_id}",
        "local_target_sha256": f"target-{page_id}",
        "edit_summary": f"Translation {page_id}",
        "change_tags": ["chatgpt", "translated-fr"],
        "publication_creation_date": "2026-08-21",
        "desired_sha256": f"desired-{page_id}",
        "operation": operation,
    }
    if revision is not None:
        row["remote_revision_id"] = revision
    return row


def test_reorder_english_plan_places_debate_before_arguments():
    plan = {"actions": [_action("A0002", "argument"), _action("debate", "debate"), _action("A0001", "argument")], "plan_sha256": "old"}
    ordered = final._reorder_english_plan(plan)
    assert [(row["page_type"], row["page_id"]) for row in ordered["actions"]] == [
        ("debate", "debate"), ("argument", "A0001"), ("argument", "A0002")
    ]
    assert ordered["plan_sha256"] != "old"


def test_detects_legacy_arguments_before_debate_only_when_debate_is_still_pending():
    legacy = {"actions": [_action("A0001", "argument"), _action("debate", "debate")]}
    assert final._english_plan_needs_debate_first_migration(legacy)
    good = {"actions": [_action("debate", "debate"), _action("A0001", "argument")]}
    assert not final._english_plan_needs_debate_first_migration(good)
    already_done = {"actions": [_action("debate", "debate", "skip", 10), _action("A0001", "argument")]}
    assert not final._english_plan_needs_debate_first_migration(already_done)


def test_order_transition_allows_proven_completed_arguments_but_requires_debate_first_among_remaining():
    old_plan = {"actions": [_action("A0001", "argument"), _action("debate", "debate"), _action("A0002", "argument")]}
    new_plan = {"actions": [_action("debate", "debate"), _action("A0001", "argument", "skip", 11), _action("A0002", "argument")]}
    result = final._english_plan_order_transition(old_plan, new_plan)
    assert [row["page_id"] for row in result["completed_before_order_migration"]] == ["A0001"]
    assert [row["page_id"] for row in result["remaining_after_order_migration"]] == ["A0002", "debate"] or [row["page_id"] for row in result["remaining_after_order_migration"]] == ["debate", "A0002"]


def test_order_migration_reseals_and_archives_old_authorization(tmp_path: Path, monkeypatch):
    state = tmp_path / ".state/final-publication/demo/WORK"
    state.mkdir(parents=True)
    release = tmp_path / "release"
    release.mkdir()
    old_plan = {"plan_sha256": "oldplan", "actions": [_action("A0001", "argument"), _action("debate", "debate")]}
    new_plan = {"plan_sha256": "newplan", "actions": [_action("debate", "debate"), _action("A0001", "argument", "skip", 42)]}
    for name, value in {
        "english-publication-config.json": {"publication_timezone": "Europe/Paris"},
        "english-publication-plan.json": old_plan,
        "preflight.json": {"preflight_sha256": "oldpre"},
        "authorization.json": {"authorization_sha256": "oldauth"},
    }.items():
        (state / name).write_text(json.dumps(value), encoding="utf-8")

    class Builder:
        def build_plan(self):
            return new_plan

    def fake_config(project_root, debate_id, release_copy, run_dir):
        cfg = {"publication_timezone": "Europe/Paris"}
        path = run_dir / "english-publication-config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        return path, cfg

    monkeypatch.setattr(final, "_english_config", fake_config)
    monkeypatch.setattr(final, "build_adapter", lambda config, root: object())
    monkeypatch.setattr(final, "GenericPublisher", lambda config, adapter, path: Builder())
    monkeypatch.setattr(final, "_reorder_english_plan", lambda plan: plan)
    monkeypatch.setattr(final, "_assert_safe_english_plan", lambda plan, approved_updates=None: None)
    monkeypatch.setattr(final, "_preflight", lambda root, state_dir, plans: {"preflight_sha256": "newpre"})
    monkeypatch.setattr(final, "_authorization", lambda state_dir, baseline, preflight: {"authorization_sha256": "newauth"})

    plans = {
        "en_config": {}, "en_config_path": state / "english-publication-config.json", "en_plan": old_plan,
        "fr_config": {}, "fr_config_path": state / "fr.json", "fr_plan": {"plan_sha256": "fr"},
        "safety_config": {}, "safety_config_path": state / "safe.json", "safety_plan": {"plan_sha256": "safe"},
    }
    out_plans, preflight, authorization = final._migrate_english_publication_order(
        tmp_path, "demo", release, state, {"baseline_sha256": "base"}, plans,
        {"preflight_sha256": "oldpre"}, {"authorization_sha256": "oldauth"},
    )
    assert out_plans["en_plan"]["plan_sha256"] == "newplan"
    assert preflight["preflight_sha256"] == "newpre"
    assert authorization["authorization_sha256"] == "newauth"
    audits = list((state / "publication-order-migrations").glob("*/migration.json"))
    assert len(audits) == 1
    audit = json.loads(audits[0].read_text(encoding="utf-8"))
    assert audit["reason"] == "owner_decision_debate_before_arguments"
    assert (audits[0].parent / "english-publication-plan.json").is_file()
