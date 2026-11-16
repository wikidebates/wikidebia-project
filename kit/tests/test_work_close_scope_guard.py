"""Bilingual work closure must reject scoped remote executions before promotion."""
from __future__ import annotations

import pytest
import wikidebia_work_close as closure


@pytest.mark.parametrize("receipt_mode,metadata_mode", [
    ("en", "en"), ("en", "all"), ("all", "en"), (None, "all"),
])
def test_partial_or_unproven_scope_never_promotes(tmp_path, monkeypatch, receipt_mode, metadata_mode):
    execution = {
        "execution_receipt": {"mode": receipt_mode},
        "meta": {"remote_execution": {"mode": metadata_mode}},
    }
    monkeypatch.setattr(closure, "_closure_dir", lambda *args: tmp_path / "closure")
    monkeypatch.setattr(closure, "_load_execution", lambda *args: execution)

    def forbidden(*args, **kwargs):
        pytest.fail("Bilingual promotion must not begin for a scoped execution")

    monkeypatch.setattr(closure, "_verify_active_source", forbidden)
    with pytest.raises(closure.WorkClosureError, match="Clôture bilingue interdite"):
        closure.close_work(tmp_path, "example", "EDIT-20261113-002",
                           "REMOTE-20261115-001", "confirmed")
