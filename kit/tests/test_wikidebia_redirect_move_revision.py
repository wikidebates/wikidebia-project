from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_wikidebia_remote_update import (
    FakeAdapter, argument, make_fixture, module,
)


def _runtime(tmp_path: Path, *, pages=None, old_pages=None, new_pages=None, adapter_class=FakeAdapter):
    config, config_path = make_fixture(
        tmp_path, languages=("fr",), old_pages=old_pages or [],
        new_pages=new_pages or [],
    )
    config["verification_attempts"] = 1
    config["verification_delay_seconds"] = 0
    config_path.write_text(json.dumps(config), encoding="utf-8")
    adapter = adapter_class(pages or {})
    return module.PlanExecutor(config, adapter, config_path), adapter


def _execute(executor, adapter, row):
    adapter.open_language("fr", "ChatGPT")
    try:
        return executor._execute_one(
            row, "ChatGPT", {"edit_summary_contract": module.EDIT_SUMMARY_CONTRACT},
        )
    finally:
        adapter.close_language()


def _redirect_row(old: str):
    target = "Argument conservé"
    return {
        "operation": "redirect",
        "language": "fr", "page_type": "argument", "page_id": "A1",
        "title": "Argument fusionné",
        "redirect_target": target,
        "expected_revision_id": 10, "old_sha256": module.sha_text(old),
        "edit_summary_policy": "merge_redirect_v1",
        "edit_summary": module.redirect_edit_summary("fr", target),
    }


def test_redirect_writes_and_immediately_attests_revision_summary_and_tag(tmp_path: Path):
    old = argument("Argument historique")
    executor, adapter = _runtime(tmp_path, pages={("fr", "Argument fusionné"): (10, old)})
    row = _redirect_row(old)
    result = _execute(executor, adapter, row)
    assert result["status"] == "redirected"
    assert result["edit_summary"] == row["edit_summary"]
    assert result["content_sha256"] == module.sha_text(module.redirect_text("fr", row["redirect_target"]))
    assert adapter.revisions[("fr", row["title"], result["revision_id"])]["tags"] == ["chatgpt"]


@pytest.mark.parametrize("damage", ["summary", "tags", "text"])
def test_redirect_does_not_report_success_if_readback_is_corrupt(tmp_path: Path, damage: str):
    old = argument("Argument historique")

    class CorruptReadback(FakeAdapter):
        def read_revision(self, title, revision_id):
            observed = super().read_revision(title, revision_id)
            if observed is None:
                return None
            result = dict(observed)
            if damage == "summary":
                result["summary"] = "Corrections"
            elif damage == "tags":
                result["tags"] = []
            else:
                result["text"] = "Contenu divergent"
            return result

    executor, adapter = _runtime(
        tmp_path, pages={("fr", "Argument fusionné"): (10, old)},
        adapter_class=CorruptReadback,
    )
    with pytest.raises(module.PlanConflict):
        _execute(executor, adapter, _redirect_row(old))
    assert len([event for event in adapter.events if event[0] == "write"]) == 1


def _move_row(tmp_path: Path, old: str, desired: str):
    output = tmp_path / "corpus/demo/output/fr/A1.wiki"
    assert output.read_text(encoding="utf-8") == desired
    return {
        "operation": "move",
        "language": "fr", "page_type": "argument", "page_id": "A1",
        "title": "Ancien titre", "old_title": "Ancien titre",
        "new_title": "Nouveau titre", "leave_redirect": True,
        "expected_revision_id": 10, "old_sha256": module.sha_text(old),
        "source_path": "corpus/demo/output/fr/A1.wiki",
        "local_file_sha256": module.sha_file(output),
        "new_sha256": module.sha_text(desired),
        "edit_summary_policy": "canonical_title_move_v1",
        "edit_summary": module.move_edit_summary("fr", "argument", old, desired),
    }


def _move_fixture(tmp_path: Path, desired=None, adapter_class=FakeAdapter):
    old = argument("Argument inchangé")
    desired = old.replace("|rubriques=Société", "|rubriques=Politique") if desired is None else desired
    executor, adapter = _runtime(
        tmp_path, pages={("fr", "Ancien titre"): (10, old)},
        old_pages=[("fr", "A1", "Ancien titre", old)],
        new_pages=[("fr", "A1", "Nouveau titre", desired)],
        adapter_class=adapter_class,
    )
    return executor, adapter, _move_row(tmp_path, old, desired)


def test_move_followed_by_target_update_attests_exact_content_revision(tmp_path: Path):
    executor, adapter, row = _move_fixture(tmp_path)
    result = _execute(executor, adapter, row)
    assert result["status"] == "moved"
    assert result["edit_summary"] == row["edit_summary"]
    assert result["content_sha256"] == row["new_sha256"]
    assert adapter.revisions[("fr", row["new_title"], result["revision_id"])]["tags"] == ["chatgpt"]


@pytest.mark.parametrize("damage", ["summary", "tags", "text"])
def test_move_target_update_blocks_when_revision_readback_is_corrupt(tmp_path: Path, damage: str):
    class CorruptReadback(FakeAdapter):
        def read_revision(self, title, revision_id):
            observed = super().read_revision(title, revision_id)
            if observed is None:
                return None
            result = dict(observed)
            if damage == "summary":
                result["summary"] = "Corrections"
            elif damage == "tags":
                result["tags"] = []
            else:
                result["text"] = "Texte non conforme"
            return result

    executor, adapter, row = _move_fixture(tmp_path, adapter_class=CorruptReadback)
    with pytest.raises(module.PlanConflict):
        _execute(executor, adapter, row)
    assert len([event for event in adapter.events if event[0] == "write"]) == 1


def test_pure_title_move_makes_no_extra_content_edit(tmp_path: Path):
    same = argument("Argument inchangé")
    executor, adapter, row = _move_fixture(tmp_path, desired=same)
    result = _execute(executor, adapter, row)
    assert result["status"] == "moved"
    assert not [event for event in adapter.events if event[0] == "write"]
