#!/usr/bin/env python3
"""Prepare and finalize a formal review of a graph_draft corpus build."""

from __future__ import annotations

from wikidebia_release_info import require_validator_report

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

from wikidebia_corpus_build import (
    FINAL_VALIDATION_JSON,
    FINAL_VALIDATION_TXT,
    KIT_VERSION,
    NORM_VERSION,
    PLACEMENT_REVIEW,
    PROMOTION_READY,
    REQUIRED_ATTESTATIONS,
    REVIEW_ENVELOPE,
    REVIEW_REPORT_JSON,
    REVIEW_REPORT_TXT,
    VALIDATOR_VERSION,
    CorpusBuildError,
    assert_graph_draft_without_final_pages,
    build_payload_sha256,
    compatible_legacy_build_payload_sha256s,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    placement_review_issues,
    prepare_placement_review,
    resolve_build,
    review_sha256,
    sha256_file,
    structural_sha256,
    validate_debate_id,
    verify_review_envelope,
    write_json,
)


def validator_command(project_root: Path, package: Path, json_output: Path, text_output: Path, *, previous_status: str | None = None) -> list[str]:
    python = project_root / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)
    validator_script = project_root / "validator" / "scripts" / "wikidebia_validate.py"
    command = [
        str(python), "-I", str(validator_script), "validate", str(package),
        "--scope", "schema", "--scope", "coherence", "--scope", "graph",
        "--scope", "files", "--scope", "workflow",
        "--format", "text", "--json-output", str(json_output), "--text-output", str(text_output),
    ]
    if previous_status:
        command.extend(["--previous-status", previous_status])
    return command


def run_validator(project_root: Path, package: Path, json_output: Path, text_output: Path, *, previous_status: str | None = None) -> dict[str, Any]:
    validator_src = project_root / "validator" / "src"
    validator_script = project_root / "validator" / "scripts" / "wikidebia_validate.py"
    if not validator_src.is_dir() or not validator_script.is_file():
        raise CorpusBuildError("validateur local incomplet; la revue formelle ne peut pas être finalisée")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    completed = subprocess.run(
        validator_command(project_root, package, json_output, text_output, previous_status=previous_status),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if not json_output.is_file():
        raise CorpusBuildError(f"Le validateur n'a pas produit son rapport : {completed.stderr[-1000:]}")
    report = load_json(json_output, "rapport du validateur")
    if completed.returncode != 0 or report.get("result") == "failed":
        raise CorpusBuildError(
            "Validation structurelle échouée; consulter " + json_output.relative_to(package).as_posix()
        )
    require_validator_report(report, CorpusBuildError)
    return report


def make_review_template(build: Path, debate_id: str, *, overwrite: bool) -> dict[str, Any]:
    manifest, registry, _ = assert_graph_draft_without_final_pages(build)
    envelope_path = build / REVIEW_ENVELOPE
    placement_path = build / PLACEMENT_REVIEW
    if not overwrite and (envelope_path.exists() or placement_path.exists()):
        existing = load_json(envelope_path, "revue globale") if envelope_path.exists() else {}
        if existing.get("schema") == "wikidebia-graph-build-review-1.0":
            raise CorpusBuildError("Une revue préparée existe déjà; utiliser --overwrite-review après modification du graphe")
    source_sha = build_payload_sha256(build)
    timestamp = now_iso()
    placement = prepare_placement_review(registry, debate_id)
    envelope = {
        "schema": "wikidebia-graph-build-review-1.0",
        "schema_version": "1.0",
        "normative_revision": NORM_VERSION,
        "kit_version": KIT_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "debate_id": debate_id,
        "prepared_at": timestamp,
        "source_build_sha256": source_sha,
        "source_global_status": manifest.get("global_status"),
        "decision": "pending",
        "reviewer": "",
        "reviewed_at": None,
        "attestations": {key: False for key in REQUIRED_ATTESTATIONS},
        "blocking_issues": [],
        "notes": "",
        "review_sha256": None,
    }
    write_json(placement_path, placement)
    write_json(envelope_path, envelope)
    return {
        "status": "review_prepared",
        "debate_id": debate_id,
        "source_build_sha256": source_sha,
        "review_path": REVIEW_ENVELOPE,
        "placement_review_path": PLACEMENT_REVIEW,
        "occurrences": len(placement["entries"]),
    }


def next_validation_id(manifest: dict[str, Any]) -> str:
    date = now_iso()[:10].replace("-", "")
    prefix = f"V{date}-"
    numbers = []
    for row in manifest.get("validations") or []:
        value = str(row.get("id") or "")
        if value.startswith(prefix):
            try:
                numbers.append(int(value.split("-")[-1]))
            except ValueError:
                pass
    return f"{prefix}{max(numbers, default=0) + 1:03d}"


def finalize_review(project_root: Path, build: Path, debate_id: str) -> dict[str, Any]:
    manifest, registry, projection = assert_graph_draft_without_final_pages(build)
    source_sha = build_payload_sha256(build)
    envelope_path = build / REVIEW_ENVELOPE
    placement_path = build / PLACEMENT_REVIEW
    review = load_json(envelope_path, "revue globale")
    placement = load_json(placement_path, "revue de placement")

    reviewed_source_sha = str(review.get("source_build_sha256") or "")
    accepted_source_sha = reviewed_source_sha if reviewed_source_sha in compatible_legacy_build_payload_sha256s(build) else source_sha
    envelope_errors = verify_review_envelope(review, debate_id=debate_id, source_sha256=accepted_source_sha)
    placement_errors = placement_review_issues(placement, registry)
    if envelope_errors or (review.get("decision") == "approved" and placement_errors):
        details = {
            "status": "review_invalid",
            "debate_id": debate_id,
            "envelope_errors": envelope_errors,
            "placement_issue_count": len(placement_errors),
            "placement_issues": placement_errors[:100],
        }
        write_json(build / REVIEW_REPORT_JSON, details)
        (build / REVIEW_REPORT_TXT).write_text(
            "REVUE DU BUILD GRAPH_DRAFT : ÉCHOUÉE\n"
            f"Erreurs d'enveloppe : {', '.join(envelope_errors) or 'aucune'}\n"
            f"Anomalies de placement : {len(placement_errors)}\n",
            encoding="utf-8",
            newline="\n",
        )
        raise CorpusBuildError("Revue incomplète ou incohérente; consulter reports/graph_build_review_report.json")

    review["review_sha256"] = review_sha256(review)
    write_json(envelope_path, review)

    if review.get("decision") == "rejected":
        report = {
            "schema": "wikidebia-graph-build-review-report-1.0",
            "status": "rejected",
            "debate_id": debate_id,
            "review_sha256": review["review_sha256"],
            "blocking_issues": review.get("blocking_issues") or [],
            "finalized_at": now_iso(),
        }
        write_json(build / REVIEW_REPORT_JSON, report)
        (build / REVIEW_REPORT_TXT).write_text(
            "REVUE DU BUILD GRAPH_DRAFT : REJETÉE\n"
            f"SHA-256 de la revue : {review['review_sha256']}\n",
            encoding="utf-8",
            newline="\n",
        )
        return report

    # Validate the untouched graph_draft first. This report is the evidence stored
    # in manifest.validations for the graph milestone.
    preflight_json = build / "reports" / "graph_review_preflight.json"
    preflight_txt = build / "reports" / "graph_review_preflight.txt"
    preflight = run_validator(project_root, build, preflight_json, preflight_txt)

    timestamp = now_iso()
    structural_hash = structural_sha256(registry)
    lifecycle = (registry.setdefault("graph", {}).setdefault("lifecycle", {}))
    lifecycle.update({
        "status": "validated",
        "validated_at": timestamp,
        "locked_at": None,
        "locked_by_stage": None,
        "structural_sha256": structural_hash,
    })
    for key in ("lifecycle", "depth_policy", "nodes", "edges", "occurrences", "derived_counts"):
        projection[key] = registry["graph"].get(key)

    manifest["global_status"] = "graph_validated"
    manifest["updated_at"] = timestamp
    manifest.setdefault("validations", []).append({
        "id": next_validation_id(manifest),
        "scope": "graph",
        "language": None,
        "validator_version": VALIDATOR_VERSION,
        "executed_at": timestamp,
        "input_sha256": source_sha,
        "result": preflight.get("result"),
        "blocking_errors": int((preflight.get("summary") or {}).get("errors") or 0),
        "warnings": int((preflight.get("summary") or {}).get("warnings") or 0),
        "report_path": "reports/graph_review_preflight.json",
    })

    originals = {
        build / "manifest.json": (build / "manifest.json").read_bytes(),
        build / "data" / "registre_debat.json": (build / "data" / "registre_debat.json").read_bytes(),
        build / "graph" / "graphe_argumentatif.json": (build / "graph" / "graphe_argumentatif.json").read_bytes(),
    }
    try:
        write_json(build / "manifest.json", manifest)
        write_json(build / "data" / "registre_debat.json", registry)
        write_json(build / "graph" / "graphe_argumentatif.json", projection)
        final_report = run_validator(
            project_root,
            build,
            build / FINAL_VALIDATION_JSON,
            build / FINAL_VALIDATION_TXT,
            previous_status="graph_draft",
        )
    except Exception:
        for path, payload in originals.items():
            path.write_bytes(payload)
        raise

    ready = {
        "schema": "wikidebia-corpus-promotion-ready-1.0",
        "debate_id": debate_id,
        "global_status": "graph_validated",
        "review_sha256": review["review_sha256"],
        "source_build_sha256": source_sha,
        "approved_build_sha256": build_payload_sha256(build),
        "structural_sha256": structural_hash,
        "validator_version": VALIDATOR_VERSION,
        "preflight_report_path": "reports/graph_review_preflight.json",
        "preflight_report_sha256": sha256_file(preflight_json),
        "validation_report_path": FINAL_VALIDATION_JSON,
        "validation_report_sha256": sha256_file(build / FINAL_VALIDATION_JSON),
        "prepared_at": now_iso(),
        "no_final_pages": True,
    }
    write_json(build / PROMOTION_READY, ready)
    report = {
        "schema": "wikidebia-graph-build-review-report-1.0",
        "status": "approved",
        "debate_id": debate_id,
        "review_sha256": review["review_sha256"],
        "source_build_sha256": source_sha,
        "approved_build_sha256": build_payload_sha256(build),
        "structural_sha256": structural_hash,
        "validator_result": final_report.get("result"),
        "validator_warnings": int((final_report.get("summary") or {}).get("warnings") or 0),
        "promotion_ready_path": PROMOTION_READY,
        "finalized_at": now_iso(),
    }
    write_json(build / REVIEW_REPORT_JSON, report)
    (build / REVIEW_REPORT_TXT).write_text(
        "REVUE DU BUILD GRAPH_DRAFT : APPROUVÉE\n"
        f"Débat : {debate_id}\n"
        f"SHA-256 de la revue : {review['review_sha256']}\n"
        f"SHA-256 structurel : {structural_hash}\n"
        "État obtenu : graph_validated\n"
        "Pages finales générées : non\n",
        encoding="utf-8",
        newline="\n",
    )
    report["validated_tree_sha256"] = full_tree_sha256(build)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Préparer ou finaliser la revue formelle d'un build graph_draft.")
    parser.add_argument("debate_id")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="Créer les deux registres de revue à compléter")
    action.add_argument("--finalize", action="store_true", help="Valider et sceller la revue complétée")
    parser.add_argument("--overwrite-review", action="store_true", help="Régénérer les registres de revue préparatoires")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    debate_id = validate_debate_id(args.debate_id)
    with exclusive_lock(project_root, debate_id, "graph_review"):
        build = resolve_build(project_root, debate_id)
        if args.prepare:
            result = make_review_template(build, debate_id, overwrite=args.overwrite_review)
        else:
            result = finalize_review(project_root, build, debate_id)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CorpusBuildError as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=sys.stderr)
        raise SystemExit(2)
