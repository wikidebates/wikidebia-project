from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


reviewer = load_module("wikidebia_remote_plan_review")
workspace_mod = sys.modules["wikidebia_editorial_workspace"]
update = sys.modules["wikidebia_update"]
remote = sys.modules["wikidebia_remote_compare"]


def operation(category: str, page_id: str, title: str, *, phase: int = 2):
    row = {
        "wiki": "fr",
        "language": "fr",
        "title": title,
        "page_id": page_id,
        "page_type": "argument",
        "old_sha256": "1" * 64 if category != "create" else None,
        "new_sha256": "2" * 64 if category != "delete" else None,
        "expected_revision_id": 10,
        "observed_revision_id": 10,
        "justification": f"Justification {category}",
        "preconditions": [],
        "result": None,
        "phase": phase,
    }
    if category == "move":
        row.update({"old_title": title, "new_title": title + " nouveau", "policy": "move"})
    if category == "redirect":
        row["redirect_target"] = "Cible"
    if category == "delete":
        row["retirement_reason"] = "suppression"
    return row


def make_comparison(tmp_path: Path, *, unresolved: str | None = None):
    project = tmp_path / "project"
    debate_id = "debat_test"
    work_id = "EDIT-PLAN-001"
    comparison_id = "REMOTE-20260803-001"
    workspace = project / ".state/editorial-workspaces" / debate_id / work_id
    workspace.mkdir(parents=True)
    run = project / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    run.mkdir(parents=True)

    operations = {name: [] for name in update.OPERATIONS}
    operations["create"].append(operation("create", "A0001", "Argument créé"))
    operations["update"].append(operation("update", "A0002", "Argument corrigé", phase=3))
    operations["move"].append(operation("move", "A0003", "Ancien titre", phase=4))
    operations["skip"].append(operation("skip", "A0004", "Argument inchangé", phase=0))
    if unresolved:
        operations[unresolved].append(operation(unresolved, "A0005", "Page problématique", phase=0))
    plan = {
        "plan_version": update.PLAN_VERSION,
        "kit_version": update.KIT_VERSION,
        "required_validator_version": update.REQUIRED_VALIDATOR_VERSION,
        "debate_id": debate_id,
        "corpus_version": "release-test",
        "languages": ["fr"],
        "scope_mode": "all",
        "state_source": {},
        "new_manifest_sha256": "3" * 64,
        "validator_report_sha256": "4" * 64,
        "config_sha256": "5" * 64,
        "operations": operations,
        "comparisons": [],
        "counts": {name: len(operations[name]) for name in update.OPERATIONS},
        "preconditions": ["read_only_comparison_completed", "plan_not_executed"],
    }
    plan["plan_sha256"] = update.sha_object(plan)
    (run / "update-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    inventory = {
        "schema": "wikidebia-observed-remote-inventory-1.0",
        "debate_id": debate_id,
        "comparison_id": comparison_id,
        "mode": "read_only",
        "pages": [],
        "write_attempts": 0,
        "remote_write_performed": False,
    }
    inventory["inventory_sha256"] = update.sha_object(inventory)
    (run / "remote-inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    validation = {"validator_version": "0.4.29", "result": "passed", "summary": {"errors": 0, "warnings": 0}}
    (run / "plan-validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status = "manual_review" if unresolved == "manual_review" else ("blocked" if unresolved == "blocked" else "plan_ready")
    receipt = {
        "schema": remote.RECEIPT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "status": status,
        "scope": "fr",
        "kit_version": update.KIT_VERSION,
        "validator_version": update.REQUIRED_VALIDATOR_VERSION,
        "release_copy_tree_sha256": "6" * 64,
        "plan_path": f".state/remote-comparisons/{debate_id}/{work_id}/{comparison_id}/update-plan.json",
        "plan_sha256": plan["plan_sha256"],
        "remote_inventory_sha256": inventory["inventory_sha256"],
        "remote_write_performed": False,
        "execution_authorized": False,
    }
    receipt["receipt_sha256"] = remote._canonical_sha(receipt, "receipt_sha256")
    (run / "comparison-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    comparison_meta = {"comparison_id": comparison_id, "status": status, "plan_sha256": plan["plan_sha256"]}
    meta = {
        "schema": "wikidebia-editorial-workspace-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "normative_revision": "1.2.27",
        "status": "remote_plan_ready" if status == "plan_ready" else ("remote_plan_manual_review" if status == "manual_review" else "remote_plan_blocked"),
        "remote_comparison": comparison_meta,
        "remote_comparisons": [comparison_meta],
    }
    meta["workspace_sha256"] = workspace_mod.workspace_receipt_hash(meta)
    (workspace / "workspace.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return project, debate_id, work_id, comparison_id, run


def fill_approved_review(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update({
        "overall_decision": "approved",
        "reviewer": "Relectrice test",
        "reviewed_at": "2026-08-03T23:45:00+02:00",
        "review_summary": "Chaque opération a été comparée à l’inventaire distant et au corpus proposé.",
    })
    value["attestations"] = {key: True for key in value["attestations"]}
    for row in value["operations"]:
        row["review_decision"] = "acknowledged" if row["category"] == "skip" else "approved"
        if row["category"] in reviewer.DESTRUCTIVE_OPERATIONS:
            row["reviewer_note"] = "Impact et cible vérifiés individuellement."
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_prepare_and_finalize_approved_plan_without_remote_write(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _ = make_comparison(tmp_path)
    prepared = reviewer.prepare_review(project, debate_id, work_id, comparison_id)
    assert prepared["status"] == "review_ready"
    assert prepared["operation_count"] == 4
    review_path = project / prepared["review"]
    fill_approved_review(review_path)
    result = reviewer.finalize_review(project, debate_id, work_id, comparison_id)
    assert result["status"] == "approved"
    assert result["remote_write_performed"] is False
    base = project / ".state/remote-plan-reviews" / debate_id / work_id / comparison_id
    acceptance = json.loads((base / "plan-acceptance.json").read_text(encoding="utf-8"))
    receipt = json.loads((base / "review-receipt.json").read_text(encoding="utf-8"))
    assert acceptance["plan_accepted"] is True
    assert acceptance["execution_handoff_ready"] is True
    assert acceptance["execution_started"] is False
    assert acceptance["remote_write_authorized"] is False
    assert receipt["remote_access_performed"] is False
    assert receipt["remote_write_performed"] is False
    meta = json.loads((project / ".state/editorial-workspaces" / debate_id / work_id / "workspace.json").read_text(encoding="utf-8"))
    assert meta["status"] == "remote_plan_approved"


def test_approval_refuses_manual_review_plan(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _ = make_comparison(tmp_path, unresolved="manual_review")
    prepared = reviewer.prepare_review(project, debate_id, work_id, comparison_id)
    review_path = project / prepared["review"]
    fill_approved_review(review_path)
    try:
        reviewer.finalize_review(project, debate_id, work_id, comparison_id)
    except reviewer.RemotePlanReviewError as exc:
        assert "manual_review" in str(exc) or "non résolue" in str(exc)
    else:
        raise AssertionError("Un plan manual_review a été approuvé")
    assert not (review_path.parent / "plan-acceptance.json").exists()


def test_rejected_review_is_sealed_without_acceptance(tmp_path: Path):
    project, debate_id, work_id, comparison_id, _ = make_comparison(tmp_path)
    prepared = reviewer.prepare_review(project, debate_id, work_id, comparison_id)
    review_path = project / prepared["review"]
    value = json.loads(review_path.read_text(encoding="utf-8"))
    value.update({
        "overall_decision": "rejected",
        "reviewer": "Relecteur test",
        "reviewed_at": "2026-08-03",
        "review_summary": "Le plan doit être reconstruit.",
        "rejection_reason": "Le déplacement proposé doit être revu.",
    })
    review_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = reviewer.finalize_review(project, debate_id, work_id, comparison_id)
    assert result["status"] == "rejected"
    assert result["acceptance_sha256"] is None
    assert not (review_path.parent / "plan-acceptance.json").exists()


def test_finalization_detects_changed_comparison_evidence(tmp_path: Path):
    project, debate_id, work_id, comparison_id, run = make_comparison(tmp_path)
    prepared = reviewer.prepare_review(project, debate_id, work_id, comparison_id)
    review_path = project / prepared["review"]
    fill_approved_review(review_path)
    plan = json.loads((run / "update-plan.json").read_text(encoding="utf-8"))
    plan["corpus_version"] = "altered"
    plan["plan_sha256"] = update.sha_object({k: v for k, v in plan.items() if k != "plan_sha256"})
    (run / "update-plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        reviewer.finalize_review(project, debate_id, work_id, comparison_id)
    except reviewer.RemotePlanReviewError as exc:
        assert "reçu et le plan divergent" in str(exc) or "modifiée" in str(exc)
    else:
        raise AssertionError("Une preuve de comparaison altérée a été acceptée")


def test_plan_review_verifies_signed_read_checkpoint(tmp_path: Path):
    project, debate_id, work_id, comparison_id, run = make_comparison(tmp_path)
    checkpoint = {
        "schema": remote.READ_CHECKPOINT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "scope": "fr",
        "release_copy_tree_sha256": "6" * 64,
        "created_at": "2026-08-03T00:00:00+00:00",
        "updated_at": "2026-08-03T00:00:00+00:00",
        "title_sets": {},
        "pages": [],
        "page_count": 0,
        "completed_batches": 0,
        "remote_write_performed": False,
    }
    checkpoint["checkpoint_sha256"] = remote._canonical_sha(checkpoint, "checkpoint_sha256")
    checkpoint_path = run / "read-checkpoint.json"
    checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    receipt_path = run / "comparison-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt.update({
        "read_checkpoint_path": checkpoint_path.relative_to(project).as_posix(),
        "read_checkpoint_sha256": checkpoint["checkpoint_sha256"],
        "read_checkpoint_page_count": 0,
    })
    receipt["receipt_sha256"] = remote._canonical_sha(receipt, "receipt_sha256")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    loaded = reviewer._load_comparison(project, debate_id, work_id, comparison_id)
    assert "read_checkpoint" in loaded["evidence"]

    checkpoint["updated_at"] = "2026-08-04T00:00:00+00:00"
    checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        reviewer._load_comparison(project, debate_id, work_id, comparison_id)
    except reviewer.RemotePlanReviewError as exc:
        assert "checkpoint" in str(exc)
    else:
        raise AssertionError("Checkpoint de lecture falsifié accepté")
