#!/usr/bin/env python3
"""Prepare, seal and apply a translation patch limited to one review unit."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import canonical_json, load_json, now_iso, relative_to_project, sha256_bytes, write_json
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_render import _load_workspace
from wikidebia_translation_packet import TranslationPacketError, build_packet
from wikidebia_translation_preflight import TranslationPreflightError, run_preflight
from wikidebia_translation_resume import TranslationResumeError, write_resume_capsule
from wikidebia_update import sha_object


PATCH_SCHEMA = "wikidebia-translation-unit-patch-1.0"
IMMUTABLE_VOCABULARY = {"concept_id", "fr", "kind", "capitalization_policy", "usages"}
IMMUTABLE_RELATION = {"id", "source_page_id", "target_node_id", "relation", "source_text"}


class TranslationPatchError(WorkspaceError):
    pass


def _review_hash(review: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(review))


def _patch_path(workspace: Path, unit_id: str) -> Path:
    return workspace / "reviews/en/unit-patches" / f"{unit_id}.json"


def _receipt_path(workspace: Path, unit_id: str) -> Path:
    return workspace / "audits/translation-patches" / f"{unit_id}-application.json"


def _unsigned_valid(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def prepare_patch(
    project_root: Path, debate_id: str, work_id: str, unit_id: str, *, overwrite: bool = False,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    packet = build_packet(project_root, debate_id, work_id, unit_id)
    workspace, _meta = _load_workspace(project_root, debate_id, validate_work_id(work_id))
    path = _patch_path(workspace, unit_id)
    if path.exists() and not overwrite:
        current = load_json(path, "correctif d’unité")
        return {**current, "status": "already_prepared", "patch_path": relative_to_project(path, project_root)}
    patch: dict[str, Any] = {
        "schema": PATCH_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "unit_id": unit_id,
        "status": "draft",
        "base_packet_sha256": packet["packet_sha256"],
        "base_translation_review_content_sha256": packet["translation_review_content_sha256"],
        "base_content_reviewed_copy_sha256": packet["current_content_reviewed_copy_sha256"],
        "arguments": [
            {"id": row["id"], "translation": copy.deepcopy(row["translation"])}
            for row in packet["arguments"]
        ],
        "vocabulary": copy.deepcopy(packet["vocabulary"]),
        "relation_labels": copy.deepcopy(packet["relation_labels"]),
        "unit_decision": {
            "status": packet["unit"].get("status") or "pending",
            "reviewer": packet["unit"].get("reviewer") or "",
            "reviewed_at": packet["unit"].get("reviewed_at"),
            "note": packet["unit"].get("note") or "",
        },
        "patch_sha256": None,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    write_json(path, patch)
    return {**patch, "status": "prepared", "patch_path": relative_to_project(path, project_root)}


def _verify_scope(patch: Mapping[str, Any], packet: Mapping[str, Any]) -> None:
    expected_arguments = {str(row["id"]): row for row in packet["arguments"]}
    arguments = patch.get("arguments")
    if not isinstance(arguments, list) or {str(row.get("id")) for row in arguments if isinstance(row, Mapping)} != set(expected_arguments):
        raise TranslationPatchError("Le correctif ne couvre pas exactement les arguments de l’unité")
    for row in arguments:
        translation = row.get("translation")
        if not isinstance(translation, dict) or "french" in translation:
            raise TranslationPatchError("Les blocs français sont interdits dans un correctif d’unité")

    for field, identity, immutable in (
        ("vocabulary", "concept_id", IMMUTABLE_VOCABULARY),
        ("relation_labels", "id", IMMUTABLE_RELATION),
    ):
        expected = {str(row.get(identity)): row for row in packet[field]}
        supplied_rows = patch.get(field)
        if not isinstance(supplied_rows, list):
            raise TranslationPatchError(f"Champ {field} invalide")
        supplied = {str(row.get(identity)): row for row in supplied_rows if isinstance(row, Mapping)}
        if set(supplied) != set(expected) or len(supplied) != len(supplied_rows):
            raise TranslationPatchError(f"Le correctif change le périmètre de {field}")
        for key, row in supplied.items():
            for name in immutable:
                if row.get(name) != expected[key].get(name):
                    raise TranslationPatchError(f"Champ immuable modifié dans {field} : {key}/{name}")


def _current_packet(project_root: Path, patch: Mapping[str, Any]) -> dict[str, Any]:
    packet = build_packet(
        project_root, str(patch.get("debate_id")), str(patch.get("work_id")), str(patch.get("unit_id")),
    )
    if packet["packet_sha256"] != patch.get("base_packet_sha256"):
        raise TranslationPatchError("Le paquet ou la revue a changé depuis la préparation du correctif")
    if packet["current_content_reviewed_copy_sha256"] != patch.get("base_content_reviewed_copy_sha256"):
        raise TranslationPatchError("Les sources françaises ont changé depuis la préparation")
    _verify_scope(patch, packet)
    return packet


def seal_patch(
    project_root: Path, debate_id: str, work_id: str, unit_id: str, *,
    reviewer: str, note: str, unit_status: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    workspace, _meta = _load_workspace(project_root, debate_id, validate_work_id(work_id))
    path = _patch_path(workspace, unit_id)
    patch = load_json(path, "correctif d’unité")
    if patch.get("schema") != PATCH_SCHEMA or patch.get("status") != "draft":
        raise TranslationPatchError("Le correctif doit être un brouillon connu")
    if any(patch.get(key) != value for key, value in (("debate_id", debate_id), ("work_id", work_id), ("unit_id", unit_id))):
        raise TranslationPatchError("Identité du correctif divergente")
    packet = _current_packet(project_root, patch)
    preflight = run_preflight(
        project_root, debate_id, work_id, unit_id,
        patch=patch, packet=packet, workspace=workspace,
    )
    if preflight["status"] != "passed":
        codes = sorted({row["code"] for row in preflight["findings"]})
        raise TranslationPatchError(
            "Préflight mécanique bloqué : " + ", ".join(codes)
        )
    reviewer, note = reviewer.strip(), note.strip()
    if len(reviewer) < 3 or len(note) < 12 or unit_status not in {"pending", "approved"}:
        raise TranslationPatchError("Relecteur, note explicite et statut d’unité valides sont obligatoires")
    sealed = copy.deepcopy(patch)
    sealed["status"] = "sealed"
    sealed["unit_decision"] = {
        "status": unit_status, "reviewer": reviewer, "reviewed_at": now_iso(), "note": note,
    }
    sealed["sealed_at"] = sealed["unit_decision"]["reviewed_at"]
    sealed["patch_sha256"] = None
    sealed["patch_sha256"] = sha_object({key: value for key, value in sealed.items() if key != "patch_sha256"})
    write_json(path, sealed)
    return {"status": "sealed", "patch_path": relative_to_project(path, project_root), **sealed}


def apply_patch(
    project_root: Path, debate_id: str, work_id: str, unit_id: str, *, confirm_patch_sha256: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    workspace, _meta = _load_workspace(project_root, debate_id, validate_work_id(work_id))
    path = _patch_path(workspace, unit_id)
    receipt_path = _receipt_path(workspace, unit_id)
    patch = load_json(path, "correctif d’unité")
    if patch.get("status") != "sealed" or not _unsigned_valid(patch, "patch_sha256"):
        raise TranslationPatchError("Correctif non scellé ou empreinte invalide")
    if any(patch.get(key) != value for key, value in (("debate_id", debate_id), ("work_id", work_id), ("unit_id", unit_id))):
        raise TranslationPatchError("Identité du correctif divergente")
    if patch.get("patch_sha256") != confirm_patch_sha256:
        raise TranslationPatchError("L’empreinte confirmée ne correspond pas au correctif")
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")
    if receipt_path.is_file():
        receipt = load_json(receipt_path, "reçu d’application du correctif")
        if _unsigned_valid(receipt, "receipt_sha256") and receipt.get("patch_sha256") == confirm_patch_sha256 and receipt.get("review_after_sha256") == _review_hash(review):
            return {"status": "already_applied", "receipt_path": relative_to_project(receipt_path, project_root), **receipt}
    if review.get("status") != "draft" or review.get("review_sha256") not in {None, ""}:
        raise TranslationPatchError("Une revue finalisée doit être rouverte avant un correctif d’unité")
    if _review_hash(review) != patch.get("base_translation_review_content_sha256"):
        raise TranslationPatchError("La revue complète a changé depuis la préparation du correctif")
    _current_packet(project_root, patch)
    before = _review_hash(review)
    argument_patch = {str(row["id"]): row["translation"] for row in patch["arguments"]}
    for row in review.get("arguments") or []:
        page_id = str(row.get("id"))
        if page_id in argument_patch:
            french = copy.deepcopy((row.get("translation") or {}).get("french"))
            row["translation"] = copy.deepcopy(argument_patch[page_id])
            row["translation"]["french"] = french
    for field, identity in (("vocabulary", "concept_id"), ("relation_labels", "id")):
        replacements = {str(row[identity]): copy.deepcopy(row) for row in patch[field]}
        review[field] = [replacements.get(str(row.get(identity)), row) for row in review.get(field) or []]
    decision = patch["unit_decision"]
    for unit in review.get("review_units") or []:
        if unit.get("id") == unit_id:
            unit.update(copy.deepcopy(decision))
    review["review_sha256"] = None
    write_json(review_path, review)
    after = _review_hash(review)
    receipt = {
        "schema": "wikidebia-translation-unit-patch-application-1.0",
        "debate_id": debate_id, "work_id": work_id, "unit_id": unit_id,
        "patch_path": relative_to_project(path, project_root),
        "patch_sha256": confirm_patch_sha256,
        "review_before_sha256": before, "review_after_sha256": after,
        "applied_at": now_iso(), "arguments_updated": len(argument_patch),
        "vocabulary_updated": len(patch["vocabulary"]),
        "relation_labels_updated": len(patch["relation_labels"]),
        "french_fields_mutated": False, "remote_access_performed": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    write_json(receipt_path, receipt)
    return {"status": "applied", "receipt_path": relative_to_project(receipt_path, project_root), **receipt}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--seal", action="store_true")
    actions.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--note")
    parser.add_argument("--unit-status", choices=("pending", "approved"))
    parser.add_argument("--confirm-patch-sha256")
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.prepare:
        result = prepare_patch(args.project_root, args.debate_id, args.work_id, args.unit_id, overwrite=args.overwrite)
    elif args.seal:
        if not args.reviewer or not args.note or not args.unit_status:
            raise TranslationPatchError("--seal exige --reviewer, --note et --unit-status")
        result = seal_patch(args.project_root, args.debate_id, args.work_id, args.unit_id, reviewer=args.reviewer, note=args.note, unit_status=args.unit_status)
    else:
        if not args.confirm_patch_sha256:
            raise TranslationPatchError("--apply exige --confirm-patch-sha256")
        result = apply_patch(args.project_root, args.debate_id, args.work_id, args.unit_id, confirm_patch_sha256=args.confirm_patch_sha256)
    capsule = write_resume_capsule(
        args.project_root, args.debate_id, args.work_id,
        event=f"translation_patch_{result.get('status')}", unit_id=args.unit_id,
    )
    compact = {
        "status": result.get("status"), "debate_id": args.debate_id,
        "work_id": args.work_id, "unit_id": args.unit_id,
        "patch_path": result.get("patch_path"),
        "patch_sha256": result.get("patch_sha256"),
        "receipt_path": result.get("receipt_path"),
        "receipt_sha256": result.get("receipt_sha256"),
        "arguments_updated": result.get("arguments_updated"),
        "remote_access_performed": result.get("remote_access_performed", False),
        "remote_write_performed": result.get("remote_write_performed", False),
        "capsule_path": capsule.get("capsule_path"),
        "capsule_sha256": capsule.get("capsule_sha256"),
    }
    print(json.dumps(compact, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationPatchError, TranslationPacketError, TranslationPreflightError, TranslationResumeError, WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"CORRECTIF D’UNITÉ BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
