#!/usr/bin/env python3
"""Write a compact signed capsule sufficient to resume English translation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    canonical_json,
    load_json,
    relative_to_project,
    sha256_bytes,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_render import _load_workspace
from wikidebia_update import sha_object


class TranslationResumeError(WorkspaceError):
    pass


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _signed_artifact(
    project_root: Path, path: Path, signature_field: str, *, required: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path.is_file():
        if required:
            raise TranslationResumeError(f"Artefact de reprise absent : {path.name}")
        return None, None
    value = load_json(path, f"artefact de reprise {path.name}")
    if not _signed(value, signature_field):
        raise TranslationResumeError(f"Signature invalide pour l’artefact de reprise : {path.name}")
    return value, {
        "path": relative_to_project(path, project_root),
        signature_field: value[signature_field],
    }


def write_resume_capsule(
    project_root: Path,
    debate_id: str,
    work_id: str,
    *,
    event: str = "status_check",
    unit_id: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")

    artifacts: dict[str, Any] = {}
    worklist, worklist_ref = _signed_artifact(
        project_root, workspace / "audits/en_translation_worklist.json", "worklist_sha256",
    )
    if worklist_ref:
        artifacts["worklist"] = worklist_ref
    selection, selection_ref = _signed_artifact(
        project_root, workspace / "audits/translation-next.json", "selection_sha256",
    )
    if selection_ref:
        artifacts["selection"] = selection_ref
    memory, memory_ref = _signed_artifact(
        project_root, workspace / "audits/translation-memory/reuse.json", "receipt_sha256",
    )
    if memory_ref:
        memory_ref["counts"] = memory.get("counts") or {}
        artifacts["memory_reuse"] = memory_ref

    active_unit = unit_id or str((selection or {}).get("unit_id") or "") or None
    packet = patch = application = None
    if active_unit:
        packet, packet_ref = _signed_artifact(
            project_root,
            workspace / f"audits/translation-packets/{active_unit}.json",
            "packet_sha256",
        )
        if packet_ref:
            packet_ref["counts"] = packet.get("counts") or {}
            artifacts["packet"] = packet_ref
        patch_path = workspace / f"reviews/en/unit-patches/{active_unit}.json"
        if patch_path.is_file():
            patch = load_json(patch_path, "correctif d’unité")
            patch_ref = {
                "path": relative_to_project(patch_path, project_root),
                "status": patch.get("status"),
                "base_packet_sha256": patch.get("base_packet_sha256"),
            }
            if patch.get("status") == "sealed":
                if not _signed(patch, "patch_sha256"):
                    raise TranslationResumeError("Signature du correctif scellé invalide")
                patch_ref["patch_sha256"] = patch["patch_sha256"]
            else:
                patch_ref["content_sha256"] = sha256_bytes(canonical_json(patch))
            artifacts["patch"] = patch_ref
        application, application_ref = _signed_artifact(
            project_root,
            workspace / f"audits/translation-patches/{active_unit}-application.json",
            "receipt_sha256",
        )
        if application_ref:
            application_ref["patch_sha256"] = application.get("patch_sha256")
            artifacts["application"] = application_ref

    next_action = "prepare_next_unit"
    next_command: str | None = (
        f"./wikidebia corpus-workspace-translation-next {debate_id} --work-id {work_id}"
    )
    edit_path: str | None = None
    if selection and selection.get("status") == "complete":
        next_action = "finalize_translation_review"
        next_command = selection.get("next_command")
    elif selection and selection.get("status") == "global_review_required":
        next_action = "complete_global_translation_review"
        next_command = None
    elif patch and patch.get("status") == "draft":
        next_action = "edit_translation_patch"
        next_command = None
        edit_path = artifacts["patch"]["path"]
    elif patch and patch.get("status") == "sealed":
        patch_sha256 = str(patch.get("patch_sha256") or "")
        if application and application.get("patch_sha256") == patch_sha256:
            next_action = "prepare_next_unit"
        else:
            next_action = "apply_translation_patch"
            next_command = (
                f"./wikidebia corpus-workspace-translation-patch {debate_id} "
                f"--work-id {work_id} --unit-id {active_unit} --apply "
                f"--confirm-patch-sha256 {patch_sha256}"
            )

    capsule: dict[str, Any] = {
        "schema": "wikidebia-translation-resume-capsule-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "event": event,
        "workspace_status": meta.get("status"),
        "workspace_sha256": meta.get("workspace_sha256"),
        "review_status": review.get("status"),
        "review_content_sha256": sha256_bytes(canonical_json(review)),
        "active_unit_id": active_unit,
        "artifacts": artifacts,
        "next_action": next_action,
        "next_command": next_command,
        **({"edit_path": edit_path} if edit_path else {}),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    capsule["capsule_sha256"] = sha_object(capsule)
    output = workspace / "audits/translation-resume.json"
    write_json(output, capsule)
    return {
        **capsule,
        "capsule_path": relative_to_project(output, project_root),
        "capsule_size_bytes": output.stat().st_size,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--event", default="status_check")
    parser.add_argument("--unit-id")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = write_resume_capsule(
        args.project_root, args.debate_id, args.work_id,
        event=args.event, unit_id=args.unit_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationResumeError, WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"CAPSULE DE REPRISE BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
