"""Fail-closed scope closure tests: no bilingual corpus promotion."""
from __future__ import annotations

import pytest
import wikidebia_work_close as closure


@pytest.mark.parametrize("mode,metadata_mode", [
    ("all", "all"), ("en", "fr"), ("fr", "en"),
])
def test_scope_closure_rejects_bilingual_or_inconsistent_execution(tmp_path, monkeypatch, mode, metadata_mode):
    monkeypatch.setattr(closure, "_load_execution", lambda *args: {
        "execution_receipt": {"mode": mode},
        "meta": {"remote_execution": {"mode": metadata_mode}},
    })
    with pytest.raises(closure.WorkClosureError, match="monolingue"):
        closure.close_scope_publication(
            tmp_path, "example", "EDIT-20261113-002", "REMOTE-20261115-001", "digest"
        )


def test_scope_closure_requires_exactly_one_published_language(tmp_path, monkeypatch):
    monkeypatch.setattr(closure, "_load_execution", lambda *args: {
        "execution_receipt": {"mode": "en", "published_states": {"en": {}, "fr": {}}},
        "meta": {"remote_execution": {"mode": "en"}},
    })
    with pytest.raises(closure.WorkClosureError, match="uniquement"):
        closure.close_scope_publication(
            tmp_path, "example", "EDIT-20261113-002", "REMOTE-20261115-001", "digest"
        )
