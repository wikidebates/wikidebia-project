#!/usr/bin/env python3
"""Record and apply signed acceptances of pages deleted outside Wikidéb'IA."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import (
    assert_control_directory,
    now_iso,
    relative_to_project,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import validate_work_id
from wikidebia_update import sha_object


REGISTRY_SCHEMA = "wikidebia-accepted-external-deletions-1.0"
COMPARISON_ID_RE = re.compile(r"REMOTE-\d{8}-\d{3}")


class ExternalDeletionError(RuntimeError):
    pass


def _signed(value: Mapping[str, Any], field: str) -> bool:
    unsigned = dict(value)
    claimed = unsigned.pop(field, None)
    return bool(claimed) and claimed == sha_object(unsigned)


def registry_path(project_root: Path, debate_id: str) -> Path:
    project_root = project_root.expanduser().resolve()
    state = assert_control_directory(project_root / ".state", project_root, create=True)
    parent = assert_control_directory(state / "external-deletions", project_root, create=True)
    return parent / f"{validate_debate_id(debate_id)}.json"


def load_registry(project_root: Path, debate_id: str) -> tuple[Path, dict[str, Any] | None]:
    path = registry_path(project_root, debate_id)
    if not path.exists():
        return path, None
    if not path.is_file() or path.is_symlink():
        raise ExternalDeletionError("Chemin du registre de suppressions externes non sûr")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != REGISTRY_SCHEMA:
        raise ExternalDeletionError("Schéma du registre de suppressions externes invalide")
    if value.get("debate_id") != debate_id:
        raise ExternalDeletionError("Registre de suppressions rattaché à un autre débat")
    if not _signed(value, "registry_sha256"):
        raise ExternalDeletionError("Empreinte du registre de suppressions externes invalide")
    entries = value.get("entries")
    if not isinstance(entries, list):
        raise ExternalDeletionError("Entrées du registre de suppressions externes invalides")
    identities: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ExternalDeletionError("Entrée du registre de suppressions externes invalide")
        identity = (str(entry.get("language") or ""), str(entry.get("page_id") or ""))
        if identity[0] not in {"fr", "en"} or not identity[1] or identity in identities:
            raise ExternalDeletionError("Identité absente ou dupliquée dans le registre")
        identities.add(identity)
        if entry.get("status") not in {"active", "revoked"}:
            raise ExternalDeletionError("Statut d’acceptation de suppression invalide")
    return path, value


def _comparison_evidence(
    project_root: Path, debate_id: str, work_id: str, comparison_id: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
    if not COMPARISON_ID_RE.fullmatch(comparison_id):
        raise ExternalDeletionError("comparison_id doit suivre REMOTE-AAAAMMJJ-NNN")
    run_dir = (
        project_root / ".state/remote-comparisons" / debate_id / work_id / comparison_id
    )
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ExternalDeletionError("Comparaison distante introuvable ou non sûre")
    receipt = json.loads((run_dir / "comparison-receipt.json").read_text(encoding="utf-8"))
    plan = json.loads((run_dir / "update-plan.json").read_text(encoding="utf-8"))
    inventory = json.loads((run_dir / "remote-inventory.json").read_text(encoding="utf-8"))
    if not _signed(receipt, "receipt_sha256"):
        raise ExternalDeletionError("Empreinte du reçu de comparaison invalide")
    if not _signed(plan, "plan_sha256"):
        raise ExternalDeletionError("Empreinte du plan de comparaison invalide")
    if not _signed(inventory, "inventory_sha256"):
        raise ExternalDeletionError("Empreinte de l’inventaire distant invalide")
    if any(receipt.get(key) != expected for key, expected in (
        ("debate_id", debate_id), ("work_id", work_id), ("comparison_id", comparison_id),
    )):
        raise ExternalDeletionError("Reçu de comparaison rattaché à une autre identité")
    if receipt.get("plan_sha256") != plan.get("plan_sha256"):
        raise ExternalDeletionError("Le plan ne correspond pas au reçu de comparaison")
    if receipt.get("remote_inventory_sha256") != inventory.get("inventory_sha256"):
        raise ExternalDeletionError("L’inventaire ne correspond pas au reçu de comparaison")
    if receipt.get("remote_write_performed") is not False:
        raise ExternalDeletionError("La preuve de comparaison indique une écriture distante")
    return run_dir, receipt, plan, inventory


def accept_external_deletion(
    project_root: Path,
    debate_id: str,
    work_id: str,
    comparison_id: str,
    *,
    language: str,
    page_id: str,
    reason: str,
    accepted_by: str,
    confirm_plan_sha256: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    if language not in {"fr", "en"}:
        raise ExternalDeletionError("La langue doit être fr ou en")
    page_id = page_id.strip()
    reason = reason.strip()
    accepted_by = accepted_by.strip()
    if not page_id or len(reason) < 10 or not accepted_by:
        raise ExternalDeletionError("page_id, accepted_by et une raison explicite sont obligatoires")
    _run_dir, receipt, plan, inventory = _comparison_evidence(
        project_root, debate_id, work_id, comparison_id,
    )
    if plan.get("plan_sha256") != confirm_plan_sha256:
        raise ExternalDeletionError("L’empreinte confirmée ne correspond pas au plan distant")
    candidates = [
        row for row in ((plan.get("operations") or {}).get("create") or [])
        if row.get("language") == language and str(row.get("page_id")) == page_id
    ]
    if len(candidates) != 1:
        raise ExternalDeletionError("La comparaison doit contenir exactement une création correspondante")
    operation = candidates[0]
    observations = [
        row for row in inventory.get("pages") or []
        if row.get("language") == language
        and row.get("canonical_title") == operation.get("title")
    ]
    if len(observations) != 1 or observations[0].get("exists") is not False:
        raise ExternalDeletionError("L’inventaire ne prouve pas que la page distante est absente")
    entry = {
        "language": language,
        "page_id": page_id,
        "page_type": operation.get("page_type"),
        "canonical_title": operation.get("title"),
        "status": "active",
        "reason": reason,
        "accepted_by": accepted_by,
        "accepted_at": now_iso(),
        "work_id": work_id,
        "comparison_id": comparison_id,
        "comparison_receipt_sha256": receipt.get("receipt_sha256"),
        "observed_absent_at": observations[0].get("observed_at"),
        "release_copy_tree_sha256": receipt.get("release_copy_tree_sha256"),
        "release_page_sha256": operation.get("new_sha256"),
        "release_file_sha256": operation.get("local_file_sha256"),
    }
    path, registry = load_registry(project_root, debate_id)
    if registry is None:
        registry = {
            "schema": REGISTRY_SCHEMA,
            "debate_id": debate_id,
            "created_at": entry["accepted_at"],
            "updated_at": entry["accepted_at"],
            "entries": [],
        }
    existing = next((
        row for row in registry["entries"]
        if row.get("language") == language and row.get("page_id") == page_id
    ), None)
    if existing is not None:
        comparable = {
            key: entry[key] for key in (
                "language", "page_id", "canonical_title", "status", "reason", "accepted_by",
                "work_id", "comparison_id", "comparison_receipt_sha256",
                "release_copy_tree_sha256", "release_page_sha256", "release_file_sha256",
            )
        }
        if any(existing.get(key) != value for key, value in comparable.items()):
            raise ExternalDeletionError("Une décision différente existe déjà pour cette page")
        return {
            "status": "already_registered",
            "registry_path": relative_to_project(path, project_root),
            "registry_sha256": registry["registry_sha256"],
            "entry": existing,
            "remote_write_performed": False,
        }
    registry["entries"].append(entry)
    registry["entries"].sort(key=lambda row: (str(row["language"]), str(row["page_id"])))
    registry["updated_at"] = entry["accepted_at"]
    registry.pop("registry_sha256", None)
    registry["registry_sha256"] = sha_object(registry)
    write_json(path, registry)
    return {
        "status": "registered",
        "registry_path": relative_to_project(path, project_root),
        "registry_sha256": registry["registry_sha256"],
        "entry": entry,
        "remote_write_performed": False,
    }


def apply_external_deletions(
    project_root: Path,
    debate_id: str,
    plan: dict[str, Any],
    inventory: Mapping[str, Any],
) -> dict[str, Any]:
    path, registry = load_registry(project_root, debate_id)
    if registry is None:
        return {"registry_present": False, "applied": 0, "source_mismatches": []}
    active = {
        (str(row["language"]), str(row["page_id"])): row
        for row in registry["entries"] if row.get("status") == "active"
    }
    absent = {
        (str(row.get("language")), str(row.get("canonical_title")))
        for row in inventory.get("pages") or [] if row.get("exists") is False
    }
    operations = plan.get("operations") or {}
    creates = list(operations.get("create") or [])
    kept: list[dict[str, Any]] = []
    skipped = list(operations.get("skip") or [])
    applied = 0
    mismatches: list[dict[str, str]] = []
    for operation in creates:
        key = (str(operation.get("language")), str(operation.get("page_id")))
        entry = active.get(key)
        if entry is None:
            kept.append(operation)
            continue
        same_source = (
            operation.get("title") == entry.get("canonical_title")
            and operation.get("new_sha256") == entry.get("release_page_sha256")
            and operation.get("local_file_sha256") == entry.get("release_file_sha256")
        )
        if not same_source:
            kept.append(operation)
            mismatches.append({"language": key[0], "page_id": key[1], "reason": "release_source_changed"})
            continue
        if (key[0], str(operation.get("title"))) not in absent:
            kept.append(operation)
            mismatches.append({"language": key[0], "page_id": key[1], "reason": "remote_absence_not_observed"})
            continue
        replacement = dict(operation)
        replacement.update({
            "justification": "Suppression externe acceptée : " + str(entry["reason"]),
            "preconditions": [
                "remote_title_absent",
                "external_deletion_registry_signature_valid",
                "release_page_matches_accepted_deletion",
            ],
            "phase": 0,
            "external_deletion_acceptance": {
                "registry_path": relative_to_project(path, project_root),
                "registry_sha256": registry["registry_sha256"],
                "accepted_at": entry["accepted_at"],
                "accepted_by": entry["accepted_by"],
                "comparison_id": entry["comparison_id"],
            },
        })
        skipped.append(replacement)
        applied += 1
    operations["create"] = kept
    operations["skip"] = skipped
    plan["counts"] = {name: len(rows) for name, rows in operations.items()}
    if applied:
        plan.setdefault("preconditions", []).append("accepted_external_deletions_applied")
    return {
        "registry_present": True,
        "registry_path": relative_to_project(path, project_root),
        "registry_sha256": registry["registry_sha256"],
        "active_entries": len(active),
        "applied": applied,
        "source_mismatches": mismatches,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--language", choices=("fr", "en"), required=True)
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--accepted-by", required=True)
    parser.add_argument("--confirm-plan-sha256", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = accept_external_deletion(
        args.project_root, args.debate_id, args.work_id, args.comparison_id,
        language=args.language, page_id=args.page_id, reason=args.reason,
        accepted_by=args.accepted_by, confirm_plan_sha256=args.confirm_plan_sha256,
    )
    if args.machine_readable:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print("Suppression externe acceptée : " + result["entry"]["canonical_title"])
        print("Registre : " + result["registry_path"])
        print("Empreinte : " + result["registry_sha256"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ExternalDeletionError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"SUPPRESSION EXTERNE BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
