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
    parser.add_argument("action", choices=("export", "verify"))
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
