#!/usr/bin/env python3
"""Count declared repeated repository reads across and within AI sessions.

This audit only processes explicitly supplied JSONL events. It cannot observe
ChatGPT or Codex tool usage, billable tokens, or the quality of any translation.
No raw file content, source paths, or session identifiers appear in the report.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

SCHEMA = "wikidebia-session-read-audit-1.0"
MAX_LOG_BYTES = 10_000_000
MAX_EVENTS = 50_000
EXCLUDED_PARTS = {
    ".git", ".state", ".venv", "private", "corpus", "archives",
    "incoming", "outgoing", "logs", "plans", "updates", "apicache",
    "__pycache__",
}
SENSITIVE_NAMES = {
    "user-password.cfg", "user-config.py", "wikidebia.local.json",
    ".gitconfig-wikidebia", "throttle.ctrl", ".netrc", ".npmrc",
    ".pypirc", "id_rsa", "id_ed25519", "credentials.json",
}
SENSITIVE_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx", ".lwp")
HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


class ReadAuditError(ValueError):
    """The declared evidence is missing, unsafe, or inconsistent."""


def _safe_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 400:
        raise ReadAuditError("invalid_repository_path")
    if (
        value.startswith("/") or "\\" in value or ":" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ReadAuditError("invalid_repository_path")
    path = PurePosixPath(value)
    if (
        path.is_absolute() or path.as_posix() != value
        or not path.parts or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(
            part in EXCLUDED_PARTS
            or part.lower() in SENSITIVE_NAMES
            or part.lower().startswith((".env", ".secret"))
            or part.lower().endswith(SENSITIVE_SUFFIXES)
            for part in path.parts
        )
    ):
        raise ReadAuditError("excluded_or_unsafe_repository_path")
    return value


def _validate_event(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, dict) or set(value) != {
        "session_id", "path", "content_sha256"
    }:
        raise ReadAuditError("invalid_event_fields")
    session = value["session_id"]
    digest = value["content_sha256"]
    if not isinstance(session, str) or not SESSION_ID.fullmatch(session):
        raise ReadAuditError("invalid_session_id")
    if not isinstance(digest, str) or not HEX_SHA256.fullmatch(digest):
        raise ReadAuditError("invalid_content_sha256")
    return session, _safe_path(value["path"]), digest


def audit_read_events(events: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Classify each event once: within-session, cross-session, or fresh.

    Sessions must form contiguous chronological blocks. A changed SHA-256
    represents a new revision, not a redundant read, even for the same path.
    """
    seen_global: set[tuple[str, str]] = set()
    seen_paths: set[str] = set()
    completed_sessions: set[str] = set()
    seen_current: set[tuple[str, str]] = set()
    current: str | None = None
    per_session: list[dict[str, int]] = []
    fresh = within = across = changed = count = 0

    for event in events:
        if count >= MAX_EVENTS:
            raise ReadAuditError("too_many_events")
        session, path, digest = _validate_event(event)
        key = (path, digest)
        if session != current:
            if session in completed_sessions:
                raise ReadAuditError("sessions_must_be_contiguous")
            if current is not None:
                completed_sessions.add(current)
            current = session
            seen_current = set()
            per_session.append({"session_index": len(per_session) + 1,
                                "events": 0, "within": 0, "across": 0, "fresh": 0})
        row = per_session[-1]
        count += 1
        row["events"] += 1
        if key in seen_current:
            within += 1
            row["within"] += 1
        elif key in seen_global:
            across += 1
            row["across"] += 1
        else:
            fresh += 1
            row["fresh"] += 1
            if path in seen_paths:
                changed += 1
        seen_current.add(key)
        seen_global.add(key)
        seen_paths.add(path)

    return {
        "schema": SCHEMA,
        "source": "declared_jsonl_events_not_automatic_instrumentation",
        "session_count": len(per_session),
        "event_count": count,
        "first_or_changed_reads": fresh,
        "changed_content_reads": changed,
        "repeated_reads_within_session": within,
        "repeated_reads_across_sessions": across,
        "session_summaries": per_session,
        "actual_billed_tokens": None,
        "actual_codex_cloud_credits": None,
        "saved_time_seconds": None,
        "raw_content_included": False,
        "file_paths_included": False,
        "session_ids_included": False,
        "remote_access_performed": False,
        "remote_write_performed": False,
    }


def audit_jsonl(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
        raise ReadAuditError("input_missing_symlink_or_too_large")
    events = []
    with path.open("r", encoding="utf-8") as stream:
        for number, raw in enumerate(stream, 1):
            if number > MAX_EVENTS:
                raise ReadAuditError("too_many_events")
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ReadAuditError("invalid_jsonl_event") from exc
    return audit_read_events(events)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path,
                        help="Private chronological JSONL log of declared full-file reads")
    args = parser.parse_args()
    try:
        result = audit_jsonl(args.events)
    except (ReadAuditError, OSError, UnicodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
