#!/usr/bin/env python3
"""Opt-in, local, complete-file read capture for the session read audit.

Only explicitly requested reads of Git-tracked public files are captured.
The exact bytes sent to stdout are hashed and logged inside .state/, never
committed. This does not intercept other tools or automatically measure Codex.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import stat
from pathlib import Path
from typing import BinaryIO

from session_read_audit import (
    MAX_EVENTS,
    MAX_LOG_BYTES,
    ReadAuditError,
    _safe_path,
    _validate_event,
    audit_read_events,
)

MAX_READ_BYTES = 512_000
LOG_NAME = "session-reads.jsonl"
LOCK_NAME = "session-reads.lock"


class CaptureError(ReadAuditError):
    """Cannot safely read or account for the requested file."""


def _tracked_regular_file(root: Path, relative: str) -> Path:
    """Resolve a public tracked file without traversing a symlink."""
    relative = _safe_path(relative)
    current = root
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            raise CaptureError("symlink_in_source_path")
    if not current.is_file() or not current.resolve().is_relative_to(root):
        raise CaptureError("source_not_regular_or_outside_repository")
    if current.stat().st_size > MAX_READ_BYTES:
        raise CaptureError("source_exceeds_read_limit")
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", relative],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError as exc:
        raise CaptureError("git_not_available") from exc
    if result.returncode != 0:
        raise CaptureError("file_not_tracked_by_git")
    return current


def _read_public_bytes(root: Path, relative_path: str) -> bytes:
    """Read via directory FDs so an attacker cannot swap a parent for a symlink.

    The Git tracking check is performed separately; only actual bytes read
    from this descriptor enter the stdout stream and the audit digest.
    """
    parts = _safe_path(relative_path).split("/")
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = None
    try:
        fd = os.open(root, dir_flags)
        for part in parts[:-1]:
            child = os.open(part, dir_flags, dir_fd=fd)
            os.close(fd)
            fd = child
        source_fd = os.open(parts[-1], file_flags, dir_fd=fd)
        with os.fdopen(source_fd, "rb") as stream:
            size = os.fstat(stream.fileno())
            if not stat.S_ISREG(size.st_mode):
                raise CaptureError("source_not_regular_file")
            if size.st_size > MAX_READ_BYTES:
                raise CaptureError("source_exceeds_read_limit")
            data = stream.read(MAX_READ_BYTES + 1)
            if len(data) > MAX_READ_BYTES:
                raise CaptureError("source_exceeds_read_limit")
            return data
    except OSError as exc:
        raise CaptureError("source_path_changed_or_unreadable") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _read_existing(log: Path) -> list[dict]:
    if not log.exists() and not log.is_symlink():
        return []
    if log.is_symlink() or not log.is_file() or log.stat().st_size > MAX_LOG_BYTES:
        raise CaptureError("unsafe_or_oversized_session_log")
    try:
        raw = log.read_bytes()
        if raw and not raw.endswith(b"\n"):
            raise CaptureError("unterminated_existing_session_log")
        entries = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        audit_read_events(entries)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise CaptureError("invalid_existing_session_log") from exc
    return entries


def capture_read(
    project_root: Path,
    relative_path: str,
    session_id: str,
    output: BinaryIO,
) -> dict[str, str]:
    """Stream a Git-tracked file and record one successfully delivered read."""
    root = project_root.expanduser().resolve()
    _tracked_regular_file(root, relative_path)
    data = _read_public_bytes(root, relative_path)
    event = {
        "session_id": session_id,
        "path": _safe_path(relative_path),
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }
    _validate_event(event)

    state = root / ".state"
    if state.is_symlink():
        raise CaptureError("unsafe_state_directory")
    state.mkdir(mode=0o700, exist_ok=True)
    if not state.is_dir() or state.is_symlink():
        raise CaptureError("unsafe_state_directory")

    lock = state / LOCK_NAME
    if lock.is_symlink():
        raise CaptureError("unsafe_session_lock")
    lock_fd = os.open(
        lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600
    )
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        log = state / LOG_NAME
        previous = _read_existing(log)
        if len(previous) >= MAX_EVENTS:
            raise CaptureError("session_log_event_limit")
        # Reject a session appearing after its block has already closed.
        audit_read_events([*previous, event])
        payload = (json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        existing_bytes = log.stat().st_size if log.exists() else 0
        if existing_bytes + len(payload) > MAX_LOG_BYTES:
            raise CaptureError("session_log_size_limit")

        # Do not count a read if its output stream refused the content.
        output.write(data)
        output.flush()

        flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        file_fd = os.open(log, flags, 0o600)
        try:
            written = os.write(file_fd, payload)
            if written != len(payload):
                raise CaptureError("short_session_log_write")
            os.fsync(file_fd)
        finally:
            os.close(file_fd)
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    return event


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--session", required=True, help="Pseudonymous contiguous session ID")
    parser.add_argument("--path", required=True, help="Git-tracked relative public file path")
    args = parser.parse_args()
    try:
        capture_read(args.project_root, args.path, args.session, sys.stdout.buffer)
    except (ReadAuditError, OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
