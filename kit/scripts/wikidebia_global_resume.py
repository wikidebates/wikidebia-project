#!/usr/bin/env python3
"""Discover active editorial work and write a signed global resume registry."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    CorpusBuildError,
    canonical_json,
    load_json,
    now_iso,
    relative_to_project,
    sha256_bytes,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_update import sha_object
from wikidebia_workspace_status import WorkspaceStatusError, summarize_workspace


class GlobalResumeError(WorkspaceError):
    pass


REGISTRY_SCHEMA = "wikidebia-global-resume-registry-1.0"
EVENT_SCHEMA = "wikidebia-global-resume-event-1.0"
WORKFLOW_SCHEMA = "wikidebia-editorial-orchestration-1.0"
FINAL_PUBLICATION_SCHEMA = "wikidebia-final-publication-receipt-1.0"


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _translation_resume(
    workspace: Path, summary: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    if summary.get("phase") != "english_translation":
        return None, None
    capsule_path = workspace / "audits/translation-resume.json"
    review_path = workspace / "reviews/en/translation_review.json"
    if not capsule_path.is_file():
        return None, None
    try:
        capsule = load_json(capsule_path, "capsule de reprise")
        review = load_json(review_path, "revue anglaise")
    except (CorpusBuildError, OSError, ValueError, KeyError) as exc:
        return None, type(exc).__name__
    if (
        capsule.get("schema") != "wikidebia-translation-resume-capsule-1.0"
        or not _signed(capsule, "capsule_sha256")
        or capsule.get("debate_id") != summary.get("debate_id")
        or capsule.get("work_id") != summary.get("work_id")
        or capsule.get("workspace_sha256") != summary.get("workspace_sha256")
        or capsule.get("review_content_sha256") != sha256_bytes(canonical_json(review))
    ):
        return None, "stale_or_invalid_translation_capsule"
    return capsule, None


def _published_receipt(
    project_root: Path, debate_id: str, work_id: str,
) -> tuple[dict[str, Any], Path] | None:
    """Return matching final evidence when the high-level workflow is published."""
    workflow_path = project_root / ".state/workflows" / debate_id / "workflow.json"
    receipt_path = (
        project_root / ".state/final-publication" / debate_id / work_id
        / "publication-receipt.json"
    )
    if (
        not workflow_path.is_file() or workflow_path.is_symlink()
        or not receipt_path.is_file() or receipt_path.is_symlink()
    ):
        return None
    try:
        workflow = load_json(workflow_path, "workflow publié")
        receipt = load_json(receipt_path, "reçu de publication finale")
    except (CorpusBuildError, OSError, ValueError, KeyError):
        return None
    embedded = workflow.get("final_publication")
    if (
        workflow.get("schema") != WORKFLOW_SCHEMA
        or workflow.get("debate_id") != debate_id
        or workflow.get("work_id") != work_id
        or workflow.get("phase") != "published"
        or workflow.get("status") != "published"
        or not isinstance(embedded, dict)
        or embedded != receipt
        or receipt.get("schema") != FINAL_PUBLICATION_SCHEMA
        or receipt.get("schema_version") != "1.0"
        or receipt.get("debate_id") != debate_id
        or receipt.get("work_id") != work_id
        or receipt.get("status") != "published"
        or not _signed(receipt, "receipt_sha256")
    ):
        return None
    return receipt, receipt_path


def _workspace_entry(
    project_root: Path, workspace_json: Path,
) -> dict[str, Any]:
    debate_id = validate_debate_id(workspace_json.parent.parent.name)
    work_id = validate_work_id(workspace_json.parent.name)
    try:
        summary = summarize_workspace(project_root, debate_id, work_id)
    except Exception as exc:
        if not isinstance(exc, (WorkspaceError, CorpusBuildError, OSError, ValueError, KeyError)):
            raise
        return {
            "debate_id": debate_id,
            "work_id": work_id,
            "workspace_path": relative_to_project(workspace_json.parent, project_root),
            "status": "invalid",
            "phase": "unknown",
            "active": True,
            "next_action": "repair_workspace_state",
            "next_command": None,
            "error_type": type(exc).__name__,
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
    publication = _published_receipt(project_root, debate_id, work_id)
    if publication is not None:
        receipt, receipt_path = publication
        return {
            "debate_id": debate_id,
            "work_id": work_id,
            "workspace_path": relative_to_project(workspace_json.parent, project_root),
            "workspace_sha256": summary.get("workspace_sha256"),
            "status": "published",
            "phase": "complete",
            "active": False,
            "next_action": "complete",
            "next_command": None,
            "publication_receipt_path": relative_to_project(receipt_path, project_root),
            "publication_receipt_sha256": receipt.get("receipt_sha256"),
            "next_remote_read_possible": False,
            "next_remote_write_possible": False,
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
    capsule, warning = _translation_resume(workspace_json.parent, summary)
    next_action = summary.get("next_action")
    next_command = summary.get("next_command")
    extra: dict[str, Any] = {}
    if capsule is not None:
        next_action = capsule.get("next_action")
        next_command = capsule.get("next_command")
        extra = {
            "active_unit_id": capsule.get("active_unit_id"),
            "translation_capsule_path": relative_to_project(
                workspace_json.parent / "audits/translation-resume.json", project_root,
            ),
            "translation_capsule_sha256": capsule.get("capsule_sha256"),
            **({"edit_path": capsule["edit_path"]} if capsule.get("edit_path") else {}),
        }
    return {
        "debate_id": debate_id,
        "work_id": work_id,
        "workspace_path": relative_to_project(workspace_json.parent, project_root),
        "workspace_sha256": summary.get("workspace_sha256"),
        "status": summary.get("status"),
        "phase": summary.get("phase"),
        "active": summary.get("status") != "work_closed",
        "next_action": next_action,
        "next_command": next_command,
        "next_remote_read_possible": summary.get("next_remote_read_possible", False),
        "next_remote_write_possible": summary.get("next_remote_write_possible", False),
        **extra,
        **({"resume_warning": warning} if warning else {}),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def _discover_workspace_entries(
    project_root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    workspaces_root = project_root / ".state/editorial-workspaces"
    entries: list[dict[str, Any]] = []
    ignored: list[dict[str, str]] = []
    for path in sorted(workspaces_root.glob("*/*/workspace.json")):
        relative = relative_to_project(path.parent, project_root)
        if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():
            ignored.append({"workspace_path": relative, "reason": "unsafe_symlink"})
            continue
        try:
            entries.append(_workspace_entry(project_root, path))
        except (WorkspaceError, CorpusBuildError, ValueError, KeyError):
            # Import and transaction backups deliberately live beside the
            # canonical Work in historical repositories. They are evidence,
            # not resumable identities, and must not block every valid Work.
            ignored.append({"workspace_path": relative, "reason": "invalid_identity"})
    return entries, ignored


def _load_events(events_dir: Path) -> tuple[list[dict[str, Any]], int]:
    valid: list[dict[str, Any]] = []
    invalid = 0
    if not events_dir.is_dir():
        return valid, invalid
    for path in sorted(events_dir.glob("*.json")):
        if path.is_symlink():
            invalid += 1
            continue
        try:
            event = load_json(path, "événement de reprise")
        except (CorpusBuildError, OSError, ValueError):
            invalid += 1
            continue
        if (
            event.get("schema") != EVENT_SCHEMA
            or not _signed(event, "event_sha256")
            or path.stem != event.get("event_sha256")
        ):
            invalid += 1
            continue
        valid.append(event)
    valid.sort(key=lambda row: (str(row.get("recorded_at") or ""), str(row["event_sha256"])))
    return valid, invalid


def _record_events(
    project_root: Path, entries: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    events_dir = project_root / ".state/resume/events"
    events, invalid = _load_events(events_dir)
    known = {
        (str(row.get("debate_id")), str(row.get("work_id")), str(row.get("state_key")))
        for row in events
    }
    for entry in entries:
        state_key = sha_object(dict(entry))
        identity = (str(entry["debate_id"]), str(entry["work_id"]), state_key)
        if identity in known:
            continue
        event: dict[str, Any] = {
            "schema": EVENT_SCHEMA,
            "debate_id": entry["debate_id"],
            "work_id": entry["work_id"],
            "state_key": state_key,
            "state": dict(entry),
            "recorded_at": now_iso(),
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
        event["event_sha256"] = sha_object(event)
        write_json(events_dir / f"{event['event_sha256']}.json", event)
        events.append(event)
        known.add(identity)
    events.sort(key=lambda row: (str(row.get("recorded_at") or ""), str(row["event_sha256"])))
    return events, invalid


def discover_resume(
    project_root: Path,
    *,
    debate_id: str | None = None,
    work_id: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    if debate_id is not None:
        debate_id = validate_debate_id(debate_id)
    if work_id is not None:
        work_id = validate_work_id(work_id)
    entries, ignored_workspaces = _discover_workspace_entries(project_root)
    events, invalid_events = _record_events(project_root, entries)
    active = [row for row in entries if row.get("active") is True]
    registry: dict[str, Any] = {
        "schema": REGISTRY_SCHEMA,
        "active_works": active,
        "active_count": len(active),
        "journal": [
            {
                "event_sha256": row["event_sha256"],
                "debate_id": row["debate_id"],
                "work_id": row["work_id"],
                "state_key": row["state_key"],
                "recorded_at": row["recorded_at"],
            }
            for row in events
        ],
        "journal_event_count": len(events),
        "ignored_invalid_event_count": invalid_events,
        "ignored_workspace_count": len(ignored_workspaces),
        "ignored_workspaces": ignored_workspaces,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    registry["registry_sha256"] = sha_object(registry)
    registry_path = project_root / ".state/resume/registry.json"
    write_json(registry_path, registry)

    matches = [
        row for row in active
        if (debate_id is None or row["debate_id"] == debate_id)
        and (work_id is None or row["work_id"] == work_id)
    ]
    selected = matches[0] if len(matches) == 1 else None
    status = "ready" if selected else ("no_active_work" if not matches else "multiple_active_works")
    choices = [
        {
            "debate_id": row["debate_id"],
            "work_id": row["work_id"],
            "status": row["status"],
            "phase": row["phase"],
            "resume_command": (
                f"./wikidebia resume --debate-id {row['debate_id']} --work-id {row['work_id']}"
            ),
        }
        for row in matches
    ]
    return {
        "schema": "wikidebia-global-resume-result-1.0",
        "status": status,
        "active_count": len(active),
        "matching_count": len(matches),
        **({"selected": selected} if selected else {"choices": choices}),
        "registry_path": relative_to_project(registry_path, project_root),
        "registry_sha256": registry["registry_sha256"],
        "journal_event_count": len(events),
        "ignored_invalid_event_count": invalid_events,
        "ignored_workspace_count": len(ignored_workspaces),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debate-id")
    parser.add_argument("--work-id")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = discover_resume(
        args.project_root, debate_id=args.debate_id, work_id=args.work_id,
    )
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    elif result.get("selected"):
        selected = result["selected"]
        print(f"Débat : {selected['debate_id']}")
        print(f"Work : {selected['work_id']}")
        print(f"État : {selected['status']} ({selected['phase']})")
        print("Action suivante : " + str(selected.get("next_action") or "aucune"))
        print("Commande suivante : " + str(selected.get("next_command") or "aucune"))
        if selected.get("edit_path"):
            print("Fichier à modifier : " + str(selected["edit_path"]))
    else:
        print(f"État : {result['status']}")
        for row in result.get("choices") or []:
            print(f"- {row['debate_id']} / {row['work_id']} : {row['resume_command']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        GlobalResumeError, WorkspaceStatusError, WorkspaceError, CorpusBuildError,
        OSError, ValueError, KeyError,
    ) as exc:
        print(f"REPRISE GLOBALE BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
