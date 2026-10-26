import json
from pathlib import Path

import pytest

import wikidebia_workflow_baseline as baseline
from wikidebia_corpus_build import full_tree_sha256
from wikidebia_editorial_workspace import workspace_receipt_hash


def _signed(obj: dict, field: str) -> dict:
    value = dict(obj)
    value[field] = baseline.sha_object(value)
    return value


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_release_boundary(tmp_path: Path):
    project = tmp_path
    debate_id = "debat_test"
    work_id = "EDIT-20260820-001"
    workspace = project / ".state/editorial-workspaces" / debate_id / work_id
    release_copy = workspace / "release-copy"
    (release_copy / "reports").mkdir(parents=True)
    (release_copy / "release").mkdir(parents=True)
    _write_json(release_copy / "reports/release_report.json", {
        "result": "passed", "debate_id": debate_id, "work_id": work_id,
    })
    _write_json(release_copy / "release/release_manifest.json", {
        "debate_id": debate_id, "work_id": work_id, "status": "release_ready",
    })
    release_tree = full_tree_sha256(release_copy)
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "release_ready",
        "release_copy": {"path": "release-copy", "tree_sha256": release_tree, "status": "release_ready"},
    }
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    _write_json(workspace / "workspace.json", meta)

    release_receipt = _signed({
        "schema": "wikidebia-local-release-receipt-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "release_copy_tree_sha256": release_tree,
        "publication_started": False,
        "semantic_convergence_passes": 2,
        "semantic_content_sha256": "1" * 64,
        "semantic_convergence_review_sha256": "2" * 64,
    }, "receipt_sha256")
    _write_json(project / ".state/corpus-releases" / debate_id / work_id / "release-receipt.json", release_receipt)

    content_receipt = _signed({
        "schema": "wikidebia-fr-publication-receipt-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "published",
        "plan_sha256": "3" * 64,
    }, "receipt_sha256")
    _write_json(project / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json", content_receipt)

    workflow = {
        "schema": "wikidebia-editorial-orchestration-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "phase": "release_ready",
        "status": "release_ready",
        "french_content_publication": {"status": "published", "receipt_sha256": content_receipt["receipt_sha256"]},
    }
    _write_json(project / ".state/workflows" / debate_id / "workflow.json", workflow)

    fr_state = _signed({
        "schema": "wikidebia-published-state-1.0",
        "debate_id": debate_id,
        "language": "fr",
        "plan_sha256": content_receipt["plan_sha256"],
        "pages": [],
    }, "state_sha256")
    _write_json(project / ".state/published" / debate_id / "fr/latest.json", fr_state)

    _write_json(project / "corpus" / debate_id / "manifest.json", {
        "debate_id": debate_id,
        "translation_status": {"en": "deferred"},
        "pages": [{"language": "fr", "page_id": "debat_test"}],
    })
    return project, debate_id, work_id, release_copy


def test_work_scoped_baseline_attests_first_english_publication(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    value = baseline.resolve_workflow_release_baseline(project, debate_id, release_copy, expected_work_id=work_id)
    assert value is not None
    assert value["fr"]["mode"] == "published_checkpoint_state"
    assert value["en"]["mode"] == "never_published_by_this_work"
    assert value["en"]["empty_baseline"] is True
    assert value["en"]["remote_absence_not_assumed"] is True
    assert value["semantic_convergence"]["reused_without_rerun"] is True
    assert value["baseline_sha256"] == baseline._canonical(value, "baseline_sha256")


def _add_signed_french_correction_chain(
    project: Path,
    debate_id: str,
    work_id: str,
    *,
    receipt_outside_work: bool = False,
    corrected_revision: int = 11,
) -> None:
    state_dir = project / ".state/published" / debate_id / "fr"
    latest_path = state_dir / "latest.json"
    anchor = json.loads(latest_path.read_text(encoding="utf-8"))
    anchor.pop("state_sha256", None)
    anchor.update({
        "publication_date": "2026-08-20T20:00:00Z",
        "source_manifest_sha256": "5" * 64,
        "corpus_version": "manifest-test",
        "receipt_sha256": "6" * 64,
        "pages": [{
            "page_id": "A0001", "page_type": "argument", "canonical_title": "Titre source",
            "content_sha256": "7" * 64, "revision_id": 10, "status": "published",
        }],
    })
    anchor = _signed(anchor, "state_sha256")
    _write_json(state_dir / "20260820T200000Z.json", anchor)

    correction = _signed({
        "schema": "wikidebia-french-correction-receipt-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "language": "fr",
        "plan_sha256": "4" * 64,
    }, "receipt_sha256")
    if receipt_outside_work:
        receipt_path = project / ".state/other/correction-receipt.json"
    else:
        receipt_path = project / ".state/fr-publication" / debate_id / work_id / "content/correction-receipt.json"
    _write_json(receipt_path, correction)

    corrected = dict(anchor)
    corrected.pop("state_sha256", None)
    corrected.update({
        "publication_date": "2026-08-20T21:00:00Z",
        "plan_sha256": correction["plan_sha256"],
        "receipt_path": receipt_path.relative_to(project).as_posix(),
        "receipt_sha256": correction["receipt_sha256"],
        "pages": [{
            "page_id": "A0001", "page_type": "argument", "canonical_title": "Titre rétabli",
            "content_sha256": "8" * 64, "revision_id": corrected_revision, "status": "published",
        }],
    })
    corrected = _signed(corrected, "state_sha256")
    _write_json(state_dir / "20260820T210000Z.json", corrected)
    _write_json(latest_path, corrected)


def test_work_scoped_baseline_attests_signed_post_checkpoint_french_corrections(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    _add_signed_french_correction_chain(project, debate_id, work_id)

    value = baseline.resolve_workflow_release_baseline(project, debate_id, release_copy, expected_work_id=work_id)

    assert value["fr"]["mode"] == "published_checkpoint_with_signed_corrections"
    succession = value["fr"]["post_checkpoint_succession"]
    assert succession["checkpoint_state_path"].endswith("20260820T200000Z.json")
    assert len(succession["corrections"]) == 1
    assert succession["corrections"][0]["receipt_sha256"]


def test_work_scoped_baseline_refuses_post_checkpoint_receipt_outside_work(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    _add_signed_french_correction_chain(project, debate_id, work_id, receipt_outside_work=True)

    with pytest.raises(baseline.WorkflowBaselineError, match="extérieur au Work"):
        baseline.resolve_workflow_release_baseline(project, debate_id, release_copy, expected_work_id=work_id)


def test_work_scoped_baseline_refuses_post_checkpoint_revision_rollback(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    _add_signed_french_correction_chain(project, debate_id, work_id, corrected_revision=9)

    with pytest.raises(baseline.WorkflowBaselineError, match="régresser une révision"):
        baseline.resolve_workflow_release_baseline(project, debate_id, release_copy, expected_work_id=work_id)


def test_work_scoped_empty_english_baseline_expires_after_signed_en_state(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    en_state = _signed({
        "schema": "wikidebia-published-state-1.0",
        "debate_id": debate_id,
        "language": "en",
        "plan_sha256": "4" * 64,
        "pages": [],
    }, "state_sha256")
    _write_json(project / ".state/published" / debate_id / "en/latest.json", en_state)
    with pytest.raises(baseline.WorkflowBaselineError, match="baseline EN vide"):
        baseline.resolve_workflow_release_baseline(project, debate_id, release_copy, expected_work_id=work_id)


def _prepare_stale_receipt_reference(project: Path, debate_id: str, work_id: str, *, current_plan: str | None = None):
    workflow_path = project / ".state/workflows" / debate_id / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    receipt_path = project / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json"
    old_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    workflow["phase"] = "final_publication"
    workflow["status"] = "blocked_final_publication"
    workflow["french_content_publication"] = dict(old_receipt)
    workflow["french_publication"] = dict(old_receipt)
    _write_json(workflow_path, workflow)

    new_receipt = dict(old_receipt)
    new_receipt.pop("receipt_sha256", None)
    new_receipt["published_at"] = "2026-08-20T21:09:36+02:00"
    if current_plan is not None:
        new_receipt["plan_sha256"] = current_plan
    new_receipt = _signed(new_receipt, "receipt_sha256")
    _write_json(receipt_path, new_receipt)
    return old_receipt, new_receipt


def test_seal_repairs_stale_workflow_receipt_hash_when_same_plan_is_signed(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    old_receipt, new_receipt = _prepare_stale_receipt_reference(project, debate_id, work_id)
    assert old_receipt["plan_sha256"] == new_receipt["plan_sha256"]
    assert old_receipt["receipt_sha256"] != new_receipt["receipt_sha256"]

    value = baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)
    assert value["fr"]["checkpoint_receipt_sha256"] == new_receipt["receipt_sha256"]
    workflow = json.loads((project / ".state/workflows" / debate_id / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["french_content_publication"]["receipt_sha256"] == new_receipt["receipt_sha256"]
    assert workflow["french_publication"]["receipt_sha256"] == new_receipt["receipt_sha256"]
    migration = workflow["compatibility_migrations"][-1]
    assert migration["kind"] == "stale_fr_content_receipt_reference_reconciled"
    assert migration["old_receipt_sha256"] == old_receipt["receipt_sha256"]
    assert migration["new_receipt_sha256"] == new_receipt["receipt_sha256"]
    assert migration["plan_sha256"] == new_receipt["plan_sha256"]


def test_seal_refuses_stale_workflow_reference_when_plan_changed(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    _old, _new = _prepare_stale_receipt_reference(project, debate_id, work_id, current_plan="4" * 64)
    with pytest.raises(baseline.WorkflowBaselineError, match="plan signé"):
        baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)


def test_seal_refuses_receipt_reference_repair_after_final_authorization(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    _prepare_stale_receipt_reference(project, debate_id, work_id)
    auth = project / ".state/final-publication" / debate_id / work_id / "authorization.json"
    _write_json(auth, {"schema": "wikidebia-final-publication-authorization-1.0"})
    with pytest.raises(baseline.WorkflowBaselineError, match="après le début"):
        baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)


def test_seal_adopts_legacy_unbound_content_receipt_when_signed_state_matches(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    workflow_path = project / ".state/workflows" / debate_id / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    # Historical orchestration states could remember only the checkpoint outcome,
    # without copying the final receipt or plan hashes into workflow.json.
    workflow["phase"] = "final_publication"
    workflow["status"] = "blocked_final_publication"
    workflow["french_content_publication"] = {"status": "no_changes"}
    workflow["french_publication"] = {"status": "no_changes"}
    _write_json(workflow_path, workflow)

    value = baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)
    receipt_path = project / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert value["fr"]["checkpoint_receipt_sha256"] == receipt["receipt_sha256"]
    repaired = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert repaired["french_content_publication"]["receipt_sha256"] == receipt["receipt_sha256"]
    assert repaired["french_content_publication"]["plan_sha256"] == receipt["plan_sha256"]
    migration = repaired["compatibility_migrations"][-1]
    assert migration["kind"] == "legacy_unbound_fr_content_receipt_reference_adopted"
    assert migration["old_receipt_sha256"] is None
    assert migration["old_plan_sha256"] is None
    assert migration["new_receipt_sha256"] == receipt["receipt_sha256"]
    assert migration["plan_sha256"] == receipt["plan_sha256"]


def test_seal_refuses_bound_legacy_receipt_without_plan(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    workflow_path = project / ".state/workflows" / debate_id / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["phase"] = "final_publication"
    workflow["status"] = "blocked_final_publication"
    workflow["french_content_publication"] = {"status": "published", "receipt_sha256": "a" * 64}
    workflow["french_publication"] = dict(workflow["french_content_publication"])
    _write_json(workflow_path, workflow)
    with pytest.raises(baseline.WorkflowBaselineError, match="sans plan signé vérifiable"):
        baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)


def test_seal_refuses_unbound_legacy_receipt_when_signed_fr_state_differs(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    workflow_path = project / ".state/workflows" / debate_id / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["phase"] = "final_publication"
    workflow["status"] = "blocked_final_publication"
    workflow["french_content_publication"] = {"status": "published"}
    workflow["french_publication"] = {"status": "published"}
    _write_json(workflow_path, workflow)
    fr_state_path = project / ".state/published" / debate_id / "fr/latest.json"
    fr_state = json.loads(fr_state_path.read_text(encoding="utf-8"))
    fr_state.pop("state_sha256", None)
    fr_state["plan_sha256"] = "9" * 64
    fr_state = _signed(fr_state, "state_sha256")
    _write_json(fr_state_path, fr_state)
    with pytest.raises(baseline.WorkflowBaselineError, match="état français signé"):
        baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)


def test_seal_adopts_legacy_unbound_content_receipt_with_old_local_status(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    workflow_path = project / ".state/workflows" / debate_id / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["phase"] = "final_publication"
    workflow["status"] = "blocked_final_publication"
    workflow["pending_review"] = None
    workflow["french_content_publication"] = {"status": "completed"}
    workflow["french_publication"] = {"status": "completed"}
    _write_json(workflow_path, workflow)

    value = baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)
    receipt_path = project / ".state/fr-publication" / debate_id / work_id / "content/publication-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert value["fr"]["checkpoint_receipt_sha256"] == receipt["receipt_sha256"]
    repaired = json.loads(workflow_path.read_text(encoding="utf-8"))
    assert repaired["french_content_publication"]["receipt_sha256"] == receipt["receipt_sha256"]
    migration = repaired["compatibility_migrations"][-1]
    assert migration["kind"] == "legacy_unbound_fr_content_receipt_reference_adopted"
    assert migration["old_status"] == "completed"
    assert migration["legacy_status_reconciled"] is True


def test_seal_refuses_old_local_status_when_workflow_is_already_bound(tmp_path: Path):
    project, debate_id, work_id, release_copy = make_release_boundary(tmp_path)
    workflow_path = project / ".state/workflows" / debate_id / "workflow.json"
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["phase"] = "final_publication"
    workflow["pending_review"] = None
    workflow["french_content_publication"] = {"status": "completed", "receipt_sha256": "a" * 64}
    workflow["french_publication"] = dict(workflow["french_content_publication"])
    _write_json(workflow_path, workflow)
    with pytest.raises(baseline.WorkflowBaselineError, match="checkpoint français final publié"):
        baseline.seal_workflow_release_baseline(project, debate_id, work_id, release_copy)
