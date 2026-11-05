#!/usr/bin/env python3
"""Prepare only the next English translation unit and its editable patch."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Sequence

from wikidebia_corpus_build import relative_to_project, validate_debate_id, write_json
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_render import _load_workspace
from wikidebia_translation_packet import TranslationPacketError, build_packet
from wikidebia_translation_patch import TranslationPatchError, prepare_patch
from wikidebia_translation_worklist import TranslationWorklistError, build_worklist
from wikidebia_update import sha_object


class TranslationNextError(WorkspaceError):
    pass


def prepare_next_unit(
    project_root: Path,
    debate_id: str,
    work_id: str,
    *,
    memory_root: Path = Path("translation-memory"),
    reuse_memory: bool = True,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, _meta = _load_workspace(project_root, debate_id, work_id)
    initial = build_worklist(project_root, debate_id, work_id)
    units = initial.get("units") or []
    if not units:
        status = "complete" if initial.get("complete") else "global_review_required"
        result: dict[str, Any] = {
            "schema": "wikidebia-translation-next-unit-1.0",
            "status": status,
            "debate_id": debate_id,
            "work_id": work_id,
            "unit_id": None,
            "worklist_sha256": initial["worklist_sha256"],
            "worklist_path": initial["worklist_path"],
            "next_command": initial.get("next_command"),
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
    else:
        unit = units[0]
        unit_id = str(unit.get("unit_id") or "")
        if not unit_id or unit_id == "unassigned":
            raise TranslationNextError("La prochaine traduction n’est rattachée à aucune unité valide")
        packet = build_packet(
            project_root,
            debate_id,
            work_id,
            unit_id,
            reuse_memory=reuse_memory,
            memory_root=memory_root,
        )
        patch = prepare_patch(project_root, debate_id, work_id, unit_id)
        if patch.get("base_packet_sha256") != packet["packet_sha256"]:
            raise TranslationNextError(
                "Le correctif existant repose sur un ancien paquet ; conservez ses éditions "
                "puis régénérez-le explicitement avec --overwrite"
            )
        current = build_worklist(project_root, debate_id, work_id)
        result = {
            "schema": "wikidebia-translation-next-unit-1.0",
            "status": "unit_prepared",
            "debate_id": debate_id,
            "work_id": work_id,
            "unit_id": unit_id,
            "max_risk_level": unit.get("max_risk_level"),
            "worklist_sha256": current["worklist_sha256"],
            "worklist_path": current["worklist_path"],
            "packet_sha256": packet["packet_sha256"],
            "packet_path": packet["packet_path"],
            "patch_path": patch["patch_path"],
            "counts": packet["counts"],
            "next_action": "edit_translation_patch",
            "seal_command_template": (
                f"./wikidebia corpus-workspace-translation-patch {debate_id} "
                f"--work-id {work_id} --unit-id {unit_id} --seal "
                "--reviewer <identité> --unit-status approved --note <note>"
            ),
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
    result["selection_sha256"] = sha_object(result)
    output = workspace / "audits/translation-next.json"
    write_json(output, result)
    return {**result, "selection_path": relative_to_project(output, project_root)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--memory-root", type=Path, default=Path("translation-memory"))
    parser.add_argument("--no-memory", action="store_true")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = prepare_next_unit(
        args.project_root,
        args.debate_id,
        args.work_id,
        memory_root=args.memory_root,
        reuse_memory=not args.no_memory,
    )
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(f"État : {result['status']}")
        print("Unité : " + str(result.get("unit_id") or "aucune"))
        print("Paquet : " + str(result.get("packet_path") or "aucun"))
        print("Correctif : " + str(result.get("patch_path") or "aucun"))
        print("Action suivante : " + str(result.get("next_action") or result.get("next_command") or "aucune"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        TranslationNextError,
        TranslationWorklistError,
        TranslationPacketError,
        TranslationPatchError,
        WorkspaceError,
        OSError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"PROCHAINE UNITÉ BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
