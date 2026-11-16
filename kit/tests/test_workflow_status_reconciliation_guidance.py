"""Regression checks for actionable, non-mutating workflow status guidance."""
from __future__ import annotations

from wikidebia_review_workflow import _print_user_result


def test_unbound_initial_workflow_shows_reconciliation_command(capsys):
    _print_user_result({
        "debate_id": "example",
        "phase": "initialize_graph",
        "status": "blocked_access_preflight",
        "work_id": "",
    })
    output = capsys.readouterr().out
    assert "./wikidebia workflow-reconcile example --work-id WORK_ID" in output
    assert "ne publie aucune page" in output


def test_bound_workflow_does_not_suggest_adoption(capsys):
    _print_user_result({
        "debate_id": "example",
        "phase": "initialize_graph",
        "status": "running",
        "work_id": "EDIT-20261113-002",
    })
    assert "--work-id WORK_ID" not in capsys.readouterr().out


def test_unbound_workflow_outside_initial_phase_does_not_suggest_adoption(capsys):
    _print_user_result({
        "debate_id": "example",
        "phase": "final_publication",
        "status": "blocked_final_publication",
        "work_id": "",
        "final_publication": {},
    })
    assert "--work-id WORK_ID" not in capsys.readouterr().out
