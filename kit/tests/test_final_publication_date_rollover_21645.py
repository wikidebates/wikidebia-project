import json
from pathlib import Path

import pytest

import wikidebia_final_publication as final
from wikidebia_publish import sha_text


class TransitionPublisher:
    def __init__(self, root: Path):
        self.root = root
        self._row = {"language": "en", "page_id": "A", "page_type": "argument", "page_origin": "new"}

    def _manifest_page(self, language: str, page_id: str):
        return {"language": language, "page_id": page_id, "page_type": "argument", "page_origin": "new"}

    def _english_translation_creation_text(self, row, text: str, publication_date: str) -> str:
        return text.replace("|creation-date=2000-01-01", f"|creation-date={publication_date}")


def _action(page_id: str, *, op: str, date: str | None, desired: str, revision=None):
    return {
        "operation_id": "workflow_final_publish_en",
        "kind": "full_page",
        "language": "en",
        "page_id": page_id,
        "page_type": "argument",
        "title": f"Title {page_id}",
        "source_path": f"output/en/arguments/{page_id}.wiki",
        "parameter": None,
        "local_file_sha256": f"file-{page_id}",
        "local_target_sha256": f"target-{page_id}",
        "edit_summary": f"Translation {page_id}",
        "change_tags": ["chatgpt", "translated-fr"],
        "operation": op,
        "publication_creation_date": date,
        "desired_sha256": desired,
        "remote_revision_id": revision,
    }


def test_rollover_transition_preserves_old_day_for_created_pages_and_moves_only_remaining_pages(tmp_path: Path):
    root = tmp_path / "corpus"
    for page_id in ("A", "B"):
        path = root / f"output/en/arguments/{page_id}.wiki"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{{Argument\n|summary=Demo\n|creation-date=2000-01-01\n}}\n", encoding="utf-8")
    publisher = TransitionPublisher(root)
    source = (root / "output/en/arguments/A.wiki").read_text(encoding="utf-8")
    old_sha = sha_text(publisher._english_translation_creation_text({}, source, "2026-08-20"))
    new_sha = sha_text(publisher._english_translation_creation_text({}, source, "2026-08-21"))

    old_plan = {
        "publication_date": "2026-08-20",
        "actions": [
            _action("A", op="create", date="2026-08-20", desired=old_sha),
            _action("B", op="create", date="2026-08-20", desired=old_sha),
        ],
    }
    new_plan = {
        "publication_date": "2026-08-21",
        "actions": [
            _action("A", op="skip", date="2026-08-20", desired=old_sha, revision=101),
            _action("B", op="create", date="2026-08-21", desired=new_sha),
        ],
    }
    result = final._english_plan_rollover_transition(publisher, old_plan, new_plan, "2026-08-21")
    assert [row["page_id"] for row in result["completed_before_rollover"]] == ["A"]
    assert result["completed_before_rollover"][0]["creation_date"] == "2026-08-20"
    assert [row["page_id"] for row in result["remaining_after_rollover"]] == ["B"]
    assert result["remaining_after_rollover"][0]["new_creation_date"] == "2026-08-21"


def test_rollover_transition_refuses_to_redate_a_page_already_created_under_old_plan(tmp_path: Path):
    root = tmp_path / "corpus"
    path = root / "output/en/arguments/A.wiki"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{{Argument\n|summary=Demo\n|creation-date=2000-01-01\n}}\n", encoding="utf-8")
    publisher = TransitionPublisher(root)
    source = path.read_text(encoding="utf-8")
    old_sha = sha_text(publisher._english_translation_creation_text({}, source, "2026-08-20"))
    new_sha = sha_text(publisher._english_translation_creation_text({}, source, "2026-08-21"))
    old_plan = {"publication_date": "2026-08-20", "actions": [_action("A", op="create", date="2026-08-20", desired=old_sha)]}
    bad_plan = {"publication_date": "2026-08-21", "actions": [_action("A", op="skip", date="2026-08-21", desired=new_sha, revision=101)]}
    with pytest.raises(final.FinalPublicationError, match="déjà créée a changé de date"):
        final._english_plan_rollover_transition(publisher, old_plan, bad_plan, "2026-08-21")


def test_publication_day_change_error_is_recognized():
    assert final._publication_day_change_error(RuntimeError("Le jour de publication a changé avant la création de X"))
    assert not final._publication_day_change_error(RuntimeError("collision distante"))

def test_rollover_reseals_plan_preflight_authorization_and_archives_previous_state(tmp_path: Path, monkeypatch):
    project = tmp_path
    state_dir = project / ".state/final-publication/demo/WORK"
    state_dir.mkdir(parents=True)
    release = project / "release"
    source = release / "output/en/arguments/A.wiki"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("{{Argument\n|summary=Demo\n|creation-date=2000-01-01\n}}\n", encoding="utf-8")
    publisher = TransitionPublisher(release)
    text = source.read_text(encoding="utf-8")
    old_sha = sha_text(publisher._english_translation_creation_text({}, text, "2026-08-20"))
    new_sha = sha_text(publisher._english_translation_creation_text({}, text, "2026-08-21"))
    old_plan = {"publication_date": "2026-08-20", "plan_sha256": "oldplan", "actions": [_action("A", op="create", date="2026-08-20", desired=old_sha)]}
    new_plan = {"publication_date": "2026-08-21", "plan_sha256": "newplan", "actions": [_action("A", op="create", date="2026-08-21", desired=new_sha)]}
    old_config = {"publication_timezone": "Europe/Paris"}
    for name, obj in {
        "english-publication-config.json": old_config,
        "english-publication-plan.json": old_plan,
        "preflight.json": {"preflight_sha256": "oldpre"},
        "authorization.json": {"authorization_sha256": "oldauth"},
    }.items():
        (state_dir / name).write_text(json.dumps(obj), encoding="utf-8")

    class Builder(TransitionPublisher):
        def build_plan(self):
            return new_plan

    def fake_config(project_root, debate_id, release_copy, run_dir):
        cfg = {"publication_timezone": "Europe/Paris"}
        path = run_dir / "english-publication-config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        return path, cfg

    monkeypatch.setattr(final, "_publication_date_from_config", lambda config: "2026-08-21")
    monkeypatch.setattr(final, "_english_config", fake_config)
    monkeypatch.setattr(final, "build_adapter", lambda config, root: object())
    monkeypatch.setattr(final, "GenericPublisher", lambda config, adapter, path: Builder(release))
    monkeypatch.setattr(final, "_reorder_english_plan", lambda plan: plan)
    monkeypatch.setattr(final, "_assert_safe_english_plan", lambda plan, approved_updates=None: None)
    monkeypatch.setattr(final, "_preflight", lambda root, state, plans: {"preflight_sha256": "newpre"})
    monkeypatch.setattr(final, "_authorization", lambda state, baseline, preflight: {"authorization_sha256": "newauth"})

    plans = {
        "en_config": old_config, "en_config_path": state_dir / "english-publication-config.json", "en_plan": old_plan,
        "fr_config": {}, "fr_config_path": state_dir / "fr.json", "fr_plan": {"plan_sha256": "fr"},
        "safety_config": {}, "safety_config_path": state_dir / "safety.json", "safety_plan": {"plan_sha256": "safe"},
    }
    new_plans, preflight, authorization = final._rollover_english_publication_date(
        project, "demo", release, state_dir, {"baseline_sha256": "base"}, plans,
        {"preflight_sha256": "oldpre"}, {"authorization_sha256": "oldauth"},
    )
    assert new_plans["en_plan"]["publication_date"] == "2026-08-21"
    assert preflight["preflight_sha256"] == "newpre"
    assert authorization["authorization_sha256"] == "newauth"
    rollovers = list((state_dir / "publication-date-rollovers").glob("*/rollover.json"))
    assert len(rollovers) == 1
    audit = json.loads(rollovers[0].read_text(encoding="utf-8"))
    assert audit["old_publication_date"] == "2026-08-20"
    assert audit["new_publication_date"] == "2026-08-21"
    assert audit["previous_authorization_sha256"] == "oldauth"
    assert audit["successor_authorization_sha256"] == "newauth"
    assert (rollovers[0].parent / "english-publication-plan.json").is_file()
