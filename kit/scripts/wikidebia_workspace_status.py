#!/usr/bin/env python3
"""Report a compact, verified workspace state and its exact next command."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import CorpusBuildError, validate_debate_id
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_remote_plan_review import RemotePlanReviewError, _load_comparison
from wikidebia_render import RenderError, _load_workspace
from wikidebia_update import OPERATIONS


class WorkspaceStatusError(WorkspaceError):
    pass


REMOTE_STATUSES = {
    "remote_plan_ready",
    "remote_plan_manual_review",
    "remote_plan_blocked",
    "remote_plan_review_ready",
    "remote_plan_approved",
    "remote_plan_rejected",
    "remote_execution_ready",
    "remote_execution_completed",
    "remote_execution_no_changes",
    "remote_execution_failed",
    "remote_execution_blocked",
    "remote_execution_no_changes_in_scope",
}


def _command(name: str, debate_id: str, work_id: str, *arguments: str) -> str:
    # Both identifiers are validated before reaching this helper. Remaining
    # values are signed IDs or hashes whose accepted alphabets contain no shell
    # metacharacters.
    parts = ["./wikidebia", name, debate_id, "--work-id", work_id, *arguments]
    return " ".join(parts)


def _next_step(meta: Mapping[str, Any], debate_id: str, work_id: str) -> dict[str, Any]:
    status = str(meta.get("status") or "")
    comparison = meta.get("remote_comparison") or {}
    review = meta.get("remote_plan_review") or {}
    execution = meta.get("remote_execution") or {}
    comparison_id = str(
        execution.get("comparison_id")
        or review.get("comparison_id")
        or comparison.get("comparison_id")
        or ""
    )

    action = "manual_review_required"
    command: str | None = None
    remote_read = False
    remote_write = False
    note: str | None = None

    if status == "workspace_initialized":
        action = "finalize_french_title_review"
        command = _command("corpus-workspace-review", debate_id, work_id, "--finalize")
    elif status in {"fr_title_review_finalized", "fr_review_finalized"}:
        digest = str((meta.get("french_review") or {}).get("review_sha256") or "")
        if digest:
            action = "apply_french_title_review"
            command = _command(
                "corpus-workspace-review", debate_id, work_id,
                "--apply", "--confirm-review-sha256", digest,
            )
    elif status in {"fr_titles_applied", "fr_metadata_applied"}:
        action = "prepare_french_content_review"
        command = _command("corpus-workspace-content-review", debate_id, work_id, "--prepare")
    elif status == "fr_content_review_ready":
        action = "finalize_french_content_review"
        command = _command("corpus-workspace-content-review", debate_id, work_id, "--finalize")
    elif status == "fr_content_review_finalized":
        digest = str((meta.get("french_content_review") or {}).get("review_sha256") or "")
        if digest:
            action = "apply_french_content_review"
            command = _command(
                "corpus-workspace-content-review", debate_id, work_id,
                "--apply", "--confirm-review-sha256", digest,
            )
    elif status == "fr_content_applied":
        action = "prepare_english_translation_review"
        command = _command("corpus-workspace-translation", debate_id, work_id, "--prepare")
    elif status == "en_translation_review_ready":
        action = "finalize_english_translation_review"
        command = _command("corpus-workspace-translation", debate_id, work_id, "--finalize")
    elif status == "en_translation_review_finalized":
        convergence = meta.get("semantic_convergence") or {}
        digest = str((meta.get("english_translation_review") or {}).get("review_sha256") or "")
        if convergence.get("status") == "converged" and digest:
            action = "apply_english_translation"
            command = _command(
                "corpus-workspace-translation", debate_id, work_id,
                "--apply", "--confirm-review-sha256", digest,
            )
        else:
            action = "record_two_semantic_convergence_passes"
            note = "Deux méthodes et notes de relecture humaines sont requises avant l’application."
    elif status in {"en_translation_applied", "bilingual_rendered", "release_ready"}:
        action = "finalize_workspace_read_only"
        command = _command("corpus-workspace-finalize", debate_id, work_id)
        remote_read = True
    elif status == "remote_plan_ready" and comparison_id:
        action = "prepare_remote_plan_review"
        command = _command(
            "corpus-workspace-plan-review", debate_id, work_id,
            "--comparison-id", comparison_id, "--prepare",
        )
    elif status == "remote_plan_review_ready" and comparison_id:
        action = "finalize_remote_plan_review"
        command = _command(
            "corpus-workspace-plan-review", debate_id, work_id,
            "--comparison-id", comparison_id, "--finalize",
        )
    elif status == "remote_plan_approved" and comparison_id:
        digest = str(review.get("acceptance_sha256") or "")
        if digest:
            action = "prepare_remote_execution"
            command = _command(
                "corpus-workspace-plan-execute", debate_id, work_id,
                "--comparison-id", comparison_id, "--prepare",
                "--confirm-acceptance-sha256", digest,
            )
            remote_read = True
    elif status == "remote_execution_ready" and comparison_id:
        digest = str(execution.get("preflight_sha256") or "")
        mode = str(execution.get("mode") or "all")
        if digest:
            action = "execute_remote_plan"
            command = _command(
                "corpus-workspace-plan-execute", debate_id, work_id,
                "--comparison-id", comparison_id, "--execute", "--mode", mode,
                "--confirm-preflight-sha256", digest,
            )
            remote_read = True
            remote_write = True
    elif status in {"remote_execution_completed", "remote_execution_no_changes"} and comparison_id:
        digest = str(execution.get("receipt_sha256") or "")
        if digest:
            action = "close_workspace"
            command = _command(
                "corpus-workspace-close", debate_id, work_id,
                "--comparison-id", comparison_id,
                "--confirm-execution-sha256", digest,
            )
    elif status in {"published", "work_closed"}:
        action = "complete"
    elif status in {"remote_plan_manual_review", "remote_plan_blocked"}:
        action = "resolve_remote_differences_then_refresh"
        command = _command(
            "corpus-workspace-finalize", debate_id, work_id, "--refresh-remote"
        )
        remote_read = True
        note = "Corriger ou accepter explicitement les divergences avant de relancer la comparaison."
    elif status == "remote_plan_rejected":
        action = "revise_release_or_create_new_comparison"
        note = "Le plan a été rejeté ; une nouvelle preuve locale est requise avant toute exécution."
    elif status.startswith("remote_execution_"):
        action = "resolve_remote_execution_block"
        note = "Le préflight ou l’exécution doit être diagnostiqué avant une nouvelle commande."

    return {
        "action": action,
        "command": command,
        "remote_read_possible": remote_read,
        "remote_write_possible": remote_write,
        **({"note": note} if note else {}),
    }


def _phase(status: str) -> str:
    if status in {"published", "work_closed"}:
        return "complete"
    if status.startswith("remote_execution_"):
        return "remote_execution"
    if status.startswith("remote_plan_"):
        return "remote_plan"
    if status == "release_ready":
        return "release"
    if status == "bilingual_rendered":
        return "render"
    if status.startswith("en_translation"):
        return "english_translation"
    if status.startswith("fr_content"):
        return "french_content"
    return "french_metadata"


def summarize_workspace(project_root: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    _, meta = _load_workspace(project_root, debate_id, work_id)
    status = str(meta.get("status") or "")
    if not status:
        raise WorkspaceStatusError("Statut du workspace absent")

    remote: dict[str, Any] | None = None
    no_change_plan_sha256: str | None = None
    comparison_meta = meta.get("remote_comparison") or {}
    comparison_id = str(comparison_meta.get("comparison_id") or "")
    if status in REMOTE_STATUSES and comparison_id:
        comparison = _load_comparison(project_root, debate_id, work_id, comparison_id)
        receipt = comparison["receipt"]
        remote = {
            "comparison_id": comparison_id,
            "status": receipt.get("status"),
            "scope": receipt.get("scope"),
            "counts": receipt.get("counts") or {},
            "plan_sha256": receipt.get("plan_sha256"),
            "receipt_sha256": receipt.get("receipt_sha256"),
        }
        plan = comparison["plan"]
        operations = plan.get("operations") or {}
        if (
            status == "remote_plan_ready"
            and receipt.get("status") == "plan_ready"
            and receipt.get("scope") == "all"
            and set(operations) == set(OPERATIONS)
            and operations.get("skip")
            and all(not operations.get(category) for category in OPERATIONS if category != "skip")
        ):
            no_change_plan_sha256 = str(plan.get("plan_sha256") or "") or None

    artifact_hashes = {
        name: str((meta.get(key) or {}).get(field) or "")
        for name, key, field in (
            ("translation_review", "translated_copy", "review_sha256"),
            ("rendered_copy", "rendered_copy", "tree_sha256"),
            ("release_copy", "release_copy", "tree_sha256"),
        )
        if (meta.get(key) or {}).get(field)
    }
    next_step = _next_step(meta, debate_id, work_id)
    if no_change_plan_sha256 and comparison_id:
        next_step = {
            "action": "close_workspace_from_signed_no_change_plan",
            "command": _command(
                "corpus-workspace-close", debate_id, work_id,
                "--comparison-id", comparison_id,
                "--confirm-no-change-plan-sha256", no_change_plan_sha256,
            ),
            "remote_read_possible": False,
            "remote_write_possible": False,
            "note": "Le plan signé de portée all ne contient que des skip ; la clôture reste locale.",
        }
    return {
        "schema": "wikidebia-compact-workspace-status-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": status,
        "phase": _phase(status),
        "workspace_sha256": meta.get("workspace_sha256"),
        "artifact_hashes": artifact_hashes,
        **({"remote": remote} if remote is not None else {}),
        "next_action": next_step["action"],
        "next_command": next_step["command"],
        "next_remote_read_possible": next_step["remote_read_possible"],
        "next_remote_write_possible": next_step["remote_write_possible"],
        **({"note": next_step["note"]} if next_step.get("note") else {}),
        "status_check_remote_access": False,
        "status_check_remote_write": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Afficher l’état compact vérifié d’un workspace et sa prochaine commande."
    )
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = summarize_workspace(args.project_root, args.debate_id, args.work_id)
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"État : {result['status']} ({result['phase']})")
        if result.get("remote"):
            print("Comparaison : " + str(result["remote"]["comparison_id"]))
            print("Compteurs : " + json.dumps(result["remote"]["counts"], ensure_ascii=False, sort_keys=True))
        print("Action suivante : " + str(result["next_action"]))
        print("Commande suivante : " + str(result["next_command"] or "aucune"))
        if result.get("note"):
            print("Note : " + str(result["note"]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (WorkspaceStatusError, RemotePlanReviewError, RenderError, WorkspaceError, CorpusBuildError) as exc:
        print(f"ÉTAT DU WORKSPACE BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
