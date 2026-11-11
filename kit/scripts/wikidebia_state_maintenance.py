#!/usr/bin/env python3
"""Audit local state storage and delete only exact, signed stale-backup plans.

The default mode is read-only.  Destructive cleanup requires a previously
written plan plus its exact SHA-256 confirmation.  No wiki access is performed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    CorpusBuildError,
    assert_control_directory,
    assert_no_symlinks,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, fsync_directory, validate_work_id
from wikidebia_render import RenderError, _load_workspace
from wikidebia_update import sha_object


PLAN_SCHEMA = "wikidebia-state-maintenance-plan-1.0"
RECEIPT_SCHEMA = "wikidebia-state-maintenance-receipt-1.0"
POST_PUBLICATION_SCHEMA = "wikidebia-post-publication-reconciliation-receipt-1.0"
BACKUP_RE = re.compile(
    r"^(?P<work>[A-Z0-9][A-Z0-9_-]{2,63})\.review-import-backup-(?P<suffix>[0-9a-f]{8})$"
)


class StateMaintenanceError(WorkspaceError):
    pass


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _tree_usage(root: Path) -> dict[str, int]:
    assert_no_symlinks(root)
    logical = 0
    allocated = 0
    files = 0
    seen_inodes: set[tuple[int, int]] = set()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stat = path.stat()
        files += 1
        logical += stat.st_size
        identity = (stat.st_dev, stat.st_ino)
        if identity not in seen_inodes:
            allocated += stat.st_blocks * 512
            seen_inodes.add(identity)
    return {
        "file_count": files,
        "logical_bytes": logical,
        "allocated_bytes_unique_inodes": allocated,
        "unique_inode_count": len(seen_inodes),
    }


def _state_usage(state: Path) -> dict[str, Any]:
    logical = 0
    allocated = 0
    files = 0
    unsafe = 0
    seen_inodes: set[tuple[int, int]] = set()
    categories: dict[str, dict[str, int]] = {}
    if not state.is_dir() or state.is_symlink():
        raise StateMaintenanceError("Racine .state absente ou non sûre")
    for path in sorted(state.rglob("*")):
        try:
            relative = path.relative_to(state)
            if path.is_symlink():
                unsafe += 1
                continue
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            unsafe += 1
            continue
        category = relative.parts[0] if relative.parts else "."
        row = categories.setdefault(category, {
            "file_count": 0,
            "logical_bytes": 0,
            "allocated_bytes_unique_inodes": 0,
        })
        files += 1
        logical += stat.st_size
        row["file_count"] += 1
        row["logical_bytes"] += stat.st_size
        identity = (stat.st_dev, stat.st_ino)
        if identity not in seen_inodes:
            blocks = stat.st_blocks * 512
            allocated += blocks
            row["allocated_bytes_unique_inodes"] += blocks
            seen_inodes.add(identity)
    filesystem = os.statvfs(state)
    return {
        "file_count": files,
        "logical_bytes": logical,
        "allocated_bytes_unique_inodes": allocated,
        "unique_inode_count": len(seen_inodes),
        "unsafe_path_count": unsafe,
        "filesystem": {
            "fragment_size": filesystem.f_frsize,
            "total_bytes": filesystem.f_blocks * filesystem.f_frsize,
            "available_bytes": filesystem.f_bavail * filesystem.f_frsize,
        },
        "categories": [
            {"name": name, **row} for name, row in sorted(categories.items())
        ],
        "measurement_limitations": [
            "allocated_bytes_unique_inodes repose sur st_blocks et ne déduplique pas les extents reflink partagés",
            "available_bytes porte sur tout le système de fichiers et peut varier avec les autres processus",
        ],
    }


def _terminal_publication(
    project_root: Path, debate_id: str, work_id: str,
) -> dict[str, Any]:
    _, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") != "published":
        raise StateMaintenanceError("workspace canonique non terminal")
    path = (
        project_root / ".state/post-publication" / debate_id / work_id
        / "reconciliation-receipt.json"
    )
    if not path.is_file() or path.is_symlink():
        raise StateMaintenanceError("reçu post-publication absent")
    receipt = load_json(path, "reçu post-publication")
    if (
        receipt.get("schema") != POST_PUBLICATION_SCHEMA
        or receipt.get("debate_id") != debate_id
        or receipt.get("work_id") != work_id
        or receipt.get("status") != "published"
        or receipt.get("workspace_sha256") != meta.get("workspace_sha256")
        or not _signed(receipt, "receipt_sha256")
    ):
        raise StateMaintenanceError("reçu post-publication divergent")
    return receipt


def build_plan(project_root: Path) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    state = project_root / ".state"
    usage = _state_usage(state)
    root = state / "editorial-workspaces"
    candidates: list[dict[str, Any]] = []
    blocked: list[dict[str, str]] = []
    if root.is_dir() and not root.is_symlink():
        for path in sorted(root.glob("*/*.review-import-backup-*")):
            relative = relative_to_project(path, project_root)
            match = BACKUP_RE.fullmatch(path.name)
            if not match or path.is_symlink() or not path.is_dir():
                blocked.append({"path": relative, "reason": "invalid_or_unsafe_identity"})
                continue
            try:
                debate_id = validate_debate_id(path.parent.name)
                work_id = validate_work_id(match.group("work"))
                publication = _terminal_publication(project_root, debate_id, work_id)
                metrics = _tree_usage(path)
                tree_sha = full_tree_sha256(path)
            except (CorpusBuildError, WorkspaceError, RenderError, OSError, ValueError):
                blocked.append({"path": relative, "reason": "terminal_proof_or_tree_invalid"})
                continue
            candidates.append({
                "path": relative,
                "debate_id": debate_id,
                "work_id": work_id,
                "backup_suffix": match.group("suffix"),
                "tree_sha256": tree_sha,
                "publication_reconciliation_sha256": publication.get("receipt_sha256"),
                **metrics,
            })
    plan: dict[str, Any] = {
        "schema": PLAN_SCHEMA,
        "schema_version": "1.0",
        "created_at": now_iso(),
        "mode": "dry_run",
        "state_usage": usage,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "blocked_count": len(blocked),
        "blocked": blocked,
        "reclaimable_logical_bytes": sum(row["logical_bytes"] for row in candidates),
        "reclaimable_allocated_bytes": sum(
            row["allocated_bytes_unique_inodes"] for row in candidates
        ),
        "requires_exact_plan_confirmation": True,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    plan["plan_sha256"] = sha_object(plan)
    return plan


def _validate_plan(plan: Mapping[str, Any], confirmation: str) -> None:
    if (
        plan.get("schema") != PLAN_SCHEMA
        or plan.get("schema_version") != "1.0"
        or not _signed(plan, "plan_sha256")
        or confirmation != plan.get("plan_sha256")
    ):
        raise StateMaintenanceError("Plan absent, altéré ou confirmation divergente")


def apply_plan(
    project_root: Path, plan_path: Path, confirmation: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    plan_path = plan_path.expanduser().resolve()
    try:
        plan_path.relative_to(project_root)
    except ValueError as exc:
        raise StateMaintenanceError("Le plan doit être conservé dans le projet") from exc
    if not plan_path.is_file() or plan_path.is_symlink():
        raise StateMaintenanceError("Plan de maintenance absent ou non sûr")
    plan = load_json(plan_path, "plan de maintenance")
    _validate_plan(plan, confirmation)
    state = assert_control_directory(project_root / ".state", project_root)
    receipts = assert_control_directory(state / "state-maintenance", project_root, create=True)
    run_root = assert_control_directory(
        receipts / str(plan["plan_sha256"]), project_root, create=True
    )
    receipt_path = run_root / "deletion-receipt.json"
    if receipt_path.is_file() and not receipt_path.is_symlink():
        receipt = load_json(receipt_path, "reçu de maintenance")
        if (
            receipt.get("schema") == RECEIPT_SCHEMA
            and receipt.get("plan_sha256") == plan.get("plan_sha256")
            and _signed(receipt, "receipt_sha256")
        ):
            return dict(receipt)
        raise StateMaintenanceError("Reçu de maintenance existant invalide")

    quarantine = assert_control_directory(run_root / "quarantine", project_root, create=True)
    deleted: list[dict[str, Any]] = []
    for index, row in enumerate(plan.get("candidates") or [], 1):
        if not isinstance(row, dict):
            raise StateMaintenanceError("Candidat de maintenance invalide")
        debate_id = validate_debate_id(str(row.get("debate_id") or ""))
        work_id = validate_work_id(str(row.get("work_id") or ""))
        suffix = str(row.get("backup_suffix") or "")
        if not re.fullmatch(r"[0-9a-f]{8}", suffix):
            raise StateMaintenanceError("Suffixe de sauvegarde invalide")
        expected = (
            project_root / ".state/editorial-workspaces" / debate_id
            / f"{work_id}.review-import-backup-{suffix}"
        )
        if relative_to_project(expected, project_root) != row.get("path"):
            raise StateMaintenanceError("Chemin candidat divergent")
        publication = _terminal_publication(project_root, debate_id, work_id)
        if publication.get("receipt_sha256") != row.get("publication_reconciliation_sha256"):
            raise StateMaintenanceError("Preuve terminale modifiée depuis le plan")
        staged = quarantine / f"{index:04d}-{debate_id}-{work_id}-{suffix}"
        item_path = run_root / "items" / f"{index:04d}.json"
        item: dict[str, Any] | None = None
        if item_path.is_file() and not item_path.is_symlink():
            item = load_json(item_path, "checkpoint de suppression")
            if (
                item.get("schema") != "wikidebia-state-maintenance-item-1.0"
                or item.get("plan_sha256") != plan.get("plan_sha256")
                or item.get("path") != row.get("path")
                or item.get("tree_sha256") != row.get("tree_sha256")
                or item.get("status") not in {"quarantined", "deleted"}
                or not _signed(item, "checkpoint_sha256")
            ):
                raise StateMaintenanceError("Checkpoint de suppression divergent")
        elif item_path.exists() or item_path.is_symlink():
            raise StateMaintenanceError("Checkpoint de suppression non sûr")
        if expected.exists() or expected.is_symlink():
            if item is not None:
                raise StateMaintenanceError("Sauvegarde réapparue après son checkpoint")
            if expected.is_symlink() or not expected.is_dir():
                raise StateMaintenanceError("Sauvegarde candidate devenue non sûre")
            metrics = _tree_usage(expected)
            if (
                full_tree_sha256(expected) != row.get("tree_sha256")
                or any(metrics.get(key) != row.get(key) for key in metrics)
            ):
                raise StateMaintenanceError("Sauvegarde candidate modifiée depuis le plan")
            os.replace(expected, staged)
            fsync_directory(expected.parent)
        if staged.is_dir() and not staged.is_symlink():
            if full_tree_sha256(staged) != row.get("tree_sha256"):
                raise StateMaintenanceError("Quarantaine divergente du plan")
            if item is None:
                item = {
                    "schema": "wikidebia-state-maintenance-item-1.0",
                    "plan_sha256": plan.get("plan_sha256"),
                    "path": row.get("path"),
                    "tree_sha256": row.get("tree_sha256"),
                    "status": "quarantined",
                }
                item["checkpoint_sha256"] = sha_object(item)
                write_json(item_path, item)
            shutil.rmtree(staged)
        elif staged.exists() or staged.is_symlink():
            raise StateMaintenanceError("Quarantaine devenue non sûre")
        elif item is None:
            raise StateMaintenanceError("Sauvegarde candidate absente avant suppression")
        if item.get("status") != "deleted":
            item = {
                "schema": "wikidebia-state-maintenance-item-1.0",
                "plan_sha256": plan.get("plan_sha256"),
                "path": row.get("path"),
                "tree_sha256": row.get("tree_sha256"),
                "status": "deleted",
            }
            item["checkpoint_sha256"] = sha_object(item)
            write_json(item_path, item)
        deleted.append({
            "path": row["path"],
            "tree_sha256": row["tree_sha256"],
            "logical_bytes": row["logical_bytes"],
            "allocated_bytes_unique_inodes": row["allocated_bytes_unique_inodes"],
        })
    usage_after = _state_usage(state)
    before_usage = plan.get("state_usage") or {}
    before_filesystem = before_usage.get("filesystem") or {}
    after_filesystem = usage_after.get("filesystem") or {}
    receipt: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "schema_version": "1.0",
        "status": "completed",
        "completed_at": now_iso(),
        "plan_path": relative_to_project(plan_path, project_root),
        "plan_sha256": plan.get("plan_sha256"),
        "deleted_count": len(deleted),
        "deleted": deleted,
        "reclaimed_logical_bytes": sum(row["logical_bytes"] for row in deleted),
        "reclaimed_allocated_bytes_estimate": sum(
            row["allocated_bytes_unique_inodes"] for row in deleted
        ),
        "state_usage_after": usage_after,
        "allocated_bytes_delta_since_plan": (
            int(before_usage.get("allocated_bytes_unique_inodes") or 0)
            - int(usage_after.get("allocated_bytes_unique_inodes") or 0)
        ),
        "filesystem_available_bytes_delta_since_plan": (
            int(after_filesystem.get("available_bytes") or 0)
            - int(before_filesystem.get("available_bytes") or 0)
        ),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    write_json(receipt_path, receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply-plan", type=Path)
    parser.add_argument("--confirm-plan-sha256")
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    if bool(args.apply_plan) != bool(args.confirm_plan_sha256):
        raise StateMaintenanceError(
            "--apply-plan et --confirm-plan-sha256 sont requis ensemble"
        )
    if args.apply_plan:
        plan_path = args.apply_plan if args.apply_plan.is_absolute() else project_root / args.apply_plan
        with exclusive_lock(project_root, "state_maintenance", "state-maintenance"):
            result = apply_plan(project_root, plan_path, args.confirm_plan_sha256)
    else:
        result = build_plan(project_root)
        if args.output:
            output = args.output if args.output.is_absolute() else project_root / args.output
            try:
                output.resolve().relative_to(project_root)
            except ValueError as exc:
                raise StateMaintenanceError("La sortie doit rester dans le projet") from exc
            write_json(output, result)
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.machine_readable
        else json.dumps(result, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (StateMaintenanceError, WorkspaceError, CorpusBuildError, OSError) as exc:
        print(f"MAINTENANCE D’ÉTAT BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
