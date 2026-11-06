"""Regression checks for resuming *before* English translation (issue #81).

These tests intentionally do not run translation or modify corpus files.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_global_resume as global_resume
from wikidebia_workspace_status import _next_step


DEBATE = "test-reprise"
WORK = "work-test"


@pytest.mark.parametrize(
    ("status", "expected_action", "command_part"),
    [
        ("workspace_initialized", "finalize_french_title_review", "corpus-workspace-review"),
        ("fr_title_review_finalized", "apply_french_title_review", "corpus-workspace-review"),
        ("fr_titles_applied", "prepare_french_content_review", "corpus-workspace-content-review"),
        ("fr_content_review_ready", "finalize_french_content_review", "corpus-workspace-content-review"),
        ("fr_content_review_finalized", "apply_french_content_review", "corpus-workspace-content-review"),
        ("fr_content_applied", "prepare_english_translation_review", "corpus-workspace-translation"),
    ],
)
def test_resume_selects_next_pretranslation_stage(status, expected_action, command_part):
    metadata = {"status": status}
    if status == "fr_title_review_finalized":
        metadata["french_review"] = {"review_sha256": "a" * 64}
    if status == "fr_content_review_finalized":
        metadata["french_content_review"] = {"review_sha256": "b" * 64}
    result = _next_step(metadata, DEBATE, WORK)
    assert result["action"] == expected_action
    assert command_part in result["command"]
    assert result["remote_write_possible"] is False
    assert result["remote_read_possible"] is False


def test_global_resume_reuses_existing_workspace_status(monkeypatch, tmp_path):
    """An existing French review must resume, not initialize another workspace."""
    workspace = tmp_path / ".state" / "editorial-workspaces" / DEBATE / WORK
    workspace.mkdir(parents=True)
    workspace_json = workspace / "workspace.json"
    workspace_json.write_text("{}", encoding="utf-8")
    next_step = _next_step({"status": "fr_content_review_ready"}, DEBATE, WORK)
    monkeypatch.setattr(
        global_resume, "summarize_workspace",
        lambda *_args: {
            "status": "fr_content_review_ready",
            "phase": "french",
            "workspace_sha256": "c" * 64,
            "next_action": next_step["action"],
            "next_command": next_step["command"],
        },
    )
    monkeypatch.setattr(global_resume, "_published_receipt", lambda *_args: None)
    monkeypatch.setattr(global_resume, "_translation_resume", lambda *_args: (None, None))
    result = global_resume._workspace_entry(tmp_path, workspace_json)
    assert result["next_action"] == "finalize_french_content_review"
    assert "corpus-workspace-content-review" in result["next_command"]
    assert "corpus-workspace-init" not in result["next_command"]
    assert result["remote_write_performed"] is False


def test_pretranslation_resume_does_not_skip_missing_approval():
    """No fabricated approval hash: a human-gated stage stays blocked."""
    result = _next_step({"status": "fr_content_review_finalized"}, DEBATE, WORK)
    assert result["action"] == "manual_review_required"
    assert result["command"] is None
