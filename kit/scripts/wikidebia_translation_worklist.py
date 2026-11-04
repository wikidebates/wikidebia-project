#!/usr/bin/env python3
"""Build a compact differential worklist for an English translation review."""
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
    relative_to_project,
    sha256_bytes,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_render import RenderError, _load_workspace
from wikidebia_translation_review import (
    TRANSLATION_REVIEW_SCHEMA,
    TranslationReviewError,
    _assert_content_copy,
    _french_source_page_origin,
    _reuses_existing_english_page,
    _source_snapshot,
    translation_review_sha256,
)
from wikidebia_update import sha_object


class TranslationWorklistError(WorkspaceError):
    pass


def _source_hash(metadata: Mapping[str, Any], content: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json({"metadata": metadata, "content": content}))


def _source_reason(
    embedded: Any, metadata: Mapping[str, Any], content: Mapping[str, Any]
) -> tuple[list[str], str, str]:
    current_hash = _source_hash(metadata, content)
    if not isinstance(embedded, Mapping):
        return ["embedded_french_source_missing"], "", current_hash
    prepared_hash = _source_hash(
        embedded.get("metadata") or {}, embedded.get("content") or {}
    )
    return (
        ([] if embedded == {"metadata": metadata, "content": content} else ["french_source_changed"]),
        prepared_hash,
        current_hash,
    )


def _pending_nested(translation: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    pending_citations = [
        str(row.get("id") or "")
        for row in translation.get("citations") or []
        if isinstance(row, Mapping) and row.get("status") != "approved"
    ]
    if pending_citations:
        reasons.append("citations_pending:" + ",".join(pending_citations))
    pending_passages = [
        str(row.get("id") or "")
        for row in translation.get("citation_passages") or []
        if isinstance(row, Mapping)
        and row.get("status") not in {None, "approved", "translated_and_reviewed"}
    ]
    if pending_passages:
        reasons.append("citation_passages_pending:" + ",".join(pending_passages))
    return reasons


def _render_markdown(value: Mapping[str, Any]) -> str:
    counts = value["counts"]
    rows = [
        "# Liste différentielle de traduction anglaise",
        "",
        f"- Débat : `{value['debate_id']}`",
        f"- Work : `{value['work_id']}`",
        f"- Statut de la revue : `{value['review_status']}`",
        f"- Arguments à reprendre : **{counts['arguments_to_review']}** / {counts['arguments_total']}",
        f"- Unités à reprendre : **{counts['units_to_review']}** / {counts['units_total']}",
        f"- Entrées de vocabulaire à reprendre : **{counts['vocabulary_to_review']}**",
        f"- Libellés relationnels à reprendre : **{counts['relation_labels_to_review']}**",
        "",
    ]
    if value.get("debate"):
        rows.extend(["## Debate", "", "- " + "; ".join(value["debate"]["reasons"]), ""])
    if value["units"]:
        rows.extend(["## Unités Argument", ""])
        for unit in value["units"]:
            rows.append(
                f"- **{unit['unit_id']}** ({unit['max_risk_level']}) : "
                + ", ".join(unit["page_ids"])
            )
            for page_id, reasons in unit["reasons_by_page"].items():
                rows.append(f"  - `{page_id}` : " + "; ".join(reasons))
        rows.append("")
    if value["vocabulary"]:
        rows.extend(["## Vocabulaire", "", "- " + ", ".join(value["vocabulary"]), ""])
    if value["relation_labels"]:
        rows.extend(["## Libellés relationnels", "", "- " + ", ".join(value["relation_labels"]), ""])
    if value["global_reasons"]:
        rows.extend(["## Contrôles globaux", ""])
        rows.extend(f"- {reason}" for reason in value["global_reasons"])
        rows.append("")
    if value.get("next_command"):
        rows.extend(["## Commande suivante", "", "```text", str(value["next_command"]), "```", ""])
    return "\n".join(rows).rstrip() + "\n"


def build_worklist(project_root: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    source = _assert_content_copy(workspace, meta)
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")
    if (
        review.get("schema") != TRANSLATION_REVIEW_SCHEMA
        or review.get("debate_id") != debate_id
        or review.get("work_id") != work_id
    ):
        raise TranslationWorklistError("Schéma ou identité de revue anglaise invalide")
    review_status = str(review.get("status") or "")
    if review_status == "approved":
        claimed = str(review.get("review_sha256") or "")
        if not claimed or claimed != translation_review_sha256(review):
            raise TranslationWorklistError("Empreinte de revue anglaise invalide")

    registry, metadata_lock, content_lock, _vocabulary = _source_snapshot(source)
    meta_by_id = {
        str(row.get("entity_id") or row.get("id")): row
        for row in metadata_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    content_by_id = {
        str(row.get("id")): row
        for row in content_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    active_nodes = [
        row for row in ((registry.get("graph") or {}).get("nodes") or [])
        if row.get("status") == "active"
    ]
    expected_ids = {
        str(row.get("id")) for row in active_nodes if not _reuses_existing_english_page(row)
    }
    review_rows = {
        str(row.get("id")): row
        for row in review.get("arguments") or [] if isinstance(row, Mapping) and row.get("id")
    }
    unit_by_page: dict[str, Mapping[str, Any]] = {}
    units = [row for row in review.get("review_units") or [] if isinstance(row, Mapping)]
    for unit in units:
        for page_id in unit.get("page_ids") or []:
            unit_by_page[str(page_id)] = unit

    page_reasons: dict[str, list[str]] = {}
    source_hashes: dict[str, dict[str, str]] = {}
    for page_id in sorted(expected_ids | set(review_rows)):
        reasons: list[str] = []
        prepared_hash = ""
        current_hash = ""
        row = review_rows.get(page_id)
        if page_id not in expected_ids:
            reasons.append("page_removed_or_reused_since_preparation")
        elif row is None:
            reasons.append("translation_entry_missing")
        else:
            translation = row.get("translation") or {}
            source_reasons, prepared_hash, current_hash = _source_reason(
                translation.get("french"), meta_by_id.get(page_id) or {}, content_by_id.get(page_id) or {}
            )
            reasons.extend(source_reasons)
            if translation.get("status") != "approved":
                reasons.append("translation_not_approved")
            reasons.extend(_pending_nested(translation))
            unit = unit_by_page.get(page_id)
            if unit is None:
                reasons.append("review_unit_missing")
            elif unit.get("status") != "approved":
                reasons.append("review_unit_not_approved")
        if reasons:
            page_reasons[page_id] = list(dict.fromkeys(reasons))
            if prepared_hash or current_hash:
                source_hashes[page_id] = {
                    "prepared_sha256": prepared_hash,
                    "current_sha256": current_hash,
                }

    debate_translation = review.get("debate") or {}
    debate_reasons, debate_prepared, debate_current = _source_reason(
        debate_translation.get("french"),
        metadata_lock.get("debate") or {},
        content_lock.get("debate") or {},
    )
    if debate_translation.get("status") != "approved":
        debate_reasons.append("translation_not_approved")
    debate_row = (
        {
            "reasons": list(dict.fromkeys(debate_reasons)),
            "prepared_source_sha256": debate_prepared,
            "current_source_sha256": debate_current,
        }
        if debate_reasons else None
    )

    unit_rows: list[dict[str, Any]] = []
    known_unit_pages: set[str] = set()
    for unit in units:
        unit_id = str(unit.get("id") or "unassigned")
        page_ids = [str(value) for value in unit.get("page_ids") or []]
        reasons_by_page = {
            page_id: page_reasons[page_id]
            for page_id in page_ids if page_id in page_reasons
        }
        if unit.get("status") != "approved":
            for page_id in page_ids:
                reasons_by_page.setdefault(page_id, ["review_unit_not_approved"])
        if reasons_by_page:
            known_unit_pages.update(reasons_by_page)
            unit_rows.append({
                "unit_id": unit_id,
                "max_risk_level": str(unit.get("max_risk_level") or "unknown"),
                "target_size": unit.get("target_size"),
                "page_ids": list(reasons_by_page),
                "reasons_by_page": reasons_by_page,
            })
    unassigned = {key: value for key, value in page_reasons.items() if key not in known_unit_pages}
    if unassigned:
        unit_rows.append({
            "unit_id": "unassigned",
            "max_risk_level": "unknown",
            "target_size": None,
            "page_ids": list(unassigned),
            "reasons_by_page": unassigned,
        })

    vocabulary_pending = [
        str(row.get("concept_id") or row.get("fr") or "")
        for row in review.get("vocabulary") or []
        if isinstance(row, Mapping)
        and (
            row.get("status") != "approved"
            or row.get("idiomatic_equivalent") is not True
            or row.get("same_concept") is not True
        )
    ]
    labels_pending = [
        str(row.get("id") or "")
        for row in review.get("relation_labels") or []
        if isinstance(row, Mapping)
        and (
            not str(row.get("translated_text") or "").strip()
            or row.get("equivalent_to_french") is not True
        )
    ]
    global_review = review.get("global_review") or {}
    global_reasons = []
    for field in (
        "all_entities_translated", "all_equivalences_reviewed",
        "all_selected_sources_verified", "relations_and_occurrences_unchanged",
        "no_final_pages_generated", "remote_access_not_used",
    ):
        if global_review.get(field) is not True:
            global_reasons.append("global_attestation_missing:" + field)
    if global_review.get("blocking_issues") not in ([], None):
        global_reasons.append("global_blocking_issues_present")

    arguments_to_review = len(page_reasons)
    complete = not any((debate_row, unit_rows, vocabulary_pending, labels_pending, global_reasons))
    next_command = (
        f"./wikidebia corpus-workspace-translation {debate_id} --work-id {work_id} --finalize"
        if complete and review_status != "approved" else None
    )
    value: dict[str, Any] = {
        "schema": "wikidebia-translation-worklist-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "workspace_status": meta.get("status"),
        "review_status": review_status,
        "review_content_sha256": sha256_bytes(canonical_json(review)),
        "prepared_content_reviewed_copy_sha256": review.get("prepared_content_reviewed_copy_sha256"),
        "current_content_reviewed_copy_sha256": (meta.get("content_reviewed_copy") or {}).get("tree_sha256"),
        "complete": complete,
        "counts": {
            "arguments_total": len(expected_ids),
            "arguments_to_review": arguments_to_review,
            "arguments_ready": len(expected_ids) - len(set(page_reasons) & expected_ids),
            "units_total": len(units),
            "units_to_review": len(unit_rows),
            "vocabulary_to_review": len(vocabulary_pending),
            "relation_labels_to_review": len(labels_pending),
        },
        "debate": debate_row,
        "units": unit_rows,
        "vocabulary": vocabulary_pending,
        "relation_labels": labels_pending,
        "global_reasons": global_reasons,
        "source_hashes": source_hashes,
        "next_command": next_command,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    value["worklist_sha256"] = sha_object(value)
    output_json = workspace / "audits/en_translation_worklist.json"
    output_md = workspace / "audits/en_translation_worklist.md"
    write_json(output_json, value)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_markdown(value), encoding="utf-8", newline="\n")
    return {
        **value,
        "worklist_path": relative_to_project(output_json, project_root),
        "worklist_markdown_path": relative_to_project(output_md, project_root),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lister uniquement les unités de traduction anglaise à reprendre."
    )
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_worklist(args.project_root, args.debate_id, args.work_id)
    if args.machine_readable:
        compact = {
            key: result[key]
            for key in (
                "schema", "debate_id", "work_id", "review_status", "complete",
                "counts", "worklist_sha256", "worklist_path", "worklist_markdown_path",
                "next_command", "remote_access_performed", "remote_write_performed",
            )
        }
        print(json.dumps(compact, ensure_ascii=False, sort_keys=True))
    else:
        print(_render_markdown(result), end="")
        print("JSON : " + result["worklist_path"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        TranslationWorklistError,
        TranslationReviewError,
        RenderError,
        WorkspaceError,
        CorpusBuildError,
    ) as exc:
        print(f"LISTE DE TRADUCTION BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
