#!/usr/bin/env python3
"""Prepare and seal a formal human review of a read-only remote plan.

This phase is deliberately local. It never opens MediaWiki and never mutates the
signed comparison evidence. An approved review creates a separate acceptance
handoff binding the exact plan, remote inventory, comparison receipt and release
copy. Execution remains a later, explicit phase.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from wikidebia_corpus_build import (
    assert_control_directory,
    exclusive_lock,
    load_json,
    now_iso,
    relative_to_project,
    sha256_file,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id, workspace_receipt_hash
from wikidebia_render import _load_workspace
from wikidebia_remote_compare import READ_CHECKPOINT_SCHEMA, _canonical_sha, _validate_comparison_id
from wikidebia_update import KIT_VERSION, REQUIRED_VALIDATOR_VERSION, OPERATIONS, sha_object

REVIEW_SCHEMA = "wikidebia-remote-plan-review-1.0"
RECEIPT_SCHEMA = "wikidebia-remote-plan-review-receipt-1.0"
ACCEPTANCE_SCHEMA = "wikidebia-remote-plan-acceptance-1.0"
MUTATING_OPERATIONS = ("create", "update", "move", "redirect", "delete")
DESTRUCTIVE_OPERATIONS = ("move", "redirect", "delete")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T.*)?$")


class RemotePlanReviewError(WorkspaceError):
    pass


def _canonical_review_sha(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("review_sha256", None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _review_root(project_root: Path, debate_id: str, work_id: str, comparison_id: str) -> Path:
    state = assert_control_directory(project_root / ".state", project_root, create=True)
    root = assert_control_directory(state / "remote-plan-reviews", project_root, create=True)
    debate = assert_control_directory(root / debate_id, project_root, create=True)
    work = assert_control_directory(debate / work_id, project_root, create=True)
    return work / comparison_id


def _verify_sha_object(value: dict[str, Any], field: str, label: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if not claimed or claimed != sha_object(body):
        raise RemotePlanReviewError(f"Empreinte {label} invalide")


def _load_comparison(
    project_root: Path, debate_id: str, work_id: str, comparison_id: str
) -> dict[str, Any]:
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("workspace_sha256") != workspace_receipt_hash(meta):
        raise RemotePlanReviewError("Empreinte du workspace invalide")
    allowed = {
        "remote_plan_ready", "remote_plan_manual_review", "remote_plan_blocked",
        "remote_plan_review_ready", "remote_plan_approved", "remote_plan_rejected",
        "remote_execution_ready", "remote_execution_completed", "remote_execution_no_changes",
        "remote_execution_failed", "remote_execution_blocked", "remote_execution_no_changes_in_scope",
    }
    if meta.get("status") not in allowed:
        raise RemotePlanReviewError(f"Statut incompatible avec la revue du plan : {meta.get('status')}")

    run_dir = project_root / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise RemotePlanReviewError("Comparaison distante absente ou non sûre")
    required = {
        "plan": run_dir / "update-plan.json",
        "comparison_receipt": run_dir / "comparison-receipt.json",
        "remote_inventory": run_dir / "remote-inventory.json",
        "plan_validation": run_dir / "plan-validation.json",
    }
    for label, path in required.items():
        if not path.is_file() or path.is_symlink():
            raise RemotePlanReviewError(f"Preuve de comparaison absente : {label}")

    plan = load_json(required["plan"], "plan distant")
    _verify_sha_object(plan, "plan_sha256", "du plan")
    # Producer release numbers are provenance only; the signed plan schema and
    # its hashes determine compatibility and integrity.
    receipt = load_json(required["comparison_receipt"], "reçu de comparaison")
    if receipt.get("receipt_sha256") != _canonical_sha(receipt, "receipt_sha256"):
        raise RemotePlanReviewError("Empreinte du reçu de comparaison invalide")
    checkpoint_rel = str(receipt.get("read_checkpoint_path") or "")
    if checkpoint_rel:
        checkpoint_path = (project_root / checkpoint_rel).resolve()
        expected_checkpoint = (run_dir / "read-checkpoint.json").resolve()
        if checkpoint_path != expected_checkpoint or not checkpoint_path.is_file() or checkpoint_path.is_symlink():
            raise RemotePlanReviewError("Checkpoint de lecture distant absent ou extérieur à la comparaison")
        checkpoint = load_json(checkpoint_path, "checkpoint de lecture distant")
        if checkpoint.get("schema") != READ_CHECKPOINT_SCHEMA:
            raise RemotePlanReviewError("Schéma du checkpoint de lecture distant invalide")
        if checkpoint.get("checkpoint_sha256") != _canonical_sha(checkpoint, "checkpoint_sha256"):
            raise RemotePlanReviewError("Empreinte du checkpoint de lecture distant invalide")
        if checkpoint.get("checkpoint_sha256") != receipt.get("read_checkpoint_sha256"):
            raise RemotePlanReviewError("Le reçu et le checkpoint de lecture distant divergent")
        if (
            type(checkpoint.get("page_count")) is not int
            or type(receipt.get("read_checkpoint_page_count")) is not int
            or checkpoint["page_count"] != receipt["read_checkpoint_page_count"]
        ):
            raise RemotePlanReviewError("Compteur du checkpoint de lecture distant divergent")
        checkpoint_identity = {
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "scope": receipt.get("scope"),
            "release_copy_tree_sha256": receipt.get("release_copy_tree_sha256"),
        }
        if any(checkpoint.get(field) != expected for field, expected in checkpoint_identity.items()):
            raise RemotePlanReviewError("Identité du checkpoint de lecture distant divergente")
        if checkpoint.get("remote_write_performed") is not False:
            raise RemotePlanReviewError("Le checkpoint indique une écriture distante")
        required["read_checkpoint"] = checkpoint_path
    inventory = load_json(required["remote_inventory"], "inventaire distant")
    _verify_sha_object(inventory, "inventory_sha256", "de l’inventaire distant")
    validation = load_json(required["plan_validation"], "validation du plan")

    if receipt.get("debate_id") != debate_id or receipt.get("work_id") != work_id:
        raise RemotePlanReviewError("Le reçu de comparaison vise un autre corpus")
    if receipt.get("comparison_id") != comparison_id:
        raise RemotePlanReviewError("Le reçu vise une autre comparaison")
    if receipt.get("plan_sha256") != plan.get("plan_sha256"):
        raise RemotePlanReviewError("Le reçu et le plan divergent")
    if receipt.get("remote_inventory_sha256") != inventory.get("inventory_sha256"):
        raise RemotePlanReviewError("Le reçu et l’inventaire distant divergent")
    if receipt.get("remote_write_performed") is not False or receipt.get("execution_authorized") is not False:
        raise RemotePlanReviewError("La comparaison ne porte pas les barrières de lecture seule attendues")
    if inventory.get("remote_write_performed") is not False or int(inventory.get("write_attempts", 0)) != 0:
        raise RemotePlanReviewError("L’inventaire indique une tentative d’écriture distante")
    summary = validation.get("summary") or {}
    if int(summary.get("errors", 0)) or validation.get("result") not in {"passed", "passed_with_warnings", None}:
        raise RemotePlanReviewError("La validation locale du plan n’est pas positive")

    counts = plan.get("counts") or {}
    operations = plan.get("operations") or {}
    for category in OPERATIONS:
        if int(counts.get(category, -1)) != len(operations.get(category) or []):
            raise RemotePlanReviewError(f"Compteur divergent dans le plan : {category}")

    known = [row for row in (meta.get("remote_comparisons") or []) if row.get("comparison_id") == comparison_id]
    if not known:
        raise RemotePlanReviewError("La comparaison n’est pas enregistrée dans le workspace")
    if known[-1].get("plan_sha256") != plan.get("plan_sha256"):
        raise RemotePlanReviewError("Le workspace référence une autre empreinte de plan")

    evidence = {
        label: {
            "path": relative_to_project(path, project_root),
            "file_sha256": sha256_file(path),
        }
        for label, path in required.items()
    }
    release_sha = str(receipt.get("release_copy_tree_sha256") or "")
    if not release_sha:
        raise RemotePlanReviewError("Empreinte de release-copy absente du reçu de comparaison")
    return {
        "workspace": workspace,
        "meta": meta,
        "run_dir": run_dir,
        "plan": plan,
        "receipt": receipt,
        "inventory": inventory,
        "validation": validation,
        "evidence": evidence,
        "release_sha256": release_sha,
    }


def _operation_id(category: str, row: Mapping[str, Any]) -> str:
    payload = {
        "category": category,
        "language": row.get("language"),
        "page_id": row.get("page_id"),
        "page_type": row.get("page_type"),
        "title": row.get("title"),
        "old_title": row.get("old_title"),
        "new_title": row.get("new_title"),
        "phase": row.get("phase"),
        "comparison_id": row.get("comparison_id"),
    }
    return sha_object(payload)[:24]


def _operation_reviews(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    operations = plan.get("operations") or {}
    for category in OPERATIONS:
        for row in operations.get(category) or []:
            result.append({
                "operation_id": _operation_id(category, row),
                "category": category,
                "language": str(row.get("language") or ""),
                "page_id": str(row.get("page_id") or ""),
                "page_type": str(row.get("page_type") or "unknown"),
                "title": str(row.get("title") or ""),
                "old_title": row.get("old_title"),
                "new_title": row.get("new_title"),
                "redirect_target": row.get("redirect_target"),
                "retirement_reason": row.get("retirement_reason"),
                "phase": int(row.get("phase", 99)),
                "justification": str(row.get("justification") or ""),
                "comparison_id": row.get("comparison_id"),
                "remote_revision_id": row.get("observed_revision_id"),
                "review_decision": "pending",
                "reviewer_note": "",
            })
    return result


def _attestation_template() -> dict[str, bool]:
    return {
        "exact_plan_and_sha256_reviewed": False,
        "remote_inventory_and_revisions_reviewed": False,
        "operation_categories_and_scope_reviewed": False,
        "human_or_indeterminate_changes_are_not_overwritten": False,
        "moves_redirects_and_deletions_reviewed_individually": False,
        "execution_is_a_separate_explicit_phase": False,
        "no_remote_write_was_performed_during_review": False,
    }


def _update_workspace(meta: dict[str, Any], workspace: Path, entry: dict[str, Any], status: str) -> None:
    meta["remote_plan_review"] = entry
    history = list(meta.get("remote_plan_reviews") or [])
    history.append(entry)
    meta["remote_plan_reviews"] = history
    meta["status"] = status
    meta["workspace_sha256"] = workspace_receipt_hash(meta)
    write_json(workspace / "workspace.json", meta)


def prepare_review(
    project_root: Path,
    debate_id: str,
    work_id: str,
    comparison_id: str,
    *,
    overwrite_review: bool = False,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    comparison_id = _validate_comparison_id(comparison_id)
    comparison = _load_comparison(project_root, debate_id, work_id, comparison_id)
    review_dir = _review_root(project_root, debate_id, work_id, comparison_id)
    if review_dir.exists() or review_dir.is_symlink():
        review_path = review_dir / "plan-review.json"
        if not overwrite_review:
            raise RemotePlanReviewError("Une revue de ce plan existe déjà")
        if review_path.is_file():
            existing = load_json(review_path, "revue du plan")
            if existing.get("status") in {"approved", "rejected"}:
                raise RemotePlanReviewError("Une revue finalisée ne peut pas être écrasée")
        import shutil
        shutil.rmtree(review_dir)
    review_dir.mkdir(parents=False)

    plan = comparison["plan"]
    review = {
        "schema": REVIEW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "status": "draft",
        "prepared_at": now_iso(),
        "kit_version": KIT_VERSION,
        "validator_version": REQUIRED_VALIDATOR_VERSION,
        "comparison_status": comparison["receipt"].get("status"),
        "scope": comparison["receipt"].get("scope"),
        "release_copy_tree_sha256": comparison["release_sha256"],
        "plan_sha256": plan["plan_sha256"],
        "plan_counts": dict(plan.get("counts") or {}),
        "evidence": comparison["evidence"],
        "overall_decision": "pending",
        "reviewer": "",
        "reviewed_at": "",
        "review_summary": "",
        "rejection_reason": "",
        "attestations": _attestation_template(),
        "operations": _operation_reviews(plan),
        "review_sha256": None,
    }
    write_json(review_dir / "plan-review.json", review)
    entry = {
        "comparison_id": comparison_id,
        "status": "draft",
        "review_path": relative_to_project(review_dir / "plan-review.json", project_root),
        "plan_sha256": plan["plan_sha256"],
        "prepared_at": review["prepared_at"],
    }
    _update_workspace(comparison["meta"], comparison["workspace"], entry, "remote_plan_review_ready")
    return {
        "status": "review_ready",
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "review": entry["review_path"],
        "plan_sha256": plan["plan_sha256"],
        "operation_count": len(review["operations"]),
        "remote_write_performed": False,
    }


def _verify_evidence(project_root: Path, review: Mapping[str, Any]) -> None:
    for label, row in (review.get("evidence") or {}).items():
        path = project_root / str(row.get("path") or "")
        if not path.is_file() or path.is_symlink():
            raise RemotePlanReviewError(f"Preuve disparue depuis la préparation : {label}")
        if sha256_file(path) != row.get("file_sha256"):
            raise RemotePlanReviewError(f"Preuve modifiée depuis la préparation : {label}")


def _verify_operation_rows(review: Mapping[str, Any], plan: Mapping[str, Any]) -> list[str]:
    expected = _operation_reviews(plan)
    actual = review.get("operations")
    if not isinstance(actual, list):
        raise RemotePlanReviewError("La liste des décisions d’opération est absente")
    if len(actual) != len(expected):
        raise RemotePlanReviewError("La revue ne couvre pas toutes les opérations")
    errors: list[str] = []
    immutable = (
        "operation_id", "category", "language", "page_id", "page_type", "title",
        "old_title", "new_title", "redirect_target", "retirement_reason", "phase",
        "justification", "comparison_id", "remote_revision_id",
    )
    for index, (observed, wanted) in enumerate(zip(actual, expected)):
        if not isinstance(observed, dict):
            errors.append(f"opération {index + 1}: objet attendu")
            continue
        for field in immutable:
            if observed.get(field) != wanted.get(field):
                errors.append(f"opération {index + 1}: champ figé modifié ({field})")
    return errors


def _valid_reviewed_at(value: str) -> bool:
    if not value or not ISO_DATE_RE.match(value):
        return False
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def finalize_review(
    project_root: Path,
    debate_id: str,
    work_id: str,
    comparison_id: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    comparison_id = _validate_comparison_id(comparison_id)
    comparison = _load_comparison(project_root, debate_id, work_id, comparison_id)
    review_dir = _review_root(project_root, debate_id, work_id, comparison_id)
    review_path = review_dir / "plan-review.json"
    if not review_path.is_file() or review_path.is_symlink():
        raise RemotePlanReviewError("Revue préparée absente")
    review = load_json(review_path, "revue du plan")
    if review.get("schema") != REVIEW_SCHEMA:
        raise RemotePlanReviewError("Schéma de revue inconnu")
    if review.get("status") in {"approved", "rejected"}:
        if review.get("review_sha256") != _canonical_review_sha(review):
            raise RemotePlanReviewError("Empreinte de la revue finalisée invalide")
        return {
            "status": review["status"],
            "review_sha256": review["review_sha256"],
            "comparison_id": comparison_id,
            "remote_write_performed": False,
        }
    if review.get("status") != "draft":
        raise RemotePlanReviewError("Statut de revue incompatible")
    if review.get("debate_id") != debate_id or review.get("work_id") != work_id or review.get("comparison_id") != comparison_id:
        raise RemotePlanReviewError("La revue vise un autre corpus ou une autre comparaison")
    if review.get("plan_sha256") != comparison["plan"].get("plan_sha256"):
        raise RemotePlanReviewError("La revue vise une autre empreinte de plan")
    if review.get("release_copy_tree_sha256") != comparison["release_sha256"]:
        raise RemotePlanReviewError("La revue vise une autre release-copy")
    _verify_evidence(project_root, review)
    errors = _verify_operation_rows(review, comparison["plan"])

    decision = str(review.get("overall_decision") or "")
    if decision not in {"approved", "rejected"}:
        errors.append("overall_decision doit être approved ou rejected")
    if not str(review.get("reviewer") or "").strip():
        errors.append("reviewer est obligatoire")
    if not _valid_reviewed_at(str(review.get("reviewed_at") or "")):
        errors.append("reviewed_at doit être une date ISO valide")
    if not str(review.get("review_summary") or "").strip():
        errors.append("review_summary est obligatoire")

    operations = review.get("operations") or []
    if decision == "approved":
        plan_operations = comparison["plan"].get("operations") or {}
        if plan_operations.get("manual_review") or plan_operations.get("blocked"):
            errors.append("Un plan manual_review ou blocked ne peut pas être approuvé")
        if comparison["receipt"].get("status") != "plan_ready":
            errors.append("Le reçu de comparaison n’autorise pas l’approbation du plan")
        for row in operations:
            category = row.get("category")
            item_decision = row.get("review_decision")
            if category in MUTATING_OPERATIONS and item_decision != "approved":
                errors.append(f"{row.get('operation_id')}: opération mutante non approuvée")
            elif category == "skip" and item_decision != "acknowledged":
                errors.append(f"{row.get('operation_id')}: skip non attesté")
            elif category in {"manual_review", "blocked"}:
                errors.append(f"{row.get('operation_id')}: opération non résolue")
            if category in DESTRUCTIVE_OPERATIONS and not str(row.get("reviewer_note") or "").strip():
                errors.append(f"{row.get('operation_id')}: note obligatoire pour {category}")
        attestations = review.get("attestations") or {}
        expected_attestations = _attestation_template()
        if set(attestations) != set(expected_attestations):
            errors.append("Jeu d’attestations divergent")
        else:
            for key in expected_attestations:
                if attestations.get(key) is not True:
                    errors.append(f"Attestation manquante : {key}")
        if str(review.get("rejection_reason") or "").strip():
            errors.append("rejection_reason doit rester vide pour une approbation")
    elif decision == "rejected":
        if not str(review.get("rejection_reason") or "").strip():
            errors.append("rejection_reason est obligatoire pour un rejet")

    if errors:
        raise RemotePlanReviewError("Revue incomplète : " + " | ".join(errors[:20]))

    finalized_at = now_iso()
    review["status"] = decision
    review["finalized_at"] = finalized_at
    review["review_sha256"] = _canonical_review_sha(review)
    write_json(review_path, review)

    acceptance_path: Path | None = None
    acceptance_sha: str | None = None
    if decision == "approved":
        acceptance = {
            "schema": ACCEPTANCE_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "work_id": work_id,
            "comparison_id": comparison_id,
            "status": "accepted",
            "accepted_at": finalized_at,
            "plan_path": comparison["receipt"].get("plan_path"),
            "plan_sha256": comparison["plan"]["plan_sha256"],
            "comparison_receipt_sha256": comparison["receipt"]["receipt_sha256"],
            "remote_inventory_sha256": comparison["inventory"]["inventory_sha256"],
            "release_copy_tree_sha256": comparison["release_sha256"],
            "review_path": relative_to_project(review_path, project_root),
            "review_sha256": review["review_sha256"],
            "plan_accepted": True,
            "execution_handoff_ready": True,
            "execution_started": False,
            "remote_write_authorized": False,
            "remote_access_performed_during_review": False,
            "remote_write_performed": False,
        }
        acceptance["acceptance_sha256"] = _canonical_sha(acceptance, "acceptance_sha256")
        acceptance_path = review_dir / "plan-acceptance.json"
        write_json(acceptance_path, acceptance)
        acceptance_sha = acceptance["acceptance_sha256"]

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "status": decision,
        "created_at": finalized_at,
        "kit_version": KIT_VERSION,
        "validator_version": REQUIRED_VALIDATOR_VERSION,
        "plan_sha256": comparison["plan"]["plan_sha256"],
        "comparison_receipt_sha256": comparison["receipt"]["receipt_sha256"],
        "review_path": relative_to_project(review_path, project_root),
        "review_sha256": review["review_sha256"],
        "acceptance_path": relative_to_project(acceptance_path, project_root) if acceptance_path else None,
        "acceptance_sha256": acceptance_sha,
        "remote_access_performed": False,
        "remote_write_performed": False,
        "execution_started": False,
    }
    receipt["receipt_sha256"] = _canonical_sha(receipt, "receipt_sha256")
    receipt_path = review_dir / "review-receipt.json"
    write_json(receipt_path, receipt)

    entry = {
        "comparison_id": comparison_id,
        "status": decision,
        "plan_sha256": comparison["plan"]["plan_sha256"],
        "review_path": relative_to_project(review_path, project_root),
        "review_sha256": review["review_sha256"],
        "receipt_path": relative_to_project(receipt_path, project_root),
        "receipt_sha256": receipt["receipt_sha256"],
        "acceptance_path": receipt["acceptance_path"],
        "acceptance_sha256": acceptance_sha,
        "finalized_at": finalized_at,
    }
    status = "remote_plan_approved" if decision == "approved" else "remote_plan_rejected"
    _update_workspace(comparison["meta"], comparison["workspace"], entry, status)
    return {
        "status": decision,
        "debate_id": debate_id,
        "work_id": work_id,
        "comparison_id": comparison_id,
        "plan_sha256": comparison["plan"]["plan_sha256"],
        "review_sha256": review["review_sha256"],
        "acceptance_sha256": acceptance_sha,
        "remote_write_performed": False,
        "execution_started": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Préparer ou finaliser la revue formelle d’un plan distant")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--comparison-id", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--finalize", action="store_true")
    parser.add_argument("--overwrite-review", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    args = parser.parse_args(argv)
    with exclusive_lock(args.project_root.resolve(), args.debate_id, "remote-plan-review"):
        if args.prepare:
            result = prepare_review(
                args.project_root, args.debate_id, args.work_id, args.comparison_id,
                overwrite_review=args.overwrite_review,
            )
        else:
            result = finalize_review(args.project_root, args.debate_id, args.work_id, args.comparison_id)
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Revue du plan : {result['status']}")
        if result.get("review_sha256"):
            print(f"SHA-256 de la revue : {result['review_sha256']}")
        if result.get("acceptance_sha256"):
            print(f"SHA-256 de l’acceptation : {result['acceptance_sha256']}")
    return 0 if result["status"] in {"review_ready", "approved"} else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RemotePlanReviewError as exc:
        print(f"REVUE DU PLAN BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
