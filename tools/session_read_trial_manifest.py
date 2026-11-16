#!/usr/bin/env python3
"""Finalize a private, opt-in read-trial manifest from observed events.

Reads only the local Git HEAD, a tracked protocol and an existing private
JSONL event log. Does not run models, alter a Work, or touch remote APIs.
The review and task-completion flags are supplied by the operator, not verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

from session_read_audit import (
    MAX_LOG_BYTES, ReadAuditError, _safe_path, audit_read_events,
)
from session_read_capture import _read_public_bytes, _tracked_regular_file
from session_read_compare import COVERAGE, TASK_RE, TRIAL_SCHEMA

NAME_RE = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z")
CONDITIONS = ("control", "handoff")
REVIEWS = ("passed", "failed", "not_reviewed")


class TrialManifestError(ValueError):
    """Cannot safely finalize this trial's evidence."""


def _name(value: str, suffix: str) -> str:
    if (
        not isinstance(value, str)
        or not NAME_RE.fullmatch(value)
        or value.startswith(".")
        or not value.endswith(suffix)
    ):
        raise TrialManifestError("invalid_private_filename")
    return value


def _private_state(root: Path) -> Path:
    path = root / ".state"
    if path.is_symlink() or not path.is_dir():
        raise TrialManifestError("private_state_directory_missing_or_unsafe")
    return path


def _read_private_events(path: Path) -> tuple[bytes, dict]:
    if path.is_symlink():
        raise TrialManifestError("unsafe_event_log")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise TrialManifestError("event_log_not_readable") from exc
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o077):
            raise TrialManifestError("unsafe_event_log_permissions")
        if info.st_size > MAX_LOG_BYTES:
            raise TrialManifestError("event_log_too_large")
        raw = stream.read(MAX_LOG_BYTES + 1)
    if len(raw) > MAX_LOG_BYTES or not raw.endswith(b"\n"):
        raise TrialManifestError("event_log_too_large_or_unterminated")
    try:
        events = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        report = audit_read_events(events)
    except (UnicodeError, ValueError, TypeError, ReadAuditError) as exc:
        raise TrialManifestError("invalid_observed_events") from exc
    if report["session_count"] < 2:
        raise TrialManifestError("at_least_two_sessions_required")
    return raw, report


def _git_head(root: Path, protocol: str) -> str:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True, check=True, text=True,
        ).stdout.strip()
        # Protocol must match the actual HEAD, not an edited working copy.
        check = subprocess.run(
            ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--", protocol],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise TrialManifestError("git_head_unavailable") from exc
    if not re.fullmatch(r"[0-9a-f]{40}", head) or check.returncode != 0:
        raise TrialManifestError("missing_commit_or_modified_protocol")
    return head


def finalize_trial(
    project_root: Path,
    *,
    condition: str,
    task_id: str,
    protocol_path: str,
    events_name: str = "session-reads.jsonl",
    output_name: str | None = None,
    task_completed: bool = False,
    quality_review: str = "not_reviewed",
) -> dict:
    root = project_root.expanduser().resolve()
    if condition not in CONDITIONS:
        raise TrialManifestError("invalid_trial_condition")
    if not isinstance(task_id, str) or not TASK_RE.fullmatch(task_id):
        raise TrialManifestError("invalid_task_id")
    if quality_review not in REVIEWS:
        raise TrialManifestError("invalid_quality_review")
    if type(task_completed) is not bool:
        raise TrialManifestError("task_completed_must_be_boolean")
    try:
        protocol_path = _safe_path(protocol_path)
        _tracked_regular_file(root, protocol_path)
        protocol_bytes = _read_public_bytes(root, protocol_path)
    except (ReadAuditError, OSError) as exc:
        raise TrialManifestError("invalid_tracked_protocol") from exc
    head = _git_head(root, protocol_path)

    state = _private_state(root)
    event_filename = _name(events_name, ".jsonl")
    output_filename = _name(output_name or condition + "-trial.json", ".json")
    event_path = state / event_filename
    output_path = state / output_filename
    if event_path == output_path or output_path.is_symlink() or output_path.exists():
        raise TrialManifestError("trial_manifest_already_exists_or_unsafe")
    observed, report = _read_private_events(event_path)

    manifest = {
        "schema": TRIAL_SCHEMA,
        "condition": condition,
        "task_id": task_id,
        "base_commit": head,
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "events_sha256": hashlib.sha256(observed).hexdigest(),
        "task_completed": task_completed,
        "quality_review": quality_review,
        "coverage": COVERAGE,
    }
    payload = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=".read-trial-", dir=state)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # Publish without overwriting an existing trial. A failed attempt
        # must not silently rewrite an operator's prior attestation.
        os.link(temporary, output_path, follow_symlinks=False)
    except FileExistsError as exc:
        raise TrialManifestError("trial_manifest_already_exists_or_unsafe") from exc
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        "schema": "wikidebia-session-trial-finalization-1.0",
        "condition": condition,
        "session_count": report["session_count"],
        "event_count": report["event_count"],
        "manifest_written": True,
        "task_completed_self_reported": task_completed,
        "quality_review_self_reported": quality_review,
        "actual_billed_tokens": None,
        "actual_codex_cloud_credits": None,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--protocol", required=True, help="Tracked public file, unchanged from HEAD")
    parser.add_argument("--events-name", default="session-reads.jsonl")
    parser.add_argument("--output-name")
    parser.add_argument("--task-completed", action="store_true")
    parser.add_argument("--quality-review", choices=REVIEWS, default="not_reviewed")
    args = parser.parse_args()
    try:
        result = finalize_trial(
            args.project_root, condition=args.condition, task_id=args.task_id,
            protocol_path=args.protocol, events_name=args.events_name,
            output_name=args.output_name, task_completed=args.task_completed,
            quality_review=args.quality_review,
        )
    except (TrialManifestError, ReadAuditError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
