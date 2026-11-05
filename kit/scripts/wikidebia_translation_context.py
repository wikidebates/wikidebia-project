#!/usr/bin/env python3
"""Build compact translation context references and record local byte savings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import canonical_json, load_json, relative_to_project, sha256_bytes, validate_debate_id, write_json
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_render import _load_workspace
from wikidebia_update import sha_object


class TranslationContextError(WorkspaceError):
    pass


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _load_signed(path: Path, field: str, label: str) -> dict[str, Any]:
    value = load_json(path, label)
    if not _signed(value, field):
        raise TranslationContextError(f"Empreinte invalide : {label}")
    return value


def _load_ledger(path: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema": "wikidebia-context-telemetry-1.0",
            "debate_id": debate_id,
            "work_id": work_id,
            "events": [],
            "totals": {
                "events": 0,
                "full_review_bytes": 0,
                "selected_context_bytes": 0,
                "avoided_context_bytes": 0,
            },
            "remote_access_performed": False,
            "remote_write_performed": False,
            "telemetry_sha256": None,
        }
    ledger = load_json(path, "télémétrie de contexte")
    if (
        ledger.get("schema") != "wikidebia-context-telemetry-1.0"
        or ledger.get("debate_id") != debate_id
        or ledger.get("work_id") != work_id
        or not _signed(ledger, "telemetry_sha256")
    ):
        raise TranslationContextError("Registre de télémétrie invalide")
    return ledger


def build_translation_context(
    project_root: Path,
    debate_id: str,
    work_id: str,
    unit_id: str,
    *,
    output_mode: str = "compact",
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    if output_mode not in {"compact", "full"}:
        raise TranslationContextError("output_mode doit être compact ou full")
    workspace, _meta = _load_workspace(project_root, debate_id, work_id)
    review_path = workspace / "reviews/en/translation_review.json"
    packet_path = workspace / f"audits/translation-packets/{unit_id}.json"
    patch_path = workspace / f"reviews/en/unit-patches/{unit_id}.json"
    capsule_path = workspace / "audits/translation-resume.json"
    for path, label in (
        (review_path, "revue anglaise"),
        (packet_path, "paquet d’unité"),
        (patch_path, "correctif d’unité"),
        (capsule_path, "capsule de reprise"),
    ):
        if not path.is_file():
            raise TranslationContextError(f"{label} absent : {path}")
    packet = _load_signed(packet_path, "packet_sha256", "paquet d’unité")
    capsule = _load_signed(capsule_path, "capsule_sha256", "capsule de reprise")
    patch = load_json(patch_path, "correctif d’unité")
    if patch.get("base_packet_sha256") != packet.get("packet_sha256"):
        raise TranslationContextError("Le correctif ne correspond pas au paquet courant")
    active = capsule.get("active_unit_id")
    if active not in {None, "", unit_id}:
        raise TranslationContextError("La capsule désigne une autre unité active")

    full_review_bytes = review_path.stat().st_size
    selected_context_bytes = sum(
        path.stat().st_size for path in (packet_path, patch_path, capsule_path)
    )
    avoided_context_bytes = max(0, full_review_bytes - selected_context_bytes)
    event: dict[str, Any] = {
        "unit_id": unit_id,
        "packet_sha256": packet["packet_sha256"],
        "patch_content_sha256": sha256_bytes(canonical_json(patch)),
        "capsule_sha256": capsule["capsule_sha256"],
        "full_review_bytes": full_review_bytes,
        "selected_context_bytes": selected_context_bytes,
        "avoided_context_bytes": avoided_context_bytes,
        "avoided_ratio": round(
            avoided_context_bytes / full_review_bytes, 6,
        ) if full_review_bytes else 0.0,
    }
    event["event_key"] = sha_object(event)

    ledger_path = project_root / ".state/context-telemetry" / debate_id / f"{work_id}.json"
    ledger = _load_ledger(ledger_path, debate_id, work_id)
    if event["event_key"] not in {str(row.get("event_key")) for row in ledger["events"]}:
        ledger["events"].append(event)
    ledger["totals"] = {
        "events": len(ledger["events"]),
        "full_review_bytes": sum(int(row["full_review_bytes"]) for row in ledger["events"]),
        "selected_context_bytes": sum(int(row["selected_context_bytes"]) for row in ledger["events"]),
        "avoided_context_bytes": sum(int(row["avoided_context_bytes"]) for row in ledger["events"]),
    }
    ledger["telemetry_sha256"] = None
    ledger["telemetry_sha256"] = sha_object({key: value for key, value in ledger.items() if key != "telemetry_sha256"})
    write_json(ledger_path, ledger)

    context: dict[str, Any] = {
        "schema": "wikidebia-translation-context-1.0",
        "mode": output_mode,
        "debate_id": debate_id,
        "work_id": work_id,
        "unit_id": unit_id,
        "artifacts": {
            "packet": {
                "path": relative_to_project(packet_path, project_root),
                "packet_sha256": packet["packet_sha256"],
            },
            "patch": {
                "path": relative_to_project(patch_path, project_root),
                "content_sha256": event["patch_content_sha256"],
            },
            "capsule": {
                "path": relative_to_project(capsule_path, project_root),
                "capsule_sha256": capsule["capsule_sha256"],
            },
        },
        "telemetry": event,
        "telemetry_ledger_sha256": ledger["telemetry_sha256"],
        **({"payload": {"packet": packet, "patch": patch}} if output_mode == "full" else {}),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    context["context_sha256"] = sha_object(context)
    output = workspace / "audits/translation-context" / f"{unit_id}-{output_mode}.json"
    write_json(output, context)
    return {
        "status": "ready",
        "mode": output_mode,
        "debate_id": debate_id,
        "work_id": work_id,
        "unit_id": unit_id,
        "context_path": relative_to_project(output, project_root),
        "context_sha256": context["context_sha256"],
        "context_size_bytes": output.stat().st_size,
        "telemetry": event,
        "telemetry_totals": ledger["totals"],
        "telemetry_path": relative_to_project(ledger_path, project_root),
        "telemetry_sha256": ledger["telemetry_sha256"],
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--output-mode", choices=("compact", "full"), default="compact")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_translation_context(
        args.project_root, args.debate_id, args.work_id, args.unit_id,
        output_mode=args.output_mode,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationContextError, WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"CONTEXTE DE TRADUCTION BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
