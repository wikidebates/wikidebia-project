#!/usr/bin/env python3
"""Run deterministic checks on one translation-unit patch before sealing it."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from wikidebia_corpus_build import load_json, relative_to_project, validate_debate_id, write_json
from wikidebia_editorial_workspace import WorkspaceError, validate_work_id
from wikidebia_render import _load_workspace
from wikidebia_translation_packet import TranslationPacketError, build_packet
from wikidebia_translation_review import _english_capitalization_issues, _title_format_issues
from wikidebia_update import sha_object


PREFLIGHT_SCHEMA = "wikidebia-translation-mechanical-preflight-1.0"
IMMUTABLE_CONTEXT_FIELDS = {"page_origin", "source_page_origin", "preserved_parameters"}
RELATIONSHIP_FIELDS = {"justifications", "objections", "justification", "objection"}
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class TranslationPreflightError(WorkspaceError):
    pass


def _finding(code: str, location: str, message: str) -> dict[str, str]:
    return {"code": code, "location": location, "message": message}


def _walk_forbidden(value: Any, location: str, findings: list[dict[str, str]]) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_location = f"{location}.{key}"
            if str(key) in RELATIONSHIP_FIELDS:
                findings.append(_finding(
                    "relationship_field_forbidden", child_location,
                    "Les relations du graphe ne sont jamais éditables dans une traduction",
                ))
            _walk_forbidden(child, child_location, findings)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_forbidden(child, f"{location}[{index}]", findings)


def analyze_patch(patch: Mapping[str, Any], packet: Mapping[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    packet_arguments = {str(row.get("id")): row for row in packet.get("arguments") or []}
    patch_arguments = {str(row.get("id")): row for row in patch.get("arguments") or [] if isinstance(row, Mapping)}
    for page_id, source in packet_arguments.items():
        location = f"arguments.{page_id}"
        supplied = patch_arguments.get(page_id)
        if supplied is None:
            findings.append(_finding("argument_missing", location, "Argument absent du correctif"))
            continue
        translation = supplied.get("translation")
        expected = source.get("translation") or {}
        if not isinstance(translation, Mapping):
            findings.append(_finding("translation_invalid", location, "Bloc de traduction invalide"))
            continue
        if source.get("source_changed") is True:
            findings.append(_finding(
                "french_source_changed", location,
                "La source française a changé depuis la préparation de la revue",
            ))
        for field in IMMUTABLE_CONTEXT_FIELDS:
            if translation.get(field) != expected.get(field):
                findings.append(_finding(
                    "work_context_modified", f"{location}.translation.{field}",
                    "Champ de contexte du Work modifié",
                ))
        _walk_forbidden(translation, f"{location}.translation", findings)
        for field in ("canonical_title", "displayed_title"):
            value = translation.get(field)
            text = str(value or "")
            field_location = f"{location}.translation.{field}"
            if not text.strip():
                findings.append(_finding("title_empty", field_location, "Titre anglais vide"))
                continue
            if text != text.strip():
                findings.append(_finding("outer_whitespace", field_location, "Espaces externes déterministes"))
            for issue in _title_format_issues(text, canonical=field == "canonical_title"):
                findings.append(_finding("title_" + issue, field_location, issue))
            if CONTROL_CHARACTERS.search(text):
                findings.append(_finding("control_character", field_location, "Caractère de contrôle interdit"))

    english_terms: dict[str, str] = {}
    for row in patch.get("vocabulary") or []:
        if not isinstance(row, Mapping):
            continue
        concept_id = str(row.get("concept_id") or row.get("fr") or "?")
        location = f"vocabulary.{concept_id}.en"
        value = str(row.get("en") or "")
        if not value.strip():
            findings.append(_finding("vocabulary_empty", location, "Équivalent anglais vide"))
            continue
        if value != value.strip():
            findings.append(_finding("outer_whitespace", location, "Espaces externes déterministes"))
        kind = str(row.get("en_kind") or row.get("kind") or "")
        for issue in _english_capitalization_issues(value.strip(), kind):
            findings.append(_finding("vocabulary_" + issue, location, issue))
        key = value.strip().casefold()
        previous = english_terms.get(key)
        if previous is not None and previous != concept_id:
            findings.append(_finding(
                "vocabulary_duplicate", location,
                f"Équivalent déjà utilisé par {previous}",
            ))
        english_terms.setdefault(key, concept_id)
        if CONTROL_CHARACTERS.search(value):
            findings.append(_finding("control_character", location, "Caractère de contrôle interdit"))

    for row in patch.get("relation_labels") or []:
        if not isinstance(row, Mapping):
            continue
        relation_id = str(row.get("id") or "?")
        location = f"relation_labels.{relation_id}.translated_text"
        value = str(row.get("translated_text") or "")
        if not value.strip():
            findings.append(_finding("relation_label_empty", location, "Libellé relationnel anglais vide"))
        elif value != value.strip():
            findings.append(_finding("outer_whitespace", location, "Espaces externes déterministes"))
        if CONTROL_CHARACTERS.search(value):
            findings.append(_finding("control_character", location, "Caractère de contrôle interdit"))
    return findings


def run_preflight(
    project_root: Path,
    debate_id: str,
    work_id: str,
    unit_id: str,
    *,
    patch: Mapping[str, Any] | None = None,
    packet: Mapping[str, Any] | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    if workspace is None:
        workspace, _meta = _load_workspace(project_root, debate_id, work_id)
    patch_path = workspace / "reviews/en/unit-patches" / f"{unit_id}.json"
    patch = dict(patch) if patch is not None else load_json(patch_path, "correctif d’unité")
    packet = dict(packet) if packet is not None else build_packet(
        project_root, debate_id, work_id, unit_id,
    )
    if patch.get("base_packet_sha256") != packet.get("packet_sha256"):
        raise TranslationPreflightError("Le correctif repose sur un paquet obsolète")
    findings = analyze_patch(patch, packet)
    report: dict[str, Any] = {
        "schema": PREFLIGHT_SCHEMA,
        "status": "passed" if not findings else "blocked",
        "debate_id": debate_id,
        "work_id": work_id,
        "unit_id": unit_id,
        "packet_sha256": packet["packet_sha256"],
        "patch_content_sha256": sha_object(patch),
        "findings": findings,
        "counts": {"blocking": len(findings)},
        "semantic_review_performed": False,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }
    report["preflight_sha256"] = sha_object(report)
    output = workspace / "audits/translation-preflight" / f"{unit_id}.json"
    write_json(output, report)
    return {**report, "preflight_path": relative_to_project(output, project_root)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--unit-id", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_preflight(args.project_root, args.debate_id, args.work_id, args.unit_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True) if args.machine_readable else json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TranslationPreflightError, TranslationPacketError, WorkspaceError, OSError, ValueError, KeyError) as exc:
        print(f"PRÉFLIGHT MÉCANIQUE BLOQUÉ : {exc}", file=os.sys.stderr)
        raise SystemExit(2)
