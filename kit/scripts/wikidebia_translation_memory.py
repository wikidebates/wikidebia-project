#!/usr/bin/env python3
"""Export and verify a signed translation memory shared by several debates."""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import unicodedata
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
from wikidebia_translation_review import (
    TRANSLATION_REVIEW_SCHEMA,
    _assert_content_copy,
    _source_snapshot,
    translation_review_sha256,
)
from wikidebia_update import sha_object


INDEX_SCHEMA = "wikidebia-translation-memory-index-1.0"
ENTRY_SCHEMA = "wikidebia-translation-memory-entry-1.0"
LANGUAGE_PAIR = {"source": "fr", "target": "en"}
NON_PORTABLE_TRANSLATION_FIELDS = {"french", "existing_english_update"}
WORK_CONTEXT_FIELDS = {
    "french", "existing_english_update", "page_origin",
    "source_page_origin", "preserved_parameters",
}
REUSE_RECEIPT_SCHEMA = "wikidebia-translation-memory-reuse-1.0"


class TranslationMemoryError(WorkspaceError):
    pass


def _signed(value: Mapping[str, Any], field: str) -> bool:
    body = dict(value)
    claimed = body.pop(field, None)
    return bool(claimed) and claimed == sha_object(body)


def _normal_title(value: Any) -> str:
    title = re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()
    if not title:
        raise TranslationMemoryError("Titre canonique français absent")
    return title


def _source_revision(metadata: Mapping[str, Any], content: Mapping[str, Any]) -> tuple[str, str]:
    candidates = [
        str(metadata.get("source_import_sha256") or ""),
        str(content.get("import_sha256") or ""),
    ]
    hashes = {value for value in candidates if value}
    if len(hashes) > 1:
        raise TranslationMemoryError("Empreintes d’import françaises contradictoires")
    if hashes:
        return "source_import_sha256", hashes.pop()
    return "source_snapshot_sha256", sha256_bytes(
        canonical_json({"metadata": metadata, "content": content})
    )


def _memory_key(title: str, revision_sha256: str) -> str:
    return sha_object({
        "source_language": LANGUAGE_PAIR["source"],
        "target_language": LANGUAGE_PAIR["target"],
        "canonical_title": title,
        "source_revision_sha256": revision_sha256,
    })


def _portable_translation(value: Mapping[str, Any]) -> dict[str, Any]:
    portable = copy.deepcopy(dict(value))
    for field in NON_PORTABLE_TRANSLATION_FIELDS:
        portable.pop(field, None)
    return portable


def _reusable_translation(value: Mapping[str, Any]) -> dict[str, Any]:
    reusable = copy.deepcopy(dict(value))
    for field in WORK_CONTEXT_FIELDS:
        reusable.pop(field, None)
    return reusable


def _remap_page_ids(value: Any, old_page_id: str, new_page_id: str) -> Any:
    if isinstance(value, dict):
        return {key: _remap_page_ids(item, old_page_id, new_page_id) for key, item in value.items()}
    if isinstance(value, list):
        return [_remap_page_ids(item, old_page_id, new_page_id) for item in value]
    if isinstance(value, str):
        if value == old_page_id:
            return new_page_id
        if value.startswith(old_page_id + "-"):
            return new_page_id + value[len(old_page_id):]
    return value


def _reuse_receipt_path(workspace: Path) -> Path:
    return workspace / "audits/translation-memory/reuse.json"


def _empty_index() -> dict[str, Any]:
    index: dict[str, Any] = {
        "schema": INDEX_SCHEMA,
        "language_pair": copy.deepcopy(LANGUAGE_PAIR),
        "entries": [],
        "index_sha256": None,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    index["index_sha256"] = sha_object({key: value for key, value in index.items() if key != "index_sha256"})
    return index


def _load_index(memory_root: Path) -> dict[str, Any]:
    path = memory_root / "index.json"
    if not path.is_file():
        return _empty_index()
    index = load_json(path, "index de mémoire de traduction")
    if index.get("schema") != INDEX_SCHEMA or index.get("language_pair") != LANGUAGE_PAIR:
        raise TranslationMemoryError("Schéma ou paire de langues de la mémoire invalide")
    if not _signed(index, "index_sha256"):
        raise TranslationMemoryError("Empreinte de l’index de traduction invalide")
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise TranslationMemoryError("Entrées de l’index de traduction invalides")
    keys = [str(row.get("memory_key")) for row in entries if isinstance(row, Mapping)]
    if len(keys) != len(entries) or len(keys) != len(set(keys)) or keys != sorted(keys):
        raise TranslationMemoryError("Index de traduction non unique ou non trié")
    return index


def _object_path(memory_root: Path, entry_sha256: str) -> Path:
    return memory_root / "objects" / f"{entry_sha256}.json"


def verify_memory(project_root: Path, memory_root: Path) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    memory_root = memory_root if memory_root.is_absolute() else project_root / memory_root
    memory_root = memory_root.resolve()
    index = _load_index(memory_root)
    for row in index["entries"]:
        entry_sha256 = str(row.get("entry_sha256") or "")
        path = _object_path(memory_root, entry_sha256)
        expected_relative = f"objects/{entry_sha256}.json"
        if row.get("object_path") != expected_relative or not path.is_file():
            raise TranslationMemoryError(f"Objet de traduction absent : {expected_relative}")
        entry = load_json(path, "objet de mémoire de traduction")
        if entry.get("schema") != ENTRY_SCHEMA or not _signed(entry, "entry_sha256"):
            raise TranslationMemoryError(f"Objet de traduction invalide : {expected_relative}")
        if entry.get("entry_sha256") != entry_sha256 or entry.get("memory_key") != row.get("memory_key"):
            raise TranslationMemoryError(f"Objet et index divergents : {expected_relative}")
        if entry.get("translation_sha256") != sha_object(entry.get("translation") or {}):
            raise TranslationMemoryError(f"Traduction altérée : {expected_relative}")
        for field in NON_PORTABLE_TRANSLATION_FIELDS:
            if field in (entry.get("translation") or {}):
                raise TranslationMemoryError(f"Champ non portable dans la mémoire : {field}")
    return {
        "status": "valid",
        "memory_root": relative_to_project(memory_root, project_root),
        "index_sha256": index["index_sha256"],
        "entries": len(index["entries"]),
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def _memory_objects(memory_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    index = _load_index(memory_root)
    by_key: dict[str, dict[str, Any]] = {}
    by_title: dict[str, list[dict[str, Any]]] = {}
    for row in index["entries"]:
        entry = load_json(
            _object_path(memory_root, str(row["entry_sha256"])),
            "objet de mémoire de traduction",
        )
        by_key[str(row["memory_key"])] = entry
        by_title.setdefault(str(row["canonical_title"]), []).append(row)
    return index, by_key, by_title


def verified_reuse_coverage(
    workspace: Path,
    review_by_id: Mapping[str, Mapping[str, Any]],
    metadata_by_id: Mapping[str, Mapping[str, Any]],
    content_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    path = _reuse_receipt_path(workspace)
    if not path.is_file():
        return [], []
    receipt = load_json(path, "reçu de réutilisation de traduction")
    if receipt.get("schema") != REUSE_RECEIPT_SCHEMA or not _signed(receipt, "receipt_sha256"):
        raise TranslationMemoryError("Reçu de réutilisation de traduction invalide")
    for reused in receipt.get("reused") or []:
        page_id = str(reused.get("page_id") or "")
        review_row = review_by_id.get(page_id)
        metadata, content = metadata_by_id.get(page_id), content_by_id.get(page_id)
        if review_row is None or metadata is None or content is None:
            raise TranslationMemoryError(f"Source réutilisée absente du Work : {page_id}")
        _kind, revision_sha256 = _source_revision(metadata, content)
        current_translation = (review_row.get("translation") or {})
        if (
            revision_sha256 != reused.get("source_revision_sha256")
            or sha_object(_reusable_translation(current_translation))
            != reused.get("applied_translation_sha256")
        ):
            raise TranslationMemoryError(f"Réutilisation devenue obsolète ou modifiée : {page_id}")
    return copy.deepcopy(receipt.get("reused") or []), copy.deepcopy(receipt.get("stale_rejected") or [])


def reuse_review(
    project_root: Path, debate_id: str, work_id: str, memory_root: Path,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    memory_root = memory_root if memory_root.is_absolute() else project_root / memory_root
    memory_root = memory_root.resolve()
    verify_memory(project_root, memory_root)
    index, entries_by_key, entries_by_title = _memory_objects(memory_root)
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    source = _assert_content_copy(workspace, meta)
    review_path = workspace / "reviews/en/translation_review.json"
    review = load_json(review_path, "revue anglaise")
    if (
        review.get("schema") != TRANSLATION_REVIEW_SCHEMA
        or review.get("debate_id") != debate_id
        or review.get("work_id") != work_id
        or review.get("status") != "draft"
        or review.get("review_sha256") not in {None, ""}
    ):
        raise TranslationMemoryError("La réutilisation exige une revue anglaise brouillon non scellée")
    _registry, metadata_lock, content_lock, _vocabulary = _source_snapshot(source)
    metadata_by_id = {
        str(row.get("entity_id") or row.get("id")): row
        for row in metadata_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    content_by_id = {
        str(row.get("id")): row
        for row in content_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    before_sha256 = sha256_bytes(canonical_json(review))
    reused: list[dict[str, Any]] = []
    stale_rejected: list[dict[str, Any]] = []
    changed = 0
    for row in review.get("arguments") or []:
        if not isinstance(row, dict):
            continue
        page_id = str(row.get("id") or "")
        metadata, content = metadata_by_id.get(page_id), content_by_id.get(page_id)
        translation = row.get("translation")
        if not page_id or metadata is None or content is None or not isinstance(translation, Mapping):
            raise TranslationMemoryError(f"Données source ou traduction absentes : {page_id or '?'}")
        title = _normal_title(metadata.get("canonical_title") or content.get("canonical_title"))
        _revision_kind, revision_sha256 = _source_revision(metadata, content)
        key = _memory_key(title, revision_sha256)
        entry = entries_by_key.get(key)
        if entry is None:
            stale = entries_by_title.get(title) or []
            if stale:
                stale_rejected.append({
                    "page_id": page_id,
                    "canonical_title": title,
                    "current_source_revision_sha256": revision_sha256,
                    "memory_source_revision_sha256": sorted(
                        str(candidate["source_revision_sha256"]) for candidate in stale
                    ),
                    "reason": "source_revision_changed",
                })
            continue
        origin_page_id = str((entry.get("origin") or {}).get("page_id") or "")
        reusable = _remap_page_ids(
            _reusable_translation(entry.get("translation") or {}), origin_page_id, page_id,
        )
        candidate = copy.deepcopy(reusable)
        for field in WORK_CONTEXT_FIELDS:
            if field in translation:
                candidate[field] = copy.deepcopy(translation[field])
        applied_sha256 = sha_object(_reusable_translation(candidate))
        current_reusable_sha256 = sha_object(_reusable_translation(translation))
        if translation.get("status") == "approved" and current_reusable_sha256 != applied_sha256:
            raise TranslationMemoryError(
                f"Traduction approuvée divergente déjà présente dans le Work : {page_id}"
            )
        if dict(translation) != candidate:
            row["translation"] = candidate
            changed += 1
        reused.append({
            "page_id": page_id,
            "memory_key": key,
            "entry_sha256": entry["entry_sha256"],
            "origin_page_id": origin_page_id,
            "source_revision_sha256": revision_sha256,
            "applied_translation_sha256": applied_sha256,
        })
    write_json(review_path, review)
    after_sha256 = sha256_bytes(canonical_json(review))
    receipt: dict[str, Any] = {
        "schema": REUSE_RECEIPT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "memory_index_sha256": index["index_sha256"],
        "review_before_sha256": before_sha256,
        "review_after_sha256": after_sha256,
        "reused": reused,
        "stale_rejected": stale_rejected,
        "counts": {
            "matched": len(reused),
            "changed": changed,
            "already_identical": len(reused) - changed,
            "stale_rejected": len(stale_rejected),
        },
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    receipt_path = _reuse_receipt_path(workspace)
    write_json(receipt_path, receipt)
    return {
        "status": "reused",
        "debate_id": debate_id,
        "work_id": work_id,
        "memory_index_sha256": index["index_sha256"],
        "receipt_path": relative_to_project(receipt_path, project_root),
        "receipt_sha256": receipt["receipt_sha256"],
        **receipt["counts"],
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def export_review(
    project_root: Path, debate_id: str, work_id: str, memory_root: Path,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    memory_root = memory_root if memory_root.is_absolute() else project_root / memory_root
    memory_root = memory_root.resolve()
    workspace, meta = _load_workspace(project_root, debate_id, work_id)
    source = _assert_content_copy(workspace, meta)
    review = load_json(workspace / "reviews/en/translation_review.json", "revue anglaise")
    if (
        review.get("schema") != TRANSLATION_REVIEW_SCHEMA
        or review.get("debate_id") != debate_id
        or review.get("work_id") != work_id
        or review.get("status") != "approved"
    ):
        raise TranslationMemoryError("Seule une revue anglaise approuvée et identifiée peut être exportée")
    if not review.get("review_sha256") or review.get("review_sha256") != translation_review_sha256(review):
        raise TranslationMemoryError("Empreinte de la revue anglaise invalide")

    _registry, metadata_lock, content_lock, _vocabulary = _source_snapshot(source)
    metadata_by_id = {
        str(row.get("entity_id") or row.get("id")): row
        for row in metadata_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    content_by_id = {
        str(row.get("id")): row
        for row in content_lock.get("arguments") or [] if isinstance(row, Mapping)
    }
    index = _load_index(memory_root)
    indexed = {str(row["memory_key"]): row for row in index["entries"]}
    added = reused = 0
    for row in review.get("arguments") or []:
        if not isinstance(row, Mapping):
            continue
        page_id = str(row.get("id") or "")
        translation = row.get("translation")
        metadata, content = metadata_by_id.get(page_id), content_by_id.get(page_id)
        if not page_id or not isinstance(translation, Mapping) or metadata is None or content is None:
            raise TranslationMemoryError(f"Données source ou traduction absentes : {page_id or '?'}")
        if translation.get("status") != "approved":
            raise TranslationMemoryError(f"Traduction non approuvée dans une revue finalisée : {page_id}")
        title = _normal_title(metadata.get("canonical_title") or content.get("canonical_title"))
        revision_kind, revision_sha256 = _source_revision(metadata, content)
        memory_key = _memory_key(title, revision_sha256)
        portable = _portable_translation(translation)
        translation_sha256 = sha_object(portable)
        current = indexed.get(memory_key)
        if current is not None:
            if current.get("translation_sha256") != translation_sha256:
                raise TranslationMemoryError(
                    f"Traductions divergentes pour la même source française : {title}"
                )
            reused += 1
            continue
        entry: dict[str, Any] = {
            "schema": ENTRY_SCHEMA,
            "memory_key": memory_key,
            "language_pair": copy.deepcopy(LANGUAGE_PAIR),
            "source_identity": {
                "entity_type": "argument",
                "canonical_title": title,
                "identity_sha256": sha_object({"language": "fr", "canonical_title": title}),
            },
            "source_revision": {"kind": revision_kind, "sha256": revision_sha256},
            "translation": portable,
            "translation_sha256": translation_sha256,
            "origin": {
                "debate_id": debate_id,
                "work_id": work_id,
                "page_id": page_id,
                "translation_review_sha256": review["review_sha256"],
                "finalized_at": review.get("finalized_at"),
            },
            "remote_access_performed": False,
            "remote_write_performed": False,
        }
        entry["entry_sha256"] = sha_object(entry)
        object_path = _object_path(memory_root, entry["entry_sha256"])
        write_json(object_path, entry)
        indexed[memory_key] = {
            "memory_key": memory_key,
            "canonical_title": title,
            "source_revision_sha256": revision_sha256,
            "translation_sha256": translation_sha256,
            "entry_sha256": entry["entry_sha256"],
            "object_path": f"objects/{entry['entry_sha256']}.json",
        }
        added += 1
    index["entries"] = [indexed[key] for key in sorted(indexed)]
    index["index_sha256"] = None
    index["index_sha256"] = sha_object({key: value for key, value in index.items() if key != "index_sha256"})
    write_json(memory_root / "index.json", index)
    verification = verify_memory(project_root, memory_root)
    return {
        "status": "exported",
        "debate_id": debate_id,
        "work_id": work_id,
        "memory_root": verification["memory_root"],
        "index_sha256": verification["index_sha256"],
        "entries": verification["entries"],
        "entries_added": added,
        "entries_reused": reused,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "verify", "reuse"))
    parser.add_argument("debate_id", nargs="?")
    parser.add_argument("--work-id")
    parser.add_argument("--memory-root", type=Path, default=Path("translation-memory"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "export":
        if not args.debate_id or not args.work_id:
            raise TranslationMemoryError("export exige debate_id et --work-id")
        result = export_review(args.project_root, args.debate_id, args.work_id, args.memory_root)
    elif args.action == "reuse":
        if not args.debate_id or not args.work_id:
            raise TranslationMemoryError("reuse exige debate_id et --work-id")
        result = reuse_review(args.project_root, args.debate_id, args.work_id, args.memory_root)
    else:
        result = verify_memory(args.project_root, args.memory_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationMemoryError, WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"MÉMOIRE DE TRADUCTION BLOQUÉE : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
