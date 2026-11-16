"""Integration checks for finalizing controlled multi-session read evidence."""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from session_read_capture import capture_read
from session_read_compare import compare_trials
from session_read_trial_manifest import TrialManifestError, finalize_trial


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
    (root / "docs").mkdir()
    (root / "kit").mkdir()
    (root / "docs/protocol.md").write_bytes(b"One fixed task; two sessions\n")
    (root / "kit/public.py").write_bytes(b"print('public')\n")
    subprocess.run(["git", "-C", str(root), "add", "docs/protocol.md", "kit/public.py"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root


def _reads(root: Path, prefix: str) -> None:
    capture_read(root, "kit/public.py", prefix + "_one", io.BytesIO())
    capture_read(root, "kit/public.py", prefix + "_two", io.BytesIO())


def _finalize(root: Path, **kwargs):
    args = {
        "condition": "control", "task_id": "issue81_probe",
        "protocol_path": "docs/protocol.md", "task_completed": True,
        "quality_review": "passed",
    }
    args.update(kwargs)
    return finalize_trial(root, **args)


def test_produces_real_git_and_content_shas(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    report = _finalize(root)
    assert report["event_count"] == 2
    assert report["session_count"] == 2
    assert report["actual_codex_cloud_credits"] is None
    manifest_path = root / ".state/control-trial.json"
    manifest = json.loads(manifest_path.read_text())
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert manifest["base_commit"] == head
    assert manifest["protocol_sha256"] == hashlib.sha256(
        (root / "docs/protocol.md").read_bytes()
    ).hexdigest()
    assert manifest["events_sha256"] == hashlib.sha256(
        (root / ".state/session-reads.jsonl").read_bytes()
    ).hexdigest()
    assert manifest["quality_review"] == "passed"
    assert manifest_path.stat().st_mode & 0o077 == 0
    assert "kit/public.py" not in json.dumps(report)


def test_two_real_logs_from_same_git_commit_are_comparable(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "control")
    state = root / ".state"
    (state / "session-reads.jsonl").rename(state / "control.jsonl")
    _finalize(root, events_name="control.jsonl")
    _reads(root, "handoff")
    (state / "session-reads.jsonl").rename(state / "handoff.jsonl")
    out = finalize_trial(
        root, condition="handoff", task_id="issue81_probe",
        protocol_path="docs/protocol.md", events_name="handoff.jsonl",
        task_completed=True, quality_review="passed",
    )
    assert out["session_count"] == 2
    comparison = compare_trials(
        state / "control.jsonl", state / "control-trial.json",
        state / "handoff.jsonl", state / "handoff-trial.json",
    )
    assert comparison["comparison_eligible_for_descriptive_counts"] is True
    assert comparison["causal_savings_established"] is False
    assert comparison["control"]["repeated_reads_across_sessions"] == 1
    assert comparison["handoff"]["repeated_reads_across_sessions"] == 1
    assert comparison["descriptive_difference_not_causal_savings"][
        "repeated_reads_across_sessions_handoff_minus_control"
    ] == 0


def test_defaults_do_not_assert_completed_or_quality_review(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    finalize_trial(root, condition="control", task_id="issue81_probe", protocol_path="docs/protocol.md")
    manifest = json.loads((root / ".state/control-trial.json").read_text())
    assert manifest["task_completed"] is False
    assert manifest["quality_review"] == "not_reviewed"


def test_rejects_dirty_or_untracked_protocol(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    (root / "docs/protocol.md").write_text("changed task\n")
    with pytest.raises(TrialManifestError, match="modified_protocol"):
        _finalize(root)
    assert not (root / ".state/control-trial.json").exists()
    (root / "docs/new.md").write_text("untracked\n")
    with pytest.raises(TrialManifestError) as exc:
        _finalize(root, protocol_path="docs/new.md")
    assert "tracked" in str(exc.value)


def test_single_session_ineligible_to_finalize(tmp_path):
    root = _repo(tmp_path)
    capture_read(root, "kit/public.py", "one", io.BytesIO())
    with pytest.raises(TrialManifestError, match="two_sessions"):
        _finalize(root)
    assert not (root / ".state/control-trial.json").exists()


def test_existing_manifest_cannot_be_replaced(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    _finalize(root)
    before = (root / ".state/control-trial.json").read_bytes()
    with pytest.raises(TrialManifestError, match="already_exists"):
        _finalize(root)
    assert (root / ".state/control-trial.json").read_bytes() == before


@pytest.mark.parametrize("name", [
    "../outside.json", "inside/control.json", ".secret.json",
    "unknown.txt", "CONTROL.JSON",
])
def test_rejects_unsafe_output_name(tmp_path, name):
    root = _repo(tmp_path)
    _reads(root, "c")
    with pytest.raises(TrialManifestError, match="invalid_private_filename"):
        _finalize(root, output_name=name)


def test_symlink_log_is_rejected(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    log = root / ".state/session-reads.jsonl"
    other = tmp_path / "other"
    log.rename(other)
    log.symlink_to(other)
    with pytest.raises(TrialManifestError, match="unsafe_event_log"):
        _finalize(root)


def test_malformed_log_is_rejected_without_new_manifest(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    log = root / ".state/session-reads.jsonl"
    log.write_bytes(log.read_bytes() + b"{broken}\n")
    with pytest.raises(TrialManifestError, match="invalid_observed_events"):
        _finalize(root)
    assert not (root / ".state/control-trial.json").exists()


def test_cli_creates_private_manifest_without_paths_in_stdout(tmp_path):
    root = _repo(tmp_path)
    _reads(root, "c")
    script = Path(__file__).with_name("session_read_trial_manifest.py")
    proc = subprocess.run([
        sys.executable, str(script),
        "--project-root", str(root),
        "--condition", "control",
        "--task-id", "issue81_probe",
        "--protocol", "docs/protocol.md",
    ], capture_output=True, check=True)
    data = json.loads(proc.stdout)
    assert proc.stderr == b""
    assert data["manifest_written"] is True
    assert data["quality_review_self_reported"] == "not_reviewed"
    assert b"docs/protocol.md" not in proc.stdout
    assert b"kit/public.py" not in proc.stdout
