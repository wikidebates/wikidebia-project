from __future__ import annotations

import json
from pathlib import Path

import wikidebia_workspace_status as status


def _meta(workspace_status: str, **extra):
    return {
        "status": workspace_status,
        "workspace_sha256": "w" * 64,
        "translated_copy": {"review_sha256": "t" * 64},
        "rendered_copy": {"tree_sha256": "r" * 64},
        "release_copy": {"tree_sha256": "l" * 64},
        **extra,
    }


def test_summary_verifies_remote_comparison_and_returns_exact_command(tmp_path: Path, monkeypatch):
    meta = _meta(
        "remote_plan_ready",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_comparisons=[{"comparison_id": "REMOTE-20261104-003"}],
        remote_history=[{"large": "x" * 10000}],
    )
    monkeypatch.setattr(status, "_load_workspace", lambda *args: (tmp_path, meta))
    monkeypatch.setattr(
        status,
        "_load_comparison",
        lambda *args: {
            "plan": {
                "plan_sha256": "p" * 64,
                "operations": {
                    "create": [{}], "update": [], "move": [], "redirect": [],
                    "delete": [], "skip": [{}] * 697, "manual_review": [], "blocked": [],
                },
            },
            "receipt": {
                "status": "plan_ready",
                "scope": "all",
                "counts": {"skip": 697, "create": 1},
                "plan_sha256": "p" * 64,
                "receipt_sha256": "c" * 64,
            }
        },
    )

    result = status.summarize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")

    assert result["next_command"] == (
        "./wikidebia corpus-workspace-plan-review debat_test --work-id EDIT-TEST-001 "
        "--comparison-id REMOTE-20261104-003 --prepare"
    )
    assert result["next_remote_read_possible"] is False
    assert result["next_remote_write_possible"] is False
    assert result["status_check_remote_access"] is False
    assert result["remote"]["counts"] == {"skip": 697, "create": 1}
    assert "remote_history" not in result
    assert len(json.dumps(result)) < 2500


def test_summary_shortcuts_signed_all_skip_plan_to_local_closure(tmp_path: Path, monkeypatch):
    meta = _meta(
        "remote_plan_ready",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_comparisons=[{"comparison_id": "REMOTE-20261104-003"}],
    )
    operations = {
        "create": [], "update": [], "move": [], "redirect": [], "delete": [],
        "skip": [{"page_id": "A0001"}], "manual_review": [], "blocked": [],
    }
    monkeypatch.setattr(status, "_load_workspace", lambda *args: (tmp_path, meta))
    monkeypatch.setattr(
        status,
        "_load_comparison",
        lambda *args: {
            "plan": {"plan_sha256": "p" * 64, "operations": operations},
            "receipt": {
                "status": "plan_ready", "scope": "all", "counts": {"skip": 1},
                "plan_sha256": "p" * 64, "receipt_sha256": "c" * 64,
            },
        },
    )

    result = status.summarize_workspace(tmp_path, "debat_test", "EDIT-TEST-001")

    assert result["next_action"] == "close_workspace_from_signed_no_change_plan"
    assert result["next_command"].endswith("--confirm-no-change-plan-sha256 " + "p" * 64)
    assert result["next_remote_read_possible"] is False
    assert result["next_remote_write_possible"] is False
    assert "locale" in result["note"]


def test_status_maps_signed_acceptance_to_preflight_command():
    meta = _meta(
        "remote_plan_approved",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_plan_review={
            "comparison_id": "REMOTE-20261104-003",
            "acceptance_sha256": "a" * 64,
        },
    )

    result = status._next_step(meta, "debat_test", "EDIT-TEST-001")

    assert result["command"].endswith("--confirm-acceptance-sha256 " + "a" * 64)
    assert result["remote_read_possible"] is True
    assert result["remote_write_possible"] is False


def test_status_marks_execution_as_the_only_remote_write_step():
    meta = _meta(
        "remote_execution_ready",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_execution={
            "comparison_id": "REMOTE-20261104-003",
            "mode": "no-delete",
            "preflight_sha256": "f" * 64,
        },
    )

    result = status._next_step(meta, "debat_test", "EDIT-TEST-001")

    assert "--execute --mode no-delete" in result["command"]
    assert result["command"].endswith("--confirm-preflight-sha256 " + "f" * 64)
    assert result["remote_read_possible"] is True
    assert result["remote_write_possible"] is True


def test_status_maps_completed_execution_to_exact_closure_command():
    meta = _meta(
        "remote_execution_completed",
        remote_comparison={"comparison_id": "REMOTE-20261104-003"},
        remote_execution={
            "comparison_id": "REMOTE-20261104-003",
            "receipt_sha256": "e" * 64,
        },
    )

    result = status._next_step(meta, "debat_test", "EDIT-TEST-001")

    assert result["action"] == "close_workspace"
    assert result["command"].endswith("--confirm-execution-sha256 " + "e" * 64)
    assert result["remote_write_possible"] is False


def test_status_routes_local_finalization_without_copying_hashes():
    result = status._next_step(
        _meta("en_translation_applied"), "debat_test", "EDIT-TEST-001"
    )

    assert result["command"] == (
        "./wikidebia corpus-workspace-finalize debat_test --work-id EDIT-TEST-001"
    )
    assert "sha256" not in result["command"]
    assert result["remote_write_possible"] is False


def test_status_does_not_invent_semantic_review_inputs():
    result = status._next_step(
        _meta("en_translation_review_finalized"), "debat_test", "EDIT-TEST-001"
    )

    assert result["action"] == "record_two_semantic_convergence_passes"
    assert result["command"] is None
    assert "humaines" in result["note"]


def test_published_workspace_is_terminal():
    result = status._next_step(
        _meta("published"), "debat_test", "EDIT-TEST-001"
    )

    assert result["action"] == "complete"
    assert result["command"] is None
    assert status._phase("published") == "complete"
