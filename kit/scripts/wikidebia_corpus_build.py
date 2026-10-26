#!/usr/bin/env python3
"""Shared safety helpers for graph-draft review and corpus promotion."""

from __future__ import annotations

from wikidebia_release_info import KIT_VERSION, NORM_VERSION, VALIDATOR_VERSION

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

REVIEW_ENVELOPE = "reviews/graph_build_review.json"
PLACEMENT_REVIEW = "reviews/graph_placement_review.json"
GRAPH_CORRECTION_REVIEW = "reviews/graph_correction.json"
GRAPH_TITLE_REVIEW = "reviews/fr/graph_title_review.json"
REVIEW_REPORT_JSON = "reports/graph_build_review_report.json"
REVIEW_REPORT_TXT = "reports/graph_build_review_report.txt"
FINAL_VALIDATION_JSON = "reports/graph_review_validation.json"
FINAL_VALIDATION_TXT = "reports/graph_review_validation.txt"
PROMOTION_READY = "reports/corpus_promotion_ready.json"

# Review files are deliberately excluded from the prepared source fingerprint:
# reviewers must be able to edit them without invalidating the graph snapshot.
REVIEW_MUTABLE_PATHS = {
    REVIEW_ENVELOPE,
    PLACEMENT_REVIEW,
    GRAPH_CORRECTION_REVIEW,
    GRAPH_TITLE_REVIEW,
    REVIEW_REPORT_JSON,
    REVIEW_REPORT_TXT,
    FINAL_VALIDATION_JSON,
    FINAL_VALIDATION_TXT,
    PROMOTION_READY,
}

# This execution trace contains no corpus data and older kit releases stored
# absolute workspace paths in its two report fields.  Keeping it outside the
# graph payload fingerprint makes review packages portable across machines and
# sanitized continuity snapshots.
PORTABILITY_MUTABLE_PATHS = {
    "reports/initial_validation_execution.json",
}

REQUIRED_ATTESTATIONS = (
    "scope_and_proposition_reviewed",
    "graph_completeness_reviewed",
    "main_argument_placement_reviewed",
    "parent_child_relations_reviewed",
    "reuse_and_occurrences_reviewed",
    "canonical_titles_reviewed",
    "import_provenance_reviewed",
    "imports_are_not_final_outputs_confirmed",
    "no_final_pages_generated_confirmed",
)

class CorpusBuildError(RuntimeError):
    pass


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def load_json(path: Path, label: str | None = None) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusBuildError(f"{label or path.name} illisible : {path}") from exc
    if not isinstance(value, dict):
        raise CorpusBuildError(f"{label or path.name} doit être un objet JSON")
    return value


def validate_debate_id(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,127}", value):
        raise CorpusBuildError("debate_id invalide; utiliser 2 à 128 caractères minuscules, chiffres, _ ou -")
    return value


def relative_to_project(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError as exc:
        raise CorpusBuildError(f"Chemin extérieur au projet interdit : {path}") from exc


def assert_no_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise CorpusBuildError(f"Lien symbolique interdit : {root}")
    for path in root.rglob("*"):
        try:
            mode = path.lstat().st_mode
        except OSError as exc:
            raise CorpusBuildError(f"Fichier inaccessible pendant le contrôle : {path}") from exc
        if stat.S_ISLNK(mode):
            raise CorpusBuildError(f"Lien symbolique interdit dans le build : {path.relative_to(root).as_posix()}")
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise CorpusBuildError(f"Type de fichier interdit dans le build : {path.relative_to(root).as_posix()}")


def inventory(root: Path, *, excluded: Iterable[str] = ()) -> list[dict[str, Any]]:
    excluded_set = set(excluded)
    rows: list[dict[str, Any]] = []
    for path in sorted((p for p in root.rglob("*") if p.is_file()), key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if rel in excluded_set:
            continue
        rows.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return rows


def inventory_sha256(rows: list[dict[str, Any]]) -> str:
    return sha256_bytes(canonical_json(rows))


def build_payload_sha256(root: Path) -> str:
    return inventory_sha256(inventory(root, excluded=REVIEW_MUTABLE_PATHS | PORTABILITY_MUTABLE_PATHS))


def compatible_legacy_build_payload_sha256s(root: Path) -> set[str]:
    """Return tightly bounded pre-portability fingerprints for old reviews.

    Before the execution trace was excluded, its ``report_json`` and
    ``report_text`` fields contained absolute paths.  A continuity snapshot may
    sanitize those two fields.  Reconstruct only that historical representation
    in memory; every other byte remains covered by the legacy fingerprint.
    """
    rows = inventory(root, excluded=REVIEW_MUTABLE_PATHS)
    candidates = {inventory_sha256(rows)}
    rel = "reports/initial_validation_execution.json"
    path = root / rel
    if not path.is_file() or path.is_symlink():
        return candidates
    try:
        execution = load_json(path, "trace d’exécution de la validation initiale")
    except CorpusBuildError:
        return candidates
    if not isinstance(execution.get("report_json"), str) or not isinstance(execution.get("report_text"), str):
        return candidates
    legacy = dict(execution)
    legacy["report_json"] = str((root / "reports/initial_validation.json").resolve())
    legacy["report_text"] = str((root / "reports/initial_validation.txt").resolve())
    payload = json.dumps(legacy, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    virtual_rows = [dict(row) for row in rows]
    row = next((item for item in virtual_rows if item.get("path") == rel), None)
    if row is None:
        return candidates
    row["size_bytes"] = len(payload)
    row["sha256"] = sha256_bytes(payload)
    candidates.add(inventory_sha256(virtual_rows))
    return candidates


def full_tree_sha256(root: Path) -> str:
    return inventory_sha256(inventory(root))


def assert_control_directory(path: Path, project_root: Path, *, create: bool = False) -> Path:
    if path.is_symlink():
        raise CorpusBuildError(f"Lien symbolique interdit pour un répertoire de contrôle : {path}")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    resolved = path.resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError as exc:
        raise CorpusBuildError(f"Répertoire de contrôle extérieur au projet interdit : {path}") from exc
    return resolved


def resolve_build(project_root: Path, debate_id: str) -> Path:
    validate_debate_id(debate_id)
    state = project_root / ".state"
    assert_control_directory(state, project_root)
    base_raw = state / "corpus-builds"
    base = assert_control_directory(base_raw, project_root)
    raw_build = base_raw / debate_id
    if raw_build.is_symlink():
        raise CorpusBuildError(f"Lien symbolique interdit pour le build : {raw_build}")
    build = raw_build.resolve()
    try:
        build.relative_to(base)
    except ValueError as exc:
        raise CorpusBuildError("Build extérieur à .state/corpus-builds interdit") from exc
    if build.parent != base:
        raise CorpusBuildError("Le build doit être exactement .state/corpus-builds/<debate_id>")
    if not build.is_dir():
        raise CorpusBuildError(f"Build introuvable : .state/corpus-builds/{debate_id}")
    assert_no_symlinks(build)
    manifest = load_json(build / "manifest.json", "manifest.json")
    if manifest.get("debate_id") != debate_id:
        raise CorpusBuildError("Le debate_id du manifeste ne correspond pas au dossier du build")
    registry = load_json(build / "data" / "registre_debat.json", "registre maître")
    if (registry.get("debate") or {}).get("id") != debate_id:
        raise CorpusBuildError("Le debate_id du registre maître ne correspond pas au build")
    return build




def resolve_active_corpus(project_root: Path, debate_id: str) -> Path:
    """Resolve exactly ``corpus/<debate_id>`` and reject links or draft builds."""
    validate_debate_id(debate_id)
    corpus_root_raw = project_root / "corpus"
    corpus_root = assert_control_directory(corpus_root_raw, project_root)
    raw_corpus = corpus_root_raw / debate_id
    if raw_corpus.is_symlink():
        raise CorpusBuildError(f"Lien symbolique interdit pour le corpus : {raw_corpus}")
    corpus = raw_corpus.resolve()
    try:
        corpus.relative_to(corpus_root)
    except ValueError as exc:
        raise CorpusBuildError("Corpus extérieur à corpus/ interdit") from exc
    if corpus.parent != corpus_root:
        raise CorpusBuildError("Le corpus doit être exactement corpus/<debate_id>")
    if not corpus.is_dir():
        raise CorpusBuildError(f"Corpus promu introuvable : corpus/{debate_id}")
    assert_no_symlinks(corpus)
    manifest = load_json(corpus / "manifest.json", "manifest.json")
    if manifest.get("debate_id") != debate_id:
        raise CorpusBuildError("Le debate_id du manifeste ne correspond pas au dossier du corpus")
    registry = load_json(corpus / "data" / "registre_debat.json", "registre maître")
    if (registry.get("debate") or {}).get("id") != debate_id:
        raise CorpusBuildError("Le debate_id du registre maître ne correspond pas au corpus")
    assert_graph_validated_without_final_pages(corpus)
    return corpus

def assert_graph_draft_without_final_pages(build: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = load_json(build / "manifest.json", "manifest.json")
    registry = load_json(build / "data" / "registre_debat.json", "registre maître")
    projection = load_json(build / "graph" / "graphe_argumentatif.json", "projection du graphe")
    if manifest.get("global_status") != "graph_draft":
        raise CorpusBuildError(f"La revue exige global_status=graph_draft, trouvé {manifest.get('global_status')!r}")
    lifecycle = ((registry.get("graph") or {}).get("lifecycle") or {})
    if lifecycle.get("status") != "draft":
        raise CorpusBuildError("La revue exige un graphe au statut draft")
    if manifest.get("pages"):
        raise CorpusBuildError("Le build graph_draft ne doit déclarer aucune page finale")
    forbidden: list[str] = []
    output = build / "output"
    if output.exists():
        forbidden.extend(p.relative_to(build).as_posix() for p in output.rglob("*") if p.is_file())
    if forbidden:
        raise CorpusBuildError(f"Pages ou sorties finales interdites avant promotion : {forbidden[:5]}")
    release = manifest.get("release") or {}
    if any(release.get(key) is not None for key in ("release_manifest_path", "release_zip_path", "released_at", "archived_at", "release_receipt_path")):
        raise CorpusBuildError("Le build graph_draft contient déjà des métadonnées de libération")
    return manifest, registry, projection


def assert_graph_validated_without_final_pages(build: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = load_json(build / "manifest.json", "manifest.json")
    registry = load_json(build / "data" / "registre_debat.json", "registre maître")
    projection = load_json(build / "graph" / "graphe_argumentatif.json", "projection du graphe")
    if manifest.get("global_status") != "graph_validated":
        raise CorpusBuildError(f"La promotion exige global_status=graph_validated, trouvé {manifest.get('global_status')!r}")
    lifecycle = ((registry.get("graph") or {}).get("lifecycle") or {})
    if lifecycle.get("status") != "validated" or not lifecycle.get("structural_sha256"):
        raise CorpusBuildError("La promotion exige un graphe validé avec empreinte structurelle")
    if manifest.get("pages"):
        raise CorpusBuildError("La promotion de cette phase interdit toute page finale déclarée")
    output = build / "output"
    if output.exists() and any(p.is_file() for p in output.rglob("*")):
        raise CorpusBuildError("La promotion de cette phase interdit tout fichier sous output/")
    return manifest, registry, projection


def active_graph(registry: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    graph = registry.get("graph") or {}
    nodes = [n for n in graph.get("nodes", []) if n.get("status") == "active"]
    node_ids = {n.get("id") for n in nodes}
    edges = [e for e in graph.get("edges", []) if e.get("status") == "active"]
    edge_ids = {e.get("id") for e in edges}
    occurrences = [o for o in graph.get("occurrences", []) if o.get("node_id") in node_ids and (o.get("edge_id") is None or o.get("edge_id") in edge_ids)]
    return nodes, edges, occurrences


def structural_payload(registry: Mapping[str, Any]) -> dict[str, Any]:
    nodes, edges, occurrences = active_graph(registry)
    payload_nodes = []
    for node in sorted(nodes, key=lambda item: item["id"]):
        fr = node.get("fr") or {}
        payload_nodes.append({
            "id": node["id"],
            "canonical_title_fr": fr.get("canonical_title", ""),
            "displayed_title_fr": fr.get("displayed_title", ""),
        })
    payload_edges = [
        {key: edge.get(key) for key in ("id", "parent_node_id", "child_node_id", "relation", "order")}
        for edge in sorted(edges, key=lambda item: item["id"])
    ]
    payload_occurrences = [
        {key: occ.get(key) for key in ("id", "node_id", "parent_occurrence_id", "edge_id", "branch", "depth", "order", "occurrence_role", "render_children")}
        for occ in sorted(occurrences, key=lambda item: item["id"])
    ]
    return {"nodes": payload_nodes, "edges": payload_edges, "occurrences": payload_occurrences}


def structural_sha256(registry: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(structural_payload(registry)))


def prepare_placement_review(registry: Mapping[str, Any], debate_id: str) -> dict[str, Any]:
    _, edges, occurrences = active_graph(registry)
    edge_by_id = {edge.get("id"): edge for edge in edges}
    entries: list[dict[str, Any]] = []
    for occ in sorted(occurrences, key=lambda item: item["id"]):
        depth = occ.get("depth")
        if depth == 1:
            entry = {
                "occurrence_id": occ.get("id"),
                "node_id": occ.get("node_id"),
                "declared_depth": depth,
                "placement_status": "pending",
                "declared_function": "main_argument",
                "semantic_target": "debate",
                "direct_fit": False,
                "rationale": "",
                "correction": {
                    "action": "none",
                    "target_node_id": None,
                    "new_parent_occurrence_id": None,
                    "new_relation": None,
                    "new_branch": None,
                    "page_disposition": None,
                    "reason": "",
                    "edit_summary_parent": "",
                    "edit_summary_page": "",
                },
                "main_argument_review": {
                    "direct_answer_to_debate": False,
                    "autonomous_without_parent": False,
                    "organizes_distinct_argument_family": False,
                    "more_general_nonduplicate_parent_available": None,
                    "principally_supports_or_attacks_specific_argument": None,
                    "principally_example_or_specialization": None,
                },
            }
        else:
            edge = edge_by_id.get(occ.get("edge_id")) or {}
            entry = {
                "occurrence_id": occ.get("id"),
                "node_id": occ.get("node_id"),
                "declared_depth": depth,
                "placement_status": "pending",
                "declared_function": edge.get("relation"),
                "semantic_target": occ.get("parent_occurrence_id"),
                "direct_fit": False,
                "rationale": "",
                "correction": {
                    "action": "none",
                    "target_node_id": None,
                    "new_parent_occurrence_id": None,
                    "new_relation": None,
                    "new_branch": None,
                    "page_disposition": None,
                    "reason": "",
                    "edit_summary_parent": "",
                    "edit_summary_page": "",
                },
                "subordinate_review": {
                    "parent_is_best_immediate_target": False,
                    "relation_to_parent_explicit": False,
                },
            }
        entries.append(entry)
    return {
        "schema_version": "1.0",
        "normative_revision": NORM_VERSION,
        "debate_id": debate_id,
        "entries": entries,
    }


def placement_review_issues(review: Any, registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(review, dict):
        return [{"reason": "missing_or_invalid_document"}]
    debate_id = (registry.get("debate") or {}).get("id")
    if review.get("debate_id") != debate_id:
        issues.append({"reason": "debate_id", "expected": debate_id, "actual": review.get("debate_id")})
    entries = review.get("entries")
    if not isinstance(entries, list):
        return issues + [{"reason": "missing_entries"}]
    _, edges, occurrences = active_graph(registry)
    occ_by_id = {o.get("id"): o for o in occurrences}
    edge_by_id = {e.get("id"): e for e in edges}
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("occurrence_id"), str):
            issues.append({"reason": "invalid_entry"})
            continue
        oid = entry["occurrence_id"]
        if oid in by_id:
            issues.append({"reason": "duplicate_entry", "occurrence_id": oid})
        by_id[oid] = entry
    if set(by_id) != set(occ_by_id):
        issues.append({"reason": "coverage", "missing": sorted(set(occ_by_id) - set(by_id)), "extra": sorted(set(by_id) - set(occ_by_id))})
    for oid, occ in occ_by_id.items():
        entry = by_id.get(oid)
        if not entry:
            continue
        depth = occ.get("depth")
        if entry.get("node_id") != occ.get("node_id"):
            issues.append({"reason": "node_id", "occurrence_id": oid})
        if entry.get("declared_depth") != depth:
            issues.append({"reason": "declared_depth", "occurrence_id": oid})
        if entry.get("placement_status") not in {"approved", "moved_after_review"}:
            issues.append({"reason": "placement_status", "occurrence_id": oid})
        if entry.get("direct_fit") is not True:
            issues.append({"reason": "direct_fit", "occurrence_id": oid})
        if not isinstance(entry.get("rationale"), str) or len(entry["rationale"].strip()) < 24:
            issues.append({"reason": "rationale", "occurrence_id": oid})
        if depth == 1:
            if entry.get("declared_function") != "main_argument":
                issues.append({"reason": "declared_function", "occurrence_id": oid})
            if entry.get("semantic_target") != "debate":
                issues.append({"reason": "semantic_target", "occurrence_id": oid})
            main = entry.get("main_argument_review")
            if not isinstance(main, dict):
                issues.append({"reason": "main_argument_review", "occurrence_id": oid})
                continue
            for field in ("direct_answer_to_debate", "autonomous_without_parent", "organizes_distinct_argument_family"):
                if main.get(field) is not True:
                    issues.append({"reason": field, "occurrence_id": oid})
            for field in ("more_general_nonduplicate_parent_available", "principally_supports_or_attacks_specific_argument", "principally_example_or_specialization"):
                if main.get(field) is not False:
                    issues.append({"reason": field, "occurrence_id": oid})
        else:
            edge = edge_by_id.get(occ.get("edge_id")) or {}
            if entry.get("semantic_target") != occ.get("parent_occurrence_id"):
                issues.append({"reason": "semantic_target", "occurrence_id": oid})
            if entry.get("declared_function") != edge.get("relation"):
                issues.append({"reason": "declared_function", "occurrence_id": oid})
            subordinate = entry.get("subordinate_review")
            if not isinstance(subordinate, dict):
                issues.append({"reason": "subordinate_review", "occurrence_id": oid})
                continue
            for field in ("parent_is_best_immediate_target", "relation_to_parent_explicit"):
                if subordinate.get(field) is not True:
                    issues.append({"reason": field, "occurrence_id": oid})
    return issues


def review_sha256(review: Mapping[str, Any]) -> str:
    body = dict(review)
    body.pop("review_sha256", None)
    return sha256_bytes(canonical_json(body))


def verify_review_envelope(review: dict[str, Any], *, debate_id: str, source_sha256: str) -> list[str]:
    errors: list[str] = []
    if review.get("schema") != "wikidebia-graph-build-review-1.0":
        errors.append("schema")
    # kit_version / validator_version are retained as provenance. The stable
    # review schema is the compatibility gate.
    if review.get("debate_id") != debate_id:
        errors.append("debate_id")
    if review.get("source_build_sha256") != source_sha256:
        errors.append("source_build_sha256")
    if review.get("decision") not in {"approved", "rejected"}:
        errors.append("decision")
    if not isinstance(review.get("reviewer"), str) or len(review["reviewer"].strip()) < 2:
        errors.append("reviewer")
    reviewed_at = review.get("reviewed_at")
    try:
        parsed_reviewed_at = dt.datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
        if parsed_reviewed_at.utcoffset() is None:
            errors.append("reviewed_at_timezone")
    except Exception:
        errors.append("reviewed_at")
    attestations = review.get("attestations")
    if not isinstance(attestations, dict):
        errors.append("attestations")
    elif review.get("decision") == "approved":
        for key in REQUIRED_ATTESTATIONS:
            if attestations.get(key) is not True:
                errors.append(f"attestation:{key}")
    blocking = review.get("blocking_issues")
    if not isinstance(blocking, list):
        errors.append("blocking_issues")
    elif review.get("decision") == "approved" and blocking:
        errors.append("blocking_issues_not_empty")
    elif review.get("decision") == "rejected" and not blocking:
        errors.append("blocking_issues_required_for_rejection")
    if not isinstance(review.get("notes"), str) or len(review["notes"].strip()) < 3:
        errors.append("notes")
    return errors


@contextlib.contextmanager
def exclusive_lock(project_root: Path, debate_id: str, operation: str) -> Iterator[Path]:
    state = project_root / ".state"
    assert_control_directory(state, project_root, create=True)
    lock_dir = project_root / ".state" / "locks"
    assert_control_directory(lock_dir, project_root, create=True)
    lock = lock_dir / f"corpus-{debate_id}.lock"
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock, flags, 0o600)
    except FileExistsError as exc:
        raise CorpusBuildError(f"Une opération corpus est déjà en cours pour {debate_id} : {lock.relative_to(project_root)}") from exc
    try:
        payload = {"debate_id": debate_id, "operation": operation, "pid": os.getpid(), "created_at": now_iso()}
        os.write(fd, canonical_json(payload) + b"\n")
        os.fsync(fd)
        os.close(fd)
        yield lock
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()
