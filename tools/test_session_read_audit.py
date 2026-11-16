"""Regression tests for explicit read-event accounting and privacy."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).with_name("session_read_audit.py")
spec = importlib.util.spec_from_file_location("session_read_audit", MODULE_PATH)
assert spec and spec.loader
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def event(session, path="kit/scripts/a.py", digest="a" * 64):
    return {"session_id": session, "path": path, "content_sha256": digest}


def test_separates_within_across_and_changed_revisions():
    report = audit.audit_read_events([
        event("session_1"),                  # first
        event("session_1"),                  # within
        event("session_1", "kit/b.py"),       # first
        event("session_2"),                  # across
        event("session_2"),                  # within
        event("session_2", digest="b" * 64),  # changed, not redundant
        event("session_3", digest="b" * 64),  # across
    ])
    assert report["event_count"] == 7
    assert report["first_or_changed_reads"] == 3
    assert report["changed_content_reads"] == 1
    assert report["repeated_reads_within_session"] == 2
    assert report["repeated_reads_across_sessions"] == 2
    assert report["session_count"] == 3
    assert report["actual_billed_tokens"] is None
    assert report["actual_codex_cloud_credits"] is None
    assert report["saved_time_seconds"] is None
    rendered = json.dumps(report)
    assert "kit/scripts/a.py" not in rendered
    assert "session_1" not in rendered


@pytest.mark.parametrize("path", [
    "../secret", "/etc/passwd", "kit/../private/x.py",
    ".state/notes.json", "corpus/secret.wiki", "private/x.py",
    "kit/.env.local", "kit//x.py", "C:/secrets.txt", "kit\\x.py",
])
def test_rejects_private_or_unsafe_paths(path):
    with pytest.raises(audit.ReadAuditError):
        audit.audit_read_events([event("s1", path=path)])


@pytest.mark.parametrize("payload", [
    {"session_id": "a", "path": "kit/a.py"},
    {"session_id": "../escape", "path": "kit/a.py", "content_sha256": "a" * 64},
    {"session_id": "s", "path": "kit/a.py", "content_sha256": "short"},
    {"session_id": "s", "path": "kit/a.py", "content_sha256": "a" * 64, "secret": "x"},
])
def test_rejects_invalid_event_schema(payload):
    with pytest.raises(audit.ReadAuditError):
        audit.audit_read_events([payload])


def test_session_interleaving_is_rejected_not_miscounted():
    with pytest.raises(audit.ReadAuditError, match="contiguous"):
        audit.audit_read_events([event("a"), event("b"), event("a")])


def test_jsonl_input_is_read_only_and_private(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps(event("s1")) + "\n" + json.dumps(event("s2")) + "\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    assert audit.audit_jsonl(path)["repeated_reads_across_sessions"] == 1
    assert path.read_bytes() == before


def test_does_not_follow_symlink(tmp_path):
    target = tmp_path / "target.jsonl"
    target.write_text(json.dumps(event("s")) + "\n", encoding="utf-8")
    link = tmp_path / "link.jsonl"
    link.symlink_to(target)
    with pytest.raises(audit.ReadAuditError):
        audit.audit_jsonl(link)


def test_rejects_unbounded_or_invalid_input(tmp_path, monkeypatch):
    file = tmp_path / "reads.jsonl"
    file.write_text("{invalid}\n", encoding="utf-8")
    with pytest.raises(audit.ReadAuditError):
        audit.audit_jsonl(file)
    file.write_text(json.dumps(event("s")) + "\n", encoding="utf-8")
    monkeypatch.setattr(audit, "MAX_LOG_BYTES", 1)
    with pytest.raises(audit.ReadAuditError):
        audit.audit_jsonl(file)


def test_empty_evidence_does_not_fake_savings():
    report = audit.audit_read_events([])
    assert report["event_count"] == 0
    assert report["session_count"] == 0
    assert report["repeated_reads_across_sessions"] == 0
    assert report["actual_billed_tokens"] is None
