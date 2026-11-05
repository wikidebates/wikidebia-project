#!/usr/bin/env python3
"""Build a compact signed packet for one English translation review unit."""
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
    _source_snapshot,
    translation_review_sha256,
)
from wikidebia_translation_memory import (
    TranslationMemoryError,
    reuse_review,
    verified_reuse_coverage,
)
from wikidebia_update import sha_object


UNIT_ID_RE = re.compile(r"U\d{3,}")


class TranslationPacketError(WorkspaceError):
    pass


def _source_hash(metadata: Mapping[str, Any], content: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json({"metadata": metadata, "content": content}))


def _render_markdown(packet: Mapping[str, Any]) -> str:
    rows = [
        "# Paquet d’unité de traduction anglaise",
        "",
        f"- Débat : `{packet['debate_id']}`",
        f"- Work : `{packet['work_id']}`",
        f"- Unité : `{packet['unit']['id']}`",
        f"- Risque maximal : `{packet['unit'].get('max_risk_level')}`",
        f"- Arguments : **{packet['counts']['arguments']}**",
        f"- Arguments de l’unité : **{packet['counts']['unit_arguments']}**",
        f"- Traductions réutilisées : **{packet['counts']['memory_reused']}**",
        f"- Entrées obsolètes refusées : **{packet['counts']['memory_stale_rejected']}**",
        f"- Sources françaises modifiées : **{packet['counts']['changed_french_sources']}**",
        f"- Vocabulaire pertinent : **{packet['counts']['vocabulary']}**",
        f"- Libellés relationnels pertinents : **{packet['counts']['relation_labels']}**",
        "",
        "## Arguments",
        "",
    ]
    for argument in packet["arguments"]:
        status = (argument.get("translation") or {}).get("status") or "unknown"
        changed = " — source française modifiée" if argument["source_changed"] else ""
        rows.append(f"- `{argument['id']}` : `{status}`{changed}")
    if packet.get("memory_reuse"):
        rows.extend(["", "## Traductions réutilisées", ""])
        for reused in packet["memory_reuse"]:
            rows.append(f"- `{reused['page_id']}` : `{reused['entry_sha256']}`")
    if packet.get("memory_stale_rejected"):
        rows.extend(["", "## Entrées obsolètes refusées", ""])
        for stale in packet["memory_stale_rejected"]:
            rows.append(f"- `{stale['page_id']}` : source française modifiée")
    rows.extend([
        "",
        "Le JSON contient uniquement cette unité, ses sources françaises courantes,",
        "son vocabulaire et les occurrences relationnelles qui la touchent.",
        "Aucun accès distant n’a été effectué.",
        "",
    ])
    return "\n".join(rows)


def build_packet(
    project_root: Path, debate_id: str, work_id: str, unit_id: str, *,
    reuse_memory: bool = False, memory_root: Path = Path("translation-memory"),
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    if not UNIT_ID_RE.fullmatch(unit_id):
        raise TranslationPacketError("unit_id doit suivre U suivi d’au moins trois chiffres")
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    if reuse_memory:
        reuse_review(project_root, debate_id, work_id, memory_root)
    source = _assert_content_copy(workspace, meta)
    review = load_json(workspace / "reviews/en/translation_review.json", "revue anglaise")
    if (
        review.get("schema") != TRANSLATION_REVIEW_SCHEMA
        or review.get("debate_id") != debate_id
        or review.get("work_id") != work_id
    ):
        raise TranslationPacketError("Schéma ou identité de revue anglaise invalide")
    if review.get("status") == "approved":
        claimed = str(review.get("review_sha256") or "")
        if not claimed or claimed != translation_review_sha256(review):
            raise TranslationPacketError("Empreinte de revue anglaise invalide")

    _registry, metadata_lock, content_lock, _source_vocabulary = _source_snapshot(source)
    metadata_by_id = {
        str(row.get("entity_id") or row.get("id")): row
        for row in metadata_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    content_by_id = {
        str(row.get("id")): row
        for row in content_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    units = [row for row in review.get("review_units") or [] if isinstance(row, Mapping)]
    matching = [row for row in units if row.get("id") == unit_id]
    if len(matching) != 1:
        raise TranslationPacketError(f"Unité de traduction introuvable ou dupliquée : {unit_id}")
    unit = copy.deepcopy(matching[0])
    page_ids = [str(value) for value in unit.get("page_ids") or []]
    review_by_id = {
        str(row.get("id")): row
        for row in review.get("arguments") or [] if isinstance(row, Mapping) and row.get("id")
    }
    reused_rows, stale_rows = verified_reuse_coverage(
        workspace, review_by_id, metadata_by_id, content_by_id,
    )
    reused_by_id = {str(row["page_id"]): row for row in reused_rows}
    stale_by_id = {str(row["page_id"]): row for row in stale_rows}
    arguments: list[dict[str, Any]] = []
    changed_sources = 0
    for page_id in page_ids:
        row = review_by_id.get(page_id)
        metadata = metadata_by_id.get(page_id)
        content = content_by_id.get(page_id)
        if row is None or metadata is None or content is None:
            raise TranslationPacketError(f"Données de traduction ou source absentes : {page_id}")
        if page_id in reused_by_id:
            continue
        prepared = ((row.get("translation") or {}).get("french") or {})
        prepared_hash = _source_hash(
            prepared.get("metadata") or {}, prepared.get("content") or {},
        )
        current_hash = _source_hash(metadata, content)
        compact_row = copy.deepcopy(row)
        translation = compact_row.get("translation") or {}
        translation.pop("french", None)
        changed = prepared != {"metadata": metadata, "content": content}
        changed_sources += int(changed)
        arguments.append({
            **compact_row,
            "current_french": {"metadata": metadata, "content": content},
            "prepared_source_sha256": prepared_hash,
            "current_source_sha256": current_hash,
            "source_changed": changed,
        })

    page_set = set(page_ids)
    vocabulary = [
        copy.deepcopy(row) for row in review.get("vocabulary") or []
        if isinstance(row, Mapping) and any(
            isinstance(usage, Mapping) and str(usage.get("page_id")) in page_set
            for usage in row.get("usages") or []
        )
    ]
    relation_labels = [
        copy.deepcopy(row) for row in review.get("relation_labels") or []
        if isinstance(row, Mapping) and (
            str(row.get("source_page_id")) in page_set
            or str(row.get("target_node_id")) in page_set
        )
    ]
    packet: dict[str, Any] = {
        "schema": "wikidebia-translation-unit-packet-1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "unit": unit,
        "review_status": review.get("status"),
        "translation_review_sha256": review.get("review_sha256"),
        "translation_review_content_sha256": sha256_bytes(canonical_json(review)),
        "prepared_content_reviewed_copy_sha256": review.get("prepared_content_reviewed_copy_sha256"),
        "current_content_reviewed_copy_sha256": (meta.get("content_reviewed_copy") or {}).get("tree_sha256"),
        "section_mapping": copy.deepcopy(review.get("section_mapping") or {}),
        "arguments": arguments,
        "memory_reuse": [copy.deepcopy(reused_by_id[page_id]) for page_id in page_ids if page_id in reused_by_id],
        "memory_stale_rejected": [copy.deepcopy(stale_by_id[page_id]) for page_id in page_ids if page_id in stale_by_id],
        "vocabulary": vocabulary,
        "relation_labels": relation_labels,
        "counts": {
            "arguments": len(arguments),
            "unit_arguments": len(page_ids),
            "memory_reused": sum(page_id in reused_by_id for page_id in page_ids),
            "memory_stale_rejected": sum(page_id in stale_by_id for page_id in page_ids),
            "changed_french_sources": changed_sources,
            "vocabulary": len(vocabulary),
            "relation_labels": len(relation_labels),
        },
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    packet["packet_sha256"] = sha_object(packet)
    output_dir = workspace / "audits/translation-packets"
    output_json = output_dir / f"{unit_id}.json"
    output_md = output_dir / f"{unit_id}.md"
    write_json(output_json, packet)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_markdown(packet), encoding="utf-8", newline="\n")
    return {
        **packet,
        "packet_path": relative_to_project(output_json, project_root),
        "packet_markdown_path": relative_to_project(output_md, project_root),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--reuse-memory", action="store_true")
    parser.add_argument("--memory-root", type=Path, default=Path("translation-memory"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = build_packet(
        args.project_root, args.debate_id, args.work_id, args.unit_id,
        reuse_memory=args.reuse_memory, memory_root=args.memory_root,
    )
    if args.machine_readable:
        print(json.dumps({key: result[key] for key in (
            "schema", "debate_id", "work_id", "unit", "counts", "packet_sha256",
            "packet_path", "packet_markdown_path", "remote_access_performed",
            "remote_write_performed",
        )}, ensure_ascii=False, sort_keys=True))
    else:
        print(_render_markdown(result), end="")
        print("JSON : " + result["packet_path"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        TranslationPacketError, TranslationMemoryError, TranslationReviewError, RenderError,
        WorkspaceError, CorpusBuildError, OSError, ValueError,
    ) as exc:
        print(f"PAQUET DE TRADUCTION BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
