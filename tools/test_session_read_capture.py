"""Integration tests for opt-in, measured reads of tracked repository files."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from session_read_capture import CaptureError, capture_read
from session_read_audit import ReadAuditError, audit_jsonl


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    path = root / "kit/a.py"
    path.parent.mkdir()
    path.write_bytes(b"print('public')\n")
    subprocess.run(["git", "-C", str(root), "add", "kit/a.py"], check=True)
    return root


def _run(root: Path, session="one", relative="kit/a.py") -> tuple[bytes, dict]:
    out = io.BytesIO()
    result = capture_read(root, relative, session, out)
    return out.getvalue(), result


def test_captures_exact_bytes_and_real_sha256(tmp_path):
    root = _repo(tmp_path)
    output, event = _run(root)
    data = (root / "kit/a.py").read_bytes()
    assert output == data
    assert event == {
        "session_id": "one", "path": "kit/a.py",
        "content_sha256": hashlib.sha256(data).hexdigest(),
    }
    log = root / ".state/session-reads.jsonl"
    assert json.loads(log.read_text()) == event
    assert log.stat().st_mode & 0o077 == 0
    assert audit_jsonl(log)["event_count"] == 1


def test_repeated_within_across_and_changed_bytes(tmp_path):
    root = _repo(tmp_path)
    _run(root, "one")
    _run(root, "one")
    _run(root, "two")
    (root / "kit/a.py").write_bytes(b"changed content\n")
    _run(root, "two")
    _run(root, "three")
    report = audit_jsonl(root / ".state/session-reads.jsonl")
    assert report["event_count"] == 5
    assert report["first_or_changed_reads"] == 2
    assert report["changed_content_reads"] == 1
    assert report["repeated_reads_within_session"] == 1
    assert report["repeated_reads_across_sessions"] == 2
    assert report["actual_codex_cloud_credits"] is None


@pytest.mark.parametrize("relative", [
    "/etc/passwd", "../secret", ".state/secret.txt",
    "private/password", "kit/../kit/a.py", "kit//a.py",
    "kit/.env", "kit\\a.py",
])
def test_refuses_unsafe_paths_without_output_or_log(tmp_path, relative):
    root = _repo(tmp_path)
    out = io.BytesIO()
    with pytest.raises(ReadAuditError):
        capture_read(root, relative, "one", out)
    assert out.getvalue() == b""
    assert not (root / ".state/session-reads.jsonl").exists()


def test_rejects_untracked_files(tmp_path):
    root = _repo(tmp_path)
    (root / "kit/untracked.py").write_text("untracked")
    out = io.BytesIO()
    with pytest.raises(CaptureError, match="not_tracked"):
        capture_read(root, "kit/untracked.py", "one", out)
    assert out.getvalue() == b""


def test_does_not_follow_symlinks(tmp_path):
    root = _repo(tmp_path)
    secret = tmp_path / "private"
    secret.write_bytes(b"SECRET CONTENT")
    (root / "kit/link.py").symlink_to(secret)
    subprocess.run(["git", "-C", str(root), "add", "kit/link.py"], check=True)
    out = io.BytesIO()
    with pytest.raises(CaptureError, match="symlink"):
        capture_read(root, "kit/link.py", "one", out)
    assert out.getvalue() == b""


def test_refuses_symlinked_state_and_log(tmp_path):
    root = _repo(tmp_path)
    (root / ".state").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(CaptureError, match="state"):
        _run(root)
    (root / ".state").unlink()
    (root / ".state").mkdir()
    external = tmp_path / "external-log.txt"
    external.write_text("private")
    (root / ".state/session-reads.jsonl").symlink_to(external)
    with pytest.raises(CaptureError, match="log"):
        _run(root)
    assert external.read_text() == "private"


def test_rejects_session_interleaving_before_printing(tmp_path):
    root = _repo(tmp_path)
    _run(root, "one")
    _run(root, "two")
    out = io.BytesIO()
    original = (root / ".state/session-reads.jsonl").read_bytes()
    with pytest.raises(ReadAuditError, match="contiguous"):
        capture_read(root, "kit/a.py", "one", out)
    assert out.getvalue() == b""
    assert (root / ".state/session-reads.jsonl").read_bytes() == original


def test_refuses_broken_existing_log_without_changing_it(tmp_path):
    root = _repo(tmp_path)
    state = root / ".state"
    state.mkdir()
    log = state / "session-reads.jsonl"
    log.write_text("{not-json}\n")
    out = io.BytesIO()
    with pytest.raises(CaptureError, match="invalid_existing"):
        capture_read(root, "kit/a.py", "one", out)
    assert out.getvalue() == b""
    assert log.read_text() == "{not-json}\n"


def test_no_log_event_when_stdout_fails(tmp_path):
    root = _repo(tmp_path)

    class FailOutput(io.BytesIO):
        def write(self, data):
            raise OSError("broken pipe")

    with pytest.raises(OSError, match="broken pipe"):
        capture_read(root, "kit/a.py", "one", FailOutput())
    assert not (root / ".state/session-reads.jsonl").exists()


def test_rejects_large_file_before_printing(tmp_path, monkeypatch):
    import session_read_capture as capture
    root = _repo(tmp_path)
    monkeypatch.setattr(capture, "MAX_READ_BYTES", 3)
    out = io.BytesIO()
    with pytest.raises(CaptureError, match="read_limit"):
        capture_read(root, "kit/a.py", "one", out)
    assert out.getvalue() == b""
    assert not (root / ".state").exists()


def test_cli_prints_only_file_bytes(tmp_path):
    root = _repo(tmp_path)
    script = Path(__file__).with_name("session_read_capture.py")
    completed = subprocess.run(
        [sys.executable, str(script), "--project-root", str(root),
         "--session", "session-1", "--path", "kit/a.py"],
        check=True, capture_output=True,
    )
    assert completed.stdout == b"print('public')\n"
    assert completed.stderr == b""
    assert audit_jsonl(root / ".state/session-reads.jsonl")["event_count"] == 1
