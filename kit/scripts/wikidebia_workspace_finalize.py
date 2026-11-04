#!/usr/bin/env python3
"""Resume the local finalization pipeline and its read-only remote comparison.

The command derives every confirmation hash from the verified workspace.  It
creates only the missing render and release stages, then either reuses the
latest signed comparison or refreshes it explicitly.  It never writes to a
wiki.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    CorpusBuildError,
    assert_no_symlinks,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    validate_debate_id,
)
from wikidebia_editorial_review import EditorialReviewError
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_release import ReleaseError, release_workspace
from wikidebia_remote_compare import (
    RemoteComparisonError,
    _verify_release,
    compare_workspace,
)
from wikidebia_remote_plan_review import RemotePlanReviewError, _load_comparison
from wikidebia_render import RenderError, _load_workspace, render_workspace


class WorkspaceFinalizeError(WorkspaceError):
    pass


def _translation_review(workspace: Path, meta: Mapping[str, Any]) -> str:
    translated = workspace / "translated-copy"
    if not translated.is_dir() or translated.is_symlink():
        raise WorkspaceFinalizeError("translated-copy absent ou non sûr")
    assert_no_symlinks(translated)
    expected_tree = str((meta.get("translated_copy") or {}).get("tree_sha256") or "")
    if not expected_tree or full_tree_sha256(translated) != expected_tree:
        raise WorkspaceFinalizeError("translated-copy a changé depuis son verrouillage")
    lock = load_json(translated / "data/en_translation_lock.json", "verrou de traduction")
    review_sha = str(lock.get("review_sha256") or "")
    recorded = str((meta.get("translated_copy") or {}).get("review_sha256") or "")
    if not review_sha or review_sha != recorded:
        raise WorkspaceFinalizeError("La revue verrouillée diverge de workspace.json")
    return review_sha


def _reuse_render(workspace: Path, meta: Mapping[str, Any], review_sha: str) -> dict[str, Any] | None:
    target = workspace / "rendered-copy"
    if not target.exists() and not target.is_symlink():
        return None
    if not target.is_dir() or target.is_symlink():
        raise WorkspaceFinalizeError("rendered-copy existe sous une forme non sûre")
    assert_no_symlinks(target)
    record = meta.get("rendered_copy") or {}
    expected = str(record.get("tree_sha256") or "")
    if not expected or full_tree_sha256(target) != expected:
        raise WorkspaceFinalizeError("rendered-copy a changé depuis le rendu")
    if record.get("translation_review_sha256") != review_sha:
        raise WorkspaceFinalizeError("rendered-copy ne correspond pas à la traduction verrouillée")
    lock = load_json(target / "data/bilingual_render_lock.json", "verrou de rendu")
    if lock.get("status") != "rendered_and_validated":
        raise WorkspaceFinalizeError("Le verrou de rendu n’atteste pas un rendu validé")
    return {"status": "reused", "tree_sha256": expected}


def _reuse_release(
    project_root: Path, debate_id: str, work_id: str, meta: Mapping[str, Any]
) -> dict[str, Any] | None:
    target = project_root / ".state/editorial-workspaces" / debate_id / work_id / "release-copy"
    if not target.exists() and not target.is_symlink():
        return None
    release_sha = str((meta.get("release_copy") or {}).get("tree_sha256") or "")
    if not release_sha:
        raise WorkspaceFinalizeError("release-copy existe sans empreinte enregistrée")
    _verify_release(project_root, debate_id, work_id, release_sha)
    return {"status": "reused", "tree_sha256": release_sha}


def _reuse_comparison(
    project_root: Path,
    debate_id: str,
    work_id: str,
    meta: Mapping[str, Any],
    *,
    scope: str,
    release_sha: str,
) -> dict[str, Any] | None:
    latest = meta.get("remote_comparison") or {}
    comparison_id = str(latest.get("comparison_id") or "")
    if not comparison_id:
        return None
    loaded = _load_comparison(project_root, debate_id, work_id, comparison_id)
    receipt = loaded["receipt"]
    if receipt.get("scope") != scope:
        return None
    if loaded.get("release_sha256") != release_sha:
        raise WorkspaceFinalizeError("La comparaison distante vise une autre release-copy")
    if latest.get("receipt_sha256") != receipt.get("receipt_sha256"):
        raise WorkspaceFinalizeError("Le workspace référence un autre reçu de comparaison")
    return {
        "status": "reused",
        "comparison_status": receipt.get("status"),
        "comparison_id": comparison_id,
        "plan": receipt.get("plan_path"),
        "plan_sha256": receipt.get("plan_sha256"),
        "counts": receipt.get("counts") or {},
        "receipt_sha256": receipt.get("receipt_sha256"),
        "remote_write_performed": False,
    }


def finalize_workspace(
    project_root: Path,
    debate_id: str,
    work_id: str,
    *,
    scope: str = "all",
    refresh_remote: bool = False,
    comparison_id: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    if scope not in {"all", "fr", "en"}:
        raise WorkspaceFinalizeError("scope doit être all, fr ou en")
    if comparison_id and not refresh_remote:
        raise WorkspaceFinalizeError("--comparison-id exige --refresh-remote")

    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    review_sha = _translation_review(workspace, meta)
    render_step = _reuse_render(workspace, meta, review_sha)
    if render_step is None:
        rendered = render_workspace(project_root, debate_id, work_id, review_sha)
        render_step = {
            "status": "created",
            "tree_sha256": rendered["rendered_copy_tree_sha256"],
        }

    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    release_step = _reuse_release(project_root, debate_id, work_id, meta)
    if release_step is None:
        released = release_workspace(
            project_root, debate_id, work_id, render_step["tree_sha256"]
        )
        release_step = {
            "status": "created",
            "tree_sha256": released["release_copy_tree_sha256"],
            "archive_sha256": released["archive_sha256"],
        }

    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    remote_step = None if refresh_remote else _reuse_comparison(
        project_root,
        debate_id,
        work_id,
        meta,
        scope=scope,
        release_sha=release_step["tree_sha256"],
    )
    if remote_step is None:
        compared = compare_workspace(
            project_root,
            debate_id,
            work_id,
            release_step["tree_sha256"],
            scope=scope,
            comparison_id=comparison_id,
        )
        remote_step = {
            "status": "created",
            "comparison_status": compared["status"],
            "comparison_id": compared["comparison_id"],
            "plan": compared["plan"],
            "plan_sha256": compared["plan_sha256"],
            "counts": compared["counts"],
            "remote_write_performed": False,
        }

    return {
        "status": remote_step["comparison_status"],
        "debate_id": debate_id,
        "work_id": work_id,
        "scope": scope,
        "steps": {
            "render": render_step,
            "release": release_step,
            "remote_compare": remote_step,
        },
        "remote_write_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reprendre le rendu, la release et la comparaison distante en lecture seule."
    )
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--scope", choices=("all", "fr", "en"), default="all")
    parser.add_argument(
        "--refresh-remote",
        action="store_true",
        help="Relire le wiki même si une comparaison signée compatible existe",
    )
    parser.add_argument(
        "--comparison-id",
        help="Identifiant de la nouvelle comparaison (avec --refresh-remote)",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    with exclusive_lock(project_root, args.debate_id, "workspace-finalize"):
        result = finalize_workspace(
            project_root,
            args.debate_id,
            args.work_id,
            scope=args.scope,
            refresh_remote=args.refresh_remote,
            comparison_id=args.comparison_id,
        )
    print(
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.machine_readable
        else json.dumps(result, ensure_ascii=False, indent=2)
    )
    return 0 if result["status"] == "plan_ready" else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        WorkspaceFinalizeError,
        RenderError,
        ReleaseError,
        RemoteComparisonError,
        RemotePlanReviewError,
        EditorialReviewError,
        WorkspaceError,
        CorpusBuildError,
    ) as exc:
        print(f"FINALISATION BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
