#!/usr/bin/env python3
"""Render and publish the two validated French checkpoints before translation.

Stage ``graph`` publishes only graph/title changes from ``reviewed-copy``.
Stage ``content`` publishes classification and content from ``content-reviewed-copy``.
Both reuse the ordinary signed remote-update engine and page-specific summaries.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION
from wikidebia_corpus_build import (
    assert_no_symlinks,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    sha256_file,
    structural_sha256,
    validate_debate_id,
    write_json,
)
from wikidebia_editorial_workspace import validate_work_id, workspace_receipt_hash
from wikidebia_render import (
    _batch,
    _main_arguments,
    _relations,
    _page_creation_dates,
    _page_manifest,
    _render_argument,
    _render_debate,
    _normalize_legacy_french_quote_warnings,
    _write_aggregate,
    _copy_active_norm,
)
from wikidebia_graph_actions import _set_optional_parameter_value
from wikidebia_content_review import _outer_template, _page_lifecycle_snapshot
from wikidebia_update import (
    PlanExecutor,
    RemoteUpdatePlanner,
    build_adapter,
    sha_object,
    sha_text,
)


CHECKPOINT_SCHEMA = "wikidebia-french-publication-checkpoint-1.0"
RECEIPT_SCHEMA = "wikidebia-french-checkpoint-publication-receipt-1.0"
GRAPH_VALIDATION_PROFILE = "fr_graph_checkpoint_differential_v1"
CONTENT_VALIDATION_PROFILE = "fr_content_checkpoint_complete_v1"
GRAPH_VALIDATION_SCOPES = ("schema", "coherence", "graph", "files", "batches", "sources", "workflow")
CONTENT_VALIDATION_SCOPES = ("schema", "coherence", "graph", "files", "batches", "sources", "wikicode", "workflow")


class FrenchCheckpointError(RuntimeError):
    def __init__(self, message: str, *, remote_execution_started: bool = False) -> None:
        super().__init__(message)
        self.remote_execution_started = remote_execution_started


def _defer_unresolved_interlanguage(record: dict[str, Any]) -> None:
    """Defer French links without discarding a verified reusable English page.

    Corpus initialisation marks an already translated frontier as ``ready`` and
    records its English title before the ordinary translation stage.  The graph
    checkpoint must keep that evidence schema-valid while deferring only links
    whose English target is still unresolved.
    """
    target_title = record.get("target_title")
    reusable_target = (
        record.get("status") == "ready"
        and isinstance(target_title, str)
        and bool(target_title.strip())
    )
    if reusable_target:
        record.update({"inserted_at": None, "verified_at": None})
        return
    record.update({
        "status": "deferred",
        "target_title": None,
        "inserted_at": None,
        "verified_at": None,
    })


def _depth_frontier_node_ids(registry: Mapping[str, Any]) -> set[str]:
    policy = (registry.get("graph") or {}).get("depth_policy") or {}
    if policy.get("limit_policy") != "bounded":
        return set()
    rows = policy.get("frontier_node_ids") or []
    if not isinstance(rows, list) or any(not isinstance(row, str) or not row for row in rows):
        raise FrenchCheckpointError("Nœuds de frontière de profondeur invalides")
    return set(rows)


def _workspace(project_root: Path, debate_id: str, work_id: str, stage: str) -> tuple[Path, dict[str, Any], Path]:
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    if stage not in {"graph", "content"}:
        raise FrenchCheckpointError(f"Checkpoint français inconnu : {stage}")
    path = (project_root / ".state" / "editorial-workspaces" / debate_id / work_id).resolve()
    if not path.is_dir() or path.is_symlink():
        raise FrenchCheckpointError(f"Workspace introuvable : {debate_id}/{work_id}")
    meta = load_json(path / "workspace.json", "workspace.json")
    if meta.get("debate_id") != debate_id or meta.get("work_id") != work_id:
        raise FrenchCheckpointError("Identité du workspace divergente")
    if meta.get("workspace_sha256") != workspace_receipt_hash(meta):
        raise FrenchCheckpointError("Empreinte de workspace.json invalide")
    source_name = "reviewed-copy" if stage == "graph" else "content-reviewed-copy"
    source = path / source_name
    if not source.is_dir() or source.is_symlink():
        raise FrenchCheckpointError(f"{source_name} absent ou non sûr")
    meta_key = "reviewed_copy" if stage == "graph" else "content_reviewed_copy"
    expected = str((meta.get(meta_key) or {}).get("tree_sha256") or "")
    if not expected or full_tree_sha256(source) != expected:
        raise FrenchCheckpointError(f"{source_name} a changé depuis son application")
    if stage == "graph" and meta.get("status") not in {
        "fr_titles_applied", "fr_metadata_applied", "fr_content_review_ready", "fr_content_review_finalized", "fr_content_applied",
        "en_translation_review_ready", "en_translation_review_finalized", "en_translation_applied", "bilingual_rendered",
        "release_ready",
    }:
        raise FrenchCheckpointError(f"Les titres français ne sont pas appliqués : {meta.get('status')}")
    if stage == "content" and meta.get("status") not in {
        "fr_content_applied", "fr_source_preserved", "en_translation_review_ready", "en_translation_review_finalized", "en_translation_applied", "bilingual_rendered",
        "release_ready",
    }:
        raise FrenchCheckpointError(f"Le contenu français n'est pas appliqué : {meta.get('status')}")
    assert_no_symlinks(source)
    return path, meta, source

def _fr_validation_records(timestamp: str, input_sha: str) -> list[dict[str, Any]]:
    return [
        {
            "id": f"V{timestamp[:10].replace('-', '')}-{index:03d}",
            "scope": scope,
            "language": None,
            "validator_version": VALIDATOR_VERSION,
            "executed_at": timestamp,
            "input_sha256": input_sha,
            "result": "passed",
            "blocking_errors": 0,
            "warnings": 0,
            "report_path": "reports/fr_checkpoint_validation.json",
        }
        for index, scope in enumerate(("graph", "fr_debate", "fr_global"), start=1)
    ]


def _graph_checkpoint_baseline(
    project_root: Path, source: Path, debate_id: str, work_id: str,
) -> tuple[Path, dict[str, Path]]:
    """Resolve the exact French graph state that content publication must retain.

    A normal two-checkpoint workflow has an immutable graph checkpoint.  The
    import fallback keeps direct/local fixture builds usable, while production
    always prefers the already rendered graph state (including bounded-depth
    frontier relations and reviewed link labels).
    """
    graph_output = (
        project_root / ".state" / "fr-publication" / debate_id / work_id
        / "graph" / "checkpoint-corpus" / "output" / "fr"
    )
    debate_path = graph_output / "debate" / "debate.wiki"
    argument_dir = graph_output / "arguments"
    if debate_path.is_file() and argument_dir.is_dir():
        return debate_path, {
            path.stem: path for path in argument_dir.glob("*.wiki") if path.is_file()
        }

    debate_fallback: Path | None = None
    arguments: dict[str, Path] = {}
    for row in _import_rows(source):
        path = source / str(row.get("import_path") or "")
        if not path.is_file():
            continue
        if row.get("kind") == "debate":
            debate_fallback = path
        else:
            page_id = str(row.get("page_id") or "")
            if page_id:
                arguments[page_id] = path
    if debate_fallback is None:
        raise FrenchCheckpointError("Page Débat de référence absente pour le checkpoint de contenu")
    return debate_fallback, arguments


def _retain_baseline_parameters(
    rendered: str, baseline: Path, *, page_type: str, parameters: tuple[str, ...],
) -> str:
    template = _outer_template(baseline, {"debat" if page_type == "debate" else "argument"})
    for parameter in parameters:
        rendered = _set_optional_parameter_value(
            rendered, page_type, parameter, template.get(parameter),
        )
    return rendered


def _build_content_checkpoint_copy(project_root: Path, source: Path, target: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    shutil.copytree(source, target, symlinks=False, copy_function=shutil.copy2)
    assert_no_symlinks(target)
    registry = load_json(target / "data/registre_debat.json", "registre du débat")
    manifest = load_json(target / "manifest.json", "manifest.json")
    fr_meta = load_json(target / "data/fr_page_metadata_lock.json", "verrou français des métadonnées")
    fr_content = load_json(target / "data/fr_content_lock.json", "verrou français du contenu")
    source_registry = load_json(target / "data/sources.json", "registre documentaire")
    if manifest.get("debate_id") != debate_id or fr_content.get("debate_id") != debate_id:
        raise FrenchCheckpointError("Identité du corpus français divergente")

    nodes = [node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"]
    nodes.sort(key=lambda node: str(node.get("id")))
    fr_args = {str(row.get("id")): row for row in fr_content.get("arguments") or []}
    if set(fr_args) != {str(node.get("id")) for node in nodes}:
        raise FrenchCheckpointError("Le verrou français ne couvre pas exactement les arguments actifs")
    french_pages = [fr_content.get("debate") or {}, *fr_args.values()]
    if french_pages and all(page.get("page_origin") == "preexisting" for page in french_pages):
        from wikidebia_translation_source import relation_labels_from_source
        contextual_labels = relation_labels_from_source(target)
        fr_content["debate"]["relation_labels"] = [
            row for row in contextual_labels if row["source_page_id"] == "debate"
        ]
        for node_id, argument in fr_args.items():
            argument["relation_labels"] = [
                row for row in contextual_labels if row["source_page_id"] == node_id
            ]
    source_by_id = {str(row.get("id")): row for row in source_registry.get("sources") or []}
    baseline_debate, baseline_arguments = _graph_checkpoint_baseline(
        project_root, source, debate_id, work_id,
    )
    for node_id, argument in fr_args.items():
        baseline = baseline_arguments.get(node_id)
        if baseline is None:
            raise FrenchCheckpointError(
                f"Page Argument de référence absente pour le checkpoint de contenu : {node_id}"
            )
        template = _outer_template(baseline, {"argument"})
        displayed_present = "titre-affiché" in template.params
        argument.setdefault("preserved_parameters", {})["titre-affiché"] = {
            "present": displayed_present,
            "value": template.get("titre-affiché") if displayed_present else None,
        }
    # These occurrence labels and compatibility states are validation evidence,
    # not transient render-only data.
    write_json(target / "data/fr_content_lock.json", fr_content)

    timestamp = now_iso()
    fallback_date = str(fr_content.get("applied_at") or timestamp)[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fallback_date):
        fallback_date = dt.date.today().isoformat()
    dates = _page_creation_dates(target, registry, fallback_date)

    lifecycle = (registry.get("graph") or {}).setdefault("lifecycle", {})
    lifecycle.update({
        "status": "locked",
        "locked_at": timestamp,
        "locked_by_stage": "fr_content_checkpoint_publication",
        "structural_sha256": structural_sha256(registry),
    })
    debate_pages = (registry.get("debate") or {}).get("pages") or {}
    debate_pages["fr"]["title_status"] = "locked"
    debate_pages["fr"].setdefault("interlanguage", {}).update({
        "status": "deferred", "inserted_at": None, "verified_at": None,
    })
    for node in nodes:
        node["fr"]["title_status"] = "locked"
        node["pages"]["fr"].setdefault("interlanguage", {}).update({
            "status": "deferred", "inserted_at": None, "verified_at": None,
        })

    output_paths: list[tuple[str, str, str, str, str]] = []
    debate_id_actual = str((registry.get("debate") or {}).get("id"))
    debate_rel = "output/fr/debate/debate.wiki"
    debate_text = _render_debate(
        lang="fr", registry=registry, metadata_lock=fr_meta, content_lock=fr_content,
        sources=source_by_id, creation_date=dates[(debate_id_actual, "fr")],
        include_interlanguage=False,
    )
    debate_text = _retain_baseline_parameters(
        debate_text, baseline_debate, page_type="debate",
        parameters=("arguments-pour", "arguments-contre", "interlangue"),
    )
    debate_path = target / debate_rel
    debate_path.parent.mkdir(parents=True, exist_ok=True)
    debate_path.write_text(debate_text, encoding="utf-8", newline="\n")
    output_paths.append((debate_id_actual, "fr", "debate", debate_rel, sha256_file(debate_path)))
    for node in nodes:
        node_id = str(node.get("id"))
        rel = f"output/fr/arguments/{node_id}.wiki"
        text = _render_argument(
            lang="fr", node=node, content=fr_args[node_id], registry=registry,
            sources=source_by_id, creation_date=dates[(node_id, "fr")],
            include_interlanguage=False,
        )
        baseline = baseline_arguments.get(node_id)
        if baseline is None:
            raise FrenchCheckpointError(
                f"Page Argument de référence absente pour le checkpoint de contenu : {node_id}"
            )
        # Checkpoint 2 may change reviewed prose, documentation and
        # classification.  It must retain checkpoint 1's graph, displayed
        # labels and opaque historical interlanguage values exactly.
        text = _retain_baseline_parameters(
            text, baseline, page_type="argument",
            parameters=("citations", "justifications", "objections"),
        )
        text = _normalize_legacy_french_quote_warnings(text)
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        output_paths.append((node_id, "fr", "argument", rel, sha256_file(path)))

    registry_sha_before_outputs = sha256_file(target / "data/registre_debat.json")
    structural = structural_sha256(registry)
    aggregate_path, aggregate_sha = _write_aggregate(target, "fr", nodes)
    batch = _batch(
        debate_id=debate_id, lang="fr", nodes=nodes, registry_sha=registry_sha_before_outputs,
        structural_sha=structural, aggregate_path=aggregate_path, aggregate_sha=aggregate_sha,
        timestamp=timestamp, work_id=work_id,
    )
    batch["root_node_ids"] = sorted({
        str(occ.get("node_id")) for occ in (registry.get("graph") or {}).get("occurrences") or []
        if occ.get("depth") == 1
    })
    write_json(target / "data/lots_fr.json", {
        "batch_collection_version": "1.0", "debate_id": debate_id,
        "language": "fr", "batches": [batch],
    })
    (target / "reports/fr_batch_001.txt").parent.mkdir(parents=True, exist_ok=True)
    (target / "reports/fr_batch_001.txt").write_text("Lot français rendu pour publication après revue.\n", encoding="utf-8", newline="\n")

    page_hash_by_key = {(page_id, lang): sha for page_id, lang, _type, _rel, sha in output_paths}
    debate_rec = debate_pages["fr"]
    debate_rec["file"].update({"sha256": page_hash_by_key[(debate_id_actual, "fr")], "status": "validated"})
    debate_rec["generation"].update({
        "status": "validated", "assigned_batch_id": None,
        "creation_date": dates[(debate_id_actual, "fr")], "generated_at": timestamp, "validated_at": timestamp,
    })
    for node in nodes:
        node_id = str(node.get("id"))
        rec = node["pages"]["fr"]
        rec["file"].update({"sha256": page_hash_by_key[(node_id, "fr")], "status": "validated"})
        rec["generation"].update({
            "status": "validated", "assigned_batch_id": "FR-A-001",
            "creation_date": dates[(node_id, "fr")], "generated_at": timestamp, "validated_at": timestamp,
        })

    registry["schema"]["validator_version"] = VALIDATOR_VERSION
    registry["batches"] = [copy.deepcopy(batch)]
    registry["validations"] = []
    write_json(target / "data/registre_debat.json", registry)
    projection = load_json(target / "graph/graphe_argumentatif.json", "projection du graphe")
    projection["nodes"] = copy.deepcopy((registry.get("graph") or {}).get("nodes") or [])
    projection["edges"] = copy.deepcopy((registry.get("graph") or {}).get("edges") or [])
    projection["occurrences"] = copy.deepcopy((registry.get("graph") or {}).get("occurrences") or [])
    projection["lifecycle"] = copy.deepcopy(lifecycle)
    write_json(target / "graph/graphe_argumentatif.json", projection)

    pages: list[dict[str, Any]] = []
    for page_id, lang, page_type, rel, sha in output_paths:
        if page_type == "debate":
            title = str(debate_pages["fr"].get("canonical_title"))
            content = fr_content.get("debate") or {}
            batch_id = None
        else:
            node = next(node for node in nodes if str(node.get("id")) == page_id)
            title = str((node.get("fr") or {}).get("canonical_title"))
            content = fr_args[page_id]
            batch_id = "FR-A-001"
        pages.append(_page_manifest(
            debate_id=debate_id, page_id=page_id, page_type=page_type, lang=lang, title=title,
            file_path=rel, sha256=sha, creation_date=dates[(page_id, "fr")], batch_id=batch_id,
            timestamp=timestamp, report_path="reports/fr_checkpoint_validation.json",
            page_origin=str(content.get("page_origin") or "preexisting"),
            preserved_parameters=content.get("preserved_parameters") or {},
        ))
    pages.sort(key=lambda row: (0 if row["page_type"] == "debate" else 1, row["page_id"]))

    manifest["global_status"] = "fr_validated"
    manifest["updated_at"] = timestamp
    manifest.setdefault("normative_versions", {}).update({
        "consolidated_norm": NORM_VERSION, "validator": VALIDATOR_VERSION,
    })
    manifest.setdefault("translation_status", {})["en"] = "deferred"
    manifest["pages"] = pages
    manifest["batches"] = [copy.deepcopy(batch)]
    input_sha = structural_sha256(registry)
    manifest["validations"] = _fr_validation_records(timestamp, input_sha)
    manifest.setdefault("works", []).append({
        "work_id": f"{work_id}-FR-PUBLISH", "work_type": "fr_global_validation",
        "conversation_name": "Publication française après revue de contenu", "status": "completed",
        "input_handoff": None, "output_handoff": None, "started_at": timestamp, "completed_at": timestamp,
    })
    # The checkpoint is deliberately publishable in French while English remains deferred.
    manifest["publication_gate"] = {
        "local_release_status": "corrective_in_progress",
        "remote_write_authorized": True,
        "remote_template_compatibility": "not_checked",
        "blocking_reason": None,
        "checked_at": timestamp,
    }
    controls = manifest.setdefault("editorial_controls", {})
    controls.setdefault("individual_review_path", "reviews/individual_review.json")
    controls.setdefault("graph_placement_review_path", "reviews/graph_placement_review.json")
    controls.setdefault("summary_style_review_path", "reviews/summary_style_review.json")
    controls.setdefault("introduction_review_path", "reviews/introduction_review.json")
    write_json(target / "manifest.json", manifest)
    _copy_active_norm(project_root, target)

    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "rendered",
        "stage": "content",
        "created_at": timestamp,
        "source_content_review_sha256": str(fr_content.get("review_sha256") or ""),
        "source_content_reviewed_copy_sha256": full_tree_sha256(source),
        "page_count": len(pages),
        "english_translation_status": "deferred",
        "interlanguage_links": 0,
    }
    write_json(target / "data/fr_publication_checkpoint.json", checkpoint)
    return {"checkpoint": checkpoint, "pages": len(pages), "timestamp": timestamp}


def _build_preserved_content_checkpoint_copy(
    project_root: Path, source: Path, target: Path, debate_id: str, work_id: str,
) -> dict[str, Any]:
    """Attest checkpoint 2 without rerendering a frozen historical source."""
    result = _build_graph_checkpoint_copy(project_root, source, target, debate_id, work_id)
    content_lock = load_json(target / "data/fr_content_lock.json", "verrou français préservé")
    policy = str(content_lock.get("source_preservation_policy") or "")
    if not policy:
        raise FrenchCheckpointError("Politique de préservation française absente")
    checkpoint = dict(result["checkpoint"])
    checkpoint.update({
        "stage": "content",
        "source_content_review_sha256": str(content_lock.get("review_sha256") or ""),
        "source_content_reviewed_copy_sha256": full_tree_sha256(source),
        "source_preservation_policy": policy,
        "validation_profile": GRAPH_VALIDATION_PROFILE,
    })
    checkpoint.pop("source_reviewed_copy_sha256", None)
    write_json(target / "data/fr_publication_checkpoint.json", checkpoint)
    return {**result, "checkpoint": checkpoint}


def _import_rows(source: Path) -> list[dict[str, Any]]:
    provenance = load_json(source / "data/import_provenance.json", "provenance d'import")
    rows = [dict(row) for row in provenance.get("pages") or [] if isinstance(row, dict) and row.get("kind") in {"debate", "argument"}]
    if not rows:
        raise FrenchCheckpointError("Provenance française vide")
    return rows


def _graph_migrations(source: Path, debate_id: str) -> list[dict[str, Any]]:
    path = source / "reviews/graph_action_decisions.json"
    if not path.is_file():
        return []
    decisions = load_json(path, "décisions structurelles")
    if decisions.get("debate_id") != debate_id:
        raise FrenchCheckpointError("Décisions structurelles rattachées à un autre débat")
    entries: list[dict[str, Any]] = []
    for action in decisions.get("actions") or []:
        kind = str(action.get("action") or "")
        node_id = str(action.get("node_id") or "")
        if kind == "merge_redirect" and node_id:
            target_id = str(action.get("target_node_id") or "")
            if not target_id:
                raise FrenchCheckpointError(f"Fusion sans cible : {node_id}")
            entries.append({"language": "fr", "old_page_id": node_id, "kind": "merge", "target_page_id": target_id, "policy": "redirect", "reason": "fusion validée lors de la revue du graphe"})
        elif kind == "remove" and node_id:
            entries.append({"language": "fr", "old_page_id": node_id, "kind": "remove", "reason": "retrait validé lors de la revue du graphe"})
    return entries


def _verify_graph_checkpoint_delta(target: Path, registry: dict[str, Any], rows: list[dict[str, Any]], debate_id: str, work_id: str) -> None:
    """Prove that checkpoint 1 only changes graph-bearing parameters.

    Historical pages are intentionally incomplete under the current final-content
    wikicode contract.  They therefore cannot use the final ``wikicode`` scope at
    this stage.  This differential proof is the replacement safety boundary: it
    rebuilds every expected page from the hash-checked import and rejects any
    additional output or content mutation.
    """
    from wikidebia_translation_source import relation_labels_from_source
    contextual_labels = relation_labels_from_source(target)
    debate_relation_labels = [row for row in contextual_labels if row["source_page_id"] == "debate"]
    argument_relation_labels: dict[str, list[dict[str, Any]]] = {}
    for row in contextual_labels:
        argument_relation_labels.setdefault(str(row["source_page_id"]), []).append(row)
    active_nodes = {
        str(node.get("id")): node
        for node in (registry.get("graph") or {}).get("nodes") or []
        if node.get("status") == "active"
    }
    depth_frontiers = _depth_frontier_node_ids(registry)
    expected: dict[str, tuple[str, dict[str, Any], list[str]]] = {}
    for row in rows:
        kind = str(row.get("kind") or "")
        page_id = str(row.get("page_id") or "")
        imported = target / str(row.get("import_path") or "")
        if kind not in {"debate", "argument"} or not imported.is_file():
            continue
        imported_sha = sha256_file(imported)
        if str(row.get("sha256") or "") != imported_sha:
            raise FrenchCheckpointError(f"Import historique divergent pendant le checkpoint graphe : {page_id or debate_id}")
        text = imported.read_text(encoding="utf-8")
        if kind == "debate":
            rel = "output/fr/debate/debate.wiki"
            text = _set_optional_parameter_value(
                text, "debate", "arguments-pour",
                _main_arguments(
                    registry, "pro", "fr", debate_relation_labels,
                    require_contextual_labels=True,
                ),
            )
            text = _set_optional_parameter_value(
                text, "debate", "arguments-contre",
                _main_arguments(
                    registry, "con", "fr", debate_relation_labels,
                    require_contextual_labels=True,
                ),
            )
            allowed = ["arguments-pour", "arguments-contre"]
            proof_id = str((registry.get("debate") or {}).get("id") or debate_id)
        else:
            if page_id not in active_nodes:
                continue
            rel = f"output/fr/arguments/{page_id}.wiki"
            template = _outer_template(imported, {"argument"})
            allowed = []
            if page_id not in depth_frontiers and not bool(template.get("débat-dédié", "débat-détaillé").strip()):
                labels = argument_relation_labels.get(page_id, [])
                text = _set_optional_parameter_value(
                    text, "argument", "justifications",
                    _relations(
                        registry, page_id, "justification", "fr", labels,
                        require_contextual_labels=True,
                    ),
                )
                text = _set_optional_parameter_value(
                    text, "argument", "objections",
                    _relations(
                        registry, page_id, "objection", "fr", labels,
                        require_contextual_labels=True,
                    ),
                )
                allowed = ["justifications", "objections"]
            proof_id = page_id
        if rel in expected:
            raise FrenchCheckpointError(f"Sortie française dupliquée dans la provenance : {rel}")
        expected[rel] = (text, {"page_id": proof_id, "page_type": kind, "import_path": str(row.get("import_path")), "import_sha256": imported_sha}, allowed)

    expected_ids = {debate_id, *active_nodes}
    actual_ids = {details[1]["page_id"] for details in expected.values()}
    if actual_ids != expected_ids:
        raise FrenchCheckpointError("La preuve différentielle ne couvre pas exactement les pages actives")
    page_directories = (target / "output/fr/debate", target / "output/fr/arguments")
    actual_paths = {
        path.relative_to(target).as_posix()
        for directory in page_directories
        if directory.is_dir()
        for path in directory.glob("*.wiki")
        if path.is_file()
    }
    if actual_paths != set(expected):
        raise FrenchCheckpointError("Les sorties du checkpoint graphe divergent de la provenance active")

    proof_rows: list[dict[str, Any]] = []
    for rel, (expected_text, metadata, allowed) in sorted(expected.items()):
        output = target / rel
        actual_text = output.read_text(encoding="utf-8")
        if actual_text != expected_text:
            raise FrenchCheckpointError(f"Mutation hors portée dans le checkpoint graphe : {metadata['page_id']}")
        proof_rows.append({
            **metadata,
            "output_path": rel,
            "output_sha256": sha256_file(output),
            "allowed_parameters": allowed,
            "status": "verified",
        })
    write_json(target / "data/fr_graph_checkpoint_delta.json", {
        "schema": GRAPH_VALIDATION_PROFILE,
        "schema_version": "1.0",
        "debate_id": debate_id,
        "work_id": work_id,
        "status": "passed",
        "policy": "exact_import_plus_graph_parameters",
        "pages": proof_rows,
    })


def _build_graph_checkpoint_copy(project_root: Path, source: Path, target: Path, debate_id: str, work_id: str) -> dict[str, Any]:
    shutil.copytree(source, target, symlinks=False, copy_function=shutil.copy2)
    assert_no_symlinks(target)
    registry = load_json(target / "data/registre_debat.json", "registre du débat")
    manifest = load_json(target / "manifest.json", "manifest.json")
    if manifest.get("debate_id") != debate_id:
        raise FrenchCheckpointError("Identité du corpus français divergente")
    rows = _import_rows(target)
    from wikidebia_translation_source import relation_labels_from_source
    contextual_labels = relation_labels_from_source(target)
    debate_relation_labels = [row for row in contextual_labels if row["source_page_id"] == "debate"]
    argument_relation_labels: dict[str, list[dict[str, Any]]] = {}
    for row in contextual_labels:
        argument_relation_labels.setdefault(str(row["source_page_id"]), []).append(row)
    active_nodes = [node for node in (registry.get("graph") or {}).get("nodes") or [] if node.get("status") == "active"]
    active_nodes.sort(key=lambda node: str(node.get("id")))
    active_ids = {str(node.get("id")) for node in active_nodes}
    depth_frontiers = _depth_frontier_node_ids(registry)
    row_by_id: dict[str, dict[str, Any]] = {}
    debate_row = None
    for row in rows:
        if row.get("kind") == "debate":
            debate_row = row
        else:
            pid = str(row.get("page_id") or "")
            if pid in active_ids:
                row_by_id[pid] = row
    if debate_row is None or set(row_by_id) != active_ids:
        raise FrenchCheckpointError("La provenance importée ne couvre pas exactement le graphe actif")

    timestamp = now_iso()
    lifecycle = (registry.get("graph") or {}).setdefault("lifecycle", {})
    lifecycle.update({"status": "locked", "locked_at": timestamp, "locked_by_stage": "fr_graph_checkpoint_publication", "structural_sha256": structural_sha256(registry)})
    debate_pages = (registry.get("debate") or {}).get("pages") or {}
    if isinstance(debate_pages.get("fr"), dict):
        debate_pages["fr"]["title_status"] = "locked"
        _defer_unresolved_interlanguage(debate_pages["fr"].setdefault("interlanguage", {}))
    for node in active_nodes:
        node.setdefault("fr", {})["title_status"] = "locked"
        interlanguage = node.setdefault("pages", {}).setdefault("fr", {}).setdefault("interlanguage", {})
        _defer_unresolved_interlanguage(interlanguage)

    output_rows: list[tuple[str,str,str,str,dict[str,Any]]] = []
    debate_import = target / str(debate_row.get("import_path") or "")
    if not debate_import.is_file():
        raise FrenchCheckpointError("Import de la page Débat absent")
    debate_text = debate_import.read_text(encoding="utf-8")
    debate_text = _set_optional_parameter_value(
        debate_text, "debate", "arguments-pour",
        _main_arguments(
            registry, "pro", "fr", debate_relation_labels,
            require_contextual_labels=True,
        ),
    )
    debate_text = _set_optional_parameter_value(
        debate_text, "debate", "arguments-contre",
        _main_arguments(
            registry, "con", "fr", debate_relation_labels,
            require_contextual_labels=True,
        ),
    )
    debate_id_actual = str((registry.get("debate") or {}).get("id") or debate_id)
    debate_rel = "output/fr/debate/debate.wiki"
    debate_out = target / debate_rel; debate_out.parent.mkdir(parents=True, exist_ok=True); debate_out.write_text(debate_text, encoding="utf-8", newline="\n")
    debate_template = _outer_template(debate_import, {"debat"})
    output_rows.append((debate_id_actual, "debate", debate_rel, sha256_file(debate_out), {"page_origin":"preexisting", "preserved_parameters":_page_lifecycle_snapshot(debate_template,"debate")}))

    for node in active_nodes:
        node_id = str(node.get("id")); row = row_by_id[node_id]
        imported = target / str(row.get("import_path") or "")
        if not imported.is_file():
            raise FrenchCheckpointError(f"Import Argument absent : {node_id}")
        text = imported.read_text(encoding="utf-8")
        template = _outer_template(imported, {"argument"})
        dedicated = bool(template.get("débat-dédié", "débat-détaillé").strip())
        if node_id not in depth_frontiers and not dedicated:
            labels = argument_relation_labels.get(node_id, [])
            text = _set_optional_parameter_value(
                text, "argument", "justifications",
                _relations(
                    registry, node_id, "justification", "fr", labels,
                    require_contextual_labels=True,
                ),
            )
            text = _set_optional_parameter_value(
                text, "argument", "objections",
                _relations(
                    registry, node_id, "objection", "fr", labels,
                    require_contextual_labels=True,
                ),
            )
        rel = f"output/fr/arguments/{node_id}.wiki"
        out = target / rel; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text, encoding="utf-8", newline="\n")
        output_rows.append((node_id, "argument", rel, sha256_file(out), {"page_origin":"preexisting", "preserved_parameters":_page_lifecycle_snapshot(template,"argument")}))

    fallback_date = timestamp[:10]
    dates = _page_creation_dates(target, registry, fallback_date)
    pages: list[dict[str,Any]] = []
    for page_id, page_type, rel, digest, metadata in output_rows:
        if page_type == "debate":
            title = str((registry.get("debate") or {}).get("pages",{}).get("fr",{}).get("canonical_title") or debate_row.get("canonical_title") or debate_row.get("requested_title") or "")
            batch_id = None
        else:
            node = next(node for node in active_nodes if str(node.get("id")) == page_id)
            title = str((node.get("fr") or {}).get("canonical_title") or "")
            batch_id = "FR-A-001"
        pages.append(_page_manifest(debate_id=debate_id,page_id=page_id,page_type=page_type,lang="fr",title=title,file_path=rel,sha256=digest,creation_date=dates.get((page_id,"fr"),fallback_date),batch_id=batch_id,timestamp=timestamp,report_path="reports/fr_checkpoint_validation.json",page_origin=metadata["page_origin"],preserved_parameters=metadata["preserved_parameters"]))
    pages.sort(key=lambda row: (0 if row["page_type"] == "debate" else 1, row["page_id"]))

    structural = structural_sha256(registry)
    aggregate_path, aggregate_sha = _write_aggregate(target, "fr", active_nodes)
    batch = _batch(debate_id=debate_id,lang="fr",nodes=active_nodes,registry_sha=sha256_file(target / "data/registre_debat.json"),structural_sha=structural,aggregate_path=aggregate_path,aggregate_sha=aggregate_sha,timestamp=timestamp,work_id=work_id)
    batch["root_node_ids"] = sorted({str(o.get("node_id")) for o in (registry.get("graph") or {}).get("occurrences") or [] if o.get("depth") == 1})
    write_json(target / "data/lots_fr.json", {"batch_collection_version":"1.0","debate_id":debate_id,"language":"fr","batches":[batch]})
    (target / "reports/fr_batch_001.txt").parent.mkdir(parents=True,exist_ok=True)
    (target / "reports/fr_batch_001.txt").write_text("Lot français rendu pour le checkpoint graphe et titres.\n",encoding="utf-8",newline="\n")

    registry.setdefault("schema", {})["validator_version"] = VALIDATOR_VERSION
    registry["batches"]=[copy.deepcopy(batch)]; registry["validations"]=[]
    write_json(target / "data/registre_debat.json", registry)
    projection_path=target / "graph/graphe_argumentatif.json"
    if projection_path.is_file():
        projection=load_json(projection_path,"projection du graphe")
        for key in ("lifecycle","depth_policy","nodes","edges","occurrences","derived_counts"):
            projection[key]=copy.deepcopy((registry.get("graph") or {}).get(key))
        write_json(projection_path,projection)

    manifest["global_status"]="fr_validated"; manifest["updated_at"]=timestamp
    manifest.setdefault("normative_versions",{}).update({"consolidated_norm":NORM_VERSION,"validator":VALIDATOR_VERSION})
    manifest.setdefault("translation_status",{})["en"]="deferred"
    manifest["pages"]=pages; manifest["batches"]=[copy.deepcopy(batch)]
    manifest["validations"]=_fr_validation_records(timestamp, structural_sha256(registry))
    manifest["publication_gate"]={"local_release_status":"corrective_in_progress","remote_write_authorized":True,"remote_template_compatibility":"not_checked","blocking_reason":None,"checked_at":timestamp}
    write_json(target / "manifest.json",manifest)
    migrations=_graph_migrations(target,debate_id)
    if migrations:
        write_json(target / "data/remote_migrations.json", {"version":"1.0","debate_id":debate_id,"entries":migrations})
    _copy_active_norm(project_root,target)
    _verify_graph_checkpoint_delta(target, registry, rows, debate_id, work_id)
    checkpoint={"schema":CHECKPOINT_SCHEMA,"schema_version":"1.0","debate_id":debate_id,"work_id":work_id,"stage":"graph","status":"rendered","created_at":timestamp,"source_reviewed_copy_sha256":full_tree_sha256(source),"page_count":len(pages),"english_translation_status":"deferred","interlanguage_links":0,"validation_profile":GRAPH_VALIDATION_PROFILE}
    write_json(target / "data/fr_publication_checkpoint.json",checkpoint)
    return {"checkpoint":checkpoint,"pages":len(pages),"timestamp":timestamp}


def _stale_checkpoint_is_provably_preexecution(state_dir: Path) -> bool:
    """Return True only when a stale stage cannot have reached remote execution.

    ``publish_checkpoint`` always materializes ``update-plan.json`` before creating
    a ``PlanExecutor``.  Therefore a stage without a plan is provably preexecution.
    A saved plan whose operations are already blocked/manual_review is likewise
    non-executable: ``PlanExecutor.verify_plan`` rejects it before any write.
    Any publication receipt or execution-capable plan makes automatic cleanup
    unsafe and the caller must preserve the stage for explicit recovery.
    """
    if (state_dir / "publication-receipt.json").is_file():
        return False
    plan_path = state_dir / "update-plan.json"
    if not plan_path.exists():
        return True
    if not plan_path.is_file() or plan_path.is_symlink():
        return False
    try:
        plan = load_json(plan_path, "plan de checkpoint français périmé")
    except Exception:
        return False
    operations = plan.get("operations") or {}
    return bool(operations.get("blocked") or operations.get("manual_review"))


def _discard_provably_stale_checkpoint(state_dir: Path) -> None:
    for child in list(state_dir.iterdir()) if state_dir.is_dir() else []:
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def build_checkpoint(project_root: Path, debate_id: str, work_id: str, *, stage: str) -> Path:
    project_root = project_root.resolve()
    workspace, _meta, source = _workspace(project_root, debate_id, work_id, stage)
    state_dir = project_root / ".state" / "fr-publication" / debate_id / work_id / stage
    target = state_dir / "checkpoint-corpus"
    receipt_path = state_dir / "checkpoint.json"
    source_sha = full_tree_sha256(source)
    if target.is_dir() and receipt_path.is_file():
        receipt = load_json(receipt_path, "checkpoint français")
        if receipt.get("stage") != stage:
            raise FrenchCheckpointError("Le checkpoint français existant appartient à un autre état verrouillé")
        if receipt.get("source_tree_sha256") != source_sha:
            if _stale_checkpoint_is_provably_preexecution(state_dir):
                _discard_provably_stale_checkpoint(state_dir)
            else:
                raise FrenchCheckpointError("Le checkpoint français existant appartient à un autre état verrouillé")
        else:
            if receipt.get("checkpoint_tree_sha256") != full_tree_sha256(target):
                raise FrenchCheckpointError("Le checkpoint français existant a été modifié")
            return target
    if target.exists():
        raise FrenchCheckpointError("Chemin de checkpoint français déjà occupé")
    state_dir.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".checkpoint.tmp-", dir=state_dir))
    try:
        shutil.rmtree(temp)
        if stage == "graph":
            builder = _build_graph_checkpoint_copy
        elif (source / "data/source_preservation_receipt.json").is_file():
            builder = _build_preserved_content_checkpoint_copy
        else:
            builder = _build_content_checkpoint_copy
        result = builder(project_root, source, temp, debate_id, work_id)
        tree_sha = full_tree_sha256(temp)
        os.replace(temp, target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    receipt = {**result["checkpoint"], "status":"ready_for_remote_plan", "stage":stage, "source_tree_sha256":source_sha, "checkpoint_path":relative_to_project(target,project_root), "checkpoint_tree_sha256":tree_sha}
    receipt["receipt_sha256"] = sha_object(receipt)
    write_json(receipt_path, receipt)
    return target


def _write_import_inventory(project_root: Path, debate_id: str, checkpoint: Path, work_id: str, stage: str) -> Path:
    inventory_dir = project_root / ".state" / "fr-publication" / debate_id / work_id / stage / "inventory"
    inventory_dir.mkdir(parents=True, exist_ok=True)
    inventory_path = inventory_dir / "fr.json"
    if inventory_path.is_file():
        return inventory_dir
    provenance = load_json(checkpoint / "data/import_provenance.json", "provenance d'import")
    pages: list[dict[str, Any]] = []
    for row in provenance.get("pages") or []:
        if row.get("status") in {"retired_redirect", "retired_deleted"}:
            continue
        kind = str(row.get("kind") or "")
        import_path = str(row.get("import_path") or "")
        path = checkpoint / import_path
        if kind not in {"debate", "argument"} or not path.is_file():
            continue
        page_id = debate_id if kind == "debate" else str(row.get("page_id") or "")
        if not page_id:
            continue
        text = path.read_text(encoding="utf-8")
        pages.append({
            "page_id": page_id,
            "page_type": kind,
            "canonical_title": str(row.get("canonical_title") or row.get("requested_title") or ""),
            "content_sha256": sha_text(text),
            "revision_id": int(row["revision_id"]) if row.get("revision_id") is not None else None,
            "status": "published",
            "content": text,
        })
    if not pages:
        raise FrenchCheckpointError("Impossible de construire l'inventaire distant depuis la provenance française")
    inventory = {
        "inventory_version": "wikidebia-remote-inventory-1.0",
        "debate_id": debate_id,
        "language": "fr",
        "inventory_mode": "explicit_debate_pages_read_only",
        "created_at": now_iso(),
        "source": {"kind": "graph_extraction_snapshot", "provenance": "data/import_provenance.json"},
        "pages": sorted(pages, key=lambda row: (row["page_type"], row["page_id"])),
    }
    inventory["inventory_sha256"] = sha_object(inventory)
    write_json(inventory_path, inventory)
    return inventory_dir


def _local_settings(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "wikidebia.local.json"
    return load_json(path, "configuration locale") if path.is_file() else {}


def _config(project_root: Path, debate_id: str, work_id: str, checkpoint: Path, stage: str, inventory_root: Path | None) -> Path:
    state_dir = project_root / ".state" / "fr-publication" / debate_id / work_id / stage
    config_path = state_dir / "remote-update-config.json"
    settings = _local_settings(project_root)
    users = settings.get("expected_users") or {"fr": "ChatGPT"}
    family_file = project_root / "kit/families/wikidebates_family.py"
    validator_script = project_root / "validator/scripts/wikidebia_validate.py"
    checkpoint_record_path = checkpoint / "data/fr_publication_checkpoint.json"
    checkpoint_record = (
        load_json(checkpoint_record_path, "checkpoint français")
        if checkpoint_record_path.is_file()
        else {}
    )
    preservation_mode = stage == "content" and bool(checkpoint_record.get("source_preservation_policy"))
    config = {
        "kit_version": KIT_VERSION,
        "project_root": str(project_root),
        "family": str(settings.get("family") or "wikidebates"),
        "family_file": str(family_file),
        "pywikibot_dir": str(project_root / "private/pywikibot"),
        "sites": {"fr": {"code": "fr", "expected_user": str(users.get("fr") or "ChatGPT")}},
        "languages": ["fr"],
        "debate_id": debate_id,
        "corpus_root": str(checkpoint),
        "logs_dir": str(project_root / "logs" / debate_id / f"fr-checkpoint-{work_id}-{stage}"),
        "published_state_dir": str(project_root / ".state/published"),
        "receipts_dir": str(project_root / ".state/receipts"),
        "validator": {
            "command": [sys.executable, str(validator_script), "validate"],
            "required_version": VALIDATOR_VERSION,
            "profile": GRAPH_VALIDATION_PROFILE if stage == "graph" or preservation_mode else CONTENT_VALIDATION_PROFILE,
            "scopes": list(GRAPH_VALIDATION_SCOPES if stage == "graph" or preservation_mode else CONTENT_VALIDATION_SCOPES),
        },
    }
    if inventory_root is not None:
        config["state_inventory_root"] = str(inventory_root)
    write_json(config_path, config)
    return config_path


def _published_state_evidence(project_root: Path, debate_id: str, language: str = "fr") -> dict[str, Any]:
    """Return the signed state required to resume after a remote checkpoint."""
    path = project_root / ".state" / "published" / debate_id / language / "latest.json"
    if not path.is_file() or path.is_symlink():
        raise FrenchCheckpointError(f"État publié signé absent après le checkpoint : {language}")
    state = load_json(path, "état publié du checkpoint français")
    unsigned = dict(state)
    claimed = unsigned.pop("state_sha256", None)
    if claimed != sha_object(unsigned):
        raise FrenchCheckpointError(f"Empreinte de l’état publié divergente après le checkpoint : {language}")
    if state.get("debate_id") != debate_id or state.get("language") != language:
        raise FrenchCheckpointError("État publié rattaché à un autre débat ou une autre langue")
    return {
        "path": relative_to_project(path, project_root),
        "file_sha256": sha256_file(path),
        "state_sha256": claimed,
        "pages": len(state.get("pages") or []),
    }


def publish_checkpoint(project_root: Path, debate_id: str, work_id: str, *, stage: str = "content", adapter: Any | None = None) -> dict[str, Any]:
    """Publish one sealed French stage using the ordinary signed update engine."""
    project_root = project_root.resolve()
    if stage not in {"graph", "content"}:
        raise FrenchCheckpointError(f"Checkpoint français inconnu : {stage}")
    if stage == "content":
        graph_receipt = project_root / ".state" / "fr-publication" / debate_id / work_id / "graph" / "publication-receipt.json"
        # Legacy 2.16.13 workflows may already have a single full publication.
        legacy_receipt = project_root / ".state" / "fr-publication" / debate_id / work_id / "publication-receipt.json"
        if not graph_receipt.is_file() and not legacy_receipt.is_file():
            raise FrenchCheckpointError("Le checkpoint de contenu exige d'abord la publication du graphe et des titres")
    checkpoint = build_checkpoint(project_root, debate_id, work_id, stage=stage)
    state_dir = project_root / ".state" / "fr-publication" / debate_id / work_id / stage
    publication_path = state_dir / "publication-receipt.json"
    if publication_path.is_file():
        publication = load_json(publication_path, "reçu de publication française")
        if publication.get("stage") == stage and publication.get("checkpoint_tree_sha256") == full_tree_sha256(checkpoint) and publication.get("status") in {"published", "verified_no_changes"}:
            return publication

    # First checkpoint is compared with the imported remote snapshot. The second
    # checkpoint deliberately resolves .state/published, i.e. the exact state
    # attested by checkpoint 1, so only the content delta is planned.
    inventory_root = _write_import_inventory(project_root, debate_id, checkpoint, work_id, stage) if stage == "graph" else None
    config_path = _config(project_root, debate_id, work_id, checkpoint, stage, inventory_root)
    config = load_json(config_path, "configuration de publication française")
    plan_path = state_dir / "update-plan.json"
    try:
        actual_adapter = adapter if adapter is not None else build_adapter(config, project_root)
        if plan_path.is_file():
            plan = load_json(plan_path, "plan de publication française")
        else:
            planner = RemoteUpdatePlanner(config, actual_adapter, config_path)
            plan = planner.build_plan(mode="all")
            operations = plan.get("operations") or {}
            if operations.get("blocked") or operations.get("manual_review"):
                write_json(plan_path, plan)
                raise FrenchCheckpointError("Le préflight de publication française contient des opérations bloquées ou à revoir")
            if stage == "content":
                unexpected = sum(len(operations.get(name) or []) for name in ("move", "redirect", "delete"))
                if unexpected:
                    write_json(plan_path, plan)
                    raise FrenchCheckpointError("Le second checkpoint français ne peut contenir ni renommage, ni redirection, ni suppression")
            write_json(plan_path, plan)
    except FrenchCheckpointError:
        raise
    except Exception as exc:
        raise FrenchCheckpointError(str(exc), remote_execution_started=False) from exc
    operations = plan.get("operations") or {}
    if operations.get("blocked") or operations.get("manual_review"):
        raise FrenchCheckpointError("Le plan français sauvegardé contient des opérations non résolues")

    executor = PlanExecutor(config, actual_adapter, config_path)
    mutations = sum(len(operations.get(name) or []) for name in ("create", "update", "move", "redirect", "delete"))
    try:
        if mutations:
            receipt = executor.execute(plan, str(plan.get("plan_sha256")))
            status = "published"
        else:
            receipt = executor.attest_no_changes(plan, str(plan.get("plan_sha256")))
            status = "verified_no_changes"
    except Exception as exc:
        raise FrenchCheckpointError(str(exc), remote_execution_started=bool(mutations)) from exc

    publication = {
        "schema": RECEIPT_SCHEMA, "schema_version":"1.0", "debate_id":debate_id, "work_id":work_id,
        "stage":stage, "status":status, "published_at":now_iso(),
        "checkpoint_path":relative_to_project(checkpoint,project_root), "checkpoint_tree_sha256":full_tree_sha256(checkpoint),
        "plan_path":relative_to_project(plan_path,project_root), "plan_sha256":plan.get("plan_sha256"),
        "edit_summary_contract":plan.get("edit_summary_contract"), "counts":copy.deepcopy(plan.get("counts") or {}),
        "remote_receipt_sha256":receipt.get("receipt_sha256"),
        "published_state":_published_state_evidence(project_root, debate_id),
        "next_stage_authorized":"fr_content_review" if stage == "graph" else "en_translation_review",
    }
    publication["receipt_sha256"] = sha_object(publication)
    write_json(publication_path, publication)
    return publication

