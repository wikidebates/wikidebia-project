from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wikidebia_access_preflight as access
import wikidebia_review_workflow as workflow


class FakeAdapter:
    def __init__(self, *, missing_right: str | None = None):
        self.language = None
        self.missing_right = missing_right
        self.events = []

    def open_language(self, language, expected_user):
        assert self.language is None
        self.language = language
        self.events.append(("open", language, expected_user))

    def close_language(self):
        self.events.append(("close", self.language))
        self.language = None

    def assert_identity(self, expected_user):
        self.events.append(("identity", self.language, expected_user))

    def user_rights(self):
        return {"edit", "createpage"} - ({self.missing_right} if self.missing_right else set())

    def available_change_tags(self):
        return {"chatgpt"}


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "kit/families").mkdir(parents=True)
    (project / "kit/families/wikidebates_family.py").write_text("# fixture\n", encoding="utf-8")
    return project


def _state() -> dict:
    return {
        "schema": workflow.WORKFLOW_SCHEMA,
        "schema_version": "1.0",
        "debate_id": "debat_test",
        "debate_title": "Débat test ?",
        "phase": "initialize_graph",
        "status": "running",
    }


def test_access_preflight_authenticates_both_sites_without_write(tmp_path: Path):
    project = _project(tmp_path)
    adapter = FakeAdapter()

    receipt = access.run_access_preflight(
        project,
        adapter=adapter,
        checked_at="2026-11-05T20:00:00+00:00",
    )

    assert receipt["status"] == "ready"
    assert receipt["remote_write_performed"] is False
    assert access.verify_access_receipt(receipt, access.access_contract_sha256(project))
    assert [row["language"] for row in receipt["results"]] == ["fr", "en"]
    assert adapter.events == [
        ("open", "fr", "ChatGPT"), ("identity", "fr", "ChatGPT"), ("close", "fr"),
        ("open", "en", "ChatGPT"), ("identity", "en", "ChatGPT"), ("close", "en"),
    ]


def test_access_preflight_closes_language_after_read_only_failure(tmp_path: Path):
    project = _project(tmp_path)
    adapter = FakeAdapter(missing_right="createpage")

    with pytest.raises(access.AccessPreflightError, match="createpage"):
        access.run_access_preflight(project, adapter=adapter)

    assert adapter.language is None
    assert not any(event[0] in {"write", "move", "delete"} for event in adapter.events)


def test_workflow_access_preflight_is_reused_until_contract_changes(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = _state()
    workflow._save_workflow(project, state)
    calls = []

    def run(root):
        calls.append(access.access_contract_sha256(root))
        return access.run_access_preflight(
            root,
            adapter=FakeAdapter(),
            checked_at=f"2026-11-05T20:0{len(calls)}:00+00:00",
        )

    monkeypatch.setattr(workflow, "run_access_preflight", run)
    first = workflow._ensure_access_preflight(project, state)
    second = workflow._ensure_access_preflight(project, dict(first))
    assert len(calls) == 1
    assert second["access_preflight"]["status"] == "ready"

    (project / "config/wikidebia.local.json").write_text(json.dumps({
        "expected_users": {"fr": "ChatGPT", "en": "AnotherBot"},
    }), encoding="utf-8")
    third = workflow._ensure_access_preflight(project, dict(second))
    assert len(calls) == 2
    assert third["access_preflight"]["contract_sha256"] != first["access_preflight"]["contract_sha256"]


def test_workflow_records_blocked_access_preflight(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    state = _state()
    workflow._save_workflow(project, state)

    def blocked(_root):
        raise access.AccessPreflightError("authentification anglaise refusée")

    monkeypatch.setattr(workflow, "run_access_preflight", blocked)
    with pytest.raises(workflow.WorkflowError, match="Diagnostic d’accès bilingue"):
        workflow._ensure_access_preflight(project, state)

    saved = workflow._load_workflow(project, "debat_test")
    assert saved["status"] == "blocked_access_preflight"
    assert saved["access_preflight"]["status"] == "blocked"
