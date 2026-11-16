#!/usr/bin/env python3
"""Start a fresh read-only comparison from a signed interrupted-execution audit.

Never replays the interrupted plan, approves a new plan, or writes MediaWiki.
The new plan must pass the ordinary independent review and acceptance gates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from wikidebia_corpus_build import exclusive_lock, load_json, sha256_file, validate_debate_id
from wikidebia_editorial_workspace import validate_work_id
from wikidebia_remote_compare import _validate_comparison_id, compare_workspace
from wikidebia_remote_plan_review import prepare_review
from wikidebia_remote_execute import AUTHORIZATION_SCHEMA, RemoteExecutionError, _canonical, _execution_dir


def prepare_fresh_recovery_comparison(
    project_root: Path, debate_id: str, work_id: str, interrupted_comparison_id: str,
    *, scope: str | None = None, comparison_id: str | None = None, adapter=None,
    validate_plan_fn=None, prepare_review_fn=None, prepare_draft_review: bool = False,
) -> dict:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    interrupted_comparison_id = _validate_comparison_id(interrupted_comparison_id)
    if comparison_id is not None:
        comparison_id = _validate_comparison_id(comparison_id)
        if comparison_id == interrupted_comparison_id:
            raise RemoteExecutionError("La comparaison de récupération doit utiliser un nouvel identifiant")
    root = _execution_dir(project_root, debate_id, work_id, interrupted_comparison_id)
    if not root.is_dir() or root.is_symlink():
        raise RemoteExecutionError("Dossier de l’exécution interrompue absent")
    audit_path = root / "interrupted-audit.json"
    if not audit_path.is_file() or audit_path.is_symlink():
        raise RemoteExecutionError("Audit signé préalable obligatoire")
    if (root / "execution-receipt.json").exists():
        raise RemoteExecutionError("Un reçu final existe : utiliser la réconciliation signée")
    audit = load_json(audit_path, "audit d’exécution interrompue")
    if audit.get("audit_sha256") != _canonical(audit, "audit_sha256"):
        raise RemoteExecutionError("Empreinte de l’audit invalide")
    for key, expected in {
        "debate_id": debate_id, "work_id": work_id,
        "comparison_id": interrupted_comparison_id,
        "status": "requires_manual_reconciliation",
        "remote_write_performed": False,
        "remote_write_authorized": False,
        "automatic_replay_allowed": False,
        "attribution_verified": False,
    }.items():
        if audit.get(key) != expected:
            raise RemoteExecutionError(f"Audit incompatible : {key}")
    events_rel = audit.get("events_path")
    if not isinstance(events_rel, str) or not events_rel.startswith(".state/remote-executions/"):
        raise RemoteExecutionError("Chemin du journal d’audit non sûr")
    events = (project_root / events_rel).resolve()
    if events != (root / "interrupted-audit-events.jsonl").resolve() or not events.is_file() or events.is_symlink():
        raise RemoteExecutionError("Journal d’audit absent ou divergent")
    if sha256_file(events) != audit.get("events_file_sha256"):
        raise RemoteExecutionError("Empreinte du journal d’audit invalide")
    authorization_path = root / "execution-authorization.json"
    if not authorization_path.is_file() or authorization_path.is_symlink():
        raise RemoteExecutionError("Autorisation initiale absente")
    authorization = load_json(authorization_path, "autorisation initiale")
    if authorization.get("schema") != AUTHORIZATION_SCHEMA or authorization.get("authorization_sha256") != _canonical(authorization, "authorization_sha256"):
        raise RemoteExecutionError("Autorisation initiale altérée")
    for key in ("authorization_sha256", "plan_sha256", "preflight_sha256"):
        expected = authorization.get(key)
        if audit.get(key) != expected:
            raise RemoteExecutionError(f"Audit et autorisation divergents : {key}")
    source_receipt_path = project_root / ".state/remote-comparisons" / debate_id / work_id / interrupted_comparison_id / "comparison-receipt.json"
    if not source_receipt_path.is_file() or source_receipt_path.is_symlink():
        raise RemoteExecutionError("Reçu de comparaison d’origine absent")
    source = load_json(source_receipt_path, "reçu de comparaison d’origine")
    if source.get("receipt_sha256") != _canonical(source, "receipt_sha256"):
        raise RemoteExecutionError("Reçu de comparaison d’origine altéré")
    if source.get("debate_id") != debate_id or source.get("work_id") != work_id or source.get("comparison_id") != interrupted_comparison_id or source.get("plan_sha256") != audit.get("plan_sha256"):
        raise RemoteExecutionError("Identité de comparaison d’origine divergente")
    original_scope = source.get("scope")
    if original_scope not in ("all", "fr", "en"):
        raise RemoteExecutionError("Portée de la comparaison initiale invalide")
    if scope is None:
        scope = original_scope
    elif scope != original_scope:
        raise RemoteExecutionError("La récupération doit conserver la portée de la comparaison initiale")
    release_sha = source.get("release_copy_tree_sha256")
    if not isinstance(release_sha, str) or len(release_sha) != 64:
        raise RemoteExecutionError("Empreinte release-copy d’origine absente")
    kwargs = {"scope": scope, "comparison_id": comparison_id, "adapter": adapter}
    if validate_plan_fn is not None:
        kwargs["validate_plan_fn"] = validate_plan_fn
    result = compare_workspace(project_root, debate_id, work_id, release_sha, **kwargs)
    # Never mask an unexpected write report from the read-only comparison.
    # Fail closed before creating any draft review or reporting success.
    if result.get("remote_write_performed") is not False:
        raise RemoteExecutionError("La comparaison de récupération n'atteste pas l'absence d'écriture distante")
    if result.get("execution_authorized") is True:
        raise RemoteExecutionError("La comparaison de récupération ne peut pas autoriser l'exécution")
    draft_review = None
    if prepare_draft_review and result.get("status") == "plan_ready":
        new_comparison_id = result.get("comparison_id")
        if not isinstance(new_comparison_id, str) or new_comparison_id == interrupted_comparison_id:
            raise RemoteExecutionError("Identifiant de la nouvelle comparaison invalide")
        review_preparer = prepare_review_fn if prepare_review_fn is not None else prepare_review
        draft_review = review_preparer(project_root, debate_id, work_id, new_comparison_id)
        if draft_review.get("status") != "review_ready":
            raise RemoteExecutionError("Préparation de la revue non aboutie")
    return {
        **result,
        "recovery_source_comparison_id": interrupted_comparison_id,
        "recovery_source_audit_sha256": audit["audit_sha256"],
        "original_execution_replayed": False,
        "new_plan_automatically_approved": False,
        "draft_review": draft_review,
        "remote_write_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Nouvelle comparaison distante sans écriture après interruption")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--interrupted-comparison-id", required=True)
    parser.add_argument("--comparison-id")
    parser.add_argument("--prepare-draft-review", action="store_true",
                        help="Préparer une revue vierge, sans approbation ni écriture")
    parser.add_argument("--scope", choices=("all", "fr", "en"), default=None,
                        help="Par défaut, réutilise la portée signée de la comparaison interrompue")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    with exclusive_lock(args.project_root.resolve(), args.debate_id, "remote-compare"):
        result = prepare_fresh_recovery_comparison(
            args.project_root, args.debate_id, args.work_id,
            args.interrupted_comparison_id, scope=args.scope, comparison_id=args.comparison_id,
            prepare_draft_review=args.prepare_draft_review,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "plan_ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
