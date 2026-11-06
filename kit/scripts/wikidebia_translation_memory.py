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
FIELD_INDEX_SCHEMA = "wikidebia-translation-field-memory-index-1.0"
FIELD_ENTRY_SCHEMA = "wikidebia-translation-field-memory-entry-1.0"
FIELD_REUSE_RECEIPT_SCHEMA = "wikidebia-translation-field-memory-reuse-1.0"


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


def _field_reuse_receipt_path(workspace: Path) -> Path:
    return workspace / "audits/translation-memory/field-reuse.json"


def _field_memory_key(field_kind: str, source_value: Any, canonical_title: str) -> str:
    return sha_object({
        "source_language": LANGUAGE_PAIR["source"],
        "target_language": LANGUAGE_PAIR["target"],
        "field_kind": field_kind,
        "canonical_title": _normal_title(canonical_title),
        "source_value_sha256": sha_object(source_value),
    })


def _field_index_path(memory_root: Path) -> Path:
    return memory_root / "fields/index.json"


def _field_object_path(memory_root: Path, entry_sha256: str) -> Path:
    return memory_root / "fields/objects" / f"{entry_sha256}.json"


def _empty_field_index() -> dict[str, Any]:
    index: dict[str, Any] = {
        "schema": FIELD_INDEX_SCHEMA,
        "language_pair": copy.deepcopy(LANGUAGE_PAIR),
        "entries": [],
        "index_sha256": None,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    index["index_sha256"] = sha_object({
        key: value for key, value in index.items() if key != "index_sha256"
    })
    return index


def _load_field_index(memory_root: Path) -> dict[str, Any]:
    path = _field_index_path(memory_root)
    if not path.is_file():
        return _empty_field_index()
    index = load_json(path, "index de mémoire de champs")
    if index.get("schema") != FIELD_INDEX_SCHEMA or index.get("language_pair") != LANGUAGE_PAIR:
        raise TranslationMemoryError("Schéma ou paire de langues de la mémoire de champs invalide")
    if not _signed(index, "index_sha256"):
        raise TranslationMemoryError("Empreinte de l’index de champs invalide")
    entries = index.get("entries")
    keys = [str(row.get("memory_key")) for row in entries or [] if isinstance(row, Mapping)]
    if not isinstance(entries, list) or len(keys) != len(entries) or keys != sorted(keys):
        raise TranslationMemoryError("Index de champs invalide ou non trié")
    if len(keys) != len(set(keys)):
        raise TranslationMemoryError("Index de champs non unique")
    return index


def _source_scalar(metadata: Mapping[str, Any], content: Mapping[str, Any], field: str) -> Any:
    if field == "canonical_title":
        return metadata.get("canonical_title") or content.get("canonical_title")
    return metadata.get(field) if metadata.get(field) not in {None, ""} else content.get(field)


def _field_candidates(
    metadata: Mapping[str, Any], content: Mapping[str, Any], translation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field in ("canonical_title", "displayed_title", "summary"):
        source_value = _source_scalar(metadata, content, field)
        target_value = translation.get(field)
        if source_value not in {None, ""} and target_value not in {None, ""}:
            candidates.append({
                "field_kind": field,
                "source_value": copy.deepcopy(source_value),
                "target_value": copy.deepcopy(target_value),
                "target_path": field,
            })
    for citation in translation.get("citations") or []:
        if not isinstance(citation, Mapping):
            continue
        source = citation.get("source") or {}
        source_value = source.get("citation") if isinstance(source, Mapping) else None
        target_value = citation.get("translated_citation")
        if source_value not in {None, ""} and target_value not in {None, ""}:
            candidates.append({
                "field_kind": "citation",
                "source_value": copy.deepcopy(source_value),
                "target_value": copy.deepcopy(target_value),
                "target_path": f"citations/{citation.get('id') or '?'}",
            })
    return candidates


def _apply_field_candidate(
    translation: dict[str, Any], field_kind: str, source_value: Any, target_value: Any,
) -> tuple[bool, str] | None:
    if field_kind in {"canonical_title", "displayed_title", "summary"}:
        current = translation.get(field_kind)
        if translation.get("status") == "approved" and current not in {None, "", target_value}:
            raise TranslationMemoryError(
                f"Champ approuvé divergent pour une même source : {field_kind}"
            )
        changed = current != target_value
        translation[field_kind] = copy.deepcopy(target_value)
        return changed, field_kind
    if field_kind == "citation":
        matches = []
        for citation in translation.get("citations") or []:
            source = citation.get("source") if isinstance(citation, Mapping) else None
            if isinstance(source, Mapping) and source.get("citation") == source_value:
                matches.append(citation)
        if not matches:
            return None
        if len(matches) != 1:
            raise TranslationMemoryError("Citation française dupliquée dans une même traduction")
        citation = matches[0]
        current = citation.get("translated_citation")
        if citation.get("status") == "approved" and current not in {None, "", target_value}:
            raise TranslationMemoryError("Citation approuvée divergente pour une même source")
        changed = current != target_value
        citation["translated_citation"] = copy.deepcopy(target_value)
        return changed, f"citations/{citation.get('id') or '?'}"
    raise TranslationMemoryError(f"Type de champ de traduction inconnu : {field_kind}")


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
    field_index = _load_field_index(memory_root)
    for row in field_index["entries"]:
        entry_sha256 = str(row.get("entry_sha256") or "")
        path = _field_object_path(memory_root, entry_sha256)
        expected_relative = f"fields/objects/{entry_sha256}.json"
        if row.get("object_path") != expected_relative or not path.is_file():
            raise TranslationMemoryError(f"Objet de champ absent : {expected_relative}")
        entry = load_json(path, "objet de mémoire de champ")
        if entry.get("schema") != FIELD_ENTRY_SCHEMA or not _signed(entry, "entry_sha256"):
            raise TranslationMemoryError(f"Objet de champ invalide : {expected_relative}")
        if entry.get("entry_sha256") != entry_sha256 or entry.get("memory_key") != row.get("memory_key"):
            raise TranslationMemoryError(f"Objet de champ et index divergents : {expected_relative}")
        if entry.get("source_value_sha256") != sha_object(entry.get("source_value")):
            raise TranslationMemoryError(f"Source de champ altérée : {expected_relative}")
        if entry.get("target_value_sha256") != sha_object(entry.get("target_value")):
            raise TranslationMemoryError(f"Traduction de champ altérée : {expected_relative}")
        expected_key = _field_memory_key(
            str(entry.get("field_kind")), entry.get("source_value"),
            str((entry.get("source_identity") or {}).get("canonical_title") or ""),
        )
        if entry.get("memory_key") != expected_key:
            raise TranslationMemoryError(f"Clé de champ invalide : {expected_relative}")
    return {
        "status": "valid",
        "memory_root": relative_to_project(memory_root, project_root),
        "index_sha256": index["index_sha256"],
        "entries": len(index["entries"]),
        "field_entries": len(field_index["entries"]),
        "field_index_sha256": field_index["index_sha256"],
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def _field_memory_objects(memory_root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    index = _load_field_index(memory_root)
    entries = {
        str(row["memory_key"]): load_json(
            _field_object_path(memory_root, str(row["entry_sha256"])),
            "objet de mémoire de champ",
        )
        for row in index["entries"]
    }
    return index, entries


def _reuse_fields(
    workspace: Path,
    debate_id: str,
    work_id: str,
    review: dict[str, Any],
    metadata_by_id: Mapping[str, Mapping[str, Any]],
    content_by_id: Mapping[str, Mapping[str, Any]],
    memory_root: Path,
) -> dict[str, Any]:
    index, entries = _field_memory_objects(memory_root)
    before_sha256 = sha256_bytes(canonical_json(review))
    reused: list[dict[str, Any]] = []
    changed = 0
    for row in review.get("arguments") or []:
        if not isinstance(row, dict):
            continue
        page_id = str(row.get("id") or "")
        metadata, content = metadata_by_id.get(page_id), content_by_id.get(page_id)
        translation = row.get("translation")
        if metadata is None or content is None or not isinstance(translation, dict):
            continue
        canonical_title = _normal_title(
            metadata.get("canonical_title") or content.get("canonical_title")
        )
        source_fields = [
            (field, _source_scalar(metadata, content, field))
            for field in ("canonical_title", "displayed_title", "summary")
        ]
        source_fields.extend(
            ("citation", (citation.get("source") or {}).get("citation"))
            for citation in translation.get("citations") or []
            if isinstance(citation, Mapping) and isinstance(citation.get("source"), Mapping)
        )
        seen_keys: set[str] = set()
        for field_kind, source_value in source_fields:
            if source_value in {None, ""}:
                continue
            key = _field_memory_key(field_kind, source_value, canonical_title)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            entry = entries.get(key)
            if entry is None:
                continue
            applied = _apply_field_candidate(
                translation, field_kind, source_value, entry.get("target_value"),
            )
            if applied is None:
                continue
            did_change, target_path = applied
            changed += int(did_change)
            reused.append({
                "page_id": page_id,
                "field_kind": field_kind,
                "target_path": target_path,
                "memory_key": key,
                "entry_sha256": entry["entry_sha256"],
                "source_value_sha256": entry["source_value_sha256"],
                "target_value_sha256": entry["target_value_sha256"],
                "changed": did_change,
            })
    receipt: dict[str, Any] = {
        "schema": FIELD_REUSE_RECEIPT_SCHEMA,
        "debate_id": debate_id,
        "work_id": work_id,
        "memory_index_sha256": index["index_sha256"],
        "review_before_sha256": before_sha256,
        "review_after_sha256": sha256_bytes(canonical_json(review)),
        "reused": reused,
        "counts": {
            "matched": len(reused),
            "changed": changed,
            "already_identical": len(reused) - changed,
        },
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    receipt["receipt_sha256"] = sha_object(receipt)
    write_json(_field_reuse_receipt_path(workspace), receipt)
    return receipt


def _export_fields(
    memory_root: Path,
    debate_id: str,
    work_id: str,
    review: Mapping[str, Any],
    metadata_by_id: Mapping[str, Mapping[str, Any]],
    content_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    index = _load_field_index(memory_root)
    indexed = {str(row["memory_key"]): row for row in index["entries"]}
    pending_objects: list[tuple[Path, dict[str, Any]]] = []
    added = reused = 0
    for row in review.get("arguments") or []:
        if not isinstance(row, Mapping):
            continue
        page_id = str(row.get("id") or "")
        translation = row.get("translation")
        metadata, content = metadata_by_id.get(page_id), content_by_id.get(page_id)
        if not isinstance(translation, Mapping) or metadata is None or content is None:
            continue
        canonical_title = _normal_title(
            metadata.get("canonical_title") or content.get("canonical_title")
        )
        for candidate in _field_candidates(metadata, content, translation):
            field_kind = str(candidate["field_kind"])
            source_value = candidate["source_value"]
            target_value = candidate["target_value"]
            memory_key = _field_memory_key(field_kind, source_value, canonical_title)
            target_sha256 = sha_object(target_value)
            current = indexed.get(memory_key)
            if current is not None:
                if current.get("target_value_sha256") != target_sha256:
                    raise TranslationMemoryError(
                        f"Traductions de champ divergentes pour une même source : {field_kind}"
                    )
                reused += 1
                continue
            entry: dict[str, Any] = {
                "schema": FIELD_ENTRY_SCHEMA,
                "memory_key": memory_key,
                "language_pair": copy.deepcopy(LANGUAGE_PAIR),
                "field_kind": field_kind,
                "source_identity": {
                    "entity_type": "argument",
                    "canonical_title": canonical_title,
                    "identity_sha256": sha_object({
                        "language": "fr", "canonical_title": canonical_title,
                    }),
                },
                "source_value": source_value,
                "source_value_sha256": sha_object(source_value),
                "target_value": target_value,
                "target_value_sha256": target_sha256,
                "origin": {
                    "debate_id": debate_id,
                    "work_id": work_id,
                    "page_id": page_id,
                    "target_path": candidate["target_path"],
                    "translation_review_sha256": review.get("review_sha256"),
                },
                "remote_access_performed": False,
                "remote_write_performed": False,
            }
            entry["entry_sha256"] = sha_object(entry)
            pending_objects.append((
                _field_object_path(memory_root, entry["entry_sha256"]), entry,
            ))
            indexed[memory_key] = {
                "memory_key": memory_key,
                "field_kind": field_kind,
                "canonical_title": canonical_title,
                "source_value_sha256": entry["source_value_sha256"],
                "target_value_sha256": target_sha256,
                "entry_sha256": entry["entry_sha256"],
                "object_path": f"fields/objects/{entry['entry_sha256']}.json",
            }
            added += 1
    for object_path, entry in pending_objects:
        write_json(object_path, entry)
    index["entries"] = [indexed[key] for key in sorted(indexed)]
    index["index_sha256"] = None
    index["index_sha256"] = sha_object({
        key: value for key, value in index.items() if key != "index_sha256"
    })
    write_json(_field_index_path(memory_root), index)
    return {"field_entries_added": added, "field_entries_reused": reused}


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


def verified_field_reuse_coverage(
    workspace: Path,
    review_by_id: Mapping[str, Mapping[str, Any]],
    metadata_by_id: Mapping[str, Mapping[str, Any]],
    content_by_id: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    path = _field_reuse_receipt_path(workspace)
    if not path.is_file():
        return []
    receipt = load_json(path, "reçu de réutilisation de champs")
    if receipt.get("schema") != FIELD_REUSE_RECEIPT_SCHEMA or not _signed(receipt, "receipt_sha256"):
        raise TranslationMemoryError("Reçu de réutilisation de champs invalide")
    for reused in receipt.get("reused") or []:
        page_id = str(reused.get("page_id") or "")
        row = review_by_id.get(page_id)
        metadata, content = metadata_by_id.get(page_id), content_by_id.get(page_id)
        if row is None or metadata is None or content is None:
            raise TranslationMemoryError(f"Champ réutilisé absent du Work : {page_id}")
        translation = row.get("translation") or {}
        field_kind = str(reused.get("field_kind") or "")
        target_path = str(reused.get("target_path") or "")
        if field_kind == "citation":
            citation_id = target_path.removeprefix("citations/")
            citations = [
                item for item in translation.get("citations") or []
                if isinstance(item, Mapping) and str(item.get("id")) == citation_id
            ]
            if len(citations) != 1:
                raise TranslationMemoryError(f"Citation réutilisée absente : {page_id}/{citation_id}")
            source = citations[0].get("source") or {}
            source_value = source.get("citation") if isinstance(source, Mapping) else None
            target_value = citations[0].get("translated_citation")
        else:
            source_value = _source_scalar(metadata, content, field_kind)
            target_value = translation.get(field_kind)
        if (
            sha_object(source_value) != reused.get("source_value_sha256")
            or sha_object(target_value) != reused.get("target_value_sha256")
        ):
            raise TranslationMemoryError(
                f"Réutilisation de champ devenue obsolète ou modifiée : {page_id}/{target_path}"
            )
    return copy.deepcopy(receipt.get("reused") or [])


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
    field_receipt = _reuse_fields(
        workspace, debate_id, work_id, review,
        metadata_by_id, content_by_id, memory_root,
    )
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
            "field_matched": field_receipt["counts"]["matched"],
            "field_changed": field_receipt["counts"]["changed"],
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
    field_counts = _export_fields(
        memory_root, debate_id, work_id, review,
        metadata_by_id, content_by_id,
    )
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
        **field_counts,
        "field_entries": verification["field_entries"],
        "field_index_sha256": verification["field_index_sha256"],
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
