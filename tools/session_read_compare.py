#!/usr/bin/env python3
"""Compare two explicitly observed multi-session read trials, without claims of savings.

The program never launches Codex, runs translation, accesses a wiki, or infers
billable tokens. Trial metadata and review results are owner-supplied attestations,
not measurements of semantic quality or experimental randomization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from session_read_audit import ReadAuditError, audit_jsonl

TRIAL_SCHEMA = "wikidebia-session-read-trial-1.0"
REPORT_SCHEMA = "wikidebia-session-read-comparison-1.0"
TASK_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
MANIFEST_BYTES_LIMIT = 4_096
COVERAGE = "instrumented_complete_file_reads_only"
METADATA_FIELDS = {
    "schema", "condition", "task_id", "base_commit", "protocol_sha256",
    "events_sha256", "task_completed", "quality_review", "coverage",
}


class ComparisonError(ValueError):
    """The experimental evidence is invalid or incommensurable."""


def _load_manifest(path: Path, expected_condition: str, events: Path) -> dict[str, Any]:
    if (
        path.is_symlink() or not path.is_file() or
        path.stat().st_size > MANIFEST_BYTES_LIMIT
    ):
        raise ComparisonError("invalid_or_oversized_trial_manifest")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ComparisonError("unreadable_trial_manifest") from exc
    if not isinstance(raw, dict) or set(raw) != METADATA_FIELDS:
        raise ComparisonError("invalid_trial_manifest_fields")
    if raw["schema"] != TRIAL_SCHEMA or raw["condition"] != expected_condition:
        raise ComparisonError("invalid_trial_manifest_schema_or_condition")
    if not isinstance(raw["task_id"], str) or not TASK_RE.fullmatch(raw["task_id"]):
        raise ComparisonError("invalid_task_id")
    if not isinstance(raw["base_commit"], str) or not COMMIT_RE.fullmatch(raw["base_commit"]):
        raise ComparisonError("invalid_base_commit")
    for name in ("protocol_sha256", "events_sha256"):
        if not isinstance(raw[name], str) or not SHA256_RE.fullmatch(raw[name]):
            raise ComparisonError("invalid_trial_digest")
    if type(raw["task_completed"]) is not bool:
        raise ComparisonError("invalid_task_completion_flag")
    if raw["quality_review"] not in {"passed", "failed", "not_reviewed"}:
        raise ComparisonError("invalid_quality_review")
    if raw["coverage"] != COVERAGE:
        raise ComparisonError("invalid_observation_scope")
    # This input is local, not attested by GitHub: bind the manifest to the
    # exact JSONL bytes being evaluated, rather than an arbitrary filename.
    if events.is_symlink() or not events.is_file():
        raise ComparisonError("invalid_trial_events")
    if hashlib.sha256(events.read_bytes()).hexdigest() != raw["events_sha256"]:
        raise ComparisonError("trial_events_digest_mismatch")
    return raw


def compare_trials(
    control_events: Path,
    control_manifest: Path,
    handoff_events: Path,
    handoff_manifest: Path,
) -> dict[str, Any]:
    """Compare descriptive read counts for two matching owner-attested trials."""
    control = _load_manifest(control_manifest, "control", control_events)
    handoff = _load_manifest(handoff_manifest, "handoff", handoff_events)
    if control_events.resolve() == handoff_events.resolve():
        raise ComparisonError("trial_logs_must_be_distinct")
    if (
        control["task_id"] != handoff["task_id"]
        or control["base_commit"] != handoff["base_commit"]
        or control["protocol_sha256"] != handoff["protocol_sha256"]
    ):
        raise ComparisonError("task_commit_or_protocol_mismatch")
    try:
        control_report = audit_jsonl(control_events)
        handoff_report = audit_jsonl(handoff_events)
    except ReadAuditError as exc:
        raise ComparisonError("invalid_trial_events") from exc

    keys = (
        "session_count", "event_count", "first_or_changed_reads",
        "changed_content_reads", "repeated_reads_within_session",
        "repeated_reads_across_sessions",
    )
    control_metrics = {key: control_report[key] for key in keys}
    handoff_metrics = {key: handoff_report[key] for key in keys}
    reasons = []
    if control_metrics["session_count"] < 2 or handoff_metrics["session_count"] < 2:
        reasons.append("at_least_two_sessions_per_condition_required")
    if control_metrics["session_count"] != handoff_metrics["session_count"]:
        reasons.append("session_count_mismatch")
    if not control["task_completed"] or not handoff["task_completed"]:
        reasons.append("task_not_completed_in_both_conditions")
    if control["quality_review"] != "passed" or handoff["quality_review"] != "passed":
        reasons.append("quality_review_not_passed_in_both_conditions")
    comparable = not reasons
    difference = None
    if comparable:
        difference = {
            key + "_handoff_minus_control": handoff_metrics[key] - control_metrics[key]
            for key in keys if key != "session_count"
        }
    return {
        "schema": REPORT_SCHEMA,
        "source": COVERAGE,
        "matched_task_base_commit_and_protocol_attested": True,
        "experiment_metadata_and_quality_reviews_self_reported": True,
        "experimental_equivalence_automatically_verified": False,
        "quality_automatically_verified": False,
        "comparison_eligible_for_descriptive_counts": comparable,
        "ineligibility_reasons": reasons,
        "control": control_metrics,
        "handoff": handoff_metrics,
        "descriptive_difference_not_causal_savings": difference,
        "causal_savings_established": False,
        "actual_billed_tokens": None,
        "actual_codex_cloud_credits": None,
        "saved_time_seconds": None,
        "file_paths_included": False,
        "session_ids_included": False,
        "raw_content_included": False,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-events", type=Path, required=True)
    parser.add_argument("--control-manifest", type=Path, required=True)
    parser.add_argument("--handoff-events", type=Path, required=True)
    parser.add_argument("--handoff-manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = compare_trials(
            args.control_events, args.control_manifest,
            args.handoff_events, args.handoff_manifest,
        )
    except (ComparisonError, OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
