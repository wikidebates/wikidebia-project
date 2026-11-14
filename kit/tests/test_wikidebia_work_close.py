from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_corpus_build as corpus
import wikidebia_editorial_workspace as workspace_mod
import wikidebia_remote_execute as execution
import wikidebia_work_close as closure
from test_wikidebia_remote_execute import argument, make_approved_fixture


def passing_validator(project_root, package_root, *, scopes, json_output, text_output):
    report = {
        "validator_version": closure.VALIDATOR_VERSION,
        "result": "passed",
        "summary": {"errors": 0, "warnings": 0},
        "scopes": list(scopes),
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text_output.write_text("Validation réussie.\n", encoding="utf-8")
    return report


closure._run_validator = passing_validator


def make_executed(tmp_path: Path, *, no_changes: bool = False):
    project, debate_id, work_id, comparison_id, approved, adapter, _ = make_approved_fixture(tmp_path, no_changes=no_changes)
    active = project / "corpus" / debate_id
    active.mkdir(parents=True)
    (active / "old.json").write_text('{"status":"graph_validated"}\n', encoding="utf-8")
    source_sha = corpus.full_tree_sha256(active)
    workspace = project / ".state/editorial-workspaces" / debate_id / work_id
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["source"] = {"path": f"corpus/{debate_id}", "tree_sha256": source_sha, "global_status": "graph_validated"}
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    prepared = execution.prepare_execution(project, debate_id, work_id, comparison_id, approved["acceptance_sha256"], adapter=adapter)
    if prepared["status"] == "no_changes_in_scope":
        preflight_path = project / ".state/remote-executions" / debate_id / work_id / comparison_id / "execution-preflight.json"
        value = json.loads(preflight_path.read_text(encoding="utf-8"))
        value["status"] = "ready"
        value["preflight_sha256"] = execution._canonical(value, "preflight_sha256")
        preflight_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        receipt_path = preflight_path.parent / "preflight-receipt.json"
        pre_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        pre_receipt["status"] = "ready"
        pre_receipt["preflight_sha256"] = value["preflight_sha256"]
        pre_receipt["receipt_sha256"] = execution._canonical(pre_receipt, "receipt_sha256")
        receipt_path.write_text(json.dumps(pre_receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        prepared["preflight_sha256"] = value["preflight_sha256"]
    receipt = execution.execute_accepted_plan(project, debate_id, work_id, comparison_id, prepared["preflight_sha256"], adapter=adapter)
    return project, debate_id, work_id, comparison_id, receipt, source_sha


def make_signed_no_change_comparison(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _, _, _ = make_approved_fixture(
        tmp_path, no_changes=True
    )
    workspace = project / ".state/editorial-workspaces" / debate_id / work_id
    meta_path = workspace / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    active = project / "corpus" / debate_id
    active.mkdir(parents=True)
    (active / "old.json").write_text('{"status":"graph_validated"}\n', encoding="utf-8")
    source_sha = corpus.full_tree_sha256(active)
    meta["status"] = "remote_plan_ready"
    meta["source"] = {
        "path": f"corpus/{debate_id}",
        "tree_sha256": source_sha,
        "global_status": "graph_validated",
    }
    meta.pop("remote_plan_review", None)
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    run = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    plan_path = run / "update-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["operations"]["skip"][0]["remote_sha256"] = plan["operations"]["skip"][0]["new_sha256"]
    plan["plan_sha256"] = closure.sha_object({key: value for key, value in plan.items() if key != "plan_sha256"})
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_path = run / "comparison-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["scope"] = "all"
    receipt["counts"] = plan["counts"]
    receipt["plan_sha256"] = plan["plan_sha256"]
    receipt["receipt_sha256"] = closure._canonical_sha(receipt, "receipt_sha256")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["remote_comparison"]["plan_sha256"] = plan["plan_sha256"]
    meta["remote_comparisons"][-1]["plan_sha256"] = plan["plan_sha256"]
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return project, debate_id, work_id, comparison_id, plan, source_sha


def test_close_promotes_published_corpus_and_archives_chain(tmp_path: Path):
    project, debate_id, work_id, comparison_id, execution_receipt, old_sha = make_executed(tmp_path)
    release = project / ".state/editorial-workspaces" / debate_id / work_id / "release-copy"
    release_sha = corpus.full_tree_sha256(release)
    result = closure.close_work(project, debate_id, work_id, comparison_id, execution_receipt["receipt_sha256"])
    active = project / "corpus" / debate_id
    assert result["status"] == "work_closed"
    assert result["atomic_exchange"] is True
    assert corpus.full_tree_sha256(active) == release_sha == result["active_corpus_tree_sha256"]
    backup = project / result["previous_corpus_archive"]
    assert backup.is_dir() and corpus.full_tree_sha256(backup) == old_sha
    evidence = project / result["evidence_archive"]
    assert evidence.is_file() and corpus.sha256_file(evidence) == result["evidence_archive_sha256"]
    assert (project / ".state/completed-works" / debate_id / "latest.json").is_file()
    workspace = json.loads((project / ".state/editorial-workspaces" / debate_id / work_id / "workspace.json").read_text(encoding="utf-8"))
    assert workspace["status"] == "work_closed"


def test_close_is_idempotent(tmp_path: Path):
    project, debate_id, work_id, comparison_id, execution_receipt, _ = make_executed(tmp_path)
    first = closure.close_work(project, debate_id, work_id, comparison_id, execution_receipt["receipt_sha256"])
    second = closure.close_work(project, debate_id, work_id, comparison_id, execution_receipt["receipt_sha256"])
    assert second["idempotent"] is True
    assert second["receipt_sha256"] == first["receipt_sha256"]


def test_close_refuses_wrong_execution_hash_without_partial_directory(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _, _ = make_executed(tmp_path)
    try:
        closure.close_work(project, debate_id, work_id, comparison_id, "0" * 64)
    except closure.WorkClosureError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("Une mauvaise empreinte d’exécution a été acceptée")
    assert not (project / ".state/work-closures" / debate_id / work_id / comparison_id).exists()


def test_close_refuses_pending_delete(tmp_path: Path):
    project, debate_id, work_id, comparison_id, execution_receipt, _ = make_executed(tmp_path)
    state_path = project / ".state/published" / debate_id / "fr/latest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["pages"][0]["status"] = "pending_delete"
    unsigned = dict(state)
    unsigned.pop("state_sha256", None)
    state["state_sha256"] = closure.sha_object(unsigned)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        closure.close_work(project, debate_id, work_id, comparison_id, execution_receipt["receipt_sha256"])
    except closure.WorkClosureError as exc:
        assert "suppression" in str(exc) and "différée" in str(exc)
    else:
        raise AssertionError("Un état pending_delete a été clôturé")


def test_published_state_accepts_signed_effective_content_for_adopted_page(tmp_path: Path):
    project, debate_id, work_id, comparison_id, execution_receipt, _ = make_executed(tmp_path)
    release = project / ".state/editorial-workspaces" / debate_id / work_id / "release-copy"
    plan_path = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id / "update-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    row = plan["operations"]["create"].pop()
    plan["operations"]["update"].append(row)
    release_sha = closure.sha_text((release / row["source_path"].split("release-copy/", 1)[-1]).read_text(encoding="utf-8"))
    effective_text = argument("Texte final").replace("|rubriques=Société", "|rubriques=Société\n|date-création=2026-08-03")
    effective_path = project / ".state/update-effective" / debate_id / "fr/A0001-effective.wiki"
    effective_path.parent.mkdir(parents=True)
    effective_path.write_text(effective_text, encoding="utf-8")
    row.update({
        "source_path": effective_path.relative_to(project).as_posix(),
        "new_sha256": closure.sha_text(effective_text),
        "original_source_path": (release / "output/fr/arguments/A0001.wiki").relative_to(project).as_posix(),
        "original_new_sha256": release_sha,
        "remote_adoption": {"observed_revision_id": 10},
        "lifecycle_preservation": {"effective_source_path": effective_path.relative_to(project).as_posix()},
    })
    plan["counts"]["create"] = 0
    plan["counts"]["update"] = 1
    unsigned_plan = dict(plan)
    unsigned_plan.pop("plan_sha256", None)
    plan["plan_sha256"] = closure.sha_object(unsigned_plan)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    state_path = project / ".state/published" / debate_id / "fr/latest.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["pages"][0]["content_sha256"] = closure.sha_text(effective_text)
    state["plan_sha256"] = plan["plan_sha256"]
    unsigned_state = dict(state)
    unsigned_state.pop("state_sha256", None)
    state["state_sha256"] = closure.sha_object(unsigned_state)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    execution_data = {
        "release_copy": release,
        "execution_receipt": {
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "plan_sha256": plan["plan_sha256"],
            "underlying_receipt_sha256": state["receipt_sha256"],
            "published_states": {"fr": {"state_sha256": state["state_sha256"]}},
        },
    }
    verified = closure._verify_published_states(project, debate_id, execution_data)
    assert verified["fr"]["page_count"] == 1


def test_published_state_accepts_earlier_signed_language_checkpoint(tmp_path: Path):
    project, debate_id, work_id, comparison_id, execution_receipt, _ = make_executed(tmp_path)
    release = project / ".state/editorial-workspaces" / debate_id / work_id / "release-copy"
    en_path = release / "output/en/arguments/A0002.wiki"
    en_path.parent.mkdir(parents=True)
    en_text = argument("Earlier English checkpoint")
    en_path.write_text(en_text, encoding="utf-8")
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["pages"].append({
        "language": "en",
        "page_id": "A0002",
        "page_type": "argument",
        "canonical_title": "Earlier argument",
        "file_path": "output/en/arguments/A0002.wiki",
        "sha256": closure.sha_text(en_text),
    })
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    en_state = {
        "debate_id": debate_id,
        "language": "en",
        "plan_sha256": "1" * 64,
        "receipt_sha256": "2" * 64,
        "pages": [{
            "page_id": "A0002",
            "canonical_title": "Earlier argument",
            "content_sha256": closure.sha_text(en_text),
            "revision_id": 9,
            "status": "published",
        }],
    }
    en_state["state_sha256"] = closure.sha_object(en_state)
    en_state_path = project / ".state/published" / debate_id / "en/latest.json"
    en_state_path.parent.mkdir(parents=True)
    en_state_path.write_text(json.dumps(en_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    execution_data = {
        "release_copy": release,
        "execution_receipt": execution_receipt,
    }
    verified = closure._verify_published_states(project, debate_id, execution_data)
    assert set(verified) == {"en", "fr"}
    assert verified["en"]["page_count"] == 1


def test_no_changes_execution_can_close(tmp_path: Path):
    project, debate_id, work_id, comparison_id, execution_receipt, _ = make_executed(tmp_path, no_changes=True)
    result = closure.close_work(project, debate_id, work_id, comparison_id, execution_receipt["receipt_sha256"])
    assert result["execution_status"] == "no_changes"
    assert result["work_completed"] is True


def test_signed_all_skip_plan_closes_without_remote_execution(tmp_path: Path):
    project, debate_id, work_id, comparison_id, plan, old_sha = make_signed_no_change_comparison(tmp_path)
    result = closure.close_no_change_work(
        project, debate_id, work_id, comparison_id, plan["plan_sha256"]
    )
    release = project / ".state/editorial-workspaces" / debate_id / work_id / "release-copy"
    assert result["closure_mode"] == "signed_no_change_plan"
    assert result["execution_status"] == "not_required"
    assert result["remote_access_performed_during_closure"] is False
    assert result["remote_write_performed_during_closure"] is False
    assert result["skip_count"] == 1
    assert corpus.full_tree_sha256(project / "corpus" / debate_id) == corpus.full_tree_sha256(release)
    assert corpus.full_tree_sha256(project / result["previous_corpus_archive"]) == old_sha
    assert not (project / ".state/remote-executions" / debate_id / work_id / comparison_id).exists()
    again = closure.close_no_change_work(
        project, debate_id, work_id, comparison_id, plan["plan_sha256"]
    )
    assert again["idempotent"] is True


def test_signed_all_skip_plan_accepts_verified_effective_url_overlay(
    tmp_path: Path, monkeypatch
):
    project, debate_id, work_id, comparison_id, plan, _ = make_signed_no_change_comparison(
        tmp_path
    )
    row = plan["operations"]["skip"][0]
    release = project / ".state/editorial-workspaces" / debate_id / work_id / "release-copy"
    release_path = project / row["source_path"]
    overlay = release_path.read_text(encoding="utf-8") + "\n"
    overlay_sha = closure.sha_text(overlay)
    effective = (
        project
        / ".state/update-effective"
        / debate_id
        / row["language"]
        / f"{row['page_id']}-{overlay_sha[:16]}.wiki"
    )
    effective.parent.mkdir(parents=True)
    effective.write_text(overlay, encoding="utf-8")
    row.update({
        "source_path": effective.relative_to(project).as_posix(),
        "local_file_sha256": closure.sha256_file(effective),
        "new_sha256": overlay_sha,
        "remote_sha256": overlay_sha,
    })
    plan["plan_sha256"] = closure.sha_object(
        {key: value for key, value in plan.items() if key != "plan_sha256"}
    )
    run = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    (run / "update-plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    receipt_path = run / "comparison-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["plan_sha256"] = plan["plan_sha256"]
    receipt["receipt_sha256"] = closure._canonical_sha(receipt, "receipt_sha256")
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    meta_path = release.parent / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["remote_comparison"]["plan_sha256"] = plan["plan_sha256"]
    meta["remote_comparisons"][-1]["plan_sha256"] = plan["plan_sha256"]
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        closure,
        "_publication_url_overlays",
        lambda *_args: {(row["language"], row["page_id"]): overlay},
    )

    result = closure.close_no_change_work(
        project, debate_id, work_id, comparison_id, plan["plan_sha256"]
    )
    assert result["closure_mode"] == "signed_no_change_plan"
    assert corpus.full_tree_sha256(project / "corpus" / debate_id) == corpus.full_tree_sha256(release)


def test_publication_url_overlay_is_rebuilt_from_owner_approved_registry(tmp_path: Path):
    release = tmp_path / "release-copy"
    page_path = release / "output/en/arguments/A0001.wiki"
    page_path.parent.mkdir(parents=True)
    old_url = "https://archive.is/example"
    new_url = "https://example.org/original"
    source = "{{Argument\n|résumé=Test\n}}\n" + old_url + "\n"
    page_path.write_text(source, encoding="utf-8")
    data = release / "data"
    data.mkdir()
    (release / "manifest.json").write_text(
        json.dumps({
            "editorial_controls": {
                "publication_url_replacements_path": "data/publication_url_replacements.json"
            },
            "pages": [{
                "language": "en",
                "page_id": "A0001",
                "page_type": "argument",
                "canonical_title": "Test",
                "file_path": "output/en/arguments/A0001.wiki",
                "sha256": closure.sha_text(source),
            }],
        }),
        encoding="utf-8",
    )
    (data / "publication_url_replacements.json").write_text(
        json.dumps({
            "debate_id": "debat_test",
            "entries": [{
                "language": "en",
                "page_id": "A0001",
                "old_url": old_url,
                "new_url": new_url,
                "owner_approved": True,
                "reason": "MediaWiki rejects the archive host; retain the original source.",
                "authorization_receipt_sha256": "a" * 64,
            }],
        }),
        encoding="utf-8",
    )
    pages = closure._release_pages(release)
    overlays = closure._publication_url_overlays(release, "debat_test", pages)
    assert overlays[("en", "A0001")] == source.replace(old_url, new_url)


def test_external_deletion_skip_requires_current_signed_registry(tmp_path: Path):
    project = tmp_path / "project"
    source = project / "release-copy/output/fr/arguments/A0001.wiki"
    source.parent.mkdir(parents=True)
    source.write_text("{{Argument\n|résumé=Test\n}}\n", encoding="utf-8")
    page = {
        "canonical_title": "Argument supprimé",
        "content_sha256": closure.sha_text(source.read_text(encoding="utf-8")),
    }
    entry = {
        "language": "fr",
        "page_id": "A0001",
        "page_type": "argument",
        "canonical_title": page["canonical_title"],
        "status": "active",
        "reason": "Suppression distante explicitement acceptée par le propriétaire.",
        "accepted_by": "project_owner",
        "accepted_at": "2026-11-12T08:00:00+00:00",
        "work_id": "EDIT-20261112-001",
        "comparison_id": "REMOTE-20261112-001",
        "release_page_sha256": page["content_sha256"],
        "release_file_sha256": closure.sha256_file(source),
    }
    registry = {
        "schema": "wikidebia-accepted-external-deletions-1.0",
        "debate_id": "debat_test",
        "created_at": entry["accepted_at"],
        "updated_at": entry["accepted_at"],
        "entries": [entry],
    }
    registry["registry_sha256"] = closure.sha_object(registry)
    registry_path = project / ".state/external-deletions/debat_test.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    row = {
        "language": "fr",
        "page_id": "A0001",
        "title": page["canonical_title"],
        "new_sha256": page["content_sha256"],
        "local_file_sha256": closure.sha256_file(source),
        "remote_sha256": None,
        "observed_revision_id": None,
        "preconditions": [
            "remote_title_absent",
            "external_deletion_registry_signature_valid",
            "release_page_matches_accepted_deletion",
        ],
        "external_deletion_acceptance": {
            "registry_path": ".state/external-deletions/debat_test.json",
            "registry_sha256": registry["registry_sha256"],
            "accepted_at": entry["accepted_at"],
            "accepted_by": entry["accepted_by"],
            "comparison_id": entry["comparison_id"],
        },
    }
    assert closure._validate_external_deletion_skip(
        project,
        "debat_test",
        "EDIT-20261112-001",
        row,
        page,
        source.resolve(),
        source.resolve(),
    ) is True


def test_signed_all_skip_close_refuses_partial_scope(tmp_path: Path):
    project, debate_id, work_id, comparison_id, plan, _ = make_signed_no_change_comparison(tmp_path)
    receipt_path = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id / "comparison-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["scope"] = "fr"
    receipt["receipt_sha256"] = closure._canonical_sha(receipt, "receipt_sha256")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        closure.close_no_change_work(project, debate_id, work_id, comparison_id, plan["plan_sha256"])
    except closure.WorkClosureError as exc:
        assert "portée all" in str(exc)
    else:
        raise AssertionError("Une comparaison partielle a clôturé le Work")


def test_signed_all_skip_close_refuses_wrong_plan_confirmation(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _, _ = make_signed_no_change_comparison(tmp_path)
    try:
        closure.close_no_change_work(project, debate_id, work_id, comparison_id, "0" * 64)
    except closure.WorkClosureError as exc:
        assert "empreinte confirmée" in str(exc)
    else:
        raise AssertionError("Une mauvaise empreinte de plan a été acceptée")


def test_signed_all_skip_close_refuses_any_actionable_operation(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _, _ = make_signed_no_change_comparison(tmp_path)
    run = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    plan_path = run / "update-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["operations"]["update"] = plan["operations"]["skip"]
    plan["operations"]["skip"] = []
    plan["counts"]["update"] = 1
    plan["counts"]["skip"] = 0
    plan["plan_sha256"] = closure.sha_object({key: value for key, value in plan.items() if key != "plan_sha256"})
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_path = run / "comparison-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["counts"] = plan["counts"]
    receipt["plan_sha256"] = plan["plan_sha256"]
    receipt["receipt_sha256"] = closure._canonical_sha(receipt, "receipt_sha256")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta_path = project / ".state/editorial-workspaces" / debate_id / work_id / "workspace.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["remote_comparison"]["plan_sha256"] = plan["plan_sha256"]
    meta["remote_comparisons"][-1]["plan_sha256"] = plan["plan_sha256"]
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        closure.close_no_change_work(
            project, debate_id, work_id, comparison_id, plan["plan_sha256"]
        )
    except closure.WorkClosureError as exc:
        assert "autres que skip" in str(exc)
    else:
        raise AssertionError("Un plan contenant une mise à jour a été clôturé sans exécution")


def test_manage_exposes_workspace_close_command():
    import wikidebia_manage as manage
    args = manage.build_parser().parse_args([
        "corpus-workspace-close", "debat_test",
        "--work-id", "EDIT-CLOSE-001",
        "--comparison-id", "REMOTE-20260804-001",
        "--confirm-execution-sha256", "a" * 64,
    ])
    assert args.command == "corpus-workspace-close"
    assert args.confirm_execution_sha256 == "a" * 64
    assert args.confirm_no_change_plan_sha256 is None

    no_change = manage.build_parser().parse_args([
        "corpus-workspace-close", "debat_test",
        "--work-id", "EDIT-CLOSE-001",
        "--comparison-id", "REMOTE-20260804-001",
        "--confirm-no-change-plan-sha256", "b" * 64,
    ])
    assert no_change.confirm_no_change_plan_sha256 == "b" * 64
