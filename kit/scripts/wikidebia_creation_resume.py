#!/usr/bin/env python3
"""Derive the next French creation task from the canonical registry, offline.

The saved queue is a disposable, hash-addressed projection, never another source
of progress. No page, batch, review or validation status is written by this tool.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any, Sequence

from wikidebia_creation_context import (
    CreationContextError, Inputs, _contained, _indexed, _json, _relative_path,
    _sha, build_creation_context,
)

SCHEMA = "wikidebia-creation-resume-1.0"
ALLOWED_STATES = {"graph_locked", "fr_debate_validated", "fr_arguments_in_progress",
                  "fr_content_complete", "fr_validated"}
GENERATION = {"pending", "assigned", "in_progress", "generated", "validated", "failed"}
PAGE = {"planned", "assigned", "generated", "validated", "failed"}
BATCH = {"planned", "assigned", "in_progress", "generated", "validated", "released", "failed"}
CLOSED_BATCH = {"validated", "released"}
SHA = re.compile(r"[a-f0-9]{64}")


class CreationResumeError(CreationContextError):
    pass


class ResumeInputs(Inputs):
    """Bind absence as well as bytes: a newly appearing draft must not be lost."""
    def __init__(self, root: Path):
        super().__init__(root)
        self.absent: set[str] = set()

    def exists(self, path: Path) -> bool:
        path = _contained(self.root, path)
        rel = path.relative_to(self.root).as_posix()
        _relative_path(rel)
        if path.exists():
            if rel in self.absent:
                raise CreationResumeError("Input appeared during preparation: " + rel)
            return True
        if rel in self.records:
            raise CreationResumeError("Input disappeared during preparation: " + rel)
        self.absent.add(rel)
        return False

    def verify(self) -> None:
        super().verify()
        for rel in sorted(self.absent):
            if _contained(self.root, self.root / rel).exists():
                raise CreationResumeError("Input appeared during preparation: " + rel)


def _strings(value: Any, label: str) -> list[str]:
    if (not isinstance(value, list) or not all(isinstance(v, str) and v for v in value)
            or len(set(value)) != len(value)):
        raise CreationResumeError("Invalid or duplicate " + label)
    return value


def _file_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.startswith("output/fr/") or not value.endswith(".wiki"):
        raise CreationResumeError("Non-canonical French page path")
    return _relative_path(value)


def _page_state(inputs: ResumeInputs, corpus: Path, page_id: str,
                manifest_page: dict[str, Any], record: dict[str, Any],
                title: str, batch_id: str | None) -> dict[str, Any]:
    page = manifest_page
    generation, file = record.get("generation") or {}, record.get("file") or {}
    g, p, f = generation.get("status"), page.get("status"), file.get("status")
    if page.get("page_origin") != "new":
        raise CreationResumeError("Not an explicitly new French page: " + page_id)
    if g not in GENERATION or p not in PAGE or f not in {"absent", "present", "validated"}:
        raise CreationResumeError("Unknown, obsolete or published page state: " + page_id)
    for wiki in (page.get("wiki") or {}, record.get("wiki") or {}):
        if (wiki.get("remote_revision_id") is not None or wiki.get("published_at")
                or wiki.get("check_status") in {"created", "equivalent_existing"}
                or wiki.get("decision") == "reuse_existing"):
            raise CreationResumeError("Already remote or reused page: " + page_id)
    if (not title or page.get("canonical_title") != title
            or page.get("batch_id") != batch_id or generation.get("assigned_batch_id") != batch_id):
        raise CreationResumeError("Page title or batch ownership differs: " + page_id)
    rel = _file_path(page.get("file_path"))
    if file.get("path") != rel.as_posix():
        raise CreationResumeError("Registry and manifest page paths differ: " + page_id)
    actual = _sha(inputs.read(corpus / rel)) if inputs.exists(corpus / rel) else None
    declared = (page.get("sha256"), file.get("sha256"))
    # Never adopt an unregistered file, nor rewrite a drifted file automatically.
    if actual is not None:
        if any(not isinstance(h, str) or not SHA.fullmatch(h) or h != actual for h in declared):
            raise CreationResumeError("Unrecorded or changed page; preserve and reconcile: " + page_id)
        if f not in {"present", "validated"}:
            raise CreationResumeError("Present file declared absent: " + page_id)
    elif any(declared) or f != "absent" or g in {"generated", "validated"} or p in {"generated", "validated"}:
        raise CreationResumeError("Recorded page is missing: " + page_id)
    validation = page.get("validation") or {}
    if g == "validated" or p == "validated" or f == "validated":
        if (g != "validated" or p != "validated" or f != "validated" or actual is None
                or validation.get("status") != "passed"
                or not generation.get("validated_at") or not validation.get("validated_at")):
            raise CreationResumeError("Contradictory recorded validation state: " + page_id)
        report = validation.get("report_path")
        if not isinstance(report, str) or not report.startswith("reports/"):
            raise CreationResumeError("Missing validation report path: " + page_id)
        if not inputs.read(corpus / _relative_path(report)).strip():
            raise CreationResumeError("Empty recorded validation report: " + page_id)
        state = "recorded_validated"
    elif g == "failed" or p == "failed" or validation.get("status") == "failed":
        state = "needs_correction"
    elif g == "generated" or p == "generated":
        if g != "generated" or p != "generated" or actual is None:
            raise CreationResumeError("Contradictory generated state: " + page_id)
        state = "awaiting_review"
    elif actual is not None:
        # A tracked in-progress text is an unfinished draft, not completed work.
        if g != "in_progress":
            raise CreationResumeError("Existing draft without in_progress state: " + page_id)
        state = "draft_in_progress"
    else:
        state = "to_generate"
    if actual is not None and g in {"generated", "validated"}:
        if (not generation.get("generated_at") or not generation.get("creation_date")
                or generation.get("creation_date") != page.get("creation_date")):
            raise CreationResumeError("Missing or divergent generation provenance: " + page_id)
    return {"page_id": page_id, "batch_id": batch_id, "state": state,
            "file_path": rel.as_posix(), "sha256": actual}


def _check_graph(registry: dict[str, Any]) -> None:
    """Reuse the installed structural algorithm, without running editorial review."""
    source = Path(__file__).resolve().parents[2] / "validator/src"
    if not source.is_dir():
        raise CreationResumeError("Installed structural validator is missing")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    from wikidebia_validator.graph import _iter_cycle_paths, structural_sha256
    graph = registry["graph"]
    nodes = _indexed(graph.get("nodes"), "id", "nodes")
    active = {key: row for key, row in nodes.items() if row.get("status") == "active"}
    edges = _indexed(graph.get("edges"), "id", "edges")
    outgoing = {key: [] for key in active}
    for edge in edges.values():
        if edge.get("status") != "active":
            continue
        a, b = edge.get("parent_node_id"), edge.get("child_node_id")
        if a not in active or b not in active or a == b:
            raise CreationResumeError("Invalid active graph edge")
        outgoing[a].append(b)
    if next(_iter_cycle_paths(active, outgoing), None) is not None:
        raise CreationResumeError("Cyclic graph cannot be scheduled")
    lifecycle = graph.get("lifecycle") or {}
    if lifecycle.get("status") != "locked" or lifecycle.get("structural_sha256") != structural_sha256(registry):
        raise CreationResumeError("Graph must be locked with its current structural hash")
    for node in active.values():
        if (node.get("fr") or {}).get("title_status") != "locked":
            raise CreationResumeError("French argument title is not locked")
    if registry["debate"]["pages"]["fr"].get("title_status") != "locked":
        raise CreationResumeError("French debate title is not locked")


def creation_inventory(inputs: ResumeInputs, corpus_path: str) -> dict[str, Any]:
    corpus = _contained(inputs.root, inputs.root / _relative_path(corpus_path))
    if corpus.relative_to(inputs.root).as_posix() != corpus_path:
        raise CreationResumeError("Use a canonical project-relative corpus path")
    manifest = inputs.document(corpus / "manifest.json")
    debate_id = manifest.get("debate_id")
    if not isinstance(debate_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,127}", debate_id):
        raise CreationResumeError("Invalid debate identity")
    if manifest.get("global_status") not in ALLOWED_STATES:
        raise CreationResumeError("Creation resume requires a locked French prepublication corpus")
    if (manifest.get("translation_status") or {}).get("en") != "deferred":
        raise CreationResumeError("Creation resume requires English explicitly deferred")
    if inputs.exists(corpus / "data/import_provenance.json"):
        raise CreationResumeError("Imported corpus is not a from-scratch creation")
    core = manifest.get("core_files") or {}
    docs = {key: inputs.document(corpus / _relative_path(core[key])) for key in ("registry", "scope", "sources")}
    registry = docs["registry"]
    if (registry.get("schema", {}).get("registry_version") != "1.0"
            or registry.get("debate", {}).get("id") != debate_id
            or docs["scope"].get("debate_id") != debate_id
            or docs["sources"].get("debate_id") != debate_id
            or docs["sources"].get("source_registry_version") != "1.0"):
        raise CreationResumeError("Unsupported or foreign corpus documents")
    _check_graph(registry)
    nodes = {key: row for key, row in _indexed(registry["graph"].get("nodes"), "id", "nodes").items()
             if row.get("status") == "active"}
    raw_pages = manifest.get("pages")
    if not isinstance(raw_pages, list) or not all(isinstance(p, dict) for p in raw_pages):
        raise CreationResumeError("Invalid page inventory")
    pages = _indexed([p for p in raw_pages if p.get("language") == "fr"], "page_id", "French pages")
    if set(pages) != {debate_id, *nodes}:
        raise CreationResumeError("French page inventory does not cover exactly the active graph")
    paths = [p.get("file_path") for p in pages.values()]
    if len(set(paths)) != len(paths):
        raise CreationResumeError("Several pages share one output file")
    for key, p in pages.items():
        if p.get("debate_id") != debate_id or p.get("page_type") != ("debate" if key == debate_id else "argument"):
            raise CreationResumeError("Foreign page or wrong page type: " + key)
    all_batches = _indexed(registry.get("batches"), "id", "batches")
    batches = [b for b in all_batches.values() if b.get("language") == "fr" and b.get("status") != "obsolete"]
    mirrors = [manifest.get("batches")]
    lots_path = corpus / "data/lots_fr.json"
    if inputs.exists(lots_path):
        mirrors.append(inputs.document(lots_path).get("batches"))
    for mirror in mirrors:
        if mirror is None:
            raise CreationResumeError("Missing canonical batch mirror")
        indexed = _indexed(mirror, "id", "batch mirror")
        fr = {key: b for key, b in indexed.items() if b.get("language") == "fr"}
        if fr != {key: b for key, b in all_batches.items() if b.get("language") == "fr"}:
            raise CreationResumeError("Batch mirrors differ")
    owner = {}
    for batch in batches:
        if (batch.get("status") not in BATCH or batch.get("debate_id") != debate_id
                or batch.get("page_type") != "argument" or not re.fullmatch(r"FR-A-\d{3,}", batch["id"])):
            raise CreationResumeError("Unknown or incompatible French batch")
        ids = _strings(batch.get("node_ids"), "batch members")
        deps = _strings(batch.get("dependency_node_ids"), "batch dependencies")
        if not ids or not set(ids + deps) <= nodes.keys() or set(ids) & set(deps):
            raise CreationResumeError("Missing or overlapping batch members/dependencies")
        for key in ids:
            if key in owner:
                raise CreationResumeError("Argument assigned to multiple batches: " + key)
            owner[key] = batch["id"]
    if set(owner) != set(nodes):
        raise CreationResumeError("Active arguments are not all assigned to a French batch")
    rows = [_page_state(inputs, corpus, debate_id, pages[debate_id], registry["debate"]["pages"]["fr"],
                        registry["debate"]["pages"]["fr"].get("canonical_title"), None)]
    for batch in batches:
        for key in batch["node_ids"]:
            rows.append(_page_state(inputs, corpus, key, pages[key], (nodes[key].get("pages") or {}).get("fr") or {},
                                    (nodes[key].get("fr") or {}).get("canonical_title"), owner[key]))
    by_id = {r["page_id"]: r for r in rows}
    for batch in batches:
        if batch["status"] in CLOSED_BATCH:
            if any(by_id[key]["state"] != "recorded_validated" for key in batch["node_ids"]):
                raise CreationResumeError("Validated batch contains unfinished pages: " + batch["id"])
            output = batch.get("outputs") or {}
            aggregate = output.get("aggregate_path")
            if not isinstance(aggregate, str) or not aggregate.startswith("output/fr/"):
                raise CreationResumeError("Missing batch aggregate path")
            if _sha(inputs.read(corpus / _relative_path(aggregate))) != output.get("aggregate_sha256"):
                raise CreationResumeError("Batch aggregate checksum differs")
            report = output.get("report_path")
            if not isinstance(report, str) or not report.startswith("reports/") or not inputs.read(corpus / _relative_path(report)).strip():
                raise CreationResumeError("Missing batch review report")
    return {"debate_id": debate_id, "corpus_path": corpus_path, "global_status": manifest["global_status"],
            "pages": rows, "batches": [{k: b[k] for k in ("id", "status", "node_ids", "dependency_node_ids")} for b in batches],
            "counts": dict(Counter(row["state"] for row in rows)),
            "argument_count": len(nodes)}


def select_next(inventory: dict[str, Any], max_pages: int) -> dict[str, Any]:
    rows = {r["page_id"]: r for r in inventory["pages"]}
    debate = rows[inventory["debate_id"]]
    incomplete = {"to_generate", "draft_in_progress", "needs_correction"}
    if debate["state"] != "recorded_validated":
        return {"action": "draft_debate" if debate["state"] in incomplete else "review_debate",
                "stage": "debat-fr", "page_ids": [debate["page_id"]], "batch_id": None, "dependency_node_ids": []}
    for batch in inventory["batches"]:
        if batch["status"] in CLOSED_BATCH:
            continue
        deps = [key for key in batch["dependency_node_ids"] if rows[key]["state"] != "recorded_validated"]
        if deps:
            return {"action": "dependency_review_required", "stage": None, "page_ids": [],
                    "batch_id": batch["id"], "dependency_node_ids": deps}
        todo = [key for key in batch["node_ids"] if rows[key]["state"] in incomplete]
        if todo:
            # Resume a tracked partial/corrective draft before starting fresh ones.
            todo.sort(key=lambda key: rows[key]["state"] == "to_generate")
            return {"action": "draft_arguments", "stage": "arguments-fr", "page_ids": todo[:max_pages],
                    "batch_id": batch["id"], "dependency_node_ids": batch["dependency_node_ids"]}
        review = [key for key in batch["node_ids"] if rows[key]["state"] == "awaiting_review"]
        return {"action": "review_arguments" if review else "batch_review_required",
                "stage": "arguments-fr" if review else None, "page_ids": review[:max_pages],
                "batch_id": batch["id"], "dependency_node_ids": batch["dependency_node_ids"]}
    return {"action": "global_review_required", "stage": None, "page_ids": [],
            "batch_id": None, "dependency_node_ids": []}


def _persist(root: Path, plan: dict[str, Any]) -> tuple[str, str, str]:
    raw = _json(plan)
    key = _sha(raw)
    parent = _contained(root, root / ".state/creation-resume" / plan["debate_id"])
    parent.mkdir(parents=True, exist_ok=True)
    target = _contained(root, parent / key)
    content = {"QUEUE.json": raw, "NEXT.md": (
        "# Reprise de creation francaise\n\n"
        f"Action : {plan['next']['action']}\n"
        f"Pages : {', '.join(plan['next']['page_ids']) or '(aucune a generer)'}\n\n"
        "Lire uniquement le contexte indique pour cette action. Conserver les textes existants.\n"
        "Une revue ne demande pas de regenerer les pages. Ne pas ouvrir un autre lot avant sa cloture.\n"
        "Cette file est derivee : ne jamais la modifier pour declarer une page terminee.\n"
        "Les etats persistent dans le registre et les manifestes canoniques, pas ici.\n"
        "Une page generated attend encore sa revue ; recorded_validated est un etat relu, pas une nouvelle preuve.\n"
        "Utiliser le workflow ordinaire pour les mises a jour coherentes et les controles editoriaux.\n"
        "Relancer creation-next apres enregistrement, correction ou validation.\n"
        "Aucune publication ni cloture automatique : les controles globaux restent obligatoires.\n"
        f"Contexte : {(plan.get('context') or {}).get('context_path') or '(controle requis avant de poursuivre)'}\n"
    ).encode("utf-8")}
    def verify():
        if not target.is_dir() or {p.name for p in target.iterdir()} != set(content):
            raise CreationResumeError("Saved queue was altered")
        for name, data in content.items():
            if _contained(root, target / name).read_bytes() != data:
                raise CreationResumeError("Saved queue checksum differs")
    reused = target.exists()
    if reused:
        verify()
    else:
        staging = Path(tempfile.mkdtemp(prefix=".preparing-", dir=parent))
        try:
            for name, data in content.items():
                (staging / name).write_bytes(data)
            try:
                os.rename(staging, target)
            except OSError:
                if not target.exists():
                    raise
                verify()
                reused = True
        finally:
            if staging.exists():
                shutil.rmtree(staging)
    return target.relative_to(root).as_posix(), key, "reused" if reused else "prepared"


def creation_resume(project_root: Path, corpus_path: str, *, max_pages: int = 8,
                    prepare: bool = True) -> dict[str, Any]:
    if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 20:
        raise CreationResumeError("max_pages must be between 1 and 20")
    root = project_root.expanduser().resolve()
    inputs = ResumeInputs(root)
    inventory = creation_inventory(inputs, corpus_path)
    next_task = select_next(inventory, max_pages)
    context = None
    if prepare and next_task["stage"]:
        context = build_creation_context(
            root, next_task["stage"], corpus_path=corpus_path,
            node_ids=next_task["page_ids"] if next_task["stage"] == "arguments-fr" else (),
            dependency_node_ids=next_task["dependency_node_ids"],
        )
        # Reuse/prepared is runtime metadata; keep the persisted plan deterministic.
        context = {k: v for k, v in context.items() if k != "status"}
    inputs.verify()
    plan = {"schema": SCHEMA, "schema_version": "1.0", **inventory,
            "next": next_task, "max_pages": max_pages, "context": context,
            "inputs": sorted(inputs.records.values(), key=lambda r: r["path"]),
            "absent_inputs": sorted(inputs.absent),
            "editorial_validation_performed": False, "publication_authorized": False,
            "remote_access_performed": False, "remote_write_performed": False,
            "actual_billed_tokens": None, "actual_codex_cloud_credits": None}
    result = {k: plan[k] for k in ("schema", "debate_id", "corpus_path", "counts", "argument_count", "next",
                                  "editorial_validation_performed", "publication_authorized", "remote_access_performed",
                                  "remote_write_performed", "actual_billed_tokens", "actual_codex_cloud_credits")}
    if prepare:
        path, key, status = _persist(root, plan)
        inputs.verify()
        result.update(status=status, queue_path=path, queue_sha256=key, context=context,
                      read_first=path + "/NEXT.md")
    else:
        result["status"] = "inspected"
    return result


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--corpus", required=True, help="Project-relative new French corpus")
    parser.add_argument("--max-pages", type=int, default=8, help="Maximum pages in the next task (1-20)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--inspect-only", action="store_true")
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        result = creation_resume(args.project_root, args.corpus, max_pages=args.max_pages, prepare=not args.inspect_only)
    except (CreationContextError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print("REPRISE DE CREATION BLOQUEE : " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
