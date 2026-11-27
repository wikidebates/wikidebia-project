"""Offline orchestration tests: real Work boundaries, synthetic resolver outputs."""
import json
from pathlib import Path

import pytest

import wikidebia_quote_bridge as bridge
import wikidebia_quote_prepare as prepare
from test_wikidebia_quote_bridge import envelope, row_for
from test_wikidebia_translation_review import common, make_french_locked


def setup(tmp_path):
    project, workspace, work = make_french_locked(tmp_path / "work")
    resolver = tmp_path / "resolver"
    resolver.mkdir()
    state = tmp_path / "private-state"
    state.mkdir(mode=0o700)
    (state / "works.sqlite3").touch(mode=0o600)
    return project, workspace, work, resolver, state


def fake_resolver(monkeypatch, state, *, wrong=False):
    calls = []
    def materialize(root, temporary, **kwargs):
        calls.append(kwargs)
        return temporary / "translation_handoff.py"
    def run(script, temporary, args, timeout):
        calls.append(args)
        request = json.loads(Path(args[args.index("--request")+1]).read_text())
        rows = [row_for(item, "insufficient_evidence") for item in request["items"]]
        value = envelope(request, rows)
        sha = bridge.digest(value)
        parent = state / "translation-handoffs"
        parent.mkdir(mode=0o700, exist_ok=True)
        directory = parent / sha
        directory.mkdir(mode=0o700, exist_ok=True)
        path = directory / "handoff.json"
        path.write_text(json.dumps(value))
        path.chmod(0o600)
        return {"handoff_sha256": sha, "request_sha256": bridge.digest(request),
                "source_lock_sha256": request["source_lock_sha256"], "occurrences": len(rows),
                "states": {"insufficient_evidence": len(rows)}, "packets": 0,
                "rights": "unreviewed", "auto_publish": False, "fresh_audit_requests": 1,
                "retrieval_requests": 1 if wrong or "--lookup-only" not in args else 0}
    monkeypatch.setattr(prepare.pinned, "materialize", materialize)
    monkeypatch.setattr(prepare, "_invoke", run)
    return calls


@pytest.mark.parametrize("mode", ["prepared", "integrated"])
def test_work_modes_and_shared_budget(tmp_path, monkeypatch, mode):
    project, workspace, work, resolver, state = setup(tmp_path)
    before = common.full_tree_sha256(workspace / "content-reviewed-copy")
    meta = (workspace / "workspace.json").read_bytes()
    calls = fake_resolver(monkeypatch, state)
    result = prepare.prepare(project, "debat_test", work, resolver_root=resolver,
                             state=state, mode=mode, batch_size=1, audit_budget=20,
                             retrieval_budget=20)
    assert result["status"] == "handoffs_inspected"
    assert calls[0] == {"entrypoint": "translation_handoff.py",
                        "include_search_data": mode == "integrated"}
    assert len(result["batches"]) == result["occurrences"] > 1
    for i, args in enumerate(calls[1:]):
        assert ("--lookup-only" in args) == (mode == "prepared")
        assert int(args[args.index("--audit-budget")+1]) == 20-i
        assert int(args[args.index("--budget")+1]) == (20 if mode == "prepared" else 20-i)
    assert result["retrieval_requests"] == (0 if mode == "prepared" else result["occurrences"])
    assert result["publication_authorized"] is False and result["translation_mutated"] is False
    assert result["states"] == {"insufficient_evidence": result["occurrences"]}
    assert common.full_tree_sha256(workspace / "content-reviewed-copy") == before
    assert (workspace / "workspace.json").read_bytes() == meta
    assert not (workspace / "translated-copy").exists()


def test_prepared_mode_rejects_retrieval_and_missing_registry(tmp_path, monkeypatch):
    project, workspace, work, resolver, state = setup(tmp_path)
    fake_resolver(monkeypatch, state, wrong=True)
    with pytest.raises(bridge.QuoteBridgeError, match="request_budget_mismatch"):
        prepare.prepare(project, "debat_test", work, resolver_root=resolver,
                        state=state, mode="prepared")
    (state / "works.sqlite3").unlink()
    with pytest.raises(bridge.QuoteBridgeError, match="prepared_registry_missing"):
        prepare.prepare(project, "debat_test", work, resolver_root=resolver,
                        state=state, mode="prepared")


def test_exhausted_shared_budget_stops_before_next_batch(tmp_path, monkeypatch):
    project, _, work, resolver, state = setup(tmp_path)
    calls = fake_resolver(monkeypatch, state)
    with pytest.raises(bridge.QuoteBridgeError, match="work_budget_exhausted"):
        prepare.prepare(project, "debat_test", work, resolver_root=resolver, state=state,
                        mode="prepared", batch_size=1, audit_budget=1)
    assert len(calls) == 2


def test_nonprivate_state_and_symlink_are_rejected(tmp_path):
    project, _, work, resolver, state = setup(tmp_path)
    state.chmod(0o755)
    with pytest.raises(bridge.QuoteBridgeError, match="state_not_private"):
        prepare.prepare(project, "debat_test", work, resolver_root=resolver,
                        state=state, mode="integrated")
    state.chmod(0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(state, target_is_directory=True)
    with pytest.raises(bridge.QuoteBridgeError, match="state_not_private"):
        prepare.prepare(project, "debat_test", work, resolver_root=resolver,
                        state=alias, mode="prepared")


def test_registry_cannot_be_inside_locked_work(tmp_path):
    project, workspace, work, resolver, _ = setup(tmp_path)
    private = workspace / "audits" / "wrong-registry"
    private.mkdir(mode=0o700, parents=True)
    with pytest.raises(bridge.QuoteBridgeError, match="overlaps_repository"):
        prepare._private_state(private, project, resolver, "integrated")
    allowed = project / ".state" / "quote-resolver"
    allowed.mkdir(mode=0o700)
    assert prepare._private_state(allowed, project, resolver, "integrated") == allowed
