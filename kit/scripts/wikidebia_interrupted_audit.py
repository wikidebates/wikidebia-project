#!/usr/bin/env python3
"""Read-only evidence audit for an interrupted remote execution.

Never authorizes writes, reconstructs an execution receipt, or marks a work
published. A matching remote content hash alone does not prove who wrote it.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from wikidebia_corpus_build import exclusive_lock, load_json, now_iso, relative_to_project, write_json
from wikidebia_editorial_workspace import validate_work_id
from wikidebia_remote_compare import _validate_comparison_id
from wikidebia_remote_execute import (
    AUTHORIZATION_SCHEMA, ArmedRecordingAdapter, RemoteExecutionError,
    _canonical, _execution_dir, _load_approved_handoff, _load_preflight,
    _run_preflight, _selected_rows, _write_events,
)
from wikidebia_update import build_adapter
from wikidebia_corpus_build import validate_debate_id, sha256_file

AUDIT_SCHEMA = "wikidebia-interrupted-execution-readonly-audit-1.0"


def audit_interrupted_execution(
    project_root: Path, debate_id: str, work_id: str, comparison_id: str,
    confirm_preflight_sha256: str, *, adapter: Any | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    debate_id = validate_debate_id(debate_id)
    work_id = validate_work_id(work_id)
    comparison_id = _validate_comparison_id(comparison_id)
    handoff = _load_approved_handoff(project_root, debate_id, work_id, comparison_id)
    root, preflight, _ = _load_preflight(project_root, handoff, comparison_id, confirm_preflight_sha256)
    if (root / "execution-receipt.json").exists():
        raise RemoteExecutionError("Un reçu final existe déjà : utiliser la réconciliation signée existante")
    authorization_path = root / "execution-authorization.json"
    if not authorization_path.is_file() or authorization_path.is_symlink():
        raise RemoteExecutionError("Autorisation initiale absente : aucune exécution interrompue attestée")
    authorization = load_json(authorization_path, "autorisation d’exécution interrompue")
    if authorization.get("schema") != AUTHORIZATION_SCHEMA or authorization.get("authorization_sha256") != _canonical(authorization, "authorization_sha256"):
        raise RemoteExecutionError("Autorisation initiale altérée")
    for key, value in {
        "debate_id": debate_id, "work_id": work_id, "comparison_id": comparison_id,
        "plan_sha256": handoff["plan"]["plan_sha256"],
        "acceptance_sha256": handoff["acceptance"]["acceptance_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
        "mode": preflight["mode"],
        "execution_started": True, "remote_write_authorized": True,
    }.items():
        if authorization.get(key) != value:
            raise RemoteExecutionError(f"Autorisation initiale divergente : {key}")
    if (root / "interrupted-audit.json").exists() or (root / "interrupted-audit-events.jsonl").exists():
        raise RemoteExecutionError("Audit précédent existant : aucune preuve écrasée")
    recorder = ArmedRecordingAdapter(adapter if adapter is not None else build_adapter(handoff["config"], project_root))
    observed = _run_preflight(handoff, recorder, str(preflight["mode"]))
    if recorder.write_attempts:
        raise RemoteExecutionError("Audit en lecture seule : tentative d’écriture")
    selected = _selected_rows(handoff["plan"], str(preflight["mode"]))
    results = [row for row in observed["checks"] if row["operation"] != "skip"]
    completed = sum(row["status"] in {"already_done", "already_absent"} for row in results)
    # No replay can be inferred from this report. A matching remote state
    # may predate the interrupted run or have been written by a third party.
    audit = {
        "schema": AUDIT_SCHEMA, "debate_id": debate_id, "work_id": work_id,
        "comparison_id": comparison_id, "created_at": now_iso(),
        "authorization_sha256": authorization["authorization_sha256"],
        "preflight_sha256": preflight["preflight_sha256"],
        "plan_sha256": handoff["plan"]["plan_sha256"],
        "mode": preflight["mode"], "selected_operation_count": len(selected),
        "observed_matching_or_absent_count": completed,
        "checks": observed["checks"], "blockers": observed["blockers"],
        "status": "requires_manual_reconciliation",
        "remote_access_performed": True, "remote_write_authorized": False,
        "remote_write_performed": False, "write_attempts": recorder.write_attempts,
        "execution_receipt_reconstructed": False,
    }
    events_path = root / "interrupted-audit-events.jsonl"
    _write_events(events_path, recorder.events)
    audit["events_path"] = relative_to_project(events_path, project_root)
    audit["events_file_sha256"] = sha256_file(events_path)
    audit["audit_sha256"] = _canonical(audit, "audit_sha256")
    write_json(root / "interrupted-audit.json", audit)
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit distant en lecture seule d’une exécution interrompue")
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--confirm-preflight-sha256", required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    with exclusive_lock(args.project_root.resolve(), args.debate_id, "remote-execution"):
        result = audit_interrupted_execution(
            args.project_root, args.debate_id, args.work_id, args.comparison_id,
            args.confirm_preflight_sha256,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RemoteExecutionError as exc:
        raise SystemExit(f"AUDIT BLOQUÉ : {exc}")
