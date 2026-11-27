"""Explicit experimental preparation of the current Work's quote handoffs.

Use the same pinned resolver and private registry in either mode. This
command performs documentary requests, not model calls or wiki writes.
No selection, editorial attestation, source-lock or publication mutation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import wikidebia_quote_bridge as bridge
import wikidebia_quote_index_collect as pinned
from wikidebia_corpus_build import exclusive_lock, validate_debate_id
from wikidebia_editorial_workspace import validate_work_id

MODES = {"prepared", "integrated"}


def _private_state(state, project, resolver, mode):
    raw = Path(state).absolute()
    state = raw.resolve(strict=True)
    if (raw != state or not state.is_dir() or state.stat().st_mode & 0o077):
        raise bridge.QuoteBridgeError("resolver_state_not_private")
    for root, allowed in ((project, ".state/quote-resolver"), (resolver, ".cache")):
        root = Path(root).resolve()
        if (root.is_relative_to(state)
                or (state.is_relative_to(root) and not state.is_relative_to(root / allowed))):
            raise bridge.QuoteBridgeError("resolver_state_overlaps_repository")
    for name in ("works.sqlite3", "works.sqlite3-wal", "works.sqlite3-shm",
                 "works.sqlite3-journal", "campaign.lock", "http", "translation-handoffs"):
        child = state / name
        if child.is_symlink() or (child.exists() and child.stat().st_mode & 0o077):
            raise bridge.QuoteBridgeError("resolver_state_not_private")
        if child.exists() and (child.is_dir() != (name in {"http", "translation-handoffs"})
                               or not (child.is_dir() or child.is_file())):
            raise bridge.QuoteBridgeError("invalid_resolver_state_entry")
    if mode == "prepared" and not (state / "works.sqlite3").is_file():
        raise bridge.QuoteBridgeError("prepared_registry_missing")
    return state


def _invoke(script, temporary, args, timeout):
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", pinned.BOOTSTRAP, str(script), *args],
            cwd=temporary, env=pinned._env(temporary), timeout=timeout, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise bridge.QuoteBridgeError("resolver_handoff_interrupted") from exc
    if result.returncode or len(result.stdout) > 65536:
        raise bridge.QuoteBridgeError("resolver_handoff_failed")
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError) as exc:
        raise bridge.QuoteBridgeError("invalid_resolver_summary") from exc
    if not isinstance(value, dict):
        raise bridge.QuoteBridgeError("invalid_resolver_summary")
    return value


def _inspect_result(state, request, result, lock_sha, items, owners,
                    audit_limit, retrieval_limit, mode):
    sha = result.get("handoff_sha256")
    if not bridge.is_digest(sha):
        raise bridge.QuoteBridgeError("invalid_resolver_summary")
    path = state / "translation-handoffs" / sha / "handoff.json"
    for part in (path.parent.parent, path.parent, path):
        if (part.is_symlink() or not part.exists() or part.stat().st_mode & 0o077):
            raise bridge.QuoteBridgeError("resolver_handoff_not_private")
    if not path.is_file():
        raise bridge.QuoteBridgeError("resolver_handoff_missing")
    handoff = bridge.load_json(path)
    report = bridge.inspect_handoff(request, handoff, sha, lock_sha, items, owners)
    for key in ("handoff_sha256", "request_sha256", "source_lock_sha256",
                "occurrences", "states", "packets"):
        if result.get(key) != report[key]:
            raise bridge.QuoteBridgeError("resolver_summary_mismatch")
    if result.get("rights") != "unreviewed" or result.get("auto_publish") is not False:
        raise bridge.QuoteBridgeError("resolver_summary_mismatch")
    audit, retrieval = result.get("fresh_audit_requests"), result.get("retrieval_requests")
    if (type(audit) is not int or not 0 <= audit <= audit_limit
            or type(retrieval) is not int or not 0 <= retrieval <= retrieval_limit
            or (mode == "prepared" and retrieval != 0)):
        raise bridge.QuoteBridgeError("resolver_request_budget_mismatch")
    report.update(handoff_path=str(path), fresh_audit_requests=audit, retrieval_requests=retrieval)
    if report["packets"]:
        packet = path.parent / "review.zip"
        if (packet.is_symlink() or not packet.is_file() or packet.stat().st_mode & 0o077):
            raise bridge.QuoteBridgeError("resolver_review_bundle_not_private")
        report["review_bundle_path"] = str(packet)
    return report


def prepare(project, debate, work, *, resolver_root, state, mode, page_ids=(),
            batch_size=200, audit_budget=500, retrieval_budget=300, timeout=600):
    """Export, resolve and inspect all selected batches with shared budgets.

    A prepared-only miss stays an abstention; no automatic integrated retry.
    On partial failure, already produced private handoffs remain available
    but no aggregate completion or publication approval is issued.
    """
    if (mode not in MODES or type(audit_budget) is not int or not 1 <= audit_budget <= 5000
            or type(retrieval_budget) is not int or not 1 <= retrieval_budget <= 5000
            or type(timeout) is not int or not 1 <= timeout <= 1800
            or type(batch_size) is not int or not 1 <= batch_size <= bridge.MAX_ITEMS):
        raise bridge.QuoteBridgeError("invalid_resolver_limits")
    debate, work = validate_debate_id(debate), validate_work_id(work)
    project, resolver_root = Path(project).resolve(), Path(resolver_root).resolve()
    with exclusive_lock(project, debate, "quote_prepare"):
        workspace, lock_sha, items, owners = bridge.snapshot(project, debate, work)
        requests = bridge.requests_for(lock_sha, items, owners, page_ids=page_ids,
                                      batch_size=batch_size)
        state_counts, reports = Counter(), []
        audit_left, retrieval_left = audit_budget, retrieval_budget
        if requests:
            state = _private_state(state, project, resolver_root, mode)
            with tempfile.TemporaryDirectory(prefix="wikidebia-handoff-") as directory:
                temporary = Path(directory)
                script = pinned.materialize(resolver_root, temporary,
                    entrypoint="translation_handoff.py", include_search_data=mode == "integrated")
                for request in requests:
                    if audit_left <= 0 or (mode == "integrated" and retrieval_left <= 0):
                        raise bridge.QuoteBridgeError("resolver_work_budget_exhausted")
                    path = bridge.write_private_request(workspace, request)
                    args = ["--state", str(state), "--audit-budget", str(audit_left),
                            "prepare", "--request", str(path), "--budget", str(max(1, retrieval_left))]
                    if mode == "prepared":
                        args.append("--lookup-only")
                    result = _invoke(script, temporary, args, timeout)
                    row = _inspect_result(state, request, result, lock_sha, items, owners,
                                          audit_left, retrieval_left, mode)
                    audit_left -= row["fresh_audit_requests"]
                    retrieval_left -= row["retrieval_requests"]
                    row["request_path"] = str(path)
                    reports.append(row)
                    state_counts.update(row["states"])
        if bridge.snapshot(project, debate, work) != (workspace, lock_sha, items, owners):
            raise bridge.QuoteBridgeError("resolver_source_changed_during_preparation")
        return {"status": "handoffs_inspected", "mode": mode, "source_lock_sha256": lock_sha,
                "resolver_commit": pinned.RESOLVER_COMMIT, "batches": reports,
                "occurrences": sum(row["occurrences"] for row in reports),
                "states": dict(state_counts), "fresh_audit_requests": audit_budget-audit_left,
                "retrieval_requests": retrieval_budget-retrieval_left,
                "rights": "unreviewed", "editorial_review_required": True,
                "publication_authorized": False, "translation_mutated": False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("debate_id")
    p.add_argument("--work-id", required=True)
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--resolver-root", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--mode", choices=sorted(MODES), required=True)
    p.add_argument("--page-id", action="append", default=[])
    p.add_argument("--batch-size", type=int, default=200)
    p.add_argument("--audit-budget", type=int, default=500)
    p.add_argument("--retrieval-budget", type=int, default=300)
    p.add_argument("--timeout", type=int, default=600, help="Limit per batch in seconds")
    a = p.parse_args(argv)
    try:
        result = prepare(a.project_root, validate_debate_id(a.debate_id),
                         validate_work_id(a.work_id), resolver_root=a.resolver_root,
                         state=a.state, mode=a.mode, page_ids=a.page_id,
                         batch_size=a.batch_size, audit_budget=a.audit_budget,
                         retrieval_budget=a.retrieval_budget, timeout=a.timeout)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, AttributeError, tarfile.TarError) as exc:
        reason = str(exc) if isinstance(exc, bridge.QuoteBridgeError) else type(exc).__name__
        print(json.dumps({"status": "blocked", "reason": reason, "publication_authorized": False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
