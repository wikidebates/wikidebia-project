#!/usr/bin/env python3
"""Atomically promote an approved graph build into corpus/<debate_id>."""

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
    PROMOTION_READY,
    REVIEW_ENVELOPE,
    VALIDATOR_VERSION,
    CorpusBuildError,
    assert_graph_validated_without_final_pages,
    assert_control_directory,
    build_payload_sha256,
    exclusive_lock,
    full_tree_sha256,
    load_json,
    now_iso,
    relative_to_project,
    resolve_build,
    review_sha256,
    sha256_bytes,
    sha256_file,
    validate_debate_id,
    write_json,
)


def run_validator(project_root: Path, package: Path, json_output: Path, text_output: Path) -> dict[str, Any]:
    validator_src = project_root / "validator" / "src"
    validator_script = project_root / "validator" / "scripts" / "wikidebia_validate.py"
    if not validator_src.is_dir() or not validator_script.is_file():
        raise CorpusBuildError("validateur local incomplet; promotion interdite")
    python = project_root / ".venv" / "bin" / "python"
    if not python.is_file():
        python = Path(sys.executable)
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env.pop("PYTHONHOME", None)
    command = [
        str(python), "-I", str(validator_script), "validate", str(package),
        "--scope", "schema", "--scope", "coherence", "--scope", "graph",
        "--scope", "files", "--scope", "workflow", "--format", "text",
        "--json-output", str(json_output), "--text-output", str(text_output),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, env=env, check=False)
    if not json_output.is_file():
        raise CorpusBuildError(f"Rapport de validation absent : {completed.stderr[-1000:]}")
    report = load_json(json_output, "rapport de validation de promotion")
    if completed.returncode != 0 or report.get("result") == "failed":
        raise CorpusBuildError("Validation finale de promotion échouée")
    require_validator_report(report, CorpusBuildError)
    return report


def fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def receipt_hash(receipt: dict[str, Any]) -> str:
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256_bytes(payload)


def promote(project_root: Path, debate_id: str, confirm_review_sha256: str) -> dict[str, Any]:
    build = resolve_build(project_root, debate_id)
    assert_graph_validated_without_final_pages(build)

    review = load_json(build / REVIEW_ENVELOPE, "revue globale")
    actual_review_sha = review_sha256(review)
    if review.get("decision") != "approved" or review.get("review_sha256") != actual_review_sha:
        raise CorpusBuildError("La revue approuvée est absente, altérée ou non scellée")
    if confirm_review_sha256 != actual_review_sha:
        raise CorpusBuildError("L'empreinte confirmée ne correspond pas à la revue approuvée")
    if "preserved_placements_sha256" in review:
        from wikidebia_translation_source import verify_preserved_placement_review

        registry = load_json(build / "data/registre_debat.json", "registre du débat")
        verify_preserved_placement_review(build, registry)

    ready = load_json(build / PROMOTION_READY, "attestation de promotion")
    if ready.get("debate_id") != debate_id or ready.get("review_sha256") != actual_review_sha:
        raise CorpusBuildError("L'attestation de promotion n'est pas liée à cette revue")
    if ready.get("no_final_pages") is not True:
        raise CorpusBuildError("L'attestation n'exclut pas explicitement la génération de pages finales")
    current_payload_sha = build_payload_sha256(build)
    if ready.get("approved_build_sha256") != current_payload_sha:
        raise CorpusBuildError("Le build a changé depuis l'approbation; refaire la revue")
    if ready.get("validation_report_path") != FINAL_VALIDATION_JSON:
        raise CorpusBuildError("Chemin de rapport de validation inattendu dans l'attestation")
    validation_path = build / FINAL_VALIDATION_JSON
    if not validation_path.is_file() or sha256_file(validation_path) != ready.get("validation_report_sha256"):
        raise CorpusBuildError("Le rapport de validation scellé est absent ou altéré")
    if ready.get("preflight_report_path") != "reports/graph_review_preflight.json":
        raise CorpusBuildError("Chemin de rapport de prévalidation inattendu")
    preflight_path = build / "reports" / "graph_review_preflight.json"
    if not preflight_path.is_file() or sha256_file(preflight_path) != ready.get("preflight_report_sha256"):
        raise CorpusBuildError("Le rapport de prévalidation est absent ou altéré")
    lifecycle_hash = (((load_json(build / "data" / "registre_debat.json").get("graph") or {}).get("lifecycle") or {}).get("structural_sha256"))
    if ready.get("structural_sha256") != lifecycle_hash:
        raise CorpusBuildError("L'empreinte structurelle de l'attestation diverge du registre")

    # A fresh read-only validation closes the gap between approval and promotion.
    promotion_validation_json = build / "reports" / "corpus_promotion_validation.json"
    promotion_validation_txt = build / "reports" / "corpus_promotion_validation.txt"
    validation = run_validator(project_root, build, promotion_validation_json, promotion_validation_txt)

    target_parent = project_root / "corpus"
    if target_parent.is_symlink():
        raise CorpusBuildError("Le dossier corpus/ ne peut pas être un lien symbolique")
    target_parent = assert_control_directory(target_parent, project_root, create=True)
    target = target_parent / debate_id
    if target.exists() or target.is_symlink():
        raise CorpusBuildError(f"Le corpus actif existe déjà : corpus/{debate_id}; aucun remplacement silencieux n'est autorisé")
    if build.stat().st_dev != target_parent.stat().st_dev:
        raise CorpusBuildError("Promotion atomique impossible entre systèmes de fichiers différents")

    before_tree_sha = full_tree_sha256(build)
    promotions_root = project_root / ".state" / "corpus-promotions"
    if promotions_root.is_symlink():
        raise CorpusBuildError("Le dossier .state/corpus-promotions ne peut pas être un lien symbolique")
    assert_control_directory(promotions_root, project_root, create=True)
    transaction_dir = promotions_root / debate_id
    assert_control_directory(transaction_dir, project_root, create=True)
    transaction_id = now_iso().replace(":", "").replace("+00:00", "Z")
    pending = transaction_dir / f"{transaction_id}.pending.json"
    final = transaction_dir / f"{transaction_id}.receipt.json"
    pending_payload = {
        "schema": "wikidebia-corpus-promotion-transaction-1.0",
        "status": "pending",
        "debate_id": debate_id,
        "source": relative_to_project(build, project_root),
        "destination": relative_to_project(target, project_root),
        "review_sha256": actual_review_sha,
        "approved_build_sha256": current_payload_sha,
        "tree_sha256_before": before_tree_sha,
        "created_at": now_iso(),
    }
    write_json(pending, pending_payload)
    fsync_directory(pending.parent)

    try:
        os.replace(build, target)
        fsync_directory(build.parent)
        fsync_directory(target.parent)
    except OSError as exc:
        raise CorpusBuildError(f"Échec de la promotion atomique : {exc}") from exc

    after_tree_sha = full_tree_sha256(target)
    if after_tree_sha != before_tree_sha:
        # A rename on one filesystem must preserve bytes. Do not pretend success.
        raise CorpusBuildError("Empreinte divergente après promotion atomique; transaction à examiner")

    receipt = {
        "schema": "wikidebia-corpus-promotion-receipt-1.0",
        "status": "promoted",
        "debate_id": debate_id,
        "source": f".state/corpus-builds/{debate_id}",
        "destination": f"corpus/{debate_id}",
        "review_sha256": actual_review_sha,
        "approved_build_sha256": current_payload_sha,
        "structural_sha256": ready.get("structural_sha256"),
        "tree_sha256_before": before_tree_sha,
        "tree_sha256_after": after_tree_sha,
        "validation_result": validation.get("result"),
        "validation_report_sha256": sha256_file(target / "reports" / "corpus_promotion_validation.json"),
        "atomic_rename": True,
        "final_pages_generated": False,
        "promoted_at": now_iso(),
    }
    receipt["receipt_sha256"] = receipt_hash(receipt)
    write_json(final, receipt)
    pending.unlink(missing_ok=True)
    fsync_directory(final.parent)
    return {
        "status": "promoted",
        "debate_id": debate_id,
        "destination": f"corpus/{debate_id}",
        "review_sha256": actual_review_sha,
        "tree_sha256": after_tree_sha,
        "receipt": relative_to_project(final, project_root),
        "final_pages_generated": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Promouvoir atomiquement un build graph_validated vers corpus/.")
    parser.add_argument("debate_id")
    parser.add_argument("--confirm-review-sha256", required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--machine-readable", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_root = args.project_root.expanduser().resolve()
    debate_id = validate_debate_id(args.debate_id)
    if not __import__("re").fullmatch(r"[0-9a-f]{64}", args.confirm_review_sha256):
        raise CorpusBuildError("--confirm-review-sha256 doit être une empreinte SHA-256 hexadécimale")
    with exclusive_lock(project_root, debate_id, "corpus_promotion"):
        result = promote(project_root, debate_id, args.confirm_review_sha256)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CorpusBuildError as exc:
        print(f"WIKIDEBIA BLOQUÉ : {exc}", file=sys.stderr)
        raise SystemExit(2)
