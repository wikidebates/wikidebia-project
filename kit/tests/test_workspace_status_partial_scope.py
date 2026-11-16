"""Scope-aware next-step recommendations must never promote partial releases."""
from wikidebia_workspace_status import _next_step


def test_en_only_execution_does_not_offer_bilingual_close():
    result = _next_step({
        "status": "remote_execution_completed",
        "remote_execution": {
            "comparison_id": "REMOTE-20261115-001",
            "mode": "en", "receipt_sha256": "abc",
        },
    }, "example", "EDIT-20261113-002")
    assert result["action"] == "partial_publication_requires_scope_closure"
    assert result["command"] is None
    assert result["remote_write_possible"] is False


def test_all_scope_execution_offers_existing_close():
    result = _next_step({
        "status": "remote_execution_completed",
        "remote_execution": {
            "comparison_id": "REMOTE-20261115-001",
            "mode": "all", "receipt_sha256": "abc",
        },
    }, "example", "EDIT-20261113-002")
    assert result["action"] == "close_workspace"
    assert "--confirm-execution-sha256 abc" in result["command"]
