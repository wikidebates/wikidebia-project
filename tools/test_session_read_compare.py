"""Regression coverage for paired read trials and refusal of unverified savings."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import session_read_compare as compare


def _event(session: str, path="kit/a.py", sha="a" * 64) -> dict:
    return {"session_id": session, "path": path, "content_sha256": sha}


def _trial(
    root: Path, condition: str, events: list[dict],
    *, completed=True, review="passed", task="issue_81", commit="1" * 40,
    protocol="2" * 64,
) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    log = root / (condition + ".jsonl")
    log.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    meta = root / (condition + ".metadata.json")
    meta.write_text(json.dumps({
        "schema": compare.TRIAL_SCHEMA, "condition": condition,
        "task_id": task, "base_commit": commit, "protocol_sha256": protocol,
        "events_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "task_completed": completed, "quality_review": review,
        "coverage": compare.COVERAGE,
    }), encoding="utf-8")
    return log, meta


def _paired(tmp_path: Path):
    control = _trial(tmp_path / "c", "control", [
        _event("control1"), _event("control1", "kit/b.py"),
        _event("control2"), _event("control2", "kit/b.py"),
        _event("control2"),
    ])
    handoff = _trial(tmp_path / "h", "handoff", [
        _event("handoff1"), _event("handoff1", "kit/b.py"),
        _event("handoff2", "kit/b.py"),
    ])
    return (*control, *handoff)


def test_descriptive_differences_only_when_paired_and_reviewed(tmp_path):
    args = _paired(tmp_path)
    out = compare.compare_trials(*args)
    assert out["comparison_eligible_for_descriptive_counts"] is True
    assert out["control"]["event_count"] == 5
    assert out["control"]["repeated_reads_within_session"] == 1
    assert out["control"]["repeated_reads_across_sessions"] == 2
    assert out["handoff"]["event_count"] == 3
    assert out["handoff"]["repeated_reads_across_sessions"] == 1
    assert out["descriptive_difference_not_causal_savings"] == {
        "event_count_handoff_minus_control": -2,
        "first_or_changed_reads_handoff_minus_control": 0,
        "changed_content_reads_handoff_minus_control": 0,
        "repeated_reads_within_session_handoff_minus_control": -1,
        "repeated_reads_across_sessions_handoff_minus_control": -1,
    }
    assert out["causal_savings_established"] is False
    assert out["quality_automatically_verified"] is False
    assert out["actual_billed_tokens"] is None
    assert out["actual_codex_cloud_credits"] is None
    assert out["saved_time_seconds"] is None
    rendered = json.dumps(out)
    assert "kit/a.py" not in rendered
    assert "control1" not in rendered
    assert "issue_81" not in rendered


@pytest.mark.parametrize("value,expected", [
    ("failed", "quality_review_not_passed_in_both_conditions"),
    ("not_reviewed", "quality_review_not_passed_in_both_conditions"),
])
def test_review_failure_prevents_difference(tmp_path, value, expected):
    c, cm, h, hm = _paired(tmp_path)
    data = json.loads(hm.read_text())
    data["quality_review"] = value
    hm.write_text(json.dumps(data))
    result = compare.compare_trials(c, cm, h, hm)
    assert result["comparison_eligible_for_descriptive_counts"] is False
    assert expected in result["ineligibility_reasons"]
    assert result["descriptive_difference_not_causal_savings"] is None


def test_incomplete_task_prevents_difference(tmp_path):
    c, cm, h, hm = _paired(tmp_path)
    data = json.loads(cm.read_text())
    data["task_completed"] = False
    cm.write_text(json.dumps(data))
    result = compare.compare_trials(c, cm, h, hm)
    assert not result["comparison_eligible_for_descriptive_counts"]
    assert "task_not_completed_in_both_conditions" in result["ineligibility_reasons"]


def test_less_than_two_sessions_prevents_difference(tmp_path):
    c, cm, _, _ = _paired(tmp_path)
    h, hm = _trial(tmp_path / "h2", "handoff", [_event("single")])
    result = compare.compare_trials(c, cm, h, hm)
    assert "at_least_two_sessions_per_condition_required" in result["ineligibility_reasons"]
    assert "session_count_mismatch" in result["ineligibility_reasons"]
    assert result["descriptive_difference_not_causal_savings"] is None


@pytest.mark.parametrize("field,value", [
    ("task_id", "different_task"),
    ("base_commit", "f" * 40),
    ("protocol_sha256", "e" * 64),
])
def test_mismatched_trial_inputs_are_rejected(tmp_path, field, value):
    c, cm, h, hm = _paired(tmp_path)
    data = json.loads(hm.read_text())
    data[field] = value
    hm.write_text(json.dumps(data))
    with pytest.raises(compare.ComparisonError, match="mismatch"):
        compare.compare_trials(c, cm, h, hm)


def test_changed_events_are_detected_by_digest(tmp_path):
    c, cm, h, hm = _paired(tmp_path)
    h.write_text(h.read_text() + json.dumps(_event("handoff2")) + "\n")
    with pytest.raises(compare.ComparisonError, match="digest_mismatch"):
        compare.compare_trials(c, cm, h, hm)


@pytest.mark.parametrize("field,value", [
    ("quality_review", ["passed"]),
    ("task_completed", "true"),
    ("task_id", "../other_task"),
    ("base_commit", "xyz"),
    ("events_sha256", "secret"),
    ("coverage", "all_model_reads"),
])
def test_invalid_metadata_is_rejected(tmp_path, field, value):
    c, cm, h, hm = _paired(tmp_path)
    data = json.loads(hm.read_text())
    data[field] = value
    hm.write_text(json.dumps(data))
    with pytest.raises(compare.ComparisonError):
        compare.compare_trials(c, cm, h, hm)


def test_extra_metadata_fields_are_forbidden(tmp_path):
    c, cm, h, hm = _paired(tmp_path)
    data = json.loads(hm.read_text())
    data["credentials"] = "do-not-include"
    hm.write_text(json.dumps(data))
    with pytest.raises(compare.ComparisonError, match="fields"):
        compare.compare_trials(c, cm, h, hm)


def test_symlinks_and_identical_logs_are_rejected(tmp_path):
    c, cm, h, hm = _paired(tmp_path)
    link = tmp_path / "link.jsonl"
    link.symlink_to(h)
    with pytest.raises(compare.ComparisonError, match="events"):
        compare.compare_trials(c, cm, link, hm)
    link_meta = tmp_path / "link-meta.json"
    link_meta.symlink_to(hm)
    with pytest.raises(compare.ComparisonError, match="manifest"):
        compare.compare_trials(c, cm, h, link_meta)
    # A single log cannot masquerade as both independent conditions.
    with pytest.raises(compare.ComparisonError, match="condition"):
        compare.compare_trials(c, cm, c, cm)  # condition mismatch happens first


def test_large_logs_rejected_before_digest_read(tmp_path, monkeypatch):
    c, cm, h, hm = _paired(tmp_path)
    monkeypatch.setattr(compare, "MAX_LOG_BYTES", 1)
    with pytest.raises(compare.ComparisonError, match="events"):
        compare.compare_trials(c, cm, h, hm)


def test_cli_has_only_aggregate_json(tmp_path):
    paths = _paired(tmp_path)
    script = Path(compare.__file__)
    command = [
        sys.executable, str(script),
        "--control-events", str(paths[0]), "--control-manifest", str(paths[1]),
        "--handoff-events", str(paths[2]), "--handoff-manifest", str(paths[3]),
    ]
    proc = subprocess.run(command, capture_output=True, check=True)
    report = json.loads(proc.stdout)
    assert report["comparison_eligible_for_descriptive_counts"] is True
    assert proc.stderr == b""
    assert b"kit/a.py" not in proc.stdout
