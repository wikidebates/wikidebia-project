#!/usr/bin/env python3
"""Prepare deterministic, read-only French creation context, never a review receipt.

Excerpts retain their exact source bytes. Corpus mode is explicit and restricted
to new pages; it selects an existing batch or named nodes, without changing any
registry, marking a task complete or replacing the ordinary validation workflow.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

STAGES = ("cadrage", "graphe", "debat-fr", "arguments-fr", "validation-fr")
SCHEMA = "wikidebia-creation-context-1.0"
MAX_INPUT_BYTES = 32 * 1024 * 1024
FORBIDDEN_PARTS = {"private", ".git", ".venv", "logs", "plans", "incoming", "outgoing"}


class CreationContextError(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _relative_path(value: str) -> Path:
    p = PurePosixPath(value)
    if (not value or p.is_absolute() or ".." in p.parts or "\\" in value
            or ":" in value or any(part in FORBIDDEN_PARTS for part in p.parts)):
        raise CreationContextError("Unsafe or private input path")
    return Path(*p.parts)


def _contained(root: Path, path: Path) -> Path:
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise CreationContextError("Path outside project") from exc
    current = root
    for part in rel.parts:
        if part in {"..", "."}:
            raise CreationContextError("Non-canonical path")
        current = current / part
        if current.is_symlink():
            raise CreationContextError("Symlink is not allowed")
    if not path.resolve().is_relative_to(root):
        raise CreationContextError("Resolved path outside project")
    return path


class Inputs:
    def __init__(self, root: Path):
        self.root = root
        self.records: dict[str, dict[str, Any]] = {}

    def read(self, path: Path) -> bytes:
        path = _contained(self.root, path)
        rel = path.relative_to(self.root).as_posix()
        _relative_path(rel)
        if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
            raise CreationContextError("Missing, non-regular or oversized input: " + rel)
        raw = path.read_bytes()
        row = {"path": rel, "sha256": _sha(raw), "size_bytes": len(raw)}
        if rel in self.records and self.records[rel] != row:
            raise CreationContextError("Input changed during preparation: " + rel)
        self.records[rel] = row
        return raw

    def document(self, path: Path) -> dict[str, Any]:
        value = json.loads(self.read(path))
        if not isinstance(value, dict):
            raise CreationContextError("Expected a JSON object")
        return value

    def verify(self) -> None:
        # No context from a mixture of before/after input versions may be saved.
        for record in list(self.records.values()):
            self.read(self.root / record["path"])


def split_sections(raw: bytes) -> tuple[bytes, list[dict[str, Any]]]:
    """Split H2/H3 sections while ignoring fenced code; keep byte-exact slices."""
    raw.decode("utf-8")
    lines = raw.splitlines(keepends=True)
    headings: list[tuple[int, str]] = []
    fence: bytes | None = None
    fence_length = 0
    for index, line in enumerate(lines):
        match = re.match(rb"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence, fence_length = marker[:1], len(marker)
            elif marker[:1] == fence and len(marker) >= fence_length:
                fence = None
            continue
        if fence is None and re.match(rb"^#{2,3} ", line):
            headings.append((index, line.decode("utf-8").rstrip("\r\n")))
    if fence is not None or not headings:
        raise CreationContextError("Unclosed code fence or missing norm sections")
    result = []
    for pos, (start, heading) in enumerate(headings):
        end = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines)
        result.append({"heading": heading, "start_line": start + 1, "end_line": end,
                       "raw": b"".join(lines[start:end])})
    return b"".join(lines[:headings[0][0]]), result


def normative_context(inputs: Inputs, stage: str) -> tuple[bytes, dict[str, Any]]:
    root = inputs.root
    version = inputs.document(root / "norms/VERSIONS.json").get("norm", "")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise CreationContextError("Invalid norm source locator")
    path = root / f"norms/normative_reference/01_normes/WIKIDEBIA_NORME_CONSOLIDEE_{version}.md"
    raw = inputs.read(path)
    policy = inputs.document(root / "kit/configs/creation_context_sections.json")
    if policy.get("schema") != "wikidebia-creation-context-sections-1.0" or policy.get("stages") != list(STAGES):
        raise CreationContextError("Unsupported section selection policy")
    prologue, sections = split_sections(raw)
    rows = policy.get("sections")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise CreationContextError("Invalid section selection policy")
    if [s["heading"] for s in sections] != [r.get("heading") for r in rows]:
        raise CreationContextError("Norm sections changed; classify every section before reuse")
    if len({s["heading"] for s in sections}) != len(sections):
        raise CreationContextError("Duplicate norm heading")
    pieces = [prologue]
    coverage = []
    for section, row in zip(sections, rows):
        stages = row.get("stages")
        if (not isinstance(stages, list) or not all(s in STAGES for s in stages)
                or len(set(stages)) != len(stages) or not str(row.get("rationale") or "").strip()):
            raise CreationContextError("Invalid or unexplained section classification")
        included = stage in stages
        if included:
            pieces.append(section["raw"])
        coverage.append({k: v for k, v in section.items() if k != "raw"} | {
            "sha256": _sha(section["raw"]), "included": included,
            "rationale": row["rationale"], "applicable_stages": stages,
        })
    selected = b"".join(pieces)
    return selected, {"source_path": path.relative_to(root).as_posix(),
                      "source_bytes": len(raw), "excerpt_bytes": len(selected),
                      "coverage": coverage}


def _indexed(rows: Any, key: str, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise CreationContextError("Invalid " + label)
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get(key), str) or not row[key] or row[key] in out:
            raise CreationContextError("Missing or duplicate identity in " + label)
        out[row[key]] = row
    return out


def corpus_context(inputs: Inputs, corpus: Path, stage: str, batch_id: str | None,
                   node_ids: Sequence[str], *, dependency_node_ids: Sequence[str] = ()) -> dict[str, Any]:
    corpus = _contained(inputs.root, corpus)
    manifest = inputs.document(corpus / "manifest.json")
    core = manifest.get("core_files") or {}
    docs = {name: inputs.document(corpus / _relative_path(core[name]))
            for name in ("scope", "registry", "sources")}
    registry, sources = docs["registry"], docs["sources"]
    debate_id = manifest.get("debate_id")
    if (not debate_id or registry.get("debate", {}).get("id") != debate_id
            or docs["scope"].get("debate_id") != debate_id or sources.get("debate_id") != debate_id):
        raise CreationContextError("Corpus identities differ")
    if registry.get("schema", {}).get("registry_version") != "1.0" or sources.get("source_registry_version") != "1.0":
        raise CreationContextError("Unsupported registry format")
    pages = _indexed([p for p in manifest.get("pages", []) if p.get("language") == "fr"], "page_id", "French pages")
    # Missing provenance must not silently turn imported content into a creation.
    if pages.get(debate_id, {}).get("page_origin") != "new" or (corpus / "data/import_provenance.json").exists():
        raise CreationContextError("Corpus mode requires a from-scratch French debate with explicit new provenance")
    graph = registry.get("graph") or {}
    nodes = _indexed(graph.get("nodes"), "id", "nodes")
    nodes = {key: row for key, row in nodes.items() if row.get("status") == "active"}
    edges = list(_indexed(graph.get("edges"), "id", "edges").values())
    occurrences = list(_indexed(graph.get("occurrences"), "id", "occurrences").values())
    for edge in edges:
        if edge.get("parent_node_id") not in nodes or edge.get("child_node_id") not in nodes:
            raise CreationContextError("Edge points outside active graph")
    occurrence_ids = {row["id"] for row in occurrences}
    for occurrence in occurrences:
        if (occurrence.get("node_id") not in nodes or occurrence.get("parent_occurrence_id") not in occurrence_ids | {None}):
            raise CreationContextError("Invalid occurrence reference")
    if batch_id and node_ids:
        raise CreationContextError("Choose a batch or explicit nodes, not both")
    if (len(set(dependency_node_ids)) != len(dependency_node_ids)
            or not set(dependency_node_ids) <= nodes.keys()
            or set(dependency_node_ids) & set(node_ids)
            or (dependency_node_ids and stage != "arguments-fr")):
        raise CreationContextError("Invalid explicit creation dependencies")
    dependencies: set[str] = set(dependency_node_ids)
    if batch_id:
        batch = _indexed(registry.get("batches"), "id", "batches").get(batch_id)
        if not batch or batch.get("language") != "fr" or batch.get("page_type") != "argument" or batch.get("debate_id") != debate_id:
            raise CreationContextError("Unknown or incompatible French argument batch")
        selected = list(batch.get("node_ids") or [])
        dependencies.update(batch.get("dependency_node_ids") or [])
    elif node_ids:
        selected = list(node_ids)
    else:
        if stage == "arguments-fr":
            raise CreationContextError("Select --batch-id or --node-id for argument corpus context")
        selected = list(nodes) if stage in {"graphe", "validation-fr"} else []
    if (batch_id or node_ids) and stage != "arguments-fr":
        raise CreationContextError("Node selection only applies to arguments-fr")
    if (len(set(selected)) != len(selected) or not set(selected) <= nodes.keys()
            or not dependencies <= nodes.keys() or ((batch_id or node_ids) and not selected)):
        raise CreationContextError("Empty, duplicate or unknown selected/dependency node")
    selected_set = set(selected)
    for edge in edges:
        a, b = edge["parent_node_id"], edge["child_node_id"]
        if a in selected_set or b in selected_set:
            dependencies.update((a, b))
    dependencies -= selected_set
    context_ids = selected_set | dependencies
    if stage in {"cadrage", "debat-fr", "validation-fr"}:
        context_ids.add(debate_id)
    for page_id in selected_set | {debate_id}:
        if pages.get(page_id, {}).get("page_origin") != "new":
            raise CreationContextError("Selected page lacks explicit new provenance: " + page_id)
    texts = {}
    for page_id in sorted(context_ids):
        page = pages.get(page_id)
        if page is None:
            raise CreationContextError("Missing page record: " + page_id)
        rel = page.get("file_path")
        if not isinstance(rel, str) or not rel.startswith("output/fr/") or not rel.endswith(".wiki"):
            raise CreationContextError("Non-canonical French page path")
        path = _contained(inputs.root, corpus / _relative_path(rel))
        if not path.exists():
            if page.get("status") in {"validated", "published"} or page.get("sha256"):
                raise CreationContextError("Recorded page file is missing: " + page_id)
            continue
        raw = inputs.read(path)
        if page.get("sha256") and page["sha256"] != _sha(raw):
            raise CreationContextError("Page checksum differs: " + page_id)
        texts[page_id] = {"text": raw.decode("utf-8"), "sha256": _sha(raw),
                          "declared_status": page.get("status"), "page_origin": page.get("page_origin")}
    source_index = _indexed(sources.get("sources"), "id", "documentary sources")
    source_ids = set()
    for node_id in context_ids - {debate_id}:
        refs = (nodes[node_id].get("sources") or {}).get("fr") or {}
        for values in refs.values():
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                raise CreationContextError("Invalid source references")
            source_ids.update(values)
    source_ids.update(sid for sid, row in source_index.items()
                      if any(use.get("page_id") in context_ids and use.get("language") == "fr"
                             for use in row.get("usage", [])))
    if not source_ids <= source_index.keys():
        raise CreationContextError("Selected source is missing from registry")
    equivalence_groups = {source_index[sid].get("equivalence_group") for sid in source_ids}
    equivalence_groups.discard(None)
    equivalence_groups.discard("")
    source_ids.update(sid for sid, row in source_index.items()
                      if row.get("equivalence_group") in equivalence_groups)
    # A documentary record is shared, but every page-specific usage is retained.
    # There is no network verification or automatic transfer of a prior verdict.
    selected_sources = [copy.deepcopy(source_index[sid]) for sid in sorted(source_ids)]
    return {"debate_id": debate_id, "scope": docs["scope"],
            "debate": {"scope": registry["debate"].get("scope"),
                       "fr": registry["debate"].get("pages", {}).get("fr")},
            "batch_id": batch_id, "selected_node_ids": selected,
            "dependency_node_ids": sorted(dependencies),
            "graph_overview": {"nodes": [{"id": n["id"], "fr": n.get("fr")} for n in nodes.values()],
                               "edges": edges, "occurrences": occurrences},
            "page_texts": texts, "sources": selected_sources,
            "research_complete": False, "editorial_validation_performed": False,
            "remaining_checks": ["Research new sources and omissions; selection is not exhaustive.",
                                 "Review each source usage for its exact argument.",
                                 "Keep global cross-branch, documentary and editorial reviews.",
                                 "Run all ordinary validation/release gates; no automatic completion."]}


def build_creation_context(project_root: Path, stage: str, *, corpus_path: str | None = None,
                           batch_id: str | None = None, node_ids: Sequence[str] = (),
                           dependency_node_ids: Sequence[str] = ()) -> dict[str, Any]:
    root = project_root.expanduser().resolve()
    if stage not in STAGES:
        raise CreationContextError("Unknown creation stage")
    if not corpus_path and (batch_id or node_ids or dependency_node_ids):
        raise CreationContextError("Node selection requires --corpus")
    inputs = Inputs(root)
    norm_raw, norm_info = normative_context(inputs, stage)
    payload = None
    if corpus_path:
        payload = corpus_context(inputs, root / _relative_path(corpus_path), stage, batch_id, node_ids,
                                 dependency_node_ids=dependency_node_ids)
    instructions = (
        "# Contexte de creation francaise\n\n"
        f"Etape : {stage}. Lire NORMATIVE_CONTEXT.md puis CORPUS_CONTEXT.json, si present.\n\n"
        "Les extraits sont exacts, non resumes. Leur couverture figure dans CONTEXT_MANIFEST.json.\n"
        "Les sections exclues concernent une autre etape, la traduction, une reprise ou la publication.\n"
        "Ce dossier est une aide de lecture, pas un paquet review-import ni une preuve de validation.\n"
        "Ne pas y modifier le corpus : travailler dans ses fichiers canoniques selon le workflow ordinaire.\n"
        "Aucun argument n'est declare termine ou dispense de recherche/revue par cet outil.\n"
        "Les dependances sont du contexte : ne pas les reecrire au seul motif de leur inclusion.\n"
        "Les sources selectionnees ne constituent ni une recherche exhaustive ni une verification nouvelle.\n"
        "Preserver les controles globaux inter-lots, la couverture des raisonnements et toutes les exigences editoriales.\n"
        "Aucune autorisation de publication, aucun acces distant, aucun modele IA n'est appele.\n"
        "Les octets mesures ne sont ni des tokens factures ni du quota economise.\n"
    ).encode("utf-8")
    files = {"INSTRUCTIONS.md": instructions, "NORMATIVE_CONTEXT.md": norm_raw}
    if payload is not None:
        files["CORPUS_CONTEXT.json"] = _json(payload)
    records = sorted(inputs.records.values(), key=lambda row: row["path"])
    manifest = {"schema": SCHEMA, "schema_version": "1.0", "stage": stage,
                "inputs": records, "normative_selection": norm_info,
                "selection": {"corpus_path": corpus_path, "batch_id": batch_id, "node_ids": list(node_ids), "dependency_node_ids": list(dependency_node_ids)},
                "files": [{"path": name, "size_bytes": len(raw), "sha256": _sha(raw)} for name, raw in sorted(files.items())],
                "measurement": {"norm_source_bytes": norm_info["source_bytes"],
                                "norm_excerpt_bytes": len(norm_raw),
                                "recommended_read_bytes": sum(map(len, files.values())),
                                "actual_billed_tokens": None, "actual_codex_cloud_credits": None},
                "remote_access_performed": False, "remote_write_performed": False,
                "validation_performed": False}
    key = _sha(_json(manifest))
    manifest["context_sha256"] = key
    files["CONTEXT_MANIFEST.json"] = _json(manifest)
    parent = _contained(root, root / ".state/creation-context" / stage)
    parent.mkdir(parents=True, exist_ok=True)
    target = _contained(root, parent / key)
    inputs.verify()

    def verify_existing() -> None:
        if not target.is_dir() or {p.name for p in target.iterdir()} != set(files):
            raise CreationContextError("Existing context was altered")
        for name, raw in files.items():
            p = _contained(root, target / name)
            if not p.is_file() or p.read_bytes() != raw:
                raise CreationContextError("Existing context checksum differs")

    reused = target.exists()
    if reused:
        verify_existing()
    else:
        staging = Path(tempfile.mkdtemp(prefix=".preparing-", dir=parent))
        try:
            for name, raw in files.items():
                (staging / name).write_bytes(raw)
            inputs.verify()
            try:
                os.rename(staging, target)
            except OSError:
                if not target.exists():
                    raise
                verify_existing()
                reused = True
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return {"status": "reused" if reused else "prepared", "stage": stage,
            "context_path": target.relative_to(root).as_posix(), "context_sha256": key,
            "measurement": manifest["measurement"], "validation_performed": False,
            "remote_access_performed": False, "remote_write_performed": False}


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--corpus", help="Project-relative corpus path; explicit new provenance required")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--batch-id")
    group.add_argument("--node-id", action="append", default=[])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        result = build_creation_context(args.project_root, args.stage, corpus_path=args.corpus,
                                        batch_id=args.batch_id, node_ids=args.node_id)
    except (CreationContextError, OSError, ValueError, KeyError, TypeError) as exc:
        print("CONTEXTE DE CREATION BLOQUE : " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
