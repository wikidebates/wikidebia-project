#!/usr/bin/env python3
"""Prepare, seal and apply independently signed translation argument fragments."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
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
from wikidebia_render import _load_workspace
from wikidebia_translation_packet import (
    TranslationPacketError,
    _argument_hash,
    build_packet,
)
from wikidebia_translation_preflight import analyze_patch
from wikidebia_translation_resume import write_resume_capsule
from wikidebia_translation_worklist import _pending_nested
from wikidebia_update import sha_object


FRAGMENT_SCHEMA = "wikidebia-translation-argument-fragment-1.0"
SELECTION_SCHEMA = "wikidebia-translation-argument-fragment-selection-1.0"
PAGE_ID_RE = re.compile(r"A\d+")


class TranslationFragmentError(WorkspaceError):
    pass


def _validate_page_id(page_id: str) -> str:
    if not PAGE_ID_RE.fullmatch(page_id):
        raise TranslationFragmentError("page_id doit suivre A suivi de chiffres")
    return page_id


def _fragment_path(workspace: Path, page_id: str) -> Path:
    return workspace / "reviews/en/argument-fragments" / f"{_validate_page_id(page_id)}.json"


def _receipt_path(workspace: Path, page_id: str) -> Path:
    return workspace / "audits/translation-fragments" / f"{_validate_page_id(page_id)}-application.json"


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _review_state(
    project_root: Path, debate_id: str, work_id: str,
) -> tuple[Path, dict[str, Any], Path]:
    workspace, _meta = _load_workspace(project_root, debate_id, work_id)
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")
    if (
        review.get("debate_id") != debate_id
        or review.get("work_id") != work_id
        or review.get("status") != "draft"
        or review.get("review_sha256") not in {None, ""}
    ):
        raise TranslationFragmentError("La revue anglaise doit être un brouillon du même Work")
    return workspace, review, review_path


def _argument(review: Mapping[str, Any], page_id: str) -> dict[str, Any]:
    rows = [
        row for row in review.get("arguments") or []
        if isinstance(row, dict) and str(row.get("id")) == page_id
    ]
    if len(rows) != 1:
        raise TranslationFragmentError(f"Argument de traduction introuvable ou dupliqué : {page_id}")
    return rows[0]


def _unit(review: Mapping[str, Any], unit_id: str, page_id: str) -> dict[str, Any]:
    rows = [
        row for row in review.get("review_units") or []
        if isinstance(row, dict) and str(row.get("id")) == unit_id
    ]
    if len(rows) != 1 or page_id not in {str(value) for value in rows[0].get("page_ids") or []}:
        raise TranslationFragmentError("L’argument n’appartient pas à l’unité demandée")
    return rows[0]


def _packet_argument(packet: Mapping[str, Any], page_id: str) -> dict[str, Any]:
    rows = [row for row in packet.get("arguments") or [] if str(row.get("id")) == page_id]
    if len(rows) != 1:
        raise TranslationFragmentError(
            "L’argument est absent du paquet courant ou déjà couvert par une preuve appliquée"
        )
    return rows[0]


def prepare_fragment(
    project_root: Path,
    debate_id: str,
    work_id: str,
    unit_id: str,
    page_id: str,
    *,
    overwrite: bool = False,
    packet: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    page_id = _validate_page_id(page_id)
    workspace, review, _review_path = _review_state(project_root, debate_id, work_id)
    row = _argument(review, page_id)
    _unit(review, unit_id, page_id)
    packet = dict(packet) if packet is not None else build_packet(
        project_root, debate_id, work_id, unit_id,
    )
    source = _packet_argument(packet, page_id)
    path = _fragment_path(workspace, page_id)
    if path.is_file() and not overwrite:
        current = load_json(path, "fragment d’argument")
        if (
            current.get("base_argument_sha256") != _argument_hash(row)
            or current.get("current_source_sha256") != source.get("current_source_sha256")
        ):
            raise TranslationFragmentError(
                "Le fragment existant repose sur un ancien argument ; utilisez --overwrite après sauvegarde"
            )
        return {
            **current,
            "status": "already_prepared",
            "fragment_path": relative_to_project(path, project_root),
        }
    translation = copy.deepcopy(row.get("translation") or {})
    translation.pop("french", None)
    fragment: dict[str, Any] = {
        "schema": FRAGMENT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "unit_id": unit_id,
        "page_id": page_id,
        "status": "draft",
        "base_argument_sha256": _argument_hash(row),
        "current_source_sha256": source.get("current_source_sha256"),
        "translation": translation,
        "fragment_sha256": None,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    write_json(path, fragment)
    return {
        **fragment,
        "status": "prepared",
        "fragment_path": relative_to_project(path, project_root),
    }


def seal_fragment(
    project_root: Path,
    debate_id: str,
    work_id: str,
    unit_id: str,
    page_id: str,
    *,
    reviewer: str,
    note: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    page_id = _validate_page_id(page_id)
    workspace, review, _review_path = _review_state(project_root, debate_id, work_id)
    path = _fragment_path(workspace, page_id)
    fragment = load_json(path, "fragment d’argument")
    if fragment.get("schema") != FRAGMENT_SCHEMA or fragment.get("status") != "draft":
        raise TranslationFragmentError("Le fragment doit être un brouillon connu")
    if any(
        fragment.get(key) != value
        for key, value in (
            ("debate_id", debate_id), ("work_id", work_id),
            ("unit_id", unit_id), ("page_id", page_id),
        )
    ):
        raise TranslationFragmentError("Identité du fragment divergente")
    row = _argument(review, page_id)
    _unit(review, unit_id, page_id)
    if fragment.get("base_argument_sha256") != _argument_hash(row):
        raise TranslationFragmentError("L’argument a changé depuis la préparation du fragment")
    packet = build_packet(project_root, debate_id, work_id, unit_id)
    source = _packet_argument(packet, page_id)
    if fragment.get("current_source_sha256") != source.get("current_source_sha256"):
        raise TranslationFragmentError("La source française a changé depuis la préparation")
    pseudo_packet = {"arguments": [source]}
    pseudo_patch = {
        "arguments": [{"id": page_id, "translation": fragment.get("translation")}],
        "vocabulary": [],
        "relation_labels": [],
    }
    findings = analyze_patch(pseudo_patch, pseudo_packet)
    if findings:
        codes = sorted({str(item["code"]) for item in findings})
        raise TranslationFragmentError("Préflight mécanique bloqué : " + ", ".join(codes))
    translation = fragment.get("translation") or {}
    if translation.get("status") != "approved" or _pending_nested(translation):
        raise TranslationFragmentError(
            "La traduction et ses citations doivent être approuvées avant le scellement"
        )
    reviewer, note = reviewer.strip(), note.strip()
    if len(reviewer) < 3 or len(note) < 12:
        raise TranslationFragmentError("Relecteur et note explicite sont obligatoires")
    sealed = copy.deepcopy(fragment)
    sealed.update({
        "status": "sealed",
        "reviewer": reviewer,
        "note": note,
        "sealed_at": now_iso(),
        "fragment_sha256": None,
    })
    sealed["fragment_sha256"] = sha_object({
        key: value for key, value in sealed.items() if key != "fragment_sha256"
    })
    write_json(path, sealed)
    return {**sealed, "fragment_path": relative_to_project(path, project_root)}


def apply_fragment(
    project_root: Path,
    debate_id: str,
    work_id: str,
    unit_id: str,
    page_id: str,
    *,
    confirm_fragment_sha256: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    page_id = _validate_page_id(page_id)
    workspace, review, review_path = _review_state(project_root, debate_id, work_id)
    path = _fragment_path(workspace, page_id)
    receipt_path = _receipt_path(workspace, page_id)
    fragment = load_json(path, "fragment d’argument")
    if fragment.get("status") != "sealed" or not _signed(fragment, "fragment_sha256"):
        raise TranslationFragmentError("Fragment non scellé ou empreinte invalide")
    if any(
        fragment.get(key) != value
        for key, value in (
            ("debate_id", debate_id), ("work_id", work_id),
            ("unit_id", unit_id), ("page_id", page_id),
        )
    ):
        raise TranslationFragmentError("Identité du fragment divergente")
    if fragment.get("fragment_sha256") != confirm_fragment_sha256:
        raise TranslationFragmentError("L’empreinte confirmée ne correspond pas au fragment")
    row = _argument(review, page_id)
    _unit(review, unit_id, page_id)
    if receipt_path.is_file():
        receipt = load_json(receipt_path, "reçu d’application du fragment")
        if (
            _signed(receipt, "receipt_sha256")
            and receipt.get("fragment_sha256") == confirm_fragment_sha256
            and receipt.get("argument_after_sha256") == _argument_hash(row)
        ):
            return {
                **receipt,
                "status": "already_applied",
                "receipt_path": relative_to_project(receipt_path, project_root),
            }
    if fragment.get("base_argument_sha256") != _argument_hash(row):
        raise TranslationFragmentError("L’argument a changé depuis la préparation du fragment")
    packet = build_packet(project_root, debate_id, work_id, unit_id)
    source = _packet_argument(packet, page_id)
    if fragment.get("current_source_sha256") != source.get("current_source_sha256"):
        raise TranslationFragmentError("La source française a changé depuis la préparation")
    review_before = sha256_bytes(canonical_json(review))
    argument_before = _argument_hash(row)
    french = copy.deepcopy((row.get("translation") or {}).get("french"))
    row["translation"] = copy.deepcopy(fragment["translation"])
    row["translation"]["french"] = french
    write_json(review_path, review)
    argument_after = _argument_hash(row)
    receipt: dict[str, Any] = {
        "schema": "wikidebia-translation-argument-fragment-application-1.0",
        "status": "applied",
        "debate_id": debate_id,
        "work_id": work_id,
        "unit_id": unit_id,
        "page_id": page_id,
        "fragment_sha256": confirm_fragment_sha256,
        "argument_before_sha256": argument_before,
        "argument_after_sha256": argument_after,
        "review_before_sha256": review_before,
        "review_after_sha256": sha256_bytes(canonical_json(review)),
        "applied_at": now_iso(),
        "french_fields_mutated": False,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    write_json(receipt_path, receipt)
    return {**receipt, "receipt_path": relative_to_project(receipt_path, project_root)}


def prepare_next_fragment(
    project_root: Path, debate_id: str, work_id: str,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, review, _review_path = _review_state(project_root, debate_id, work_id)
    review_by_id = {
        str(row.get("id")): row
        for row in review.get("arguments") or [] if isinstance(row, dict)
    }
    active_unit: dict[str, Any] | None = None
    page_id: str | None = None
    for unit in review.get("review_units") or []:
        if not isinstance(unit, dict) or unit.get("status") == "approved":
            continue
        if active_unit is None:
            active_unit = unit
        for candidate in unit.get("page_ids") or []:
            row = review_by_id.get(str(candidate))
            translation = (row or {}).get("translation") or {}
            if row is not None and (
                translation.get("status") != "approved" or _pending_nested(translation)
            ):
                active_unit = unit
                page_id = str(candidate)
                break
        if page_id:
            break

    if page_id is None:
        if active_unit is None:
            status = "all_arguments_complete"
            next_action = "prepare_next_translation_unit"
            next_command = (
                f"./wikidebia corpus-workspace-translation-next {debate_id} --work-id {work_id}"
            )
            unit_id = None
        else:
            status = "unit_arguments_complete"
            next_action = "complete_unit_vocabulary_relations_and_decision"
            unit_id = str(active_unit["id"])
            next_command = (
                f"./wikidebia corpus-workspace-translation-patch {debate_id} "
                f"--work-id {work_id} --unit-id {unit_id} --prepare"
            )
        result: dict[str, Any] = {
            "schema": SELECTION_SCHEMA,
            "status": status,
            "debate_id": debate_id,
            "work_id": work_id,
            "unit_id": unit_id,
            "page_id": None,
            "next_action": next_action,
            "next_command": next_command,
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
    else:
        unit_id = str(active_unit["id"])
        packet = build_packet(project_root, debate_id, work_id, unit_id)
        source = _packet_argument(packet, page_id)
        fragment = prepare_fragment(
            project_root, debate_id, work_id, unit_id, page_id, packet=packet,
        )
        compact_source = copy.deepcopy(source)
        compact_source.pop("translation", None)
        saved_fragment = load_json(
            project_root / fragment["fragment_path"], "fragment d’argument",
        )
        context: dict[str, Any] = {
            "schema": "wikidebia-translation-argument-context-1.0",
            "debate_id": debate_id,
            "work_id": work_id,
            "unit_id": unit_id,
            "page_id": page_id,
            "packet_sha256": packet["packet_sha256"],
            "argument_source": compact_source,
            "fragment": saved_fragment,
            "vocabulary": [
                row for row in packet.get("vocabulary") or []
                if any(str(use.get("page_id")) == page_id for use in row.get("usages") or [])
            ],
            "relation_labels": [
                row for row in packet.get("relation_labels") or []
                if str(row.get("source_page_id")) == page_id
                or str(row.get("target_node_id")) == page_id
            ],
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
        context["context_sha256"] = sha_object(context)
        context_path = workspace / "audits/translation-fragments" / f"{page_id}-context.json"
        write_json(context_path, context)
        packet_path = workspace / "audits/translation-packets" / f"{unit_id}.json"
        result = {
            "schema": SELECTION_SCHEMA,
            "status": "argument_fragment_prepared",
            "debate_id": debate_id,
            "work_id": work_id,
            "unit_id": unit_id,
            "page_id": page_id,
            "fragment_path": fragment["fragment_path"],
            "context_path": relative_to_project(context_path, project_root),
            "context_sha256": context["context_sha256"],
            "unit_packet_bytes": packet_path.stat().st_size,
            "argument_context_bytes": context_path.stat().st_size,
            "avoided_context_bytes": max(0, packet_path.stat().st_size - context_path.stat().st_size),
            "next_action": "edit_translation_argument_fragment",
            "next_command": None,
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
    result["selection_sha256"] = sha_object(result)
    selection_path = workspace / "audits/translation-fragment-next.json"
    write_json(selection_path, result)
    return {**result, "selection_path": relative_to_project(selection_path, project_root)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--unit-id")
    parser.add_argument("--page-id")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare-next", action="store_true")
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--seal", action="store_true")
    actions.add_argument("--apply", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--reviewer")
    parser.add_argument("--note")
    parser.add_argument("--confirm-fragment-sha256")
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.prepare_next:
        result = prepare_next_fragment(args.project_root, args.debate_id, args.work_id)
    else:
        if not args.unit_id or not args.page_id:
            raise TranslationFragmentError("--unit-id et --page-id sont obligatoires pour cette action")
        if args.prepare:
            result = prepare_fragment(
                args.project_root, args.debate_id, args.work_id, args.unit_id, args.page_id,
                overwrite=args.overwrite,
            )
        elif args.seal:
            if not args.reviewer or not args.note:
                raise TranslationFragmentError("--seal exige --reviewer et --note")
            result = seal_fragment(
                args.project_root, args.debate_id, args.work_id, args.unit_id, args.page_id,
                reviewer=args.reviewer, note=args.note,
            )
        else:
            if not args.confirm_fragment_sha256:
                raise TranslationFragmentError("--apply exige --confirm-fragment-sha256")
            result = apply_fragment(
                args.project_root, args.debate_id, args.work_id, args.unit_id, args.page_id,
                confirm_fragment_sha256=args.confirm_fragment_sha256,
            )
    capsule = write_resume_capsule(
        args.project_root, args.debate_id, args.work_id,
        event=f"argument_fragment_{result.get('status')}",
        unit_id=result.get("unit_id"), page_id=result.get("page_id"),
    )
    compact = {
        key: result.get(key) for key in (
            "status", "debate_id", "work_id", "unit_id", "page_id",
            "fragment_path", "fragment_sha256", "receipt_path", "receipt_sha256",
            "context_path", "context_sha256", "unit_packet_bytes",
            "argument_context_bytes", "avoided_context_bytes", "next_action", "next_command",
        ) if result.get(key) is not None
    }
    compact.update({
        "capsule_path": capsule["capsule_path"],
        "capsule_sha256": capsule["capsule_sha256"],
        "remote_access_performed": False,
        "remote_write_performed": False,
    })
    print(json.dumps(compact, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        TranslationFragmentError, TranslationPacketError, WorkspaceError, CorpusBuildError,
        OSError, ValueError, KeyError,
    ) as exc:
        print(f"FRAGMENT DE TRADUCTION BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
