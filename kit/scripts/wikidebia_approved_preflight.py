#!/usr/bin/env python3
"""Prepare a read-only preflight from an already signed, accepted plan.

This command only removes the need to manually copy the acceptance SHA.
It never approves a plan, authorizes remote writes, or executes a mutation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from wikidebia_remote_execute import (
    MODES, RemoteExecutionError, _load_approved_handoff, prepare_execution,
)


def prepare_approved_preflight(
    project_root: Path, debate_id: str, work_id: str, comparison_id: str,
    *, mode: str = "all", adapter: Any | None = None,
) -> dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    # The handoff verifies accepted/approved status, signed evidence,
    # unchanged release copy, and non-authorization of remote writes.
    handoff = _load_approved_handoff(project_root, debate_id, work_id, comparison_id)
    confirmation = handoff["acceptance"]["acceptance_sha256"]
    result = prepare_execution(
        project_root, debate_id, work_id, comparison_id,
        confirmation, mode=mode, adapter=adapter,
    )
    if result.get("remote_write_performed") is not False:
        raise RemoteExecutionError("Le préflight ne confirme pas l'absence d'écriture")
    return {
        **result,
        "accepted_plan_verified": True,
        "execution_authorized": False,
        "execution_started_by_command": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Préparer un préflight sans écriture depuis un plan déjà accepté",
    )
    parser.add_argument("debate_id")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--comparison-id", required=True)
    parser.add_argument("--mode", choices=MODES, default="all")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = prepare_approved_preflight(
        args.project_root, args.debate_id, args.work_id, args.comparison_id,
        mode=args.mode,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "ready" else 3


if __name__ == "__main__":
    raise SystemExit(main())
