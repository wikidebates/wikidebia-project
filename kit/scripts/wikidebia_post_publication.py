#!/usr/bin/env python3
"""Reconcile a signed final publication with its local editorial workspace.

The operation is local-only.  It validates the complete final-publication
identity, the release tree and the installed active corpus, then records a
signed, idempotent terminal state in ``workspace.json``.  It never reads or
writes a wiki.
"""
from __future__ import annotations

import argparse
import json
import os
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
from wikidebia_editorial_workspace import (
    WorkspaceError,
    validate_work_id,
    workspace_receipt_hash,
)
from wikidebia_render import RenderError, _load_workspace
from wikidebia_update import sha_object


WORKFLOW_SCHEMA = "wikidebia-editorial-orchestration-1.0"
FINAL_PUBLICATION_SCHEMA = "wikidebia-final-publication-receipt-1.0"
BASELINE_SCHEMA = "wikidebia-final-publication-baseline-1.0"
RECONCILIATION_SCHEMA = "wikidebia-post-publication-reconciliation-receipt-1.0"


class PostPublicationError(WorkspaceError):
    pass


def _regular_json(path: Path, label: str, project_root: Path) -> dict[str, Any]:
    try:
        path.resolve().relative_to(project_root)
    except ValueError as exc:
        raise PostPublicationError(f"{label} est extérieur au projet") from exc
    current = path.parent
    while current != project_root:
        if current.is_symlink():
            raise PostPublicationError(f"Parent symbolique interdit : {label}")
        if current.parent == current:
            raise PostPublicationError(f"Parent incontrôlable : {label}")
        current = current.parent
    if not path.is_file() or path.is_symlink():
        raise PostPublicationError(f"{label} absent ou non sûr")
    return load_json(path, label)


def _signed(
    path: Path, label: str, field: str, project_root: Path,
) -> dict[str, Any]:
    value = _regular_json(path, label, project_root)
    body = dict(value)
    claimed = body.pop(field, None)
    if not claimed or claimed != sha_object(body):
        raise PostPublicationError(f"Empreinte invalide : {label}")
    return value


def _publication_chain(
    project_root: Path,
    debate_id: str,
    work_id: str,
    workspace: Path,
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    workflow_path = project_root / ".state/workflows" / debate_id / "workflow.json"
    publication_path = (
        project_root / ".state/final-publication" / debate_id / work_id
        / "publication-receipt.json"
    )
    baseline_path = publication_path.with_name("baseline.json")
    workflow = _regular_json(workflow_path, "workflow publié", project_root)
    publication = _signed(
        publication_path, "reçu de publication finale", "receipt_sha256", project_root
    )
    baseline = _signed(
        baseline_path, "baseline de publication finale", "baseline_sha256", project_root
    )

    if (
        workflow.get("schema") != WORKFLOW_SCHEMA
        or workflow.get("debate_id") != debate_id
        or workflow.get("work_id") != work_id
        or workflow.get("phase") != "published"
        or workflow.get("status") != "published"
        or workflow.get("final_publication") != publication
    ):
        raise PostPublicationError("Le workflow ne scelle pas cette publication finale")
    if (
        publication.get("schema") != FINAL_PUBLICATION_SCHEMA
        or publication.get("schema_version") != "1.0"
        or publication.get("debate_id") != debate_id
        or publication.get("work_id") != work_id
        or publication.get("status") != "published"
    ):
        raise PostPublicationError("Identité du reçu de publication finale divergente")
    if (
        baseline.get("schema") != BASELINE_SCHEMA
        or baseline.get("schema_version") != "1.0"
        or baseline.get("debate_id") != debate_id
        or baseline.get("work_id") != work_id
        or publication.get("baseline_sha256") != baseline.get("baseline_sha256")
    ):
        raise PostPublicationError("Baseline finale absente, invalide ou divergente")

    expected_tree = str((meta.get("release_copy") or {}).get("tree_sha256") or "")
    release_copy = workspace / "release-copy"
    baseline_tree = str((baseline.get("release") or {}).get("release_copy_tree_sha256") or "")
    installed = publication.get("installed_release") or {}
    installed_tree = str(installed.get("tree_sha256") or "")
    installed_path = str(installed.get("path") or "")
    expected_installed_path = f"corpus/{debate_id}"
    if (
        not expected_tree
        or baseline_tree != expected_tree
        or installed_tree != expected_tree
        or installed_path != expected_installed_path
        or not release_copy.is_dir()
        or release_copy.is_symlink()
        or full_tree_sha256(release_copy) != expected_tree
    ):
        raise PostPublicationError("La release locale ne correspond pas à la publication finale")
    active = project_root / installed_path
    if (
        not active.is_dir()
        or active.is_symlink()
        or full_tree_sha256(active) != expected_tree
    ):
        raise PostPublicationError("Le corpus actif installé diverge de la release publiée")
    assert_no_symlinks(active)
    return {
        "workflow_path": workflow_path,
        "publication_path": publication_path,
        "publication": publication,
        "baseline": baseline,
        "release_tree_sha256": expected_tree,
        "installed_path": installed_path,
    }


def _desired_workspace(
    meta: Mapping[str, Any], chain: Mapping[str, Any], reconciled_at: str,
) -> dict[str, Any]:
    publication = chain["publication"]
    desired = dict(meta)
    desired["status"] = "published"
    desired["final_publication"] = {
        "status": "published",
        "reconciled_at": reconciled_at,
        "receipt_path": chain["publication_path"],
        "receipt_sha256": publication.get("receipt_sha256"),
        "baseline_sha256": publication.get("baseline_sha256"),
        "installed_corpus_path": chain["installed_path"],
        "installed_corpus_tree_sha256": chain["release_tree_sha256"],
        "remote_access_performed_during_reconciliation": False,
        "remote_write_performed_during_reconciliation": False,
    }
    # Store only a project-relative path in the portable workspace receipt.
    desired["final_publication"]["receipt_path"] = relative_to_project(
        Path(str(chain["publication_path"])), Path(str(chain["project_root"]))
    )
    desired["workspace_sha256"] = None
    desired["workspace_sha256"] = workspace_receipt_hash(desired)
    return desired


def reconcile_published_workspace(
    project_root: Path, debate_id: str, work_id: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if meta.get("status") not in {"release_ready", "published"}:
        raise PostPublicationError(
            f"Statut incompatible avec la réconciliation : {meta.get('status')}"
        )
    chain = _publication_chain(project_root, debate_id, work_id, workspace, meta)
    chain["project_root"] = project_root
    state = assert_control_directory(project_root / ".state", project_root)
    post_root = assert_control_directory(state / "post-publication", project_root, create=True)
    debate_root = assert_control_directory(post_root / debate_id, project_root, create=True)
    work_root = assert_control_directory(debate_root / work_id, project_root, create=True)
    receipt_path = work_root / "reconciliation-receipt.json"
    existing: dict[str, Any] | None = None
    if receipt_path.exists() or receipt_path.is_symlink():
        existing = _signed(
            receipt_path, "reçu de réconciliation post-publication", "receipt_sha256",
            project_root,
        )
        if (
            existing.get("schema") != RECONCILIATION_SCHEMA
            or existing.get("debate_id") != debate_id
            or existing.get("work_id") != work_id
            or existing.get("publication_receipt_sha256")
            != chain["publication"].get("receipt_sha256")
            or existing.get("baseline_sha256")
            != chain["publication"].get("baseline_sha256")
            or existing.get("release_copy_tree_sha256") != chain["release_tree_sha256"]
            or existing.get("installed_corpus_tree_sha256") != chain["release_tree_sha256"]
        ):
            raise PostPublicationError("Reçu de réconciliation existant divergent")

    if meta.get("status") == "published":
        if existing is None or meta.get("workspace_sha256") != existing.get("workspace_sha256"):
            raise PostPublicationError("Workspace publié sans reçu de réconciliation correspondant")
        desired = _desired_workspace(meta, chain, str(existing.get("reconciled_at") or ""))
        if desired != meta:
            raise PostPublicationError("État terminal publié divergent du reçu local")
        return {
            "status": "published",
            "reconciliation": "reused",
            "debate_id": debate_id,
            "work_id": work_id,
            "receipt_path": relative_to_project(receipt_path, project_root),
            "receipt_sha256": existing.get("receipt_sha256"),
            "workspace_sha256": meta.get("workspace_sha256"),
            "remote_access_performed": False,
            "remote_write_performed": False,
        }

    previous_workspace_sha = str(meta.get("workspace_sha256") or "")
    if existing is not None:
        if existing.get("previous_workspace_sha256") != previous_workspace_sha:
            raise PostPublicationError("Le workspace a changé depuis le reçu de réconciliation")
        reconciled_at = str(existing.get("reconciled_at") or "")
    else:
        reconciled_at = now_iso()
    desired = _desired_workspace(meta, chain, reconciled_at)
    if existing is None:
        receipt = {
            "schema": RECONCILIATION_SCHEMA,
            "schema_version": "1.0",
            "debate_id": debate_id,
            "work_id": work_id,
            "status": "published",
            "reconciled_at": reconciled_at,
            "previous_workspace_sha256": previous_workspace_sha,
            "workspace_sha256": desired["workspace_sha256"],
            "publication_receipt_path": relative_to_project(
                chain["publication_path"], project_root
            ),
            "publication_receipt_sha256": chain["publication"].get("receipt_sha256"),
            "baseline_sha256": chain["publication"].get("baseline_sha256"),
            "release_copy_tree_sha256": chain["release_tree_sha256"],
            "installed_corpus_tree_sha256": chain["release_tree_sha256"],
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
        receipt["receipt_sha256"] = sha_object(receipt)
        write_json(receipt_path, receipt)
    else:
        receipt = existing
        if existing.get("workspace_sha256") != desired.get("workspace_sha256"):
            raise PostPublicationError("Le reçu interrompu vise un autre état terminal")
    write_json(workspace / "workspace.json", desired)
    return {
        "status": "published",
        "reconciliation": "completed" if existing is None else "resumed",
        "debate_id": debate_id,
        "work_id": work_id,
        "receipt_path": relative_to_project(receipt_path, project_root),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "workspace_sha256": desired.get("workspace_sha256"),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    with exclusive_lock(project_root, args.debate_id, "post-publication"):
        result = reconcile_published_workspace(
            project_root, args.debate_id, args.work_id
        )
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.machine_readable
        else json.dumps(result, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PostPublicationError, RenderError, WorkspaceError, CorpusBuildError) as exc:
        print(f"RÉCONCILIATION POST-PUBLICATION BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
